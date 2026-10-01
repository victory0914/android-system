"""Shared helper for tagging log lines with the device serial they came
from.

Real finding (2026-10-01): phase2/apn_setup.py and phase2/wifi_setup.py's
own log lines carried no identifying information at all — in an 11-device
parallel batch run, once several devices' threads started failing and
interleaving their output, it became impossible to tell which log line
belonged to which device, which blocked diagnosing a real failure (see
docs/record.md, "Per-device log tagging"). src/orchestration/slot.py's own
log lines already include `slot_id`; this gives phase2/*.py the same
traceability, using the serial every function there already has via its
`client` parameter — no new plumbing needed, just this one call wrapping
the existing module-level `logger`.
"""

from __future__ import annotations

import logging

from src.device.adb_client import AdbClientProtocol


class _SerialLoggerAdapter(logging.LoggerAdapter):
    """Prefixes every message logged through it with 'device <serial>: ',
    leaving the underlying logger/handlers/formatters untouched — no global
    logging config changes needed for this to work."""

    def process(self, msg, kwargs):
        return f"device {self.extra['serial']}: {msg}", kwargs


def tagged(logger: logging.Logger, client: AdbClientProtocol) -> logging.LoggerAdapter:
    """Return a LoggerAdapter that prefixes every message logged through it
    with `client`'s adb serial, so multi-device parallel runs stay
    traceable per-device in the log file no matter how many threads'
    output interleaves."""
    return _SerialLoggerAdapter(logger, {"serial": client.serial})
