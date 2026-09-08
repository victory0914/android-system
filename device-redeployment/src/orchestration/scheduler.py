"""Dispatches Slot.run_init_apn() across many slots in parallel.

This is the orchestration *skeleton* for Phase 2 — enough state tracking and
retry-queue behavior to prove the pattern out. Phase 3 will build on top of
it once slots reach SlotState.LOGIN_INSTALL; that logic is out of scope here.
"""

from __future__ import annotations

import concurrent.futures
import logging

from src.device.model_profile import ModelProfile
from src.orchestration.slot import Slot, SlotState

logger = logging.getLogger(__name__)

DEFAULT_MAX_WORKERS = 10


def run_slot_with_retries(
    slot: Slot, profile: ModelProfile, network_config: dict, *, skip_wizard: bool = False
) -> SlotState:
    """Run one slot to completion: call Slot.run_init_apn() and, on failure,
    increment slot.retry_count and retry up to slot.max_retry, then mark
    ESCALATED and log it. Never lets an exception escape — callers
    (run_phase2_batch, or a test driving a single slot directly) rely on
    this to keep one bad slot from taking down anything else.

    `skip_wizard` is forwarded to Slot.run_init_apn() — see its docstring.
    Only main_phase2.py's `--skip-wizard` flag sets this; run_phase2_batch()
    has no equivalent parameter on purpose, so it can never reach a
    production batch run by accident.
    """
    while True:
        try:
            success = slot.run_init_apn(profile, network_config, skip_wizard=skip_wizard)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: one slot
            # must never crash the batch for the others.
            success = False
            slot.state = SlotState.FAILED
            slot.last_error = f"unexpected exception: {exc}"
            logger.exception("slot %s: unexpected exception in run_init_apn", slot.slot_id)

        if success:
            return slot.state

        slot.retry_count += 1
        if slot.retry_count > slot.max_retry:
            slot.state = SlotState.ESCALATED
            logger.error(
                "slot %s: exceeded max_retry (%d); escalating. last_error=%s",
                slot.slot_id, slot.max_retry, slot.last_error,
            )
            return slot.state

        logger.warning(
            "slot %s: attempt failed (retry %d/%d): %s",
            slot.slot_id, slot.retry_count, slot.max_retry, slot.last_error,
        )


def run_phase2_batch(
    slots: list[Slot],
    profile_map: dict,
    network_config: dict,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> dict:
    """Dispatch run_init_apn() across all slots in parallel using
    concurrent.futures.ThreadPoolExecutor. For each slot: on failure,
    increment retry_count and retry up to max_retry, then mark ESCALATED
    and log it. Return a summary dict: {slot_id: final_state} for all slots.

    `profile_map` is keyed by slot_id (dict[str, ModelProfile]) — Slot
    itself doesn't carry a model_number, so which model profile applies to
    which physical slot is external information the caller must supply.

    This function must not let one slot's exception crash the batch for
    other slots — catch and log per-slot, always.
    """
    results: dict[str, SlotState] = {}

    def _worker(slot: Slot) -> SlotState:
        profile = profile_map.get(slot.slot_id)
        if profile is None:
            slot.state = SlotState.ESCALATED
            slot.last_error = f"no ModelProfile provided for slot {slot.slot_id!r} in profile_map"
            logger.error("slot %s: %s", slot.slot_id, slot.last_error)
            return slot.state
        return run_slot_with_retries(slot, profile, network_config)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_slot = {executor.submit(_worker, slot): slot for slot in slots}
        for future in concurrent.futures.as_completed(future_to_slot):
            slot = future_to_slot[future]
            try:
                final_state = future.result()
            except Exception as exc:  # noqa: BLE001 - belt-and-suspenders; the
                # worker function already catches broadly, but guard here too
                # so a failure in the executor plumbing itself can't crash
                # the batch either.
                slot.state = SlotState.ESCALATED
                slot.last_error = f"scheduler-level exception: {exc}"
                logger.exception("slot %s: exception escaped worker function", slot.slot_id)
                final_state = slot.state
            results[slot.slot_id] = final_state

    return results
