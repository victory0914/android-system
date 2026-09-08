"""Thin wrapper around the `adb` command-line tool for one device.

This module is the *only* place in the codebase allowed to shell out to
`adb` directly. Every other module (ui_automator.py, phase2/*, orchestration/*)
depends on the `AdbClientProtocol` interface defined here, never on
subprocess or the `AdbClient` concrete class directly — that's what lets the
whole system be unit-tested with `tests/fakes.FakeAdbClient` without a real
device or `adb` binary present.
"""

from __future__ import annotations

import subprocess
from typing import Protocol, runtime_checkable


class AdbCommandError(Exception):
    """Raised when an adb command fails (non-zero exit) or times out.

    Callers should catch this specific exception rather than letting raw
    subprocess exceptions (CalledProcessError, TimeoutExpired, etc.) leak
    out of this module.
    """

    def __init__(self, command: str, message: str, returncode: int | None = None):
        self.command = command
        self.returncode = returncode
        super().__init__(f"adb command failed: {command!r} - {message}")


@runtime_checkable
class AdbClientProtocol(Protocol):
    """Interface every module should depend on instead of the concrete
    AdbClient class. Implemented by both AdbClient (real subprocess calls)
    and tests.fakes.FakeAdbClient (scripted responses, no hardware/adb
    required)."""

    serial: str

    def shell(self, command: str, timeout: int = 30) -> str:
        ...

    def install(self, apk_path: str) -> bool:
        ...

    def is_connected(self) -> bool:
        """May raise AdbCommandError if adb itself can't be invoked at all
        (e.g. a misconfigured adb_path) — that's distinct from a normal
        False (adb ran fine, this serial just isn't listed)."""
        ...

    def push(self, local_path: str, remote_path: str) -> bool:
        ...

    def pull(self, remote_path: str, local_path: str) -> bool:
        ...


class AdbClient:
    """Thin wrapper around the adb command-line tool for one device."""

    def __init__(self, serial: str, adb_path: str = "adb"):
        self.serial = serial
        self.adb_path = adb_path

    def _run_raw(self, args: list[str], timeout: int) -> subprocess.CompletedProcess:
        """Run `adb <args>` with no `-s <serial>` prefix — some commands
        (like `devices`) are global, not per-device. Raises AdbCommandError
        if adb itself can't be executed at all (e.g. adb_path points at a
        directory instead of the actual executable — a real bug this
        guards against: that used to silently look identical to "device not
        connected" rather than the config problem it actually is), or on
        timeout. Non-zero exit is NOT an error here — callers interpret
        stdout/returncode themselves.

        Decodes stdout/stderr as UTF-8 explicitly (not `text=True`, which
        uses the OS locale's codepage — e.g. cp932 on a Japanese-locale
        Windows machine). `adb`'s actual output is UTF-8 regardless of host
        locale, and device data routinely contains non-ASCII text (Wi-Fi
        SSIDs, app names, `dumpsys` output echoing device-side strings).
        Under cp932 that used to crash inside a background thread
        subprocess.run() itself spawns, invisibly to any try/except here —
        the caller would just see `stdout=None` and a confusing downstream
        TypeError. `errors="replace"` trades perfect fidelity for never
        crashing the whole flow over one stray byte in output we're usually
        only substring/regex-matching anyway.
        """
        full_command = [self.adb_path, *args]
        try:
            return subprocess.run(
                full_command,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdbCommandError(
                " ".join(full_command), f"timed out after {timeout}s"
            ) from exc
        except OSError as exc:
            raise AdbCommandError(
                " ".join(full_command),
                f"could not execute adb at {self.adb_path!r}: {exc}. Is "
                "adb_path correct? (pointing at a directory instead of the "
                "adb executable itself is a common mistake — see "
                "config/settings.yaml's adb.platform_tools_path)",
            ) from exc

    def _run(self, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
        return self._run_raw(["-s", self.serial, *args], timeout)

    def shell(self, command: str, timeout: int = 30) -> str:
        """Run `adb -s <serial> shell <command>` and return stdout.

        Raises AdbCommandError on non-zero exit or timeout — subprocess
        exceptions never leak out of this method.
        """
        result = self._run(["shell", command], timeout=timeout)
        if result.returncode != 0:
            raise AdbCommandError(
                f"shell {command}", result.stderr.strip() or "non-zero exit",
                returncode=result.returncode,
            )
        return result.stdout

    def install(self, apk_path: str) -> bool:
        """Install an APK; return True on success."""
        try:
            result = self._run(["install", "-r", apk_path], timeout=120)
        except AdbCommandError:
            return False
        return result.returncode == 0 and "Success" in result.stdout

    def is_connected(self) -> bool:
        """Return True if `adb devices` currently lists this serial as
        'device'. Raises AdbCommandError if adb itself couldn't be run at
        all (bad adb_path, timeout) — that's a setup problem, not "device
        not connected", and callers/logs should be able to tell the
        difference rather than both looking like the same failure."""
        result = self._run_raw(["devices"], timeout=10)
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == self.serial and parts[1] == "device":
                return True
        return False

    def push(self, local_path: str, remote_path: str) -> bool:
        """Push a local file to the device; return True on success."""
        try:
            result = self._run(["push", local_path, remote_path], timeout=60)
        except AdbCommandError:
            return False
        return result.returncode == 0

    def pull(self, remote_path: str, local_path: str) -> bool:
        """Pull a file from the device to local_path; return True on success."""
        try:
            result = self._run(["pull", remote_path, local_path], timeout=60)
        except AdbCommandError:
            return False
        return result.returncode == 0
