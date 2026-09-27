"""GPU-accelerated speech-to-text with faster-whisper.

Usage:
    python stt.py sample_question.wav
    python stt.py sample_question.wav --model small --language en
    python stt.py sample_question.wav --device cuda --compute-type float16
    python stt.py sample_question.wav --device cpu
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _setup_cuda_dlls() -> None:
    """Make CUDA libs from pip packages (nvidia-cublas-cu12, etc.) discoverable.

    ctranslate2 needs cublas64_12.dll / cudnn DLLs. On Windows / Python 3.8+,
    plain PATH is not enough -- DLL directories must be added explicitly.
    """
    if os.name != "nt":
        return
    candidates: list[str] = []
    for base in (sys.prefix, os.path.dirname(sys.executable)):
        nv = os.path.join(base, "Lib", "site-packages", "nvidia")
        if os.path.isdir(nv):
            for pkg in ("cublas", "cudnn", "cuda_nvrtc", "cuda_runtime"):
                d = os.path.join(nv, pkg, "bin")
                if os.path.isdir(d):
                    candidates.append(d)
    # Also cover PYTHONPATH-installed layouts.
    try:
        import site

        for sp in site.getsitepackages() + [site.getusersitepackages()]:
            nv = os.path.join(sp, "nvidia")
            if os.path.isdir(nv):
                for pkg in ("cublas", "cudnn", "cuda_nvrtc", "cuda_runtime"):
                    d = os.path.join(nv, pkg, "bin")
                    if os.path.isdir(d):
                        candidates.append(d)
    except Exception:
        pass
    for d in dict.fromkeys(candidates):  # dedupe, keep order
        try:
            os.add_dll_directory(d)
        except Exception:
            pass
        if d not in os.environ.get("PATH", ""):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


_setup_cuda_dlls()

from faster_whisper import WhisperModel


def resolve_device(requested: str) -> str:
    """Resolve 'auto' to 'cuda' or 'cpu' based on ctranslate2 CUDA availability."""
    if requested != "auto":
        return requested
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def default_compute_type(device: str) -> str:
    if device == "cuda":
        # float16 = fastest on NVIDIA GPUs; T4/T1200-class 4GB cards handle
        # base/small fine with this. int8_float16 uses less VRAM if OOM.
        return "float16"
    return "int8"


def load_model(model_name: str, device: str, compute_type: str) -> WhisperModel:
    return WhisperModel(model_name, device=device, compute_type=compute_type)


def load_model_with_fallback(
    model_name: str, device: str, compute_type: str
) -> tuple[WhisperModel, str, str]:
    """Try requested device/compute, fall back gracefully (CUDA OOM -> smaller footprint -> CPU)."""
    attempts: list[tuple[str, str]] = [(device, compute_type)]
    if device == "cuda":
        # Common fallback chain for 4GB laptop GPUs.
        for ct in ("int8_float16", "int8", "float32"):
            if (device, ct) not in attempts:
                attempts.append((device, ct))
        attempts.append(("cpu", "int8"))
    last_err: Exception | None = None
    for dev, ct in attempts:
        try:
            model = load_model(model_name, dev, ct)
            return model, dev, ct
        except Exception as e:  # noqa: BLE001 - want to try next fallback
            last_err = e
            print(
                f"[stt] failed {dev}/{ct}: {e} -- trying fallback...",
                file=sys.stderr,
            )
    raise RuntimeError(f"Could not load model {model_name!r}") from last_err


def transcribe(
    audio_path: str,
    model_name: str = "base",
    device: str = "auto",
    compute_type: str = "auto",
    language: str = "en",
    beam_size: int = 5,
    verbose: bool = False,
) -> str:
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    size = os.path.getsize(audio_path)
    if size == 0:
        raise ValueError(
            f"Audio file is empty (0 bytes): {audio_path} -- re-export/re-download it"
        )

    resolved_device = resolve_device(device)
    resolved_compute = compute_type if compute_type != "auto" else default_compute_type(resolved_device)

    model, used_device, used_compute = load_model_with_fallback(
        model_name, resolved_device, resolved_compute
    )
    if verbose:
        print(
            f"[stt] model={model_name} device={used_device} compute={used_compute}",
            file=sys.stderr,
        )

    try:
        segments, info = model.transcribe(
            audio_path,
            language=language if language != "auto" else None,
            beam_size=beam_size,
        )
        texts: list[str] = []
        for seg in segments:
            text = seg.text.strip()
            texts.append(text)
            if verbose:
                print(f"[{seg.start:.2f}s -> {seg.end:.2f}s] {text}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001 - wrap PyAV/ffmpeg decode errors
        raise RuntimeError(f"decode failed: {e}") from e
    if verbose:
        print(
            f"[stt] detected language={info.language} "
            f"prob={info.language_probability:.2f} duration={info.duration:.1f}s",
            file=sys.stderr,
        )
    return " ".join(t for t in texts if t)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Transcribe audio with faster-whisper (GPU).")
    p.add_argument("audio", help="Path to audio file (wav/mp3/m4a/flac/...)")
    p.add_argument(
        "--model",
        default=os.environ.get("STT_MODEL", "base"),
        help="tiny/base/small/medium/large-v3 (default: base)",
    )
    p.add_argument(
        "--device",
        default=os.environ.get("STT_DEVICE", "auto"),
        choices=["auto", "cuda", "cpu"],
        help="auto tries CUDA then CPU (default: auto)",
    )
    p.add_argument(
        "--compute-type",
        default=os.environ.get("STT_COMPUTE", "auto"),
        choices=["auto", "float16", "int8_float16", "int8", "float32", "int8_float32"],
        help="auto = float16 on CUDA, int8 on CPU (default: auto)",
    )
    p.add_argument(
        "--language",
        default=os.environ.get("STT_LANGUAGE", "en"),
        help="Language code, or 'auto' for detection (default: en)",
    )
    p.add_argument("--beam-size", type=int, default=5, help="Beam size (default: 5)")
    p.add_argument(
        "--json", action="store_true", help="Print result as JSON instead of plain text"
    )
    p.add_argument(
        "--verbose", action="store_true", help="Print segments/timings to stderr"
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        text = transcribe(
            args.audio,
            model_name=args.model,
            device=args.device,
            compute_type=args.compute_type,
            language=args.language,
            beam_size=args.beam_size,
            verbose=args.verbose,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        # Typically an undecodable/corrupt container from PyAV/ffmpeg.
        print(
            f"Transcription failed: could not decode {args.audio!r} ({e}). "
            f"Check the file plays in a media player and is not 0 bytes.",
            file=sys.stderr,
        )
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"Transcription failed: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"text": text, "audio": args.audio}, ensure_ascii=False))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
