#!/usr/bin/env python3
"""Local transcription backend — whisper.cpp (Metal on Apple Silicon) + sherpa-onnx
speaker diarization (ONNX models, no API key, no Hugging Face token).

Drop-in mirror of the AssemblyAI `transcribe()` in transcriber.py: returns the same
dict shape (utterances with start/end in milliseconds, audio_duration in seconds,
speaker labels A/B/C…) so all downstream formatting works unchanged.

Two entry points share the same diarization + merge core:
- `transcribe_local(audio)` — batch: ASR the whole file, then diarize + merge.
- `finalize_streaming(session_dir)` — streaming: ASR was already done chunk-by-chunk
  during the meeting (see the sidecar in transcriber.py, which writes partial.jsonl);
  here we only diarize the finalized audio.wav and merge with the pre-computed text.

Heavy deps (pywhispercpp, sherpa_onnx, soundfile) are imported lazily inside the
functions, so importing this module is cheap and never fails when only the AssemblyAI
backend is in use.
"""
import json
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

# Repo root: <repo>/.claude/skills/transcriber/scripts/transcribe_local.py → parents[4]
REPO_ROOT = Path(os.environ.get("AUGMENTATION_ROOT", Path(__file__).resolve().parents[4]))
MODELS_DIR = REPO_ROOT / "config" / "transcriber-models"  # gitignored

# Same ONNX models the `minutes` app uses — public, ungated downloads.
_SEG_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
)
_EMB_URL = (
    "https://huggingface.co/csukuangfj/speaker-embedding-models/resolve/main/"
    "3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx"
)
_SEG_MODEL = MODELS_DIR / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
_EMB_MODEL = MODELS_DIR / "campplus_voxceleb.onnx"

# Auto-clustering threshold when the number of speakers is unknown. Tuned empirically:
# lower over-detects speakers, higher merges distinct voices. 0.8 is a good default.
_AUTO_THRESHOLD = 0.8

# Diarization thread count. Benchmarked on an M3 Pro (10-min slice): 1→62s, 4→24s,
# 8→39s (oversubscription). 4 is the sweet spot — ~2.5x faster than single-threaded.
_DIARIZE_THREADS = 4

# Streaming sidecar writes one JSON object per ASR segment here (start/end in ms,
# already offset to absolute meeting time). finalize_streaming reads it back.
PARTIAL_FILE = "partial.jsonl"


# ---------------------------------------------------------------------------
# model download (idempotent, first run only)
# ---------------------------------------------------------------------------

def _download(url: str, dest: Path) -> None:
    """Download to a temp file then rename — an interrupted run never leaves a
    partial file at the final path (which would block a clean retry)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url.rsplit('/', 1)[-1]}…", file=sys.stderr)
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)


def _ensure_models() -> None:
    """Fetch the diarization ONNX models on first run; idempotent afterwards."""
    if not _SEG_MODEL.exists():
        tarball = MODELS_DIR / "seg.tar.bz2"
        _download(_SEG_URL, tarball)
        with tarfile.open(tarball, "r:bz2") as tf:
            tf.extractall(MODELS_DIR)
        tarball.unlink(missing_ok=True)
    if not _EMB_MODEL.exists():
        _download(_EMB_URL, _EMB_MODEL)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _speaker_label(index: int) -> str:
    """0 → 'A', 1 → 'B', … matching the AssemblyAI speaker-label style."""
    return chr(ord("A") + index) if index < 26 else f"S{index}"


def _resample(audio, sr: int, target_sr: int):
    """Linear resample to target_sr. Diarization models expect 16 kHz; self-recordings
    already are, but `transcribe <file>` accepts arbitrary audio — at 44.1/48 kHz the
    turns would misalign with the (rate-independent) Whisper timestamps."""
    if sr == target_sr:
        return audio
    import numpy as np

    n = int(round(len(audio) * target_sr / sr))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype("float32")


def _read_mono(audio_path: str):
    """Read an audio file as mono float32. Returns (audio, sample_rate)."""
    import soundfile as sf

    audio, sample_rate = sf.read(audio_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio[:, 0]
    return audio, sample_rate


# ---------------------------------------------------------------------------
# ASR — whisper.cpp via pywhispercpp
# ---------------------------------------------------------------------------

def load_whisper(model_size: str = "medium"):
    """Load a whisper.cpp model (Metal-accelerated on Apple Silicon). The sidecar
    loads this once and reuses it across every chunk, so the ~20s init is amortized."""
    from pywhispercpp.model import Model

    return Model(model_size, print_progress=False, print_realtime=False)


def _asr_segments(model, audio_path: str, language: str = "pt", offset_s: float = 0.0):
    """Run ASR on a file, return [(start_s, end_s, text)] in absolute time.
    whisper.cpp reports t0/t1 in centiseconds; offset_s shifts a chunk to meeting time."""
    segments = model.transcribe(audio_path, language=language)
    return [
        (s.t0 / 100.0 + offset_s, s.t1 / 100.0 + offset_s, s.text.strip())
        for s in segments
        if s.text.strip()
    ]


# ---------------------------------------------------------------------------
# diarization — sherpa-onnx (segmentation + speaker-embedding ONNX)
# ---------------------------------------------------------------------------

def _diarize(audio, sample_rate, num_speakers, num_threads: int = _DIARIZE_THREADS):
    """Return a list of (start_s, end_s, cluster_id) speaker turns (times in seconds)."""
    import sherpa_onnx

    _ensure_models()
    if num_speakers and num_speakers > 0:
        clustering = sherpa_onnx.FastClusteringConfig(num_clusters=int(num_speakers))
    else:
        clustering = sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=_AUTO_THRESHOLD)

    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(_SEG_MODEL)),
            num_threads=num_threads,
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(_EMB_MODEL), num_threads=num_threads,
        ),
        clustering=clustering,
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    diarizer = sherpa_onnx.OfflineSpeakerDiarization(config)
    audio = _resample(audio, sample_rate, diarizer.sample_rate)
    return [(s.start, s.end, s.speaker) for s in diarizer.process(audio).sort_by_start_time()]


def _speaker_for(turns, start_s: float, end_s: float) -> int:
    """Assign the speaker whose turn overlaps the [start, end] window the most."""
    best_overlap, who = 0.0, 0
    for turn_start, turn_end, cluster_id in turns:
        overlap = max(0.0, min(end_s, turn_end) - max(start_s, turn_start))
        if overlap > best_overlap:
            best_overlap, who = overlap, cluster_id
    return who


def _merge(asr, turns) -> list:
    """Label each ASR segment by max-overlap speaker, then collapse consecutive
    same-speaker segments into utterances (one paragraph per turn). `asr` is a list
    of (start_s, end_s, text); returns utterances with start/end in milliseconds.

    sherpa's cluster ids aren't contiguous (you can get 0,1,3), so remap by order of
    first appearance → A, B, C… — cleaner labels and no confusing gaps for the
    downstream speaker-matching step."""
    label_map: dict[int, str] = {}
    utterances = []
    for start_s, end_s, text in asr:
        cluster_id = _speaker_for(turns, start_s, end_s)
        if cluster_id not in label_map:
            label_map[cluster_id] = _speaker_label(len(label_map))
        speaker = label_map[cluster_id]
        if utterances and utterances[-1]["speaker"] == speaker:
            utterances[-1]["text"] += " " + text
            utterances[-1]["end"] = int(end_s * 1000)
        else:
            utterances.append({
                "speaker": speaker,
                "text": text,
                "start": int(start_s * 1000),
                "end": int(end_s * 1000),
            })
    return utterances


def _result(utterances, audio_len, sample_rate, language) -> dict:
    """Assemble the common return shape (mirrors AssemblyAI's transcribe())."""
    return {
        "status": "completed",
        "text": " ".join(u["text"] for u in utterances),
        "speakers": sorted({u["speaker"] for u in utterances}),
        "utterances": utterances,
        "audio_duration": int(audio_len / sample_rate),
        "language": language,
    }


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------

def transcribe_local(audio_path: str, model_size: str = "medium",
                     language: str = "pt", num_speakers=None) -> dict:
    """Batch: transcribe + diarize a whole file locally."""
    model = load_whisper(model_size)
    asr = _asr_segments(model, audio_path, language)

    audio, sample_rate = _read_mono(audio_path)
    turns = _diarize(audio, sample_rate, num_speakers)

    return _result(_merge(asr, turns), len(audio), sample_rate, language)


def finalize_streaming(session_dir: str, language: str = "pt", num_speakers=None) -> dict:
    """Streaming: ASR already happened chunk-by-chunk during the meeting (partial.jsonl).
    Read it back, diarize the finalized audio.wav, and merge — no whisper pass here."""
    session = Path(session_dir)
    partial = session / PARTIAL_FILE
    audio_path = session / "audio.wav"
    if not partial.exists():
        raise FileNotFoundError(f"no {PARTIAL_FILE} in {session} — was this a streaming session?")
    if not audio_path.exists():
        raise FileNotFoundError(f"no audio.wav in {session}")

    asr = []
    for line in partial.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        seg = json.loads(line)
        asr.append((seg["start"] / 1000.0, seg["end"] / 1000.0, seg["text"]))
    asr.sort(key=lambda s: s[0])

    audio, sample_rate = _read_mono(str(audio_path))
    turns = _diarize(audio, sample_rate, num_speakers)

    return _result(_merge(asr, turns), len(audio), sample_rate, language)
