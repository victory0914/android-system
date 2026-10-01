"""Tests for src/device/device_logging.py — the shared per-device log
tagging helper. Real finding (2026-10-01): phase2/apn_setup.py and
phase2/wifi_setup.py's own log lines carried no identifying info at all,
which made an 11-device parallel batch run's failures untraceable
per-device once threads interleaved. See their own `_log(client)` wrappers
and docs/record.md, "Per-device log tagging"."""

import logging

from src.device.device_logging import tagged
from tests.fakes import FakeAdbClient


def test_tagged_prefixes_the_message_with_the_devices_serial(caplog):
    client = FakeAdbClient("ABC123")
    logger = logging.getLogger("test.device_logging")

    with caplog.at_level(logging.INFO, logger="test.device_logging"):
        tagged(logger, client).info("something happened")

    messages = [r.getMessage() for r in caplog.records]
    assert "device ABC123: something happened" in messages


def test_tagged_preserves_percent_style_format_args(caplog):
    client = FakeAdbClient("XYZ789")
    logger = logging.getLogger("test.device_logging")

    with caplog.at_level(logging.WARNING, logger="test.device_logging"):
        tagged(logger, client).warning("value was %r, expected %r", "a", "b")

    messages = [r.getMessage() for r in caplog.records]
    assert "device XYZ789: value was 'a', expected 'b'" in messages


def test_tagged_uses_a_different_prefix_per_device(caplog):
    logger = logging.getLogger("test.device_logging")

    with caplog.at_level(logging.INFO, logger="test.device_logging"):
        tagged(logger, FakeAdbClient("DEVICE-ONE")).info("hello")
        tagged(logger, FakeAdbClient("DEVICE-TWO")).info("hello")

    messages = [r.getMessage() for r in caplog.records]
    assert "device DEVICE-ONE: hello" in messages
    assert "device DEVICE-TWO: hello" in messages
