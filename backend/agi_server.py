"""Minimal stdlib-only FastAGI server for the Asterisk voice loop.

Dialplan calls:  AGI(agi://host.docker.internal:4573/voice,${EXTEN},${UNIQUEID})
after recording the caller to sounds/in_<UNIQUEID>.wav.

The server runs the shared pipeline (voice.process_voice_turn) against that
file, writes sounds/out_<UNIQUEID>.wav, and sets channel variables:
  VB_STATUS = ok | error        VB_REPLY  = out_<UNIQUEID> (wav basename, no ext)
The dialplan then does Playback(custom/${VB_REPLY}).

Run (host venv, alongside the FastAPI backend):
    python agi_server.py
"""
from __future__ import annotations

import argparse
import os
import socketserver
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import voice


def _send(rfile, wfile, command: str) -> str:
    wfile.write(command.encode() + b"\n")
    wfile.flush()
    return rfile.readline().decode(errors="replace").strip()


class VoiceHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        env: dict[str, str] = {}
        try:
            while True:
                line = self.rfile.readline().decode(errors="replace").strip()
                if not line:
                    break
                if ":" in line:
                    key, _, value = line.partition(":")
                    env[key.strip()] = value.strip()

            extension = env.get("agi_arg_1", "")
            call_id = voice.sanitize_call_id(env.get("agi_arg_2", ""))
            company = voice.company_for_extension(extension)
            print(
                f"[agi] extension={extension} call={call_id} company={company}",
                file=sys.stderr,
                flush=True,
            )

            result = voice.process_voice_turn(company, voice.in_wav_path(call_id), call_id)
            reply_file = ""
            if result.get("wav_path"):
                reply_file = os.path.splitext(os.path.basename(result["wav_path"]))[0]
            status = "ok" if reply_file else "error"

            _send(self.rfile, self.wfile, f'SET VARIABLE "VB_STATUS" "{status}"')
            _send(self.rfile, self.wfile, f'SET VARIABLE "VB_REPLY" "{reply_file}"')
            voice.sweep_old_files()
        except Exception:
            traceback.print_exc()
            try:
                _send(self.rfile, self.wfile, 'SET VARIABLE "VB_STATUS" "error"')
                _send(self.rfile, self.wfile, 'SET VARIABLE "VB_REPLY" ""')
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VoiceBox FastAGI server.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=4573)
    args = parser.parse_args(argv)
    with socketserver.ThreadingTCPServer(
        (args.host, args.port), VoiceHandler, bind_and_activate=False
    ) as server:
        server.allow_reuse_address = True
        server.server_bind()
        server.server_activate()
        print(f"[agi] listening on {args.host}:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
