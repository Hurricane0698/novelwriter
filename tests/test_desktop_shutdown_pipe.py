"""The Unix guardian bridge uses real isolated descriptors, without a server."""

import os
import threading

import pytest

from app import desktop_runtime

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Unix pipe bridge")


@pytest.mark.parametrize("signal", [b"S", None])
def test_shutdown_pipe_signal_and_eof_set_existing_stop_contract(monkeypatch, signal):
    read_fd, write_fd = os.pipe()
    monkeypatch.setenv("NOVWR_DESKTOP_SHUTDOWN_FD", str(read_fd))
    event = desktop_runtime._open_desktop_shutdown_pipe()
    # The original inherited descriptor is transferred and closed; only a
    # non-inheritable private duplicate remains in the waiting daemon thread.
    with pytest.raises(OSError):
        os.fstat(read_fd)
    assert not event.is_set()
    try:
        if signal is None:
            os.close(write_fd)
            write_fd = None
        else:
            os.write(write_fd, b"?S")
        assert event.wait(1)
    finally:
        if write_fd is not None:
            os.close(write_fd)


@pytest.mark.parametrize("value", ["-1", "not-a-number", "9999999999"])
def test_shutdown_pipe_rejects_invalid_descriptor(monkeypatch, value):
    monkeypatch.setenv("NOVWR_DESKTOP_SHUTDOWN_FD", value)
    with pytest.raises(desktop_runtime.DesktopRuntimeError, match="read-only shutdown pipe"):
        desktop_runtime._open_desktop_shutdown_pipe()


def test_shutdown_pipe_rejects_regular_file_and_writer(monkeypatch, tmp_path):
    with (tmp_path / "ordinary-file").open("w+") as ordinary:
        monkeypatch.setenv("NOVWR_DESKTOP_SHUTDOWN_FD", str(ordinary.fileno()))
        with pytest.raises(desktop_runtime.DesktopRuntimeError, match="read-only shutdown pipe"):
            desktop_runtime._open_desktop_shutdown_pipe()
        ordinary.write("still owned by the caller")
    read_fd, write_fd = os.pipe()
    try:
        monkeypatch.setenv("NOVWR_DESKTOP_SHUTDOWN_FD", str(write_fd))
        with pytest.raises(desktop_runtime.DesktopRuntimeError, match="read-only shutdown pipe"):
            desktop_runtime._open_desktop_shutdown_pipe()
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_graceful_pipe_stop_finishes_current_work_before_exit(monkeypatch):
    read_fd, write_fd = os.pipe()
    monkeypatch.setenv("NOVWR_DESKTOP_SHUTDOWN_FD", str(read_fd))
    stop = desktop_runtime._open_desktop_shutdown_pipe()
    current_work = threading.Event()
    completed = []

    def worker():
        assert current_work.wait(1)
        completed.append("current job")
        assert stop.is_set()

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        os.write(write_fd, b"S")
        assert stop.wait(1)
        assert thread.is_alive()
        current_work.set()
        thread.join(1)
        assert completed == ["current job"]
    finally:
        current_work.set()
        thread.join(1)
        os.close(write_fd)
