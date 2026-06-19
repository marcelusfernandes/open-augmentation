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
from datetime import datetime
from pathlib import Path

RECORDINGS_DIR = Path.home() / "Desktop/playground-ai/augmentation/recordings"
DEFAULT_CONFIG = Path.home() / "Desktop/playground-ai/augmentation/config/assemblyai.json"
PID_FILE = RECORDINGS_DIR / ".recording.pid"
SESSION_DIR_FILE = RECORDINGS_DIR / ".recording.session"


# ---------------------------------------------------------------------------
# devices
# ---------------------------------------------------------------------------

def list_devices() -> list[dict]:
    """List available AVFoundation audio devices."""
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


def cmd_devices(_args: argparse.Namespace) -> None:
    devices = list_devices()
    if not devices:
        print("No audio devices found.", file=sys.stderr)
        sys.exit(1)
    print("Available audio devices:")
    for d in devices:
        print(f"  [{d['index']}] {d['name']}")


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------

def _build_ffmpeg_cmd(remote: str, mic: str, output: Path) -> list[str]:
    """Build ffmpeg command — mix remote + mic into mono."""
    return [
        "ffmpeg",
        "-f", "avfoundation", "-i", f":{remote}",
        "-f", "avfoundation", "-i", f":{mic}",
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
        "-f", "avfoundation", "-i", f":{device}",
        "-ar", "16000", "-ac", "1",
        "-acodec", "pcm_s16le",
        str(output),
        "-loglevel", "warning",
    ]


def cmd_record(args: argparse.Namespace) -> None:
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

    if PID_FILE.exists():
        pid = PID_FILE.read_text().strip()
        print(f"Error: recording already in progress (PID {pid}). Run 'stop' first.", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    session_dir = RECORDINGS_DIR / now.strftime("%d-%m-%Y-%H:%M")
    session_dir.mkdir(parents=True, exist_ok=True)

    if args.output:
        output = Path(args.output)
    else:
        output = session_dir / "audio.wav"

    if args.single:
        mode = "single device"
        cmd = _build_ffmpeg_cmd_single(args.remote, output)
    else:
        mode = f"meeting (remote:{args.remote} + mic:{args.mic})"
        cmd = _build_ffmpeg_cmd(args.remote, args.mic, output)

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    PID_FILE.write_text(str(proc.pid))
    SESSION_DIR_FILE.write_text(str(session_dir))

    print(f"Recording [{mode}] → {output}")
    print(f"Session: {session_dir}")
    print(f"PID: {proc.pid}")
    print("Run 'transcriber.py stop' to finish recording.")

    proc.wait()

    # cleanup if process ends on its own
    PID_FILE.unlink(missing_ok=True)
    print(f"Saved: {output}")


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------

def cmd_stop(_args: argparse.Namespace) -> None:
    if not PID_FILE.exists():
        print("No recording in progress.", file=sys.stderr)
        sys.exit(1)

    pid = int(PID_FILE.read_text().strip())
    session_dir = SESSION_DIR_FILE.read_text().strip() if SESSION_DIR_FILE.exists() else None

    try:
        os.kill(pid, signal.SIGINT)
        print(f"Stopped recording (PID {pid}).")
        if session_dir:
            print(f"Session: {session_dir}")
    except ProcessLookupError:
        print(f"Process {pid} not found (already stopped?).", file=sys.stderr)

    PID_FILE.unlink(missing_ok=True)
    SESSION_DIR_FILE.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# transcribe
# ---------------------------------------------------------------------------

def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        print(f"Error: config not found at {config_path}", file=sys.stderr)
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)


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


def cmd_transcribe(args: argparse.Namespace) -> None:
    audio_path = Path(args.audio_file).expanduser().resolve()
    if not audio_path.exists():
        print(f"Error: audio file not found: {audio_path}", file=sys.stderr)
        sys.exit(1)

    config = load_config(Path(args.config).expanduser())
    result = transcribe(str(audio_path), config["api_key"])

    if result.get("status") == "error":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)

    # save transcript next to the audio file
    transcript_path = audio_path.parent / "transcript.txt"
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
    rec.add_argument("remote", help="Remote audio device index (e.g. Zoom, Teams)")
    rec.add_argument("mic", nargs="?", default="1", help="Mic device index (default: 1 = MacBook Mic)")
    rec.add_argument("--single", action="store_true", help="Record from a single device only")
    rec.add_argument("-o", "--output", help="Output file path")

    # stop
    subs.add_parser("stop", help="Stop current recording")

    # transcribe
    tx = subs.add_parser("transcribe", help="Transcribe audio file via AssemblyAI")
    tx.add_argument("audio_file", help="Path to audio file")
    tx.add_argument(
        "--config", default=str(DEFAULT_CONFIG),
        help="Path to AssemblyAI config JSON",
    )

    args = parser.parse_args()

    commands = {
        "devices": cmd_devices,
        "record": cmd_record,
        "stop": cmd_stop,
        "transcribe": cmd_transcribe,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
