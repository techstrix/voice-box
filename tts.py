"""Text-to-speech with Microsoft Edge TTS (edge-tts 7.x).

Usage:
    python tts.py "Hello world" -o hello.mp3
    python tts.py -f text.txt -o hello.mp3
    echo "Hello" | python tts.py -o hello.mp3
    python tts.py "Hello" -o hello.mp3 --voice en-US-GuyNeural
    python tts.py --list-voices
    python tts.py --list-voices --language en
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys


DEFAULT_VOICE = os.environ.get("TTS_VOICE", "en-US-AriaNeural")


async def _save(text: str, output: str, voice: str, rate: str, volume: str, pitch: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(
        text, voice=voice, rate=rate, volume=volume, pitch=pitch
    )
    await communicate.save(output)


async def _list_voices(language: str | None = None) -> list[dict]:
    import edge_tts

    voices = await edge_tts.list_voices()
    if language:
        language = language.lower()
        voices = [v for v in voices if v.get("Locale", "").lower().startswith(language)]
    return voices


def synthesize(
    text: str,
    output: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    volume: str = "+0%",
    pitch: str = "+0Hz",
) -> str:
    text = (text or "").strip()
    if not text:
        raise ValueError("No text to synthesize (empty string).")
    parent = os.path.dirname(os.path.abspath(output))
    if parent:
        os.makedirs(parent, exist_ok=True)
    asyncio.run(_save(text, output, voice, rate, volume, pitch))
    if not os.path.isfile(output) or os.path.getsize(output) == 0:
        raise RuntimeError(f"TTS produced no audio: {output}")
    return output


def read_input_text(args: argparse.Namespace) -> str:
    if args.file:
        if args.file == "-":
            return sys.stdin.read()
        with open(args.file, encoding="utf-8") as f:
            return f.read()
    parts: list[str] = []
    if args.text:
        parts.append(" ".join(args.text))
    if not sys.stdin.isatty():
        piped = sys.stdin.read()
        if piped.strip():
            parts.append(piped)
    return "\n".join(p for p in parts if p).strip()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Synthesize speech with Edge TTS.")
    p.add_argument("text", nargs="*", help="Text to speak (or pipe via stdin)")
    p.add_argument("-f", "--file", help="Read text from file (use - for stdin)")
    p.add_argument("-o", "--output", default="output.mp3", help="Output audio file (default: output.mp3)")
    p.add_argument("-v", "--voice", default=DEFAULT_VOICE, help=f"Voice (default: {DEFAULT_VOICE})")
    p.add_argument("--rate", default="+0%", help="Speaking rate, e.g. +20%% (default: +0%%)")
    p.add_argument("--volume", default="+0%", help="Volume, e.g. +20%% (default: +0%%)")
    p.add_argument("--pitch", default="+0Hz", help="Pitch, e.g. +10Hz (default: +0Hz)")
    p.add_argument("--list-voices", action="store_true", help="List available voices and exit")
    p.add_argument("--language", default="", help="Filter --list-voices by locale, e.g. en")
    p.add_argument("--verbose", action="store_true", help="Print details to stderr")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_voices:
        try:
            voices = asyncio.run(_list_voices(args.language or None))
        except Exception as e:  # noqa: BLE001
            print(f"Could not list voices: {e}", file=sys.stderr)
            return 1
        for v in voices:
            print(f"{v.get('ShortName')}  ({v.get('Locale')}, {v.get('Gender')})")
        return 0
    try:
        text = read_input_text(args)
        out = synthesize(text, args.output, args.voice, args.rate, args.volume, args.pitch)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - network/auth failures from Edge API
        print(f"TTS failed: {e}", file=sys.stderr)
        return 1
    if args.verbose:
        size = os.path.getsize(out)
        print(f"[tts] voice={args.voice} bytes={size} -> {out}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
