from __future__ import annotations

import argparse
from importlib import import_module
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


_DATA_DIR_ENV = "NOVWR_DESKTOP_DATA_DIR"
_JWT_SECRET_ENV = "NOVWR_DESKTOP_JWT_SECRET"
_DATABASE_FILE_NAME = "novels.db"
_HOST = "127.0.0.1"
_PORT = 8000
_MINIMUM_JWT_SECRET_LENGTH = 32
_INSECURE_JWT_SECRETS = {"CHANGE-ME-IN-PRODUCTION"}


class DesktopRuntimeError(RuntimeError):
    """Raised when the packaged desktop runtime contract is invalid."""


@dataclass(frozen=True)
class DesktopRuntimeContext:
    data_dir: Path
    database_url: str
    runtime_root: Path

    @property
    def alembic_ini(self) -> Path:
        return self.runtime_root / "alembic.ini"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novwr-runtime",
        description="Internal NovWr Windows desktop runtime.",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("bootstrap", "serve", "worker"):
        subparsers.add_parser(command, allow_abbrev=False)
    return parser


def _required_environment_value(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise DesktopRuntimeError(
            f"Required environment variable {name} is missing or empty."
        )
    return value.strip()


def _load_data_dir() -> Path:
    configured = Path(_required_environment_value(_DATA_DIR_ENV)).expanduser()
    if not configured.is_absolute():
        raise DesktopRuntimeError(
            f"{_DATA_DIR_ENV} must be an absolute path: {configured}"
        )
    try:
        data_dir = configured.resolve(strict=True)
    except OSError as exc:
        raise DesktopRuntimeError(
            f"{_DATA_DIR_ENV} does not exist: {configured}"
        ) from exc
    if not data_dir.is_dir():
        raise DesktopRuntimeError(f"{_DATA_DIR_ENV} is not a directory: {data_dir}")

    database_path = data_dir / _DATABASE_FILE_NAME
    if database_path.exists() and not database_path.is_file():
        raise DesktopRuntimeError(
            f"Desktop database path is not a file: {database_path}"
        )
    return data_dir


def _load_jwt_secret() -> str:
    secret = _required_environment_value(_JWT_SECRET_ENV)
    if secret in _INSECURE_JWT_SECRETS or len(secret) < _MINIMUM_JWT_SECRET_LENGTH:
        raise DesktopRuntimeError(
            f"{_JWT_SECRET_ENV} must contain a non-default secret of at least "
            f"{_MINIMUM_JWT_SECRET_LENGTH} characters."
        )
    return secret


def _database_url(data_dir: Path) -> str:
    return f"sqlite:///{(data_dir / _DATABASE_FILE_NAME).as_posix()}"


def _runtime_root() -> Path:
    packaged_root = getattr(sys, "_MEIPASS", None)
    candidate = (
        Path(packaged_root)
        if packaged_root is not None
        else Path(__file__).resolve().parents[1]
    )
    try:
        runtime_root = candidate.resolve(strict=True)
    except OSError as exc:
        raise DesktopRuntimeError(
            f"Desktop runtime root does not exist: {candidate}"
        ) from exc
    if not runtime_root.is_dir():
        raise DesktopRuntimeError(
            f"Desktop runtime root is not a directory: {runtime_root}"
        )
    return runtime_root


def _validate_state_proto_runtime() -> None:
    from app.core.state_proto_contract import STATE_PROTO_PAYLOAD_FORMAT_VERSION

    try:
        state_proto = import_module("_novwr_state_proto")
        payload_format_version = int(state_proto.payload_format_version())
    except Exception as exc:
        raise DesktopRuntimeError(
            "Bundled Rust state-proto extension is unavailable or invalid."
        ) from exc
    if payload_format_version != STATE_PROTO_PAYLOAD_FORMAT_VERSION:
        raise DesktopRuntimeError(
            "Bundled Rust state-proto extension payload format version "
            f"{payload_format_version} does not match required version "
            f"{STATE_PROTO_PAYLOAD_FORMAT_VERSION}."
        )


def _prepare_runtime() -> DesktopRuntimeContext:
    data_dir = _load_data_dir()
    jwt_secret = _load_jwt_secret()
    database_url = _database_url(data_dir)

    os.environ["DEPLOY_MODE"] = "selfhost"
    os.environ["ENVIRONMENT"] = "desktop"
    os.environ["SCNGS_DATA_DIR"] = str(data_dir)
    os.environ["DATABASE_URL"] = database_url
    os.environ["JWT_SECRET_KEY"] = jwt_secret

    runtime_root = _runtime_root()
    os.chdir(runtime_root)
    _validate_state_proto_runtime()
    return DesktopRuntimeContext(
        data_dir=data_dir,
        database_url=database_url,
        runtime_root=runtime_root,
    )


def _run_bootstrap(context: DesktopRuntimeContext) -> int:
    if not context.alembic_ini.is_file():
        raise DesktopRuntimeError(
            f"Bundled Alembic config is missing: {context.alembic_ini}"
        )

    from app.database import Base, engine
    from app.selfhost_db_bootstrap import ensure_selfhost_database_ready

    ensure_selfhost_database_ready(
        db_engine=engine,
        metadata=Base.metadata,
        db_url=context.database_url,
        ini_path=context.alembic_ini,
    )
    return 0


def _require_desktop_port_available() -> None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind((_HOST, _PORT))
    except OSError as exc:
        raise DesktopRuntimeError(
            f"Desktop server address {_HOST}:{_PORT} is unavailable."
        ) from exc


def _run_serve() -> int:
    _require_desktop_port_available()

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=_HOST,
        port=_PORT,
        workers=1,
        reload=False,
    )
    return 0


def _run_worker() -> int:
    from app.workers.background_jobs import run_worker_loop

    return run_worker_loop(once=False)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    context = _prepare_runtime()

    if args.command == "bootstrap":
        return _run_bootstrap(context)
    if args.command == "serve":
        return _run_serve()
    if args.command == "worker":
        return _run_worker()
    raise DesktopRuntimeError(f"Unsupported desktop runtime command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
