"""Exercise a real .app in an isolated profile; native UI verification is separate.

Requires a logged-in macOS desktop session and a free localhost:8000. Never
attaches to or terminates an existing NovWr instance. Keeps test data and logs
in the report directory; removes only the Keychain item it created via the app.
"""

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
import uuid


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:8000"
HTTP = build_opener(ProxyHandler({}))
EDITED_CONTENT = "这段正文由 macOS 安装包保存，正常退出及强制退出后仍应保留。"


def request(path, *, method="GET", body=None, content_type="application/json", timeout=30):
    if isinstance(body, dict):
        body = json.dumps(body).encode()
    url = path if path.startswith("http://") else ORIGIN + path
    req = Request(url, data=body, method=method, headers={
        "Origin": ORIGIN, "Content-Type": content_type,
    })
    with HTTP.open(req, timeout=timeout) as response:
        payload = response.read()
        if "application/json" in response.headers.get("Content-Type", "") and payload:
            return json.loads(payload)
        return payload


def eventually(check, *, timeout=45, description):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (ConnectionError, URLError, TimeoutError, OSError) as error:
            last_error = error
        time.sleep(0.25)
    raise RuntimeError(f"Timed out: {description}; last error: {last_error}")


def require_free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 8000))


def process_table():
    # No command arguments/environment are collected from unrelated processes.
    output = subprocess.check_output(["ps", "-axo", "pid=,ppid=,stat=,lstart="], text=True)
    return {int(pid): (int(parent), state, born) for pid, parent, state, born in
            (line.split(maxsplit=3) for line in output.splitlines())}


def descendants(pid):
    table = process_table()
    owned = {pid}
    while True:
        found = {child for child, (parent, _, _) in table.items() if parent in owned}
        if found <= owned:
            return {child: table[child][2] for child in owned if child in table}
        owned.update(found)


def survivors(pids):
    table = process_table()
    return {pid: born for pid, born in pids.items() if pid in table
            and table[pid][2] == born and not table[pid][1].startswith("Z")}


def upload_novel(api):
    boundary = "novwr-" + uuid.uuid4().hex
    fields = {
        "title": "NovWr Mac App Smoke", "consent_acknowledged": "true",
        "consent_version": "2026-03-06", "language": "zh",
    }
    pieces = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        for name, value in fields.items()
    ]
    pieces.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="mac-smoke.txt"\r\n'
        'Content-Type: text/plain\r\n\r\n第一章\n这是 macOS 安装版持久化验证正文。\n\r\n'
        f'--{boundary}--\r\n'
    )
    return api("/api/novels/upload", method="POST", body="".join(pieces).encode(),
               content_type=f"multipart/form-data; boundary={boundary}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, default=ROOT / "reports/macos-desktop")
    args = parser.parse_args()
    app = args.app.resolve(strict=True)
    executable = app / "Contents/MacOS/NovWr"
    if not executable.is_file():
        parser.error("--app must point to the complete NovWr.app bundle")
    require_free_port()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    report = Path(tempfile.mkdtemp(prefix="smoke-", dir=args.report_dir.resolve()))
    profile = report / "profile"
    env = {**os.environ, "NOVWR_DESKTOP_DATA_ROOT": str(profile)}
    results = {"app": str(app), "profile": str(profile), "checks": [], "native_ui": "separate manual gate"}
    app_process = None
    provider = None
    owned_pids = {}
    keychain_created = False
    log_handles = []

    def passed(label):
        results["checks"].append(label)
        print(f"PASS {label}", flush=True)

    def api(path, **kwargs):
        if app_process is None or app_process.poll() is not None:
            raise RuntimeError("The test application is not running")
        children = descendants(app_process.pid)
        owned_pids.update(children)
        listening = subprocess.run(
            ["lsof", "-nP", "-t", "-iTCP:8000", "-sTCP:LISTEN"], capture_output=True, text=True, check=False,
        )
        if listening.returncode != 0 or not listening.stdout.strip():
            raise ConnectionError("The test backend is not listening yet")
        if not set(map(int, listening.stdout.split())) <= children.keys():
            raise RuntimeError("Refusing to access a listener outside the test application's process tree")
        return request(path, **kwargs)

    def start_app(label):
        nonlocal app_process
        require_free_port()
        log = (report / f"{label}.log").open("wb")
        log_handles.append(log)
        app_process = subprocess.Popen([str(executable)], env=env, stdout=log, stderr=log)

        def ready():
            healthy = api("/api/health", timeout=2).get("status") == "healthy"
            # Include the shell, plus server/worker and their guardians.
            return healthy and len(descendants(app_process.pid)) >= 5

        eventually(ready, timeout=150, description=f"{label} health")
        return app_process

    def stop_app(process, *, crash=False):
        if process.poll() is not None:
            raise RuntimeError("The test application exited before the shutdown check")
        children = descendants(process.pid)
        owned_pids.update(children)
        if crash:
            process.kill()
        else:
            # NSRunningApplication targets our exact PID and requests normal Quit.
            script = (
                "ObjC.import('AppKit'); "
                f"if (!$.NSRunningApplication.runningApplicationWithProcessIdentifier({process.pid}).terminate) "
                "throw Error('Application rejected Quit');"
            )
            subprocess.run(["osascript", "-l", "JavaScript", "-e", script], check=True, timeout=10)
        exit_code = process.wait(timeout=40)
        if not crash and exit_code != 0:
            raise RuntimeError(f"Normal Quit returned {exit_code}")
        eventually(lambda: not survivors(children), description="all owned runtime descendants exit")
        eventually(port_is_free, description="localhost:8000 released")

    try:
        provider_log = (report / "provider-process.log").open("wb")
        log_handles.append(provider_log)
        provider_ready = report / "provider-ready.json"
        fake_key = "novwr-smoke-" + uuid.uuid4().hex
        model = "novwr-controlled-smoke"
        provider = subprocess.Popen([
            "node", str(ROOT / "scripts/desktop_llm_provider_stub.mjs"),
            "--ready-file", str(provider_ready), "--log-file", str(report / "provider.jsonl"),
        ], env={**os.environ, "NOVWR_DESKTOP_PROVIDER_API_KEY": fake_key,
                "NOVWR_DESKTOP_PROVIDER_MODEL": model}, stdout=provider_log, stderr=provider_log)
        eventually(lambda: provider_ready.is_file(), timeout=10, description="controlled provider")
        provider_info = json.loads(provider_ready.read_text())

        app_process = start_app("first-launch")
        assert b'<div id="root">' in api("/")
        assert (profile / "data/novels.db").is_file()
        passed("frozen app bootstraps SQLite and serves bundled frontend")

        duplicate = subprocess.run([str(executable)], env=env, capture_output=True, timeout=10)
        assert duplicate.returncode == 0
        assert app_process.poll() is None
        passed("second launch activates the first instance and exits")

        novels = api("/api/novels")
        assert any(novel["is_seeded_demo"] for novel in novels)
        novel_id = upload_novel(api)["novel_id"]
        eventually(lambda: api(f"/api/novels/{novel_id}/status")["status"] == "fresh",
                   timeout=120, description="real worker/Rust chapter indexing")
        chapter_path = f"/api/novels/{novel_id}/chapters/1"
        assert "macOS" in api(chapter_path)["content"]
        api(chapter_path, method="PUT", body={"content": EDITED_CONTENT})
        passed("demo seeding, upload, worker indexing and chapter save")

        keychain_created = True  # The write may commit even if receiving its response fails.
        configured = api("/api/llm/config", method="PUT", body={
            "base_url": provider_info["base_url"], "api_key": fake_key, "model": model,
        })
        assert configured["api_key_configured"] and "api_key" not in configured
        assert not (profile / "llm-config.json").exists()
        probe = api("/api/llm/test", method="POST")
        results["provider_probe"] = probe
        assert probe["code"] == "llm_probe_compatible", probe
        assert all(request(provider_info["origin"] + "/health")["requests"].values())
        assert not any(fake_key.encode() in path.read_bytes()
                       for path in profile.rglob("*") if path.is_file())
        passed("native Keychain config and controlled basic/stream/JSON provider probes")

        stop_app(app_process)
        passed("normal macOS Quit reaps runtime descendants and releases port")
        app_process = start_app("restart")
        assert api(chapter_path)["content"] == EDITED_CONTENT
        assert api("/api/llm/config")["model"] == model
        assert api("/api/llm/test", method="POST")["code"] == "llm_probe_compatible"
        passed("chapter and Keychain configuration survive complete app restart")
        api("/api/llm/config", method="DELETE")
        keychain_created = False
        assert not api("/api/llm/config")["configured"]
        passed("exact test Keychain item deleted through the running app")

        stop_app(app_process, crash=True)
        passed("SIGKILL of shell automatically reaps server/worker process trees")
        app_process = start_app("crash-recovery")
        assert api(chapter_path)["content"] == EDITED_CONTENT
        stop_app(app_process)
        passed("fresh launch after crash preserves data and shuts down cleanly")
        results["status"] = "passed"
    except BaseException as error:
        results["status"] = "failed"
        results["error_type"] = type(error).__name__
        results["error"] = str(error)
        raise
    finally:
        cleanup_errors = []
        if keychain_created:
            try:
                if app_process is None or app_process.poll() is not None:
                    eventually(port_is_free, timeout=10, description="cleanup launch port")
                    app_process = start_app("cleanup")
                api("/api/llm/config", method="DELETE")
                keychain_created = False
            except Exception as error:
                cleanup_errors.append(f"Keychain: {error}")
                results["keychain_cleanup_config_path"] = str(profile / "llm-config.json")
        results["keychain_item_remaining"] = keychain_created
        for process in (app_process, provider):
            if process is None:
                continue
            try:
                try:
                    if process is app_process and process.poll() is None:
                        owned_pids.update(descendants(process.pid))
                finally:
                    process.send_signal(signal.SIGKILL if process is app_process else signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
            except Exception as error:
                cleanup_errors.append(f"Process {process.pid}: {error}")
        try:
            try:
                eventually(lambda: not survivors(owned_pids), timeout=10, description="final cleanup")
            except RuntimeError:
                results["forced_cleanup"] = True
                cleanup_errors.append("Runtime descendants required forced cleanup")
                for pid, born in survivors(owned_pids).items():
                    try:
                        if survivors({pid: born}):  # Do not signal a PID reused by another process.
                            os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                eventually(lambda: not survivors(owned_pids), timeout=10, description="forced cleanup")
        except Exception as error:
            cleanup_errors.append(f"Runtime descendants: {error}")
        if cleanup_errors:
            results.update(status="failed", cleanup_errors=cleanup_errors)
        for log in log_handles:
            log.close()
        (report / "result.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
        print(f"Evidence: {report}", flush=True)
        if cleanup_errors and "error" not in results:
            raise RuntimeError("Smoke cleanup failed; see result.json")


def port_is_free():
    require_free_port()
    return True


if __name__ == "__main__":
    main()
