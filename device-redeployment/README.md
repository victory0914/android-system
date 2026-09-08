# device-redeployment — Phase 2

Android device redeployment automation, Phase 2 only: **Initialization →
APN Setup**. Takes a device from its current state through the setup
wizard, onto Wi-Fi, with mobile APN configured, and reports progress into an
orchestration skeleton that a later Phase 3 will extend with login/app-install
logic (out of scope here — see `## Scope` below).

## Status: Stage B (partial — SHG10 only)

Stage A was developed **without a physical Android device or `adb`
attached**, entirely against a fake/mock ADB layer (`tests/fakes.FakeAdbClient`)
and hand-written fixture XML following the real `uiautomator dump` schema
structurally, with invented placeholder resource-ids everywhere.

Stage B (2026-09-08) resolved real data for **one** model — AQUOS sense7
(SHG10) — from actual `uiautomator dump` captures (`tests/fixtures/
*_SHG10.xml`) and a photographed factory-reset session for the wizard
screens (no dump is possible for wizard screens on any model — see
`docs/record.md`). The other three models (SOG08, SOG07, SHG07) are still
100% Stage A placeholders, untouched.

See **[docs/record.md](docs/record.md)** for the full real-device session
notes (test logs, navigation paths, capture methodology, why some things
couldn't be resolved) and **[PENDING_REAL_DEVICE_DATA.md](PENDING_REAL_DEVICE_DATA.md)**
for the checklist of what's resolved vs. still outstanding per model, with
the current highest-priority item (SHG10's APN Save action — genuinely
unresolved, not guessed) flagged first.

## Install dependencies

```bash
pip install -r requirements.txt
```

This installs `pyyaml` (runtime) and `pytest` (dev/test only).

## Run the test suite

```bash
pytest
```

All tests run against `tests/fakes.FakeAdbClient` and hand-written fixture
XML — no real device or `adb` binary required. `pytest.ini` adds the repo
root to `sys.path` so `src.*` imports resolve regardless of the working
directory pytest is invoked from.

## Run `main_phase2.py` (once real hardware and config values are available)

1. Copy `config/network.yaml.example` to `config/network.yaml` and fill in
   the real Wi-Fi SSID/password and carrier APN/MCC/MNC values.
   `config/network.yaml` is gitignored — never commit it.
2. Confirm `config/settings.yaml`'s `adb.platform_tools_path` points at a
   real `platform-tools` install, and that the target device shows up in
   `adb devices`.
3. Replace the placeholder resource-ids in the relevant `config/models/*.yaml`
   file with real values captured from a `uiautomator dump` on that model
   (see PENDING_REAL_DEVICE_DATA.md for what's outstanding, and the
   "Stage B" section of the original task prompt for the process).
4. Run:

   ```bash
   python src/main_phase2.py --serial <adb_serial> --model <model_number>
   ```

   e.g. `python src/main_phase2.py --serial R3CN123ABC --model SOG08`.
   Model numbers: `SOG08` (Xperia Ace III), `SOG07` (Xperia 10 IV), `SHG07`
   (AQUOS sense6s), `SHG10` (AQUOS sense7).

Logging goes to stdout and to `logs/main_phase2.log` (level controlled by
`config/settings.yaml`'s `logging.level`). Exit code is `0` on success
(device reached the `LOGIN_INSTALL` state — Phase 2's success condition;
Phase 3 will pick up from there) and `1` on failure.

## Repository layout

- `config/models/*.yaml` — one profile per target device model (wizard
  steps, Wi-Fi/APN resource-ids, APN menu path).
- `config/network.yaml.example` — template for the real (gitignored)
  `config/network.yaml`.
- `config/settings.yaml` — ADB path, retry count, logging config.
- `src/device/` — `AdbClient`/`AdbClientProtocol` (Task 2's hardware
  boundary), `ui_automator.py` (UI-dump parsing and tap/text-injection
  helpers), `model_profile.py` (loads/validates the model YAML files).
- `src/phase2/` — `wizard_walkthrough.py`, `wifi_setup.py`, `apn_setup.py`.
  These never call `client.shell(...)` directly for screen interaction —
  everything goes through `src/device/ui_automator.py`.
- `src/orchestration/` — `slot.py` (per-device state machine, plus
  device-prep like `svc power stayon usb`) and `scheduler.py` (parallel
  dispatch across slots, retry-then-escalate).
- `src/main_phase2.py` — the manual CLI entry point described above.
- `tests/` — `fakes.py` (`FakeAdbClient` test double), `tests/fixtures/` (real
  SHG10 `uiautomator dump` XML alongside hand-written Stage A fixtures), plus
  the test suite.
- `docs/record.md` — living notes from real-device capture sessions.
  `docs/screens/` — reference photos for wizard screens that can't be
  dumped (not test fixtures, nothing parses them).

Two wizard schemas coexist in `config/models/*.yaml`, both handled by
`wizard_walkthrough.py`: legacy sequence-driven `wizard_steps` (resource-id
based, still used by the 3 untouched models) and Stage B's screen-driven
`wizard` block (visible-text based, used by SHG10 — necessary because no
`uiautomator dump` is possible for wizard screens on any model). Similarly,
`apn_settings` supports both a legacy literal-resource-id-per-field shape
and SHG10's label-based shape (real captures showed APN fields share one
generic resource-id, disambiguated by their visible Japanese label).

## Scope

This task is Phase 2 only. Explicitly **not** implemented here (see the
original task prompt's "Constraints" section): Google login, app
installation, Managed Google Play enrollment, verification-screen detection
(all Phase 3), and the production orchestration dashboard — `main_phase2.py`
is a minimal CLI for manual testing, not that dashboard.
