"""Provider-observed overlap across separate foreground/background processes."""

import os
from pathlib import Path
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def test_foreground_and_background_processes_have_independent_limits(tmp_path):
    active = peak = 0
    lock = threading.Lock()
    both_entered, release = threading.Event(), threading.Event()

    class Provider(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                if active == 2:
                    both_entered.set()
            try:
                assert release.wait(10)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
            finally:
                with lock:
                    active -= 1

        def log_message(self, *args):
            pass

    code = '''
import asyncio, sys
from urllib.request import build_opener, ProxyHandler
from fastapi import HTTPException
import app.config as config
from app.core import llm_semaphore as limits
config._settings_instance = config.Settings(max_concurrent_llm_calls=1, max_background_concurrent_llm_calls=1, _env_file=None)
async def run():
    if sys.argv[2] == 'background':
        await limits.acquire_background_llm_slot_blocking()
    else:
        await limits.acquire_llm_slot()
    try:
        try:
            await limits.acquire_llm_slot()
        except HTTPException as error:
            assert error.status_code == 503
        else:
            raise AssertionError('same-process limit was bypassed')
        with build_opener(ProxyHandler({})).open(sys.argv[1], timeout=15) as response:
            assert response.read() == b'ok'
    finally:
        if sys.argv[2] == 'background':
            limits.release_background_llm_slot()
        else:
            limits.release_llm_slot()
asyncio.run(run())
'''
    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    processes = []
    try:
        for lane in ("foreground", "background"):
            processes.append(subprocess.Popen(
                [sys.executable, "-c", code, f"http://127.0.0.1:{provider.server_port}/", lane],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "SCNGS_DATA_DIR": str(tmp_path / lane)},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ))
        assert both_entered.wait(10), "both independent pools must reach the controlled provider"
        assert peak == 2
        release.set()
        for process in processes:
            out, error = process.communicate(timeout=10)
            assert process.returncode == 0, out + error
    finally:
        release.set()
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=5)
