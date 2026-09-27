"""Minimal stdlib-only FastAGI server for the Asterisk voice loop.

Two modes (first AGI argument):
  start: AGI(agi://host.docker.internal:4573/voice,start,${EXTEN},${UNIQUEID})
         Launches process_voice_turn in a background thread and returns at
         once (VB_STATUS=started) so the dialplan can keep the caller
         entertained while STT/RAG/TTS works (~20s worst case).
  check: AGI(agi://host.docker.internal:4573/voice,check,${EXTEN},${UNIQUEID})
         Polls the background job: VB_STATUS=wait | ok | error, and on
         success VB_REPLY=out_<UNIQUEID> (wav basename, no ext) for
         Playback(custom/${VB_REPLY}).

Run (host venv, alongside the FastAPI backend):
    python agi_server.py
"""
from __future__ import annotations

import argparse
import os
import socketserver
import sys
import threading
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import voice

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _send(rfile, wfile, command: str) -> str:
    wfile.write(command.encode() + b"\n")
    wfile.flush()
    return rfile.readline().decode(errors="replace").strip()


def _run_job(call_id: str, company: str | None) -> None:
    try:
        result = voice.process_voice_turn(company, voice.in_wav_path(call_id), call_id)
    except Exception as error:  # noqa: BLE001 - never leave a job hanging
        result = {"transcript": "", "answer": "", "context": "", "wav_path": None,
                  "error": str(error)}
    with _jobs_lock:
        job = _jobs.get(call_id)
        if job is not None:
            job["result"] = result
            job["done"].set()


def _handle_start(env: dict[str, str]) -> dict[str, str]:
    extension = env.get("agi_arg_2", "")
    call_id = voice.sanitize_call_id(env.get("agi_arg_3", ""))
    company = voice.company_for_extension(extension)
    voice.logger.info(
        "agi start extension=%s call=%s company=%s", extension, call_id, company
    )
    with _jobs_lock:
        _jobs[call_id] = {"done": threading.Event(), "result": None}
        # Bound concurrent background turns (GPU serializes anyway).
        while len(_jobs) > 20:
            oldest = next(iter(_jobs))
            if _jobs[oldest]["done"].is_set():
                del _jobs[oldest]
            else:
                break
    worker = threading.Thread(
        target=_run_job, args=(call_id, company), daemon=True
    )
    worker.start()
    return {"VB_STATUS": "started", "VB_REPLY": ""}


def _handle_check(env: dict[str, str]) -> dict[str, str]:
    call_id = voice.sanitize_call_id(env.get("agi_arg_3", ""))
    with _jobs_lock:
        job = _jobs.get(call_id)
    if job is None or not job["done"].is_set():
        return {"VB_STATUS": "wait", "VB_REPLY": ""}
    result = job.get("result") or {}
    wav_path = result.get("wav_path")
    if wav_path:
        reply = os.path.splitext(os.path.basename(wav_path))[0]
        voice.logger.info("agi check call=%s ready reply=%s", call_id, reply)
        with _jobs_lock:
            _jobs.pop(call_id, None)
        return {"VB_STATUS": "ok", "VB_REPLY": reply}
    voice.logger.warning("agi check call=%s finished without audio", call_id)
    with _jobs_lock:
        _jobs.pop(call_id, None)
    return {"VB_STATUS": "error", "VB_REPLY": ""}


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

            mode = (env.get("agi_arg_1", "") or "").strip().lower()
            if mode == "check":
                variables = _handle_check(env)
            else:
                variables = _handle_start(env)

            for key, value in variables.items():
                _send(self.rfile, self.wfile, f'SET VARIABLE "{key}" "{value}"')
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
        voice.logger.info("agi listening on %s:%d", args.host, args.port)
        print(f"[agi] listening on {args.host}:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
