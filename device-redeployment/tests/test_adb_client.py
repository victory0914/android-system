"""Tests for src/device/adb_client.py — regression tests for two real bugs
found running against actual hardware from a Japanese-locale Windows client
PC:

1. config/settings.yaml's adb.platform_tools_path is a *directory* (e.g.
   "C:\\platform-tools"), and passing that straight through as adb_path used
   to make every AdbClient call fail with OSError, silently swallowed into a
   plain `False` by is_connected() — indistinguishable from a genuinely
   disconnected device, even though `adb devices` worked fine in a normal
   shell. is_connected() now raises AdbCommandError for that case instead
   of returning False, so it reads as the config problem it actually is.

2. subprocess.run(..., text=True, ...) decodes stdout/stderr using the OS
   locale's codepage (cp932 on that Japanese-locale machine) rather than
   UTF-8, which is what adb's actual output uses. Real device output
   (Wi-Fi SSIDs, dumpsys strings) containing valid-UTF-8-but-invalid-cp932
   bytes crashed a background thread inside subprocess.run() itself —
   invisible to any try/except here — leaving stdout as None and surfacing
   downstream as a confusing "argument of type 'NoneType' is not
   iterable". Fixed by passing encoding="utf-8", errors="replace" explicitly.

These monkeypatch `subprocess.run` directly rather than using
tests.fakes.FakeAdbClient, since FakeAdbClient exists specifically to avoid
subprocess entirely — here we're testing AdbClient's own subprocess
invocation, not code that depends on the AdbClientProtocol interface.
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


def test_subprocess_run_uses_explicit_utf8_not_locale_default(monkeypatch):
    """Regression test for the real crash: subprocess.run() must be called
    with encoding="utf-8" (not text=True, which follows the OS locale's
    codepage) so device output containing non-cp932 bytes doesn't crash a
    background thread inside subprocess.run() itself."""
    captured_kwargs = {}

    def fake_run(args, **kwargs):
        captured_kwargs.update(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = AdbClient("XYZ123")
    client.shell("echo ok")

    assert captured_kwargs.get("encoding") == "utf-8"
    assert captured_kwargs.get("errors") == "replace"
    assert "text" not in captured_kwargs
