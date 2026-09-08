"""Test doubles implementing AdbClientProtocol, for exercising phase2/ and
orchestration/ code without a real device or the `adb` binary."""

from __future__ import annotations

from src.device.adb_client import AdbCommandError


class FakeAdbClient:
    """A scripted stand-in for AdbClient, implementing AdbClientProtocol.

    Configuration knobs:
      - shell_responses: dict[str, str] — exact-match command -> stdout to
        return from shell(). Commands not present return "" by default.
      - shell_failures: set[str] — commands (exact match) that should raise
        AdbCommandError instead of returning normally.
      - ui_dumps: list[str] — successive XML strings to hand back from
        successive `uiautomator dump` calls (i.e. successive calls to
        shell("uiautomator dump ...")). Once exhausted, the last one repeats.
      - connected: bool — is_connected() return value; can be flipped mid-test
        to simulate a disconnect.
      - fail_taps_for: set[str] — resource_ids that ui_automator.tap_resource_id
        should report as "not found" for, by omitting them from the current
        ui_dump fixture (simplest way to script a tap failure is simply not
        including that resource-id in the scripted dump XML — this set exists
        for callers who want an explicit, self-documenting way to say "this
        tap should fail" without hand-crafting XML each time).
      - install_result / push_result / pull_result: bool — canned return
        values for those methods.
    """

    def __init__(
        self,
        serial: str = "FAKESERIAL",
        *,
        shell_responses: dict[str, str] | None = None,
        shell_failures: set[str] | None = None,
        ui_dumps: list[str] | None = None,
        connected: bool = True,
        fail_taps_for: set[str] | None = None,
        install_result: bool = True,
        push_result: bool = True,
        pull_result: bool = True,
    ):
        self.serial = serial
        self.shell_responses = shell_responses or {}
        self.shell_failures = shell_failures or set()
        self.ui_dumps = ui_dumps or ["<hierarchy></hierarchy>"]
        self._ui_dump_index = 0
        self.connected = connected
        self.fail_taps_for = fail_taps_for or set()
        self.install_result = install_result
        self.push_result = push_result
        self.pull_result = pull_result

        # Records of what was called, for assertions in tests.
        self.shell_calls: list[str] = []
        self.pulled_files: dict[str, str] = {}
        # Populated lazily by dump_ui() via pull(): remote_path -> xml text
        self._pending_dump_xml: str | None = None

    def shell(self, command: str, timeout: int = 30) -> str:
        self.shell_calls.append(command)

        if command in self.shell_failures:
            raise AdbCommandError(command, "simulated failure", returncode=1)

        if command.startswith("uiautomator dump"):
            # Stage the next scripted dump so the following pull() call
            # returns it.
            self._pending_dump_xml = self._next_ui_dump()
            return ""

        if command.startswith("rm -f"):
            return ""

        return self.shell_responses.get(command, "")

    def _next_ui_dump(self) -> str:
        xml = self.ui_dumps[min(self._ui_dump_index, len(self.ui_dumps) - 1)]
        self._ui_dump_index += 1
        return xml

    def install(self, apk_path: str) -> bool:
        return self.install_result

    def is_connected(self) -> bool:
        return self.connected

    def push(self, local_path: str, remote_path: str) -> bool:
        return self.push_result

    def pull(self, remote_path: str, local_path: str) -> bool:
        # Used by ui_automator.dump_ui(): write the staged XML to local_path
        # so the caller's subsequent file read gets it.
        xml = self._pending_dump_xml if self._pending_dump_xml is not None else self._next_ui_dump()
        with open(local_path, "w", encoding="utf-8") as fh:
            fh.write(xml)
        self.pulled_files[remote_path] = local_path
        return self.pull_result
