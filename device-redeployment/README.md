# device-redeployment — Phase 2

Android device redeployment automation, Phase 2 only: **Wi-Fi → APN
Setup**, run against a device right after a factory reset + setup wizard.
Reports progress into an orchestration skeleton that a later Phase 3 will
extend with login/app-install logic (out of scope here — see `## Scope`
below).

## Status (2026-09-17): all four models confirmed working end-to-end on real hardware

- **SHG10** (AQUOS sense7) — confirmed 2026-09-11.
- **SHG07** (AQUOS sense6s) — confirmed 2026-09-15.
- **SOG07** (Xperia 10 IV) — confirmed 2026-09-17.
- **SOG08** (Xperia Ace III) — confirmed 2026-09-17.

**The setup wizard is permanently out of scope for this automation** —
client decision, 2026-09-17. A factory reset wipes ADB authorization, and
nothing restores it until a human completes the wizard and re-enables USB
debugging, so the wizard genuinely cannot be automated via ADB (see
`docs/record.md`'s "Wizard capture — RESOLVED AS NOT REMOTELY POSSIBLE").
The client performs factory reset + the wizard manually for every device;
this automation takes over from there via `--skip-wizard`, which is now
the standard way to invoke a real run, not a testing-only shortcut. Every
`wizard_steps`/`wizard` block still in `config/models/*.yaml` is inert,
kept only for documentation/history.

See **[docs/record.md](docs/record.md)** for the full real-device session
notes (test logs, navigation paths, capture methodology, every dead end
and why) and **[PENDING_REAL_DEVICE_DATA.md](PENDING_REAL_DEVICE_DATA.md)**
for the checklist of what's resolved vs. still outstanding per model.

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

## Run `main_phase2.py`

1. Copy `config/network.yaml.example` to `config/network.yaml` and fill in
   the real Wi-Fi SSID/password and carrier APN/MCC/MNC values.
   `config/network.yaml` is gitignored — never commit it. These values
   are shared across every device in a batch run by default — if one
   physical unit's actually-installed SIM needs different values (real
   finding, 2026-09-18: one unit's SIM had a different MNC than the rest
   of the batch, and Android silently rejected the APN save with no
   error), add a `device_overrides` entry for its serial; see the
   example file for the exact format.
2. Confirm `config/settings.yaml`'s `adb.platform_tools_path` points at a
   real `platform-tools` install.
3. **Factory reset the device and complete the setup wizard manually**,
   then enable USB debugging and connect it — this automation never
   touches the wizard (see `## Status` above for why). Confirm it shows up
   in `adb devices` before proceeding.
4. Run, with `--skip-wizard` (the standard flag for a real run — see
   `## Status` above). **The normal way to invoke this (2026-09-22): no
   `--device`/`--serial`/`--model` at all** — every connected, authorized
   device is auto-detected (`adb devices` + `getprop ro.product.model`,
   matched against `config/models/*.yaml`'s `model_number`s) and run in
   parallel automatically:

   ```bash
   python src/main_phase2.py --skip-wizard
   ```

   Connect whatever devices the client has plugged in (any mix of the 4
   known models) and run this one command — no need to look up or type a
   serial, and swapping in a different physical unit needs no command or
   code change. A device that isn't in `adb devices`' `device`
   (authorized/ready) state, or whose `getprop ro.product.model` doesn't
   match a known `model_number`, is logged clearly and skipped rather than
   guessed — see the log for `could not match to a known model profile`.

   `--serial`/`--model` (one specific device) and `--device SERIAL:MODEL`
   (repeatable, several specific devices) still work exactly as before, to
   override auto-detection for one or more devices — e.g. to force a
   device whose model auto-detection can't identify:

   ```bash
   python src/main_phase2.py --serial <adb_serial> --model <model_number> --skip-wizard
   # e.g.
   python src/main_phase2.py --serial HQ632M1012 --model SOG07 --skip-wizard
   ```

   Model numbers: `SOG08` (Xperia Ace III), `SOG07` (Xperia 10 IV), `SHG07`
   (AQUOS sense6s), `SHG10` (AQUOS sense7).

   Whether auto-detected or explicitly listed, all devices start at the
   same time (a thread per device) and run independently against the same
   `config/network.yaml` — one device's failure or retry never delays or
   blocks the others. Exit code is `1` if *any* device failed (including
   one auto-detection couldn't match); check the per-device
   `SUCCESS`/`FAILED` log lines for which one(s).

   `--max-retries N` overrides `config/settings.yaml`'s default (3) for
   this run only — e.g. `--max-retries 0` for a single attempt with no
   retries, useful while iterating on a specific, repeatable issue so an
   identical failure isn't repeated 3 times before you see the result.

Logging goes to stdout and to `logs/main_phase2.log` (level controlled by
`config/settings.yaml`'s `logging.level`). Exit code is `0` on success
(device reached the `LOGIN_INSTALL` state — Phase 2's success condition;
Phase 3 will pick up from there) and `1` on failure.

## Repository layout

- `config/models/*.yaml` — one profile per target device model (Wi-Fi/APN
  resource-ids, APN menu path, plus an inert `wizard_steps`/`wizard`
  block — see `## Status` above; kept for history, never exercised in a
  real `--skip-wizard` run).
- `config/network.yaml.example` — template for the real (gitignored)
  `config/network.yaml`.
- `config/settings.yaml` — ADB path, retry count, logging config.
- `src/device/` — `AdbClient`/`AdbClientProtocol` (Task 2's hardware
  boundary), `ui_automator.py` (UI-dump parsing and tap/text-injection
  helpers), `model_profile.py` (loads/validates the model YAML files).
- `src/phase2/` — `wizard_walkthrough.py` (unused in a real
  `--skip-wizard` run — see `## Status` above; kept working and tested,
  only reachable by explicitly omitting `--skip-wizard`), `wifi_setup.py`,
  `apn_setup.py`. These never call `client.shell(...)` directly for
  screen interaction — everything goes through
  `src/device/ui_automator.py`.
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
based) and Stage B's screen-driven `wizard` block (visible-text based, used
by SHG10 — necessary because no `uiautomator dump` is possible for wizard
screens on any model). Both are now inert in practice, since every real
run uses `--skip-wizard` (see `## Status` above). `apn_settings` supports
both a legacy literal-resource-id-per-field shape and the label-based
shape all four models actually use (real captures showed APN fields share
one generic resource-id, disambiguated by their visible Japanese label).

## Scope

This task is Phase 2 only. Explicitly **not** implemented here (see the
original task prompt's "Constraints" section): Google login, app
installation, Managed Google Play enrollment, verification-screen detection
(all Phase 3), and the production orchestration dashboard — `main_phase2.py`
is a minimal CLI for manual testing, not that dashboard.
