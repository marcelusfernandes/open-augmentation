#!/usr/bin/env python3
"""
Meeting transcriber CLI — record, stop, transcribe, list devices.

Usage:
    transcriber.py devices
    transcriber.py record <remote> [mic] [--single] [-o <output>]
    transcriber.py stop
    transcriber.py transcribe <audio_file> [--config <path>]
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# Platform split. The transcription engine (transcribe_local.py / AssemblyAI) is
# portable; only the audio I/O layer differs. macOS uses AVFoundation + CoreAudio
# (BlackHole); Windows uses DirectShow (dshow) for mics and native WASAPI loopback
# (wasapi_record.py) for system audio.
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# Windows consoles default to a legacy codepage (cp1252) that can't encode the
# arrows/ellipsis in our status messages, which would crash on the first print.
# Force UTF-8 on both streams (works whether they're a console or a redirected file).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# Repo root derived from this script's location:
# <repo>/.claude/skills/transcriber/scripts/transcriber.py  →  parents[4] = <repo>
# Override with the AUGMENTATION_ROOT env var if the layout differs.
REPO_ROOT = Path(os.environ.get("AUGMENTATION_ROOT", Path(__file__).resolve().parents[4]))
RECORDINGS_DIR = REPO_ROOT / "recordings"
DEFAULT_CONFIG = REPO_ROOT / "config" / "assemblyai.json"
PID_FILE = RECORDINGS_DIR / ".recording.pid"
SIDECAR_PID_FILE = RECORDINGS_DIR / ".recording.sidecar.pid"
SESSION_DIR_FILE = RECORDINGS_DIR / ".recording.session"
PREVIOUS_OUTPUT_FILE = RECORDINGS_DIR / ".previous_output"
# Cross-process stop signal. `stop` runs in a separate process from `record`, and
# Windows has no graceful cross-process SIGINT, so `stop` drops this file and the
# `record` process's watcher thread relays `q` to ffmpeg's stdin (clean finalize).
STOP_REQUEST_FILE = RECORDINGS_DIR / ".stop_request"

# Streaming ASR (local backend): ffmpeg writes 30s chunks alongside the full
# audio.wav; a sidecar transcribes each chunk as it closes, so the text is ready
# when you stop. STOP_SENTINEL tells the sidecar the last chunk is final.
SEGMENT_SECONDS = 30
CHUNK_GLOB = "chunk_*.wav"
CHUNK_PATTERN = "chunk_%04d.wav"
STOP_SENTINEL = ".stop"
PARTIAL_TEXT = "transcript.partial.txt"

AUDIO_SETUP_SCRIPT = Path(__file__).parent / "audio_setup.swift"
MULTI_OUTPUT_NAME = "BlackHole + Speakers"
# Windows system-audio capture: native WASAPI loopback (no driver, no VB-CABLE).
WASAPI_SCRIPT = Path(__file__).parent / "wasapi_record.py"

# Friendly aliases → substring match against the platform's device names.
# Resolved case-insensitively. First match wins.
#
# Windows note: Zoom/Teams don't expose a virtual *capture* device like they do on
# macOS, so the only way to grab their audio is the system loopback (WASAPI). Hence
# `zoom`/`teams`/`system` all flag system intent and route to the loopback recorder —
# recording Zoom on Windows means recording everything the system plays.
if IS_WINDOWS:
    # System audio is captured via native WASAPI loopback (see _build_wasapi_cmd), not
    # a fake input device, so zoom/teams/system/blackhole all just flag "system intent"
    # and route to the loopback recorder. 'mic' still resolves a real dshow input.
    DEVICE_ALIASES = {
        "mic": "microphone",
        "system": "system",
        "blackhole": "system",
        "zoom": "system",
        "teams": "system",
    }
    SYSTEM_SUBSTR = "system"
else:
    DEVICE_ALIASES = {
        "mic": "macbook pro microphone",
        "macbook": "macbook pro microphone",
        "blackhole": "blackhole",
        "system": "blackhole",
        "zoom": "zoomaudiodevice",
        "teams": "microsoft teams audio",
    }
    SYSTEM_SUBSTR = "blackhole"


# ---------------------------------------------------------------------------
# devices
# ---------------------------------------------------------------------------

def list_devices() -> list[dict]:
    """List available audio capture devices (platform-specific backend)."""
    return _list_devices_dshow() if IS_WINDOWS else _list_devices_avfoundation()


def _list_devices_avfoundation() -> list[dict]:
    """List AVFoundation audio devices (macOS). Identified by ffmpeg index."""
    result = subprocess.run(
        ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True,
        text=True,
    )
    audio_section = False
    devices = []
    for line in result.stderr.splitlines():
        if "AVFoundation audio devices:" in line:
            audio_section = True
            continue
        if audio_section:
            match = re.search(r"\[(\d+)\]\s+(.+)", line)
            if match:
                devices.append({"index": int(match.group(1)), "name": match.group(2).strip()})
    return devices


def _list_devices_dshow() -> list[dict]:
    """List DirectShow audio devices (Windows). dshow addresses devices by NAME, not
    index, so the returned 'index' is only a display convenience — capture uses the
    name. Handles both ffmpeg output styles: the newer per-line `... "Name" (audio)`
    tag (ffmpeg 7+) and the older `DirectShow audio devices` section header. 'Alternative
    name' lines (the @device_cm_... GUID forms) are skipped."""
    result = subprocess.run(
        ["ffmpeg", "-f", "dshow", "-list_devices", "true", "-i", "dummy"],
        capture_output=True,
        text=True,
    )
    audio_section = False
    devices = []
    for line in result.stderr.splitlines():
        low = line.lower()
        if "alternative name" in low:
            continue
        if "directshow audio devices" in low:
            audio_section = True
            continue
        if "directshow video devices" in low:
            audio_section = False
            continue
        match = re.search(r'"([^"]+)"', line)
        if not match:
            continue
        # New style tags the type inline; old style relies on the section header.
        is_audio = "(audio)" in low or (audio_section and "(video)" not in low)
        if is_audio:
            devices.append({"index": len(devices), "name": match.group(1).strip()})
    return devices


def cmd_devices(_args: argparse.Namespace) -> None:
    devices = list_devices()
    if not devices:
        print("No audio devices found.", file=sys.stderr)
        sys.exit(1)
    print("Available audio devices:")
    for d in devices:
        print(f"  [{d['index']}] {d['name']}")


def resolve_device(spec: str) -> str:
    """Resolve a device spec (digit, alias, or substring) to the value ffmpeg's input
    expects: an AVFoundation index on macOS, the device NAME on Windows (dshow).

    On macOS indices shift when drivers are added/removed, so prefer names/aliases.
    """
    devices = list_devices()

    # A bare number means the Nth listed device. dshow has no real index, so map it
    # back to that device's name; AVFoundation passes the index straight through.
    if spec.isdigit():
        if IS_WINDOWS:
            for d in devices:
                if d["index"] == int(spec):
                    return d["name"]
        else:
            return spec

    needle = DEVICE_ALIASES.get(spec.lower(), spec).lower()
    for d in devices:
        if needle in d["name"].lower():
            return d["name"] if IS_WINDOWS else str(d["index"])

    available = ", ".join(f'[{d["index"]}] {d["name"]}' for d in devices)
    print(f"Error: no audio device matches '{spec}'. Available: {available}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# system audio capture (BlackHole + Multi-Output) — auto-setup
# ---------------------------------------------------------------------------

def _swift_audio(args: list[str]) -> tuple[int, str]:
    """Invoke audio_setup.swift with the given args. Returns (exit_code, stdout)."""
    result = subprocess.run(
        ["swift", str(AUDIO_SETUP_SCRIPT), *args],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout.strip()


def _is_system_capture(spec: str) -> bool:
    """True if the spec targets system audio (BlackHole on macOS / WASAPI loopback on Windows)."""
    key = spec.lower()
    if key in ("system", "blackhole", "cable"):
        return True
    return SYSTEM_SUBSTR in DEVICE_ALIASES.get(key, spec).lower()


def _ensure_wasapi_ready() -> None:
    """Verify the Windows system-audio path is usable: PyAudioWPatch installed and at
    least one WASAPI loopback endpoint present. Native — no driver, no VB-CABLE."""
    try:
        import pyaudiowpatch as pa
    except ImportError:
        print("ERROR: recording system audio on Windows needs PyAudioWPatch.\n"
              "  Install: pip install PyAudioWPatch", file=sys.stderr)
        sys.exit(1)
    p = pa.PyAudio()
    try:
        if not list(p.get_loopback_device_info_generator()):
            print("ERROR: no WASAPI loopback endpoint found (no active audio output?).",
                  file=sys.stderr)
            sys.exit(1)
    finally:
        p.terminate()


def _build_wasapi_cmd(mic_spec: str, output: Path, chunk_path: Path, streaming: bool) -> list[str]:
    """Command to run the WASAPI loopback recorder for the Windows system-capture case.
    It writes the same audio.wav + 30s chunks the ffmpeg pipeline does and stops on the
    shared stop-request file, so the sidecar/transcribe flow is unchanged."""
    cmd = [
        sys.executable, str(WASAPI_SCRIPT),
        "--output", str(output),
        "--mic", mic_spec,
        "--loopback", "default",
        "--stop-file", str(STOP_REQUEST_FILE),
    ]
    if streaming:
        cmd += ["--chunk-pattern", str(chunk_path)]
    return cmd


def setup_system_capture() -> None:
    """Prepare system-audio capture on macOS: save the current default output, ensure
    the BlackHole Multi-Output exists, and switch to it. (Windows uses WASAPI loopback
    instead — see _build_wasapi_cmd — and never reaches this.)"""
    code, current = _swift_audio(["current-output"])
    if code != 0:
        print("Warning: couldn't query current output device.", file=sys.stderr)
        return

    # Don't overwrite previous_output with the Multi-Output itself if a prior
    # run forgot to restore — fall back to the speaker default instead.
    if current and current != MULTI_OUTPUT_NAME:
        PREVIOUS_OUTPUT_FILE.write_text(current)
    elif not PREVIOUS_OUTPUT_FILE.exists():
        PREVIOUS_OUTPUT_FILE.write_text("MacBook Pro Speakers")

    _swift_audio(["create-multi-output"])  # idempotent
    code, _ = _swift_audio(["switch-output", MULTI_OUTPUT_NAME])
    if code == 0:
        print(f"Audio output: {current} → {MULTI_OUTPUT_NAME}")
    else:
        print(f"ERROR: failed to switch output to {MULTI_OUTPUT_NAME}.", file=sys.stderr)
        sys.exit(1)


def restore_system_output() -> None:
    """Restore the default output saved by setup_system_capture (no-op otherwise).
    Windows never switches the output device, so there's nothing to restore."""
    if IS_WINDOWS:
        return
    if not PREVIOUS_OUTPUT_FILE.exists():
        return
    previous = PREVIOUS_OUTPUT_FILE.read_text().strip()
    PREVIOUS_OUTPUT_FILE.unlink(missing_ok=True)
    if not previous:
        return
    code, _ = _swift_audio(["switch-output", previous])
    if code == 0:
        print(f"Audio output restored: {previous}")
    else:
        print(f"Warning: failed to restore output to '{previous}'.", file=sys.stderr)


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------

def _input_args(device: str) -> list[str]:
    """ffmpeg input args for one resolved device. macOS addresses AVFoundation audio
    as `:<index>`; Windows addresses dshow audio by name as `audio=<name>`."""
    if IS_WINDOWS:
        return ["-f", "dshow", "-i", f"audio={device}"]
    return ["-f", "avfoundation", "-i", f":{device}"]


def _build_ffmpeg_cmd(remote: str, mic: str, output: Path) -> list[str]:
    """Build ffmpeg command — mix remote + mic into mono."""
    return [
        "ffmpeg",
        *_input_args(remote),
        *_input_args(mic),
        "-filter_complex", "amix=inputs=2:duration=longest",
        "-ar", "16000", "-ac", "1",
        "-acodec", "pcm_s16le",
        str(output),
        "-loglevel", "warning",
    ]


def _build_ffmpeg_cmd_single(device: str, output: Path) -> list[str]:
    """Build ffmpeg command for a single audio device."""
    return [
        "ffmpeg",
        *_input_args(device),
        "-ar", "16000", "-ac", "1",
        "-acodec", "pcm_s16le",
        str(output),
        "-loglevel", "warning",
    ]


# PCM tail for both streaming outputs (full file + segmented chunks).
def _pcm_full(output: Path) -> list[str]:
    return ["-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le", str(output)]


def _pcm_segments(chunk_path: Path) -> list[str]:
    return [
        "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
        "-f", "segment", "-segment_time", str(SEGMENT_SECONDS),
        "-reset_timestamps", "1", str(chunk_path),
    ]


def _build_ffmpeg_cmd_stream(remote: str, mic: str, output: Path, chunk_path: Path) -> list[str]:
    """Meeting mode, streaming: mix remote+mic, then asplit to a full file AND 30s
    chunks. SIGINT finalizes both outputs (verified). Chunks feed the live sidecar."""
    return [
        "ffmpeg",
        *_input_args(remote),
        *_input_args(mic),
        "-filter_complex", "amix=inputs=2:duration=longest,asplit=2[full][seg]",
        "-map", "[full]", *_pcm_full(output),
        "-map", "[seg]", *_pcm_segments(chunk_path),
        "-loglevel", "warning",
    ]


def _build_ffmpeg_cmd_single_stream(device: str, output: Path, chunk_path: Path) -> list[str]:
    """Single device, streaming: map the input to a full file AND 30s chunks."""
    return [
        "ffmpeg",
        *_input_args(device),
        "-map", "0:a", *_pcm_full(output),
        "-map", "0:a", *_pcm_segments(chunk_path),
        "-loglevel", "warning",
    ]


def _streaming_enabled(args: argparse.Namespace, settings: dict) -> bool:
    """Stream ASR live only for the local backend. AssemblyAI is cloud-batch — it
    uploads the whole file at the end, so chunking buys nothing there."""
    if getattr(args, "no_stream", False):
        return False
    if args.output:  # custom single-file path → plain batch, no chunks
        return False
    backend = settings.get("backend")
    if backend:
        return backend == "local"
    return not DEFAULT_CONFIG.exists()  # no AssemblyAI key configured → local default


def _spawn_sidecar(session_dir: Path, model_size: str, language: str) -> subprocess.Popen:
    """Launch the live ASR sidecar, detached so it outlives this record process and
    keeps draining chunks until it sees the stop sentinel."""
    log = open(session_dir / "sidecar.log", "w", encoding="utf-8")
    cmd = [
        sys.executable, str(Path(__file__).resolve()), "stream-asr", str(session_dir),
        "--whisper-model", model_size, "--language", language,
    ]
    # Detach so the sidecar outlives this record process. POSIX: new session (setsid).
    # Windows: new process group + no inherited console.
    if IS_WINDOWS:
        detach = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
    else:
        detach = {"start_new_session": True}
    return subprocess.Popen(cmd, stdout=log, stderr=log, **detach)


def _relay_stop_to_ffmpeg(proc: subprocess.Popen) -> None:
    """Watcher (Windows): poll for the stop-request file and relay `q` to ffmpeg's
    stdin so it finalizes the WAV cleanly. Needed because `stop` is a separate process
    and Windows has no graceful cross-process SIGINT."""
    while proc.poll() is None:
        if STOP_REQUEST_FILE.exists():
            try:
                proc.stdin.write(b"q")
                proc.stdin.flush()
            except (OSError, ValueError):
                pass
            return
        time.sleep(0.5)


def cmd_record(args: argparse.Namespace) -> None:
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

    if PID_FILE.exists():
        pid = PID_FILE.read_text().strip()
        print(f"Error: recording already in progress (PID {pid}). Run 'stop' first.", file=sys.stderr)
        sys.exit(1)

    # Clear a stale stop-request from a prior run so it can't auto-stop this one.
    STOP_REQUEST_FILE.unlink(missing_ok=True)

    now = datetime.now()
    # No ':' — it's a legal AVFoundation session label but an illegal Windows filename.
    session_dir = RECORDINGS_DIR / now.strftime("%d-%m-%Y-%H-%M")
    session_dir.mkdir(parents=True, exist_ok=True)

    output = Path(args.output) if args.output else session_dir / "audio.wav"
    chunk_path = session_dir / CHUNK_PATTERN
    settings = _transcriber_settings()
    streaming = _streaming_enabled(args, settings)

    if args.single:
        device = resolve_device(args.remote)
        mode = f"single device ({args.remote} → [{device}])"
        cmd = (_build_ffmpeg_cmd_single_stream(device, output, chunk_path) if streaming
               else _build_ffmpeg_cmd_single(device, output))
    elif IS_WINDOWS and _is_system_capture(args.remote):
        # Windows system audio (Zoom/Teams/any app): native WASAPI loopback + mic.
        # No ffmpeg, no VB-CABLE — a dedicated recorder writes the same artifacts.
        _ensure_wasapi_ready()
        cmd = _build_wasapi_cmd(args.mic, output, chunk_path, streaming)
        mode = f"meeting [WASAPI loopback + mic:{args.mic}]"
    else:
        # Auto-route system audio through Multi-Output before resolving the
        # ffmpeg index, so BlackHole actually receives audio (macOS).
        if _is_system_capture(args.remote):
            setup_system_capture()
        remote = resolve_device(args.remote)
        mic = resolve_device(args.mic)
        mode = f"meeting (remote:{args.remote}→[{remote}] + mic:{args.mic}→[{mic}])"
        cmd = (_build_ffmpeg_cmd_stream(remote, mic, output, chunk_path) if streaming
               else _build_ffmpeg_cmd(remote, mic, output))

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    PID_FILE.write_text(str(proc.pid))
    SESSION_DIR_FILE.write_text(str(session_dir))

    # Windows: `stop` can't SIGINT ffmpeg, so a watcher thread relays `q` to its stdin
    # when the stop-request file appears. macOS keeps the proven SIGINT path.
    if IS_WINDOWS:
        threading.Thread(target=_relay_stop_to_ffmpeg, args=(proc,), daemon=True).start()

    sidecar_pid = None
    if streaming:
        model_size = args.whisper_model or settings.get("whisper_model", "medium")
        sidecar_pid = _spawn_sidecar(session_dir, model_size, args.language).pid
        SIDECAR_PID_FILE.write_text(str(sidecar_pid))

    print(f"Recording [{mode}] → {output}")
    print(f"Session: {session_dir}")
    print(f"PID: {proc.pid}")
    if sidecar_pid:
        print(f"Streaming ASR ativo (sidecar PID {sidecar_pid}) → {session_dir / PARTIAL_TEXT}")
    print("Run 'transcriber.py stop' to finish recording.")

    proc.wait()

    # ffmpeg finished (via stop, or on its own). Tell the sidecar the last chunk is
    # final so it drains and exits even if 'stop' wasn't what ended the recording.
    PID_FILE.unlink(missing_ok=True)
    STOP_REQUEST_FILE.unlink(missing_ok=True)
    if streaming:
        (session_dir / STOP_SENTINEL).write_text("")
    print(f"Saved: {output}")


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------

def _pid_alive(pid: int) -> bool:
    """Cross-platform liveness check for a (possibly non-child) process."""
    if IS_WINDOWS:
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not ours to signal
    return True


def _wait_pid_gone(pid: int, timeout: float) -> bool:
    """Poll until a (possibly non-child) process exits or timeout. True if it exited."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(1)
    return False


def cmd_stop(_args: argparse.Namespace) -> None:
    if not PID_FILE.exists():
        print("No recording in progress.", file=sys.stderr)
        sys.exit(1)

    pid = int(PID_FILE.read_text().strip())
    session_dir = SESSION_DIR_FILE.read_text().strip() if SESSION_DIR_FILE.exists() else None

    # Stop gracefully so ffmpeg writes the WAV trailer (a hard kill corrupts it).
    # POSIX: SIGINT. Windows: drop the stop-request file; the record process's watcher
    # relays `q` to ffmpeg's stdin. Either way, WAIT for ffmpeg to actually exit so
    # audio.wav AND the last chunk are finalized before we signal the sidecar (else it
    # reads a truncated tail and drops the final segment) or an eager transcribe races.
    if IS_WINDOWS:
        STOP_REQUEST_FILE.write_text("")
        print(f"Stopping recording (PID {pid})…")
        if session_dir:
            print(f"Session: {session_dir}")
        if not _wait_pid_gone(pid, timeout=30):
            print(f"Warning: ffmpeg (PID {pid}) didn't stop in time.", file=sys.stderr)
        STOP_REQUEST_FILE.unlink(missing_ok=True)
    else:
        try:
            os.kill(pid, signal.SIGINT)
            print(f"Stopped recording (PID {pid}).")
            if session_dir:
                print(f"Session: {session_dir}")
            _wait_pid_gone(pid, timeout=30)
        except ProcessLookupError:
            print(f"Process {pid} not found (already stopped?).", file=sys.stderr)

    PID_FILE.unlink(missing_ok=True)
    SESSION_DIR_FILE.unlink(missing_ok=True)
    restore_system_output()

    # Streaming: tell the sidecar the last chunk is final, then wait for it to drain
    # so the partial transcript is complete by the time stop returns.
    if SIDECAR_PID_FILE.exists() and session_dir:
        session = Path(session_dir)
        (session / STOP_SENTINEL).write_text("")
        try:
            spid = int(SIDECAR_PID_FILE.read_text().strip())
        except (ValueError, OSError):
            spid = None
        if spid:
            print("Finalizando transcrição ao vivo (último trecho)…")
            _wait_pid_gone(spid, timeout=120)
        SIDECAR_PID_FILE.unlink(missing_ok=True)
        partial_txt = session / PARTIAL_TEXT
        if partial_txt.exists():
            print(f"Texto pronto: {partial_txt}")
        print("Rode 'transcribe' nessa sessão pra diarizar (quem falou) e gerar a nota.")


# ---------------------------------------------------------------------------
# stream-asr (sidecar) — transcribe chunks live during the meeting
# ---------------------------------------------------------------------------

def _chunk_duration(path: Path) -> float:
    """Duration of a chunk in seconds, from the WAV header (cheap, no full read)."""
    import soundfile as sf

    info = sf.info(str(path))
    return info.frames / info.samplerate


def cmd_stream_asr(args: argparse.Namespace) -> None:
    """Background sidecar: watch the session dir for closed 30s chunks, transcribe
    each as it appears, and append to partial.jsonl + transcript.partial.txt. A chunk
    is 'closed' once a later chunk exists (ffmpeg opened the next) or the stop sentinel
    is present (the last chunk is final). Exits when stopped and all chunks are done."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from transcribe_local import load_whisper, _asr_segments, PARTIAL_FILE

    session = Path(args.session_dir)
    partial = session / PARTIAL_FILE
    partial_txt = session / PARTIAL_TEXT

    print(f"sidecar: loading whisper '{args.whisper_model}'…", flush=True)
    model = load_whisper(args.whisper_model)
    print("sidecar: ready", flush=True)

    processed: set[str] = set()
    cumulative_s = 0.0  # absolute meeting offset = sum of durations of done chunks

    while True:
        chunks = sorted(session.glob(CHUNK_GLOB))
        stopped = (session / STOP_SENTINEL).exists()

        for i, ch in enumerate(chunks):
            if ch.name in processed:
                continue
            is_last = i == len(chunks) - 1
            if is_last and not stopped:
                continue  # still being written — wait for the next chunk or stop

            ok = False
            try:
                segs = _asr_segments(model, str(ch), args.language, offset_s=cumulative_s)
                with open(partial, "a", encoding="utf-8") as f:
                    for s0, s1, text in segs:
                        f.write(json.dumps(
                            {"start": int(s0 * 1000), "end": int(s1 * 1000), "text": text},
                            ensure_ascii=False) + "\n")
                with open(partial_txt, "a", encoding="utf-8") as f:
                    for _s0, _s1, text in segs:
                        f.write(text + "\n")
                cumulative_s += _chunk_duration(ch)
                print(f"sidecar: {ch.name} → {len(segs)} segs (t≈{cumulative_s:.0f}s)", flush=True)
                ok = True
            except Exception as exc:  # one bad chunk must not stall the whole loop
                print(f"sidecar WARN {ch.name}: {exc}", file=sys.stderr, flush=True)
                try:
                    cumulative_s += _chunk_duration(ch)
                except Exception:
                    cumulative_s += SEGMENT_SECONDS  # keep later offsets ~aligned
            processed.add(ch.name)
            # Chunks are disposable once transcribed — finalize uses audio.wav +
            # partial.jsonl, not the chunks. Delete to avoid ~2x recording disk use.
            # Keep failed chunks as evidence (rare).
            if ok:
                ch.unlink(missing_ok=True)

        if stopped and all(c.name in processed for c in sorted(session.glob(CHUNK_GLOB))):
            break
        time.sleep(2)

    print("sidecar: done", flush=True)


# ---------------------------------------------------------------------------
# transcribe
# ---------------------------------------------------------------------------

def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        print(f"Error: config not found at {config_path}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(config_path) as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error: invalid config at {config_path} ({exc})", file=sys.stderr)
        sys.exit(1)
    if not cfg.get("api_key"):
        print(f"Error: missing 'api_key' in {config_path}", file=sys.stderr)
        sys.exit(1)
    return cfg


def _format_timestamp(ms: int) -> str:
    """Convert milliseconds to HH:MM:SS."""
    total_seconds = ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _format_transcript(result: dict) -> str:
    """Format transcription result as readable text."""
    lines = []

    lang = result.get("language", "?")
    duration_s = result.get("audio_duration", 0)
    duration_min = duration_s // 60
    duration_rem = duration_s % 60
    speakers = result.get("speakers", [])

    lines.append(f"Idioma: {lang}")
    lines.append(f"Duração: {duration_min}m{duration_rem:02d}s")
    lines.append(f"Speakers: {', '.join(speakers)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for u in result.get("utterances", []):
        ts = _format_timestamp(u["start"])
        lines.append(f"[{ts}] {u['speaker']}: {u['text']}")
        lines.append("")

    return "\n".join(lines)


def transcribe(audio_path: str, api_key: str) -> dict:
    import assemblyai as aai

    aai.settings.api_key = api_key

    config = aai.TranscriptionConfig(
        speaker_labels=True,
        language_detection=True,
        speech_models=["universal-3-pro"],
    )

    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_path, config=config)

    if transcript.status == aai.TranscriptStatus.error:
        return {"error": transcript.error, "status": "error"}

    utterances = [
        {
            "speaker": u.speaker,
            "text": u.text,
            "start": u.start,
            "end": u.end,
        }
        for u in (transcript.utterances or [])
    ]

    return {
        "status": "completed",
        "text": transcript.text,
        "speakers": sorted({u["speaker"] for u in utterances}),
        "utterances": utterances,
        "audio_duration": transcript.audio_duration,
        "language": transcript.language_code,
    }


_VALID_BACKENDS = ("local", "assemblyai")


def _transcriber_settings() -> dict:
    """Optional config/transcriber.json — written by /setup. Holds backend + model.
    A broken file is a hard error, NOT a silent fallback: if the user configured
    `local` for privacy, a typo must not quietly route audio to the cloud."""
    path = REPO_ROOT / "config" / "transcriber.json"
    if not path.exists():
        return {}
    try:
        return json.load(open(path))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error: config/transcriber.json is invalid ({exc}). "
              f"Fix it or delete it.", file=sys.stderr)
        sys.exit(1)


def _resolve_backend(args: argparse.Namespace, settings: dict) -> str:
    """CLI flag → config/transcriber.json → fall back to assemblyai if a key exists, else local.
    An explicit-but-invalid backend value fails loudly (never silently to the cloud)."""
    backend = getattr(args, "backend", None) or settings.get("backend")
    if backend:
        if backend not in _VALID_BACKENDS:
            print(f"Error: unknown transcription backend '{backend}'. "
                  f"Use one of: {', '.join(_VALID_BACKENDS)}.", file=sys.stderr)
            sys.exit(1)
        return backend
    return "assemblyai" if Path(args.config).expanduser().exists() else "local"


def _local_error(exc: Exception, *, missing_pkg: bool) -> dict:
    if missing_pkg:
        return {"status": "error",
                "error": f"local backend not installed: {exc}. "
                         f"Run: pip install pywhispercpp sherpa-onnx soundfile"}
    return {"status": "error", "error": f"local transcription failed: {exc}"}


def cmd_transcribe(args: argparse.Namespace) -> None:
    # Accept either an audio file or a session directory. A streaming session has a
    # partial.jsonl (ASR done live) — we only diarize + merge, skipping whisper.
    raw = Path(args.audio_file).expanduser().resolve()
    if raw.is_dir():
        session, audio_path = raw, raw / "audio.wav"
    else:
        session, audio_path = raw.parent, raw

    settings = _transcriber_settings()
    backend = _resolve_backend(args, settings)
    streaming_session = backend == "local" and (session / "partial.jsonl").exists()

    if not streaming_session and not audio_path.exists():
        print(f"Error: audio file not found: {audio_path}", file=sys.stderr)
        sys.exit(1)

    if streaming_session:
        print("Diarizando sessão em streaming (ASR já feito ao vivo)…", file=sys.stderr)
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from transcribe_local import finalize_streaming
            result = finalize_streaming(str(session), num_speakers=args.speakers)
        except ImportError as exc:
            result = _local_error(exc, missing_pkg=True)
        except Exception as exc:
            result = _local_error(exc, missing_pkg=False)
    elif backend == "local":
        model_size = args.whisper_model or settings.get("whisper_model", "medium")
        print(f"Transcribing locally (whisper '{model_size}' + sherpa diarization)…",
              file=sys.stderr)
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from transcribe_local import transcribe_local
            result = transcribe_local(
                str(audio_path), model_size=model_size, num_speakers=args.speakers,
            )
        except ImportError as exc:
            result = _local_error(exc, missing_pkg=True)
        except Exception as exc:  # download/model/runtime failures → uniform contract
            result = _local_error(exc, missing_pkg=False)
    else:
        config = load_config(Path(args.config).expanduser())
        result = transcribe(str(audio_path), config["api_key"])

    if result.get("status") == "error":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)

    # save transcript next to the audio file
    transcript_path = session / "transcript.txt"
    transcript_path.write_text(_format_transcript(result), encoding="utf-8")

    print(f"Transcript saved: {transcript_path}")
    print()
    print(transcript_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Meeting transcriber — record, stop, transcribe, list devices.",
    )
    subs = parser.add_subparsers(dest="command", required=True)

    # devices
    subs.add_parser("devices", help="List available audio devices")

    # record
    rec = subs.add_parser("record", help="Record meeting audio (remote + mic)")
    rec.add_argument("remote", help="Remote audio device — index, name substring, or alias (zoom|teams|blackhole|system; on Windows zoom/teams/system all mean the loopback device)")
    rec.add_argument("mic", nargs="?", default="mic", help="Mic device — index, name substring, or alias (default: mic = default microphone)")
    rec.add_argument("--single", action="store_true", help="Record from a single device only")
    rec.add_argument("-o", "--output", help="Output file path")
    rec.add_argument("--no-stream", dest="no_stream", action="store_true",
                     help="Disable live streaming ASR (local backend); transcribe only after stop")
    rec.add_argument("--whisper-model", dest="whisper_model", default=None,
                     help="Streaming sidecar: whisper model size (default: medium / config)")
    rec.add_argument("--language", default="pt", help="Streaming sidecar: ASR language (default: pt)")

    # stop
    subs.add_parser("stop", help="Stop current recording")

    # stream-asr (internal — launched by record as a background sidecar)
    sa = subs.add_parser("stream-asr", help="(internal) live ASR sidecar for a recording session")
    sa.add_argument("session_dir", help="Recording session directory to watch")
    sa.add_argument("--whisper-model", dest="whisper_model", default="medium")
    sa.add_argument("--language", default="pt")

    # transcribe
    tx = subs.add_parser("transcribe", help="Transcribe an audio file (local or AssemblyAI)")
    tx.add_argument("audio_file", help="Path to audio file")
    tx.add_argument(
        "--backend", choices=["local", "assemblyai"], default=None,
        help="Override the transcription backend (default: from config/transcriber.json)",
    )
    tx.add_argument(
        "--speakers", type=int, default=None,
        help="Local backend: number of participants (from the recording prior) — sharpens diarization",
    )
    tx.add_argument(
        "--whisper-model", dest="whisper_model", default=None,
        help="Local backend: whisper model size (default: medium; try large-v3 for best quality)",
    )
    tx.add_argument(
        "--config", default=str(DEFAULT_CONFIG),
        help="AssemblyAI backend: path to config JSON with the API key",
    )

    args = parser.parse_args()

    commands = {
        "devices": cmd_devices,
        "record": cmd_record,
        "stop": cmd_stop,
        "stream-asr": cmd_stream_asr,
        "transcribe": cmd_transcribe,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
