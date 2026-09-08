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

    def _run(self, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
        full_command = [self.adb_path, "-s", self.serial, *args]
        try:
            return subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdbCommandError(
                " ".join(full_command), f"timed out after {timeout}s"
            ) from exc
        except OSError as exc:
            # e.g. adb binary not found on PATH
            raise AdbCommandError(" ".join(full_command), str(exc)) from exc

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
        """Return True if `adb devices` currently lists this serial as 'device'."""
        try:
            result = subprocess.run(
                [self.adb_path, "devices"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return False
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
