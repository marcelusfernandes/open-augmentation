#!/usr/bin/env python3
"""Windows system-audio recorder — WASAPI loopback (+ mic), no driver, no VB-CABLE.

This is the Windows replacement for the ffmpeg/BlackHole system-capture path. It
captures what the system is *playing* (Zoom/Teams/any app) via WASAPI loopback and
mixes it with the microphone, writing the SAME artifacts the ffmpeg streaming pipeline
produces so the rest of the skill (sidecar ASR, stop, transcribe, diarization, note)
works unchanged:
  - <output>            full recording, 16 kHz mono PCM s16le (audio.wav)
  - <chunk_pattern>     30 s segments chunk_0000.wav, chunk_0001.wav, … (streaming)

Why a custom recorder: mainline ffmpeg can't open a WASAPI loopback endpoint on
Windows (DirectShow only), so the capture lives here via PyAudioWPatch. A silent
keep-alive render stream keeps the audio engine active so the loopback never starves
during silence (WASAPI delivers no frames when the endpoint is idle), which keeps the
mixed timeline aligned to wall-clock.

Stop: drop the --stop-file path (the same .stop_request the `stop` command writes);
this process finalizes the WAV + last chunk and exits.
"""
import argparse
import sys
import time
import wave
from pathlib import Path

import numpy as np
import pyaudiowpatch as pa

OUT_RATE = 16000          # whisper/diarization sample rate
TICK = 0.1                # seconds of audio pulled from each source per loop
OUT_BLOCK = int(OUT_RATE * TICK)  # 1600 samples written per tick (per source)


# ---------------------------------------------------------------------------
# device resolution (PyAudio indices — NOT the dshow names the mic path uses)
# ---------------------------------------------------------------------------

def _resolve_loopback(p: pa.PyAudio, spec: str) -> dict:
    """The loopback capture endpoint. 'default'/'system' → the default render device's
    loopback; otherwise a substring match over the loopback endpoints."""
    wasapi = p.get_host_api_info_by_type(pa.paWASAPI)
    default_out = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    candidates = list(p.get_loopback_device_info_generator())
    if not candidates:
        raise RuntimeError("no WASAPI loopback endpoints found")
    if spec.lower() in ("default", "system", "blackhole", "cable", ""):
        for d in candidates:
            if default_out["name"] in d["name"]:
                return d
        return candidates[0]
    for d in candidates:
        if spec.lower() in d["name"].lower():
            return d
    raise RuntimeError(f"no loopback endpoint matches '{spec}'")


def _resolve_mic(p: pa.PyAudio, spec: str):
    """The microphone input device. 'mic'/'default' → default input; else substring.
    Returns None if spec is 'none' (loopback-only recording)."""
    if spec and spec.lower() == "none":
        return None
    if not spec or spec.lower() in ("mic", "default"):
        try:
            wasapi = p.get_host_api_info_by_type(pa.paWASAPI)
            return p.get_device_info_by_index(wasapi["defaultInputDevice"])
        except Exception:
            return p.get_default_input_device_info()
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        if d["maxInputChannels"] > 0 and spec.lower() in d["name"].lower():
            return d
    raise RuntimeError(f"no input device matches '{spec}'")


# ---------------------------------------------------------------------------
# capture helpers
# ---------------------------------------------------------------------------

def _to_mono16k(raw: bytes, channels: int) -> np.ndarray:
    """int16 interleaved bytes → mono float32 resampled to OUT_BLOCK samples (0.1 s)."""
    if not raw:
        return np.zeros(OUT_BLOCK, dtype="float32")
    samples = np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if len(samples) == OUT_BLOCK:
        return samples
    # Linear-resample the 0.1 s block to exactly OUT_BLOCK samples. Per-block edges
    # introduce negligible artifacts at speech rates.
    x_old = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=OUT_BLOCK, endpoint=False)
    return np.interp(x_new, x_old, samples).astype("float32")


def _open_silent_keepalive(p: pa.PyAudio, device_index: int):
    """A zero-filled render stream that keeps the audio engine active so the loopback
    delivers continuous frames even when the meeting is silent. Best-effort."""
    info = p.get_device_info_by_index(device_index)
    ch = max(1, int(info["maxOutputChannels"]) or 2)
    sr = int(info["defaultSampleRate"])

    def _cb(_in, frame_count, _ti, _st):
        return (b"\x00" * (frame_count * ch * 2), pa.paContinue)

    try:
        return p.open(format=pa.paInt16, channels=ch, rate=sr, output=True,
                      output_device_index=device_index, frames_per_buffer=1024,
                      stream_callback=_cb)
    except Exception as exc:
        print(f"wasapi: keep-alive unavailable ({exc}); silence gaps possible",
              file=sys.stderr, flush=True)
        return None


# ---------------------------------------------------------------------------
# main record loop
# ---------------------------------------------------------------------------

def record(output: Path, chunk_pattern: str, mic_spec: str, loopback_spec: str,
           stop_file: Path, streaming: bool, segment_s: int) -> None:
    p = pa.PyAudio()
    keepalive = None
    full = None
    chunk_wav = None
    try:
        lb = _resolve_loopback(p, loopback_spec)
        mic = _resolve_mic(p, mic_spec)
        lb_sr, lb_ch = int(lb["defaultSampleRate"]), lb["maxInputChannels"]
        print(f"wasapi: loopback='{lb['name']}' @ {lb_sr}Hz x{lb_ch}", flush=True)
        if mic:
            mic_sr, mic_ch = int(mic["defaultSampleRate"]), mic["maxInputChannels"]
            print(f"wasapi: mic='{mic['name']}' @ {mic_sr}Hz x{mic_ch}", flush=True)

        wasapi = p.get_host_api_info_by_type(pa.paWASAPI)
        keepalive = _open_silent_keepalive(p, wasapi["defaultOutputDevice"])
        if keepalive:
            keepalive.start_stream()

        lb_stream = p.open(format=pa.paInt16, channels=lb_ch, rate=lb_sr, input=True,
                           input_device_index=lb["index"], frames_per_buffer=1024)
        mic_stream = None
        if mic:
            mic_stream = p.open(format=pa.paInt16, channels=mic_ch, rate=mic_sr,
                                input=True, input_device_index=mic["index"],
                                frames_per_buffer=1024)

        lb_frames = int(lb_sr * TICK)
        mic_frames = int(mic_sr * TICK) if mic else 0

        full = wave.open(str(output), "wb")
        full.setnchannels(1); full.setsampwidth(2); full.setframerate(OUT_RATE)

        chunk_idx, chunk_samples = 0, 0
        if streaming:
            chunk_wav = _new_chunk(chunk_pattern, chunk_idx)

        print("wasapi: recording (drop the stop-request file to finish)", flush=True)
        while not stop_file.exists():
            lb_block = _to_mono16k(lb_stream.read(lb_frames, exception_on_overflow=False), lb_ch)
            if mic_stream:
                mic_block = _to_mono16k(
                    mic_stream.read(mic_frames, exception_on_overflow=False), mic_ch)
                mix = np.clip(lb_block + mic_block, -1.0, 1.0)
            else:
                mix = lb_block
            pcm = (mix * 32767.0).astype("<i2").tobytes()

            full.writeframes(pcm)
            if streaming:
                chunk_wav.writeframes(pcm)
                chunk_samples += OUT_BLOCK
                if chunk_samples >= segment_s * OUT_RATE:
                    chunk_wav.close()
                    chunk_idx += 1
                    chunk_wav = _new_chunk(chunk_pattern, chunk_idx)  # opening next
                    chunk_samples = 0                                 # closes the prev

        lb_stream.stop_stream(); lb_stream.close()
        if mic_stream:
            mic_stream.stop_stream(); mic_stream.close()
        print("wasapi: stopped", flush=True)
    finally:
        if chunk_wav:
            chunk_wav.close()
        if full:
            full.close()
        if keepalive:
            try:
                keepalive.stop_stream(); keepalive.close()
            except Exception:
                pass
        p.terminate()


def _new_chunk(chunk_pattern: str, idx: int) -> wave.Wave_write:
    w = wave.open(chunk_pattern % idx, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(OUT_RATE)
    return w


def main() -> None:
    ap = argparse.ArgumentParser(description="WASAPI loopback + mic recorder (Windows)")
    ap.add_argument("--output", required=True, help="full WAV output path (16k mono)")
    ap.add_argument("--chunk-pattern", default=None,
                    help="printf-style path for 30s chunks, e.g. .../chunk_%%04d.wav")
    ap.add_argument("--mic", default="mic", help="mic device substring/alias, or 'none'")
    ap.add_argument("--loopback", default="default", help="loopback endpoint substring or 'default'")
    ap.add_argument("--stop-file", required=True, help="path watched to stop recording")
    ap.add_argument("--no-stream", dest="no_stream", action="store_true")
    ap.add_argument("--segment", type=int, default=30, help="chunk length in seconds")
    args = ap.parse_args()

    streaming = bool(args.chunk_pattern) and not args.no_stream
    try:
        record(
            output=Path(args.output),
            chunk_pattern=args.chunk_pattern,
            mic_spec=args.mic,
            loopback_spec=args.loopback,
            stop_file=Path(args.stop_file),
            streaming=streaming,
            segment_s=args.segment,
        )
    except Exception as exc:
        print(f"wasapi ERROR: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
