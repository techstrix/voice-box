"""Inspect what Asterisk actually recorded, right after Record finishes.

The shared sounds dir is noisy (welcome/reply wavs, hourly sweep of in_/out_
files), so this tool copies each caller capture (in_*.wav) into
logs/captures/ and reports duration, peak/RMS energy, and a verdict
(SPEECH / SILENCE / EMPTY). With --stt it also runs the GPU transcription
on the capture so you see exactly what the pipeline hears.

Usage (repo root, host venv):
    python backend\\call_debug.py --latest          # analyze most recent capture
    python backend\\call_debug.py --latest 3        # analyze last 3 captures
    python backend\\call_debug.py --latest --stt    # + transcribe via faster-whisper
    python backend\\call_debug.py --watch           # archive + analyze new captures live (Ctrl+C)
    python backend\\call_debug.py --file asterisk\\sounds\\in_X.wav
"""
from __future__ import annotations

import argparse
import datetime
import os
import shutil
import struct
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUNDS_DIR = os.path.join(REPO_ROOT, "asterisk", "sounds")
CAPTURE_DIR = os.path.join(REPO_ROOT, "logs", "captures")

# Anything below this RMS is treated as line noise / digital silence.
SILENCE_RMS_THRESHOLD = 150


def analyze_wav(path: str) -> dict:
    """Return duration/energy stats for a (possibly empty) wav file."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return {"path": path, "error": "file not found"}
    if size <= 44:
        return {"path": path, "size": size, "verdict": "EMPTY", "detail": "header only, 0 audio frames"}
    try:
        with wave.open(path, "rb") as w:
            n_channels, sampwidth, framerate, n_frames = w.getparams()[:4]
            raw = w.readframes(n_frames)
    except Exception as error:  # noqa: BLE001
        return {"path": path, "size": size, "verdict": "UNREADABLE", "detail": str(error)}
    if sampwidth != 2 or n_frames == 0:
        return {"path": path, "size": size, "verdict": "EMPTY", "detail": f"sampwidth={sampwidth} frames={n_frames}"}
    samples = struct.unpack("<" + str(n_frames * n_channels) + "h", raw)
    if n_channels > 1:
        # Mono-ize for energy stats: average channels.
        samples = [
            sum(samples[i : i + n_channels]) // n_channels
            for i in range(0, len(samples), n_channels)
        ]
        n_channels = 1
    peak = max(abs(s) for s in samples) if samples else 0
    rms = int((sum(s * s for s in samples) / len(samples)) ** 0.5) if samples else 0
    crossings = sum(
        1 for a, b in zip(samples, samples[1:]) if (a < 0) != (b < 0)
    )
    duration = n_frames / float(framerate or 8000)
    loud = crossings
    if peak == 0:
        verdict, detail = "SILENCE", "all samples are zero (no RTP arrived)"
    elif rms < SILENCE_RMS_THRESHOLD:
        verdict, detail = "SILENCE", f"rms={rms} below threshold (line noise only)"
    else:
        verdict, detail = "SPEECH", f"rms={rms} peak={peak}"
    return {
        "path": path,
        "size": size,
        "channels": n_channels,
        "rate": framerate,
        "frames": n_frames,
        "duration_s": round(duration, 1),
        "peak": peak,
        "rms": rms,
        "zero_crossings": loud,
        "verdict": verdict,
        "detail": detail,
    }


def archive_capture(path: str) -> str:
    """Copy a capture into logs/captures/ (safe from the hourly sweep)."""
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(CAPTURE_DIR, f"{stamp}_{os.path.basename(path)}")
    shutil.copy2(path, dest)
    return dest


def report(stats: dict, stt_text: str | None = None) -> None:
    if "error" in stats:
        print(f"{stats['path']}: ERROR {stats['error']}")
        return
    print(f"{stats['path']}:")
    print(f"  size={stats.get('size')} bytes  verdict={stats['verdict']} -- {stats.get('detail')}")
    if "duration_s" in stats:
        print(
            f"  {stats['duration_s']}s @ {stats['rate']}Hz, "
            f"frames={stats['frames']} peak={stats['peak']} rms={stats['rms']}"
        )
    if stt_text is not None:
        print(f"  STT heard: {stt_text!r}")


def transcribe(path: str) -> str:
    import voice

    text, engine = voice.transcribe_audio(path)
    return f"[{engine}] {text}"


def latest_captures(n: int) -> list[str]:
    try:
        names = [f for f in os.listdir(SOUNDS_DIR) if f.startswith("in_") and f.endswith(".wav")]
    except OSError:
        return []
    names.sort(key=lambda f: os.path.getmtime(os.path.join(SOUNDS_DIR, f)))
    return [os.path.join(SOUNDS_DIR, f) for f in names[-n:]]


def cmd_latest(n: int, with_stt: bool) -> int:
    paths = latest_captures(n)
    if not paths:
        print(f"No captures in {SOUNDS_DIR} yet -- place a call first.")
        return 1
    for path in paths:
        dest = archive_capture(path)
        print(f"archived -> {dest}")
        stats = analyze_wav(path)
        stt_text = None
        if with_stt and stats.get("verdict") == "SPEECH":
            try:
                stt_text = transcribe(path)
            except Exception as error:  # noqa: BLE001
                stt_text = f"<failed: {error}>"
        report(stats, stt_text)
    return 0


def cmd_watch() -> int:
    seen = set(latest_captures(1000))
    print(f"Watching {SOUNDS_DIR} for new in_*.wav (Ctrl+C to stop)...")
    try:
        while True:
            time.sleep(1)
            for path in latest_captures(1000):
                if path not in seen:
                    seen.add(path)
                    # Give Record a moment to close the file.
                    time.sleep(1)
                    dest = archive_capture(path)
                    print(f"new capture archived -> {dest}")
                    report(analyze_wav(path))
    except KeyboardInterrupt:
        print("stopped.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect Asterisk call captures.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", nargs="?", const=1, type=int, metavar="N",
                       help="Analyze the N most recent captures (default 1)")
    group.add_argument("--watch", action="store_true", help="Archive + analyze new captures live")
    group.add_argument("--file", help="Analyze one specific wav file")
    parser.add_argument("--stt", action="store_true", help="Also transcribe SPEECH captures (GPU)")
    args = parser.parse_args(argv)
    if args.watch:
        return cmd_watch()
    if args.file:
        dest = archive_capture(args.file) if os.path.isfile(args.file) else None
        if dest:
            print(f"archived -> {dest}")
        stats = analyze_wav(args.file)
        stt_text = None
        if args.stt and stats.get("verdict") == "SPEECH":
            try:
                stt_text = transcribe(args.file)
            except Exception as error:  # noqa: BLE001
                stt_text = f"<failed: {error}>"
        report(stats, stt_text)
        return 0
    return cmd_latest(args.latest or 1, args.stt)


if __name__ == "__main__":
    raise SystemExit(main())
