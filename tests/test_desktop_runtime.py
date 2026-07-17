from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from app import desktop_runtime
from app.core.state_proto_contract import STATE_PROTO_PAYLOAD_FORMAT_VERSION


_JWT_SECRET = "desktop-test-secret-with-more-than-32-characters"
_RUNTIME_ENV_NAMES = (
    "DEPLOY_MODE",
    "ENVIRONMENT",
    "SCNGS_DATA_DIR",
    "DATABASE_URL",
    "JWT_SECRET_KEY",
)


@pytest.fixture(autouse=True)
def _restore_runtime_process_state():
    original_working_directory = Path.cwd()
    original_environment = {
        name: os.environ[name] if name in os.environ else None
        for name in _RUNTIME_ENV_NAMES
    }
    try:
        yield
    finally:
        os.chdir(original_working_directory)
        for name, value in original_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _configure_desktop_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    with_alembic: bool = False,
) -> tuple[Path, Path]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    runtime_root = tmp_path / "bundle"
    runtime_root.mkdir()
    if with_alembic:
        (runtime_root / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")

    monkeypatch.setenv("NOVWR_DESKTOP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("NOVWR_DESKTOP_JWT_SECRET", _JWT_SECRET)
    monkeypatch.setenv(
        "NOVWR_DESKTOP_SHUTDOWN_EVENT",
        "Local\\io.github.hurricane0698.novwr.test.shutdown",
    )
    monkeypatch.setattr(sys, "_MEIPASS", str(runtime_root), raising=False)
    state_proto_module = SimpleNamespace(
        payload_format_version=lambda: STATE_PROTO_PAYLOAD_FORMAT_VERSION
    )

    def import_module(name: str):
        if name != "_novwr_state_proto":
            raise AssertionError(f"Unexpected desktop runtime import: {name}")
        return state_proto_module

    monkeypatch.setattr(desktop_runtime, "import_module", import_module)
    return data_dir.resolve(), runtime_root.resolve()


@pytest.mark.parametrize(
    "argv",
    (
        [],
        ["unknown"],
        ["serve", "--port", "9000"],
        ["worker", "extra"],
    ),
)
def test_parser_rejects_missing_unknown_or_extra_arguments(argv: list[str]):
    parser = desktop_runtime.build_parser()
    assert parser.prog == "novwr-runtime"

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(argv)

    assert exc_info.value.code == 2


def test_runtime_requires_desktop_environment_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("NOVWR_DESKTOP_DATA_DIR", raising=False)
    monkeypatch.delenv("NOVWR_DESKTOP_JWT_SECRET", raising=False)

    with pytest.raises(
        desktop_runtime.DesktopRuntimeError, match="NOVWR_DESKTOP_DATA_DIR"
    ):
        desktop_runtime.main(["worker"])


def test_runtime_rejects_relative_or_missing_data_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("NOVWR_DESKTOP_JWT_SECRET", _JWT_SECRET)
    monkeypatch.setenv("NOVWR_DESKTOP_DATA_DIR", "relative-data")
    with pytest.raises(desktop_runtime.DesktopRuntimeError, match="absolute path"):
        desktop_runtime.main(["worker"])

    missing = tmp_path / "missing"
    monkeypatch.setenv("NOVWR_DESKTOP_DATA_DIR", str(missing))
    with pytest.raises(desktop_runtime.DesktopRuntimeError, match="does not exist"):
        desktop_runtime.main(["worker"])


@pytest.mark.parametrize(
    "secret",
    ("short", "CHANGE-ME-IN-PRODUCTION", "   "),
)
def test_runtime_rejects_insecure_desktop_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    secret: str,
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("NOVWR_DESKTOP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("NOVWR_DESKTOP_JWT_SECRET", secret)

    with pytest.raises(
        desktop_runtime.DesktopRuntimeError, match="NOVWR_DESKTOP_JWT_SECRET"
    ):
        desktop_runtime.main(["worker"])


def test_bootstrap_uses_bundled_alembic_config_and_existing_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    data_dir, runtime_root = _configure_desktop_environment(
        monkeypatch,
        tmp_path,
        with_alembic=True,
    )
    database_url = f"sqlite:///{(data_dir / 'novels.db').as_posix()}"
    engine = object()
    metadata = object()
    calls: list[dict[str, object]] = []

    database_module = ModuleType("app.database")
    database_module.Base = SimpleNamespace(metadata=metadata)
    database_module.engine = engine
    bootstrap_module = ModuleType("app.selfhost_db_bootstrap")

    def ensure_selfhost_database_ready(**kwargs):
        calls.append(kwargs)

    bootstrap_module.ensure_selfhost_database_ready = ensure_selfhost_database_ready
    monkeypatch.setitem(sys.modules, "app.database", database_module)
    monkeypatch.setitem(sys.modules, "app.selfhost_db_bootstrap", bootstrap_module)

    assert desktop_runtime.main(["bootstrap"]) == 0
    assert Path.cwd() == runtime_root
    assert os.environ["DEPLOY_MODE"] == "selfhost"
    assert os.environ["ENVIRONMENT"] == "desktop"
    assert os.environ["SCNGS_DATA_DIR"] == str(data_dir)
    assert os.environ["DATABASE_URL"] == database_url
    assert os.environ["JWT_SECRET_KEY"] == _JWT_SECRET
    assert calls == [
        {
            "db_engine": engine,
            "metadata": metadata,
            "db_url": database_url,
            "ini_path": runtime_root / "alembic.ini",
        }
    ]


def test_runtime_validates_packaged_state_proto_after_environment_setup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    data_dir, runtime_root = _configure_desktop_environment(monkeypatch, tmp_path)
    events: list[str] = []
    state_proto_module = SimpleNamespace(
        payload_format_version=lambda: (
            events.append("payload-version") or STATE_PROTO_PAYLOAD_FORMAT_VERSION
        )
    )

    def import_module(name: str):
        assert name == "_novwr_state_proto"
        assert Path.cwd() == runtime_root
        assert os.environ["SCNGS_DATA_DIR"] == str(data_dir)
        events.append("import")
        return state_proto_module

    monkeypatch.setattr(desktop_runtime, "import_module", import_module)
    stop_event = threading.Event()
    monkeypatch.setattr(
        desktop_runtime,
        "_open_desktop_shutdown_event",
        lambda: stop_event,
    )
    worker_module = ModuleType("app.workers.background_jobs")
    worker_module.run_worker_loop = lambda *, once, stop_event: (
        events.append(("worker", once, stop_event)) or 0
    )
    monkeypatch.setitem(sys.modules, "app.workers.background_jobs", worker_module)

    assert desktop_runtime.main(["worker"]) == 0
    assert events == [
        "import",
        "payload-version",
        ("worker", False, stop_event),
    ]


@pytest.mark.parametrize("failure", (ImportError("missing"), ValueError("invalid")))
def test_runtime_rejects_missing_or_invalid_packaged_state_proto(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: Exception,
):
    _configure_desktop_environment(monkeypatch, tmp_path)

    def import_module(_name: str):
        raise failure

    monkeypatch.setattr(desktop_runtime, "import_module", import_module)

    with pytest.raises(
        desktop_runtime.DesktopRuntimeError,
        match="Bundled Rust state-proto extension is unavailable or invalid",
    ):
        desktop_runtime.main(["worker"])


@pytest.mark.parametrize(
    "payload_format_version",
    (
        STATE_PROTO_PAYLOAD_FORMAT_VERSION - 1,
        STATE_PROTO_PAYLOAD_FORMAT_VERSION + 1,
    ),
)
def test_runtime_rejects_mismatched_state_proto_payload_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload_format_version: int,
):
    _configure_desktop_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        desktop_runtime,
        "import_module",
        lambda _name: SimpleNamespace(
            payload_format_version=lambda: payload_format_version
        ),
    )

    with pytest.raises(
        desktop_runtime.DesktopRuntimeError,
        match="does not match required version",
    ):
        desktop_runtime.main(["worker"])


def test_bootstrap_fails_when_bundled_alembic_config_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    _configure_desktop_environment(monkeypatch, tmp_path)

    with pytest.raises(
        desktop_runtime.DesktopRuntimeError, match="Bundled Alembic config is missing"
    ):
        desktop_runtime.main(["bootstrap"])


def test_serve_checks_fixed_port_before_starting_single_uvicorn_worker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    _data_dir, runtime_root = _configure_desktop_environment(monkeypatch, tmp_path)
    events: list[object] = []
    uvicorn_module = ModuleType("uvicorn")
    stop_event = threading.Event()
    stop_event.set()

    class Config:
        def __init__(self, app: str, **kwargs):
            self.app = app
            self.kwargs = kwargs
            events.append(("config", app, kwargs, Path.cwd()))

    class Server:
        def __init__(self, config):
            self.config = config
            self.should_exit = False

        def run(self):
            deadline = time.monotonic() + 1
            while not self.should_exit and time.monotonic() < deadline:
                time.sleep(0.001)
            assert self.should_exit
            events.append("server-stopped")

    uvicorn_module.Config = Config
    uvicorn_module.Server = Server
    monkeypatch.setattr(
        desktop_runtime,
        "_require_desktop_port_available",
        lambda: events.append("port-check"),
    )
    monkeypatch.setattr(
        desktop_runtime,
        "_open_desktop_shutdown_event",
        lambda: stop_event,
    )
    monkeypatch.setitem(sys.modules, "uvicorn", uvicorn_module)

    assert desktop_runtime.main(["serve"]) == 0
    assert events == [
        "port-check",
        (
            "config",
            "app.main:app",
            {
                "host": "127.0.0.1",
                "port": 8000,
                "workers": 1,
                "reload": False,
            },
            runtime_root,
        ),
        "server-stopped",
    ]


def test_port_conflict_fails_before_uvicorn_import(monkeypatch: pytest.MonkeyPatch):
    bound_addresses: list[tuple[str, int]] = []

    class ConflictingSocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def setsockopt(self, *args):
            return None

        def bind(self, address: tuple[str, int]):
            bound_addresses.append(address)
            raise OSError("address already in use")

    monkeypatch.setattr(socket, "socket", lambda *args: ConflictingSocket())

    with pytest.raises(desktop_runtime.DesktopRuntimeError, match="127.0.0.1:8000"):
        desktop_runtime._run_serve()

    assert bound_addresses == [("127.0.0.1", 8000)]


def test_worker_reuses_existing_worker_loop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    data_dir, runtime_root = _configure_desktop_environment(monkeypatch, tmp_path)
    worker_module = ModuleType("app.workers.background_jobs")
    stop_event = threading.Event()
    calls: list[tuple[bool, threading.Event]] = []

    def run_worker_loop(*, once: bool, stop_event: threading.Event):
        calls.append((once, stop_event))
        assert Path.cwd() == runtime_root
        assert os.environ["SCNGS_DATA_DIR"] == str(data_dir)
        return 7

    worker_module.run_worker_loop = run_worker_loop
    monkeypatch.setitem(sys.modules, "app.workers.background_jobs", worker_module)
    monkeypatch.setattr(
        desktop_runtime,
        "_open_desktop_shutdown_event",
        lambda: stop_event,
    )

    assert desktop_runtime.main(["worker"]) == 7
    assert calls == [(False, stop_event)]


def test_windows_shutdown_event_bridge_sets_and_closes_local_event(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(
        "NOVWR_DESKTOP_SHUTDOWN_EVENT",
        "Local\\io.github.hurricane0698.novwr.test.shutdown",
    )

    class FakeKernel32:
        def __init__(self):
            self.native_event = threading.Event()
            self.closed = threading.Event()
            self.opened: tuple[int, bool, str] | None = None

        def OpenEventW(self, access: int, inherit: bool, name: str):
            self.opened = (access, inherit, name)
            return 123

        def WaitForSingleObject(self, handle: int, timeout: int):
            assert handle == 123
            assert timeout == desktop_runtime._INFINITE
            assert self.native_event.wait(1)
            return desktop_runtime._WAIT_OBJECT_0

        def CloseHandle(self, handle: int):
            assert handle == 123
            self.closed.set()
            return True

    kernel32 = FakeKernel32()
    stop_event = desktop_runtime._open_desktop_shutdown_event(kernel32=kernel32)

    assert not stop_event.is_set()
    kernel32.native_event.set()
    assert stop_event.wait(1)
    assert kernel32.closed.wait(1)
    assert kernel32.opened == (
        desktop_runtime._SYNCHRONIZE,
        False,
        "Local\\io.github.hurricane0698.novwr.test.shutdown",
    )
