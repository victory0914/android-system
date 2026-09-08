"""Tests for src/device/adb_client.py — in particular the error-handling
path fixed after a real client-PC run: config/settings.yaml's
adb.platform_tools_path is a *directory* (e.g. "C:\\platform-tools"), and
passing that straight through as adb_path used to make every AdbClient call
fail with OSError, silently swallowed into a plain `False` by
is_connected() — indistinguishable from a genuinely disconnected device,
even though `adb devices` worked fine in a normal shell. is_connected() now
raises AdbCommandError for that case instead of returning False, so it
reads as the config problem it actually is.

These monkeypatch `subprocess.run` directly rather than using
tests.fakes.FakeAdbClient, since FakeAdbClient exists specifically to avoid
subprocess entirely — here we're testing AdbClient's own subprocess
error-handling, not code that depends on the AdbClientProtocol interface.
"""

import subprocess

import pytest

from src.device.adb_client import AdbClient, AdbCommandError


def test_is_connected_true_when_serial_listed(monkeypatch):
    def fake_run(args, **kwargs):
        assert args == ["adb", "devices"]
        return subprocess.CompletedProcess(args, 0, stdout="XYZ123\tdevice\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = AdbClient("XYZ123")
    assert client.is_connected() is True


def test_is_connected_false_when_serial_not_listed(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="OTHER456\tdevice\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = AdbClient("XYZ123")
    assert client.is_connected() is False


def test_is_connected_raises_clear_error_when_adb_path_is_a_directory(monkeypatch):
    """Regression test for the real bug: adb_path pointing at a directory
    (not the adb executable) used to silently return False. It must now
    raise AdbCommandError so the failure is distinguishable from a real
    disconnected device."""

    def fake_run(args, **kwargs):
        raise OSError("[WinError 5] Access is denied")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = AdbClient("XYZ123", adb_path="C:\\platform-tools")

    with pytest.raises(AdbCommandError) as exc_info:
        client.is_connected()
    message = str(exc_info.value)
    assert "platform-tools" in message
    assert "adb_path" in message


def test_is_connected_raises_on_timeout(monkeypatch):
    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=10)

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = AdbClient("XYZ123")

    with pytest.raises(AdbCommandError):
        client.is_connected()


def test_shell_still_uses_serial_prefix(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = AdbClient("XYZ123", adb_path="adb")

    result = client.shell("echo ok")

    assert result == "ok\n"
    assert calls[0] == ["adb", "-s", "XYZ123", "shell", "echo ok"]


def test_shell_raises_on_nonzero_exit(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="permission denied")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = AdbClient("XYZ123")

    with pytest.raises(AdbCommandError):
        client.shell("some command")
