# Phase 2 Development — Claude Code Task Prompt

## Project Context

We are building an Android device redeployment automation system. The full
project is split into four contract phases; this task covers **Phase 2 only**:
**Initialization → APN Setup**.

Phase 2's job: take an Android device from its current state to fully reset,
connected to Wi-Fi, with mobile APN configured — and report progress into an
orchestration layer that can eventually run many devices in parallel. Phase 2
also builds the orchestration *skeleton* (state tracking, retry queue) that a
later Phase 3 will extend with login/app-install logic — but Phase 3's own
logic is explicitly **out of scope** for this task.

**Target devices** (four models, two manufacturers — expect UI differences
between them):
- Xperia Ace III (SOG08), Sony, Android 13
- Xperia 10 IV (SOG07), Sony, Android 14
- AQUOS sense6s (SHG07), SHARP, Android 13
- AQUOS sense7 (SHG10), SHARP, Android 12

**Target throughput** (informs later scaling, not this task): 200 devices/hour.

**Language**: Python 3.10+. Only external dependency needed for this phase:
`pyyaml`. Everything else (subprocess for ADB, `xml.etree.ElementTree` for
UI-dump parsing, `concurrent.futures` for parallel dispatch) is stdlib —
do not add dependencies beyond `pyyaml` without a clear reason.

## Working Environment — Important Constraint

This repository is being developed **locally, without a physical Android
device or `adb` attached**. The real devices and `adb` live on a separate,
remote client PC accessed later via AnyDesk. That means:

- All code must be written and unit-tested against a **fake/mock ADB layer**,
  not a real device.
- Do not assume `adb` is installed or a device is connected. Any code path
  that shells out to `adb` must be isolated behind the `AdbClient` interface
  (see below) so it can be swapped for a fake implementation in tests.
- Where real hardware data is genuinely required (e.g. actual UI
  `resource-id` values from a real device), use clearly-marked placeholder
  values and leave a `# TODO(real-device): replace with captured resource-id`
  comment rather than inventing a plausible-looking fake value. Ask me for
  the real value instead of guessing if it's blocking and I haven't supplied
  it yet.

### Two-Stage Completion — No Real Dump Files Available Yet

I do not have real `uiautomator dump` XML captures from actual hardware yet.
This project should still be carried as far as possible without them, in two
stages:

**Stage A (do this now):** Build and fully test everything using
**hand-written fixture XML** that faithfully follows the real
`uiautomator dump` schema (`<hierarchy><node resource-id="..."
bounds="[x1,y1][x2,y2]" text="..." class="..." .../></hierarchy>`), even
though the specific resource-id strings and screen content in the fixtures
are invented. This format is a stable, documented Android platform format —
it does not vary by manufacturer — so code written and tested against a
correctly-shaped fixture is safe to trust structurally. What's still unknown
is only the *specific values* (which resource-id belongs to which button on
these particular models) and the *exact screen sequence* per model — not the
XML shape itself.

**Stage B (later, after I supply real dumps):** I will separately provide
real `uiautomator dump` XML files captured from actual devices. At that
point, replace the placeholder resource-ids in the model YAML files with
real values, add the real XML files as additional test fixtures alongside
the hand-written ones, and re-run the full test suite.

**Before finishing Stage A**, produce a file `PENDING_REAL_DEVICE_DATA.md` at
the repo root listing every placeholder value and every assumption that
still needs real-device confirmation, so Stage B can be picked up cleanly
without re-deriving what's outstanding. Group by model, and flag the
highest-priority item first (see the list-screen note below).

## Repository Structure to Create

```
device-redeployment/
├── config/
│   ├── models/
│   │   ├── sony_xperia_ace3.yaml
│   │   ├── sony_xperia_10iv.yaml
│   │   ├── sharp_aquos_sense6s.yaml
│   │   └── sharp_aquos_sense7.yaml
│   ├── network.yaml.example       # placeholder values — never commit real ones
│   └── settings.yaml
├── src/
│   ├── device/
│   │   ├── __init__.py
│   │   ├── adb_client.py
│   │   ├── ui_automator.py
│   │   └── model_profile.py
│   ├── phase2/
│   │   ├── __init__.py
│   │   ├── wizard_walkthrough.py
│   │   ├── wifi_setup.py
│   │   └── apn_setup.py
│   ├── orchestration/
│   │   ├── __init__.py
│   │   ├── slot.py
│   │   └── scheduler.py
│   └── main_phase2.py             # simple CLI entry point for manual testing
├── tests/
│   ├── fakes.py                   # FakeAdbClient and other test doubles
│   ├── test_model_profile.py
│   ├── test_ui_automator.py
│   ├── test_slot.py
│   └── test_scheduler.py
├── logs/                          # gitkeep only, actual logs gitignored
├── .gitignore                     # must exclude config/network.yaml, logs/*.log
└── requirements.txt                # just pyyaml (+ pytest for dev)
```

Create a `.gitignore` that excludes the real (non-`.example`) config files
containing secrets, `__pycache__/`, and `logs/*.log`.

## Naming Conventions (follow exactly)

- Files and functions: `snake_case` (e.g. `wizard_walkthrough.py`, `run_factory_reset()`)
- Classes: `PascalCase` (e.g. `Slot`, `ModelProfile`, `AdbClient`)
- Constants and enum values: `UPPER_SNAKE_CASE` (e.g. `MAX_RETRY`, `SlotState.INIT_APN`)
- Per-model config files: `config/models/<manufacturer>_<model_slug>.yaml`,
  all lowercase, underscores instead of spaces
- **One module = one responsibility.** `adb_client.py` never parses UI XML.
  `ui_automator.py` never knows about Wi-Fi/APN specifics. `wifi_setup.py`
  and `apn_setup.py` never issue raw ADB shell commands directly — they call
  into `adb_client.py` and `ui_automator.py` instead. Preserve this boundary;
  it's what keeps per-model debugging tractable later.

## Task 1 — Config Files

### 1a. `config/models/*.yaml` (all four)

Schema (use this exact shape):

```yaml
model: "Xperia Ace III"
model_number: "SOG08"
manufacturer: "Sony"
android_version: 13

wizard_steps:
  - screen: "language_select"
    resource_id: "com.google.android.setupwizard:id/next_button"
    action: "tap"
  - screen: "terms_of_service"
    resource_id: "com.android.setupwizard:id/accept_button"
    action: "tap"
  - screen: "skip_sim_check"
    resource_id: "com.android.setupwizard:id/skip_button"
    action: "tap"
    optional: true   # not every model shows this screen

wifi_settings:
  toggle_resource_id: "com.android.settings:id/wifi_toggle"
  network_list_resource_id: "com.android.settings:id/wifi_network_list"

apn_settings:
  menu_path:
    - "Settings"
    - "Network & internet"
    - "Mobile network"
    - "Access Point Names"
  name_field_resource_id: "com.android.phone:id/apn_name_edit"
  apn_field_resource_id: "com.android.phone:id/apn_apn_edit"
  save_button_resource_id: "com.android.phone:id/save"
```

Populate all four files with this structure. Use placeholder resource-ids
for now (mark with the TODO comment convention above) — I will supply real
captured values from `uiautomator dump` sessions on actual hardware and we'll
update these files then. Do not fabricate resource-ids as if they were real.

### 1b. `config/network.yaml.example` and `config/settings.yaml`

```yaml
# config/network.yaml.example
wifi:
  ssid: "<client-provided SSID>"
  password: "<client-provided password>"
apn:
  carrier: "<carrier name>"
  apn_name: "<APN value from client>"
  mcc: "<mobile country code>"
  mnc: "<mobile network code>"
```

```yaml
# config/settings.yaml
adb:
  platform_tools_path: "C:\\platform-tools"
retry:
  max_retries: 3
logging:
  level: "INFO"
  log_dir: "./logs"
```

## Task 2 — Device Control Modules (`src/device/`)

### `adb_client.py`

```python
class AdbClient:
    """Thin wrapper around the adb command-line tool for one device."""

    def __init__(self, serial: str, adb_path: str = "adb"):
        self.serial = serial
        self.adb_path = adb_path

    def shell(self, command: str, timeout: int = 30) -> str:
        """Run `adb -s <serial> shell <command>` and return stdout.
        Raise a clear, specific exception (define one, e.g. AdbCommandError)
        on non-zero exit or timeout — do not let subprocess exceptions leak
        out raw."""

    def install(self, apk_path: str) -> bool:
        """Install an APK; return True on success."""

    def is_connected(self) -> bool:
        """Return True if `adb devices` currently lists this serial as 'device'."""

    def push(self, local_path: str, remote_path: str) -> bool:
        """Push a local file to the device; return True on success."""

    def pull(self, remote_path: str, local_path: str) -> bool:
        """Pull a file from the device to local_path; return True on success."""
```

Implement this against real `subprocess` calls to `adb`. Also create an
**abstract base class or Protocol** that both `AdbClient` and the test double
in `tests/fakes.py` implement, so every other module depends on the
interface, not the concrete class — this is what lets us unit-test without
hardware.

### `ui_automator.py`

```python
def dump_ui(client: "AdbClientProtocol") -> str:
    """Run `uiautomator dump`, pull the resulting XML via the client, and
    return it as a string. Clean up the on-device temp file afterward."""

def find_resource_id(ui_xml: str, resource_id: str, *,
                      text: str | None = None,
                      index: int = 0) -> tuple[int, int] | None:
    """Parse the UI dump XML and return the (x, y) center of the matching
    node's 'bounds' attribute, or None if not found.

    IMPORTANT — do not assume resource_id is unique in the tree. List-type
    screens (e.g. the Wi-Fi network list referenced by
    wifi_settings.network_list_resource_id in the model config) very likely
    render multiple rows sharing the same resource-id, distinguished only by
    their 'text' (e.g. the SSID) or by position. This function must support:
      - matching by resource_id alone (returns the first/only match — fine
        for one-off elements like buttons)
      - matching by resource_id AND text (e.g. find the Wi-Fi row whose
        text equals a specific SSID)
      - matching by resource_id AND index (the Nth matching node, 0-based,
        for cases where text isn't a reliable discriminator)
    Raise a clear error (not a silent wrong match) if multiple nodes match
    resource_id and neither text nor index was given to disambiguate —
    silently tapping the wrong list row is worse than failing loudly."""

def tap_resource_id(client: "AdbClientProtocol", resource_id: str, *,
                     text: str | None = None, index: int = 0) -> bool:
    """Dump the UI, locate resource_id (optionally disambiguated by text or
    index — see find_resource_id), tap its center coordinates via
    `adb shell input tap x y`. Return False (not an exception) if the
    element is not present, so callers can treat an optional wizard step
    as a no-op rather than a hard failure."""

def inject_text(client: "AdbClientProtocol", text: str) -> bool:
    """Inject literal text via ADB Keyboard (assumes it's already installed
    and set as the active IME). Return True on success."""
```

### Fixture Requirements for Task 5 (Stage A)

When writing `tests/test_ui_automator.py`, hand-write at least two fixture
XML strings:
1. A simple screen with unique resource-ids (e.g. a wizard "Next" button) —
   tests the basic match-by-resource_id-alone path.
2. A **list-type screen with multiple nodes sharing one resource-id but
   different `text` values** (modeled on the Wi-Fi network list) — tests
   that matching by `text` and by `index` both work correctly, and that
   calling `find_resource_id()` with only `resource_id` (no `text`/`index`)
   on this fixture raises the disambiguation error rather than silently
   returning the first match. This second fixture is the more important of
   the two — it's standing in for the specific risk we've already identified
   before ever seeing a real device.

### `model_profile.py`

```python
class ModelProfile:
    """Loads and exposes one config/models/*.yaml file."""

    @classmethod
    def load(cls, path: str) -> "ModelProfile":
        """Parse the YAML file at `path` into a ModelProfile instance.
        Raise a clear error if required fields are missing."""

    def wizard_steps(self) -> list[dict]:
        """Return the ordered list of setup-wizard steps for this model."""

    def wifi_settings(self) -> dict:
        """Return the Wi-Fi-related resource-ids for this model."""

    def apn_settings(self) -> dict:
        """Return the resource-ids and menu path needed for APN entry."""

    @classmethod
    def load_all(cls, models_dir: str) -> dict[str, "ModelProfile"]:
        """Load every *.yaml in models_dir, keyed by model_number (e.g. 'SOG08')."""
```

## Task 3 — Phase 2 Automation (`src/phase2/`)

Each function should accept a connected `AdbClientProtocol` and a
`ModelProfile`, and use `device/ui_automator.py` for all screen interaction —
never call `client.shell("input tap ...")` directly from these modules.

```python
# wizard_walkthrough.py
def run_wizard(client: "AdbClientProtocol", profile: "ModelProfile") -> bool:
    """Walk through profile.wizard_steps() in order. For each step, call
    tap_resource_id(); if a step is marked optional and not found, continue;
    if a required step is not found after a short retry/backoff, return False."""

# wifi_setup.py
def connect_wifi(client: "AdbClientProtocol", profile: "ModelProfile",
                  ssid: str, password: str) -> bool:
    """Try `adb shell cmd wifi connect-network <ssid> wpa2 <password>` first
    (works on Android 10+ in many cases). If that fails or is unavailable,
    fall back to UI Automator against profile.wifi_settings() resource-ids.
    Return True once connected (poll `adb shell dumpsys wifi` or similar to
    confirm actual connection state, don't just assume the command succeeded)."""

# apn_setup.py
def configure_apn(client: "AdbClientProtocol", profile: "ModelProfile",
                   apn_name: str, mcc: str, mnc: str) -> bool:
    """Navigate profile.apn_settings()['menu_path'] via UI Automator, then
    use inject_text() (ADB Keyboard) to enter the APN name and value fields
    — never simulate individual keystrokes for this. Tap save. Return True
    on success."""
```

## Task 4 — Orchestration Skeleton (`src/orchestration/`)

### `slot.py`

```python
from enum import Enum, auto

class SlotState(Enum):
    IDLE = auto()
    INIT_APN = auto()
    LOGIN_INSTALL = auto()          # Phase 3 will implement this transition's
                                     # target logic — for Phase 2, treat reaching
                                     # this state as the success condition and stop.
    WAITING_FOR_HUMAN = auto()
    FAILED = auto()
    ESCALATED = auto()

class Slot:
    """Tracks one physical USB slot's device and its processing state."""

    def __init__(self, slot_id: str, client: "AdbClientProtocol",
                 max_retry: int = 3):
        self.slot_id = slot_id
        self.client = client
        self.state = SlotState.IDLE
        self.retry_count = 0
        self.max_retry = max_retry
        self.last_error: str | None = None

    def run_init_apn(self, profile: "ModelProfile", network_config: dict) -> bool:
        """Execute the Phase 2 flow (wizard, Wi-Fi, APN) for this slot's
        device via the phase2/ module functions. Update self.state as it
        progresses. Return True on success, False on failure (and set
        self.last_error with a human-readable reason)."""
```

### `scheduler.py`

```python
def run_phase2_batch(slots: list["Slot"], profile_map: dict,
                      network_config: dict, max_workers: int = 10) -> dict:
    """Dispatch run_init_apn() across all slots in parallel using
    concurrent.futures.ThreadPoolExecutor. For each slot: on failure,
    increment retry_count and retry up to max_retry, then mark ESCALATED
    and log it. Return a summary dict: {slot_id: final_state} for all slots.
    This function must not let one slot's exception crash the batch for
    other slots — catch and log per-slot, always."""
```

## Task 5 — Tests (`tests/`)

Create `tests/fakes.py` with a `FakeAdbClient` implementing the same
interface as `AdbClient`, configurable to return scripted responses
(including simulating a disconnect mid-sequence, and simulating a
`tap_resource_id` failure for a specific resource-id so we can test the
optional-step and retry logic).

Write and make passing:
- `test_model_profile.py` — loads each of the four real YAML files, asserts
  required fields are present and correctly typed.
- `test_ui_automator.py` — `find_resource_id()` against a saved sample UI-dump
  XML string (embed a realistic fixture in the test file), asserting correct
  coordinate extraction and correct `None` on no match.
- `test_slot.py` — `Slot.run_init_apn()` using `FakeAdbClient`, covering: full
  success path; a step failing then succeeding on retry; a step failing past
  `max_retry` resulting in `ESCALATED`.
- `test_scheduler.py` — `run_phase2_batch()` with 3+ fake slots, at least one
  configured to fail, confirming the batch completes and returns correct
  per-slot final states without one failure blocking the others.

Use `pytest`. Add it to `requirements.txt` as a dev dependency (comment it as
dev-only if you separate requirements files — either approach is fine, your
call).

## Task 6 — Manual Test Entry Point

Write `src/main_phase2.py` as a small CLI that:
1. Loads all model profiles from `config/models/`
2. Loads `config/network.yaml` (or `.example` if the real one doesn't exist —
   print a clear warning if falling back to the example)
3. Accepts a `--serial <adb_serial>` and `--model <model_number>` argument
4. Runs `Slot.run_init_apn()` for that one real device and prints the result

This is what I'll run manually against real hardware later — it doesn't need
to be fancy, just functional and clearly logged (use Python's `logging`
module per `config/settings.yaml`'s log level, not bare `print()`).

## Constraints — Do Not Do These

- Do not implement anything from Phase 3 (Google login, app installation,
  Managed Google Play enrollment, verification-screen detection). If you find
  yourself writing that logic, stop — it's out of scope for this task.
- Do not build the production dashboard (Section 22 of the spec). A minimal
  log/print output from `main_phase2.py` is sufficient for this phase's own
  testing.
- Do not hardcode any device-specific value (resource-id, screen sequence)
  directly in a `.py` file — it belongs in a model YAML.
- Do not commit `config/network.yaml` (only the `.example` version) or any
  file containing real credentials.
- Do not invent plausible-looking resource-id values and present them as if
  captured from a real device — use the TODO placeholder convention instead.

## Definition of Done for This Task (Stage A)

- All files in the repository structure above exist.
- `pytest` passes cleanly with no real device connected, using hand-written
  fixtures per the Task 5 fixture requirements above (including the
  list-screen disambiguation fixture).
- `python src/main_phase2.py --help` runs and shows usage without error.
- All four model YAML files parse successfully via `ModelProfile.load()`,
  with placeholder resource-ids clearly marked per the TODO convention.
- `find_resource_id()` / `tap_resource_id()` support disambiguation by
  `text` and `index`, and raise a clear error on ambiguous matches rather
  than guessing.
- Code follows the naming conventions and module-boundary rules above.
- `PENDING_REAL_DEVICE_DATA.md` exists at the repo root, listing every
  placeholder value and open assumption, grouped by model, with the
  Wi-Fi-list disambiguation question flagged as highest priority.
- A short `README.md` at the repo root explains: how to install dependencies,
  how to run the test suite, how to run `main_phase2.py` once real hardware
  and real config values are available, and a pointer to
  `PENDING_REAL_DEVICE_DATA.md` for what Stage B needs to complete.

## Stage B — Resuming After Real Dump Files Are Supplied

This section applies later, once I supply real `uiautomator dump` XML files
(via git, as additional files in the repo). When that happens:

1. Read `PENDING_REAL_DEVICE_DATA.md` first to see what was left outstanding.
2. For each supplied dump, extract the real resource-id values needed and
   update the corresponding model YAML file(s), removing the TODO markers
   for whichever entries are now resolved.
3. Add the real XML file(s) into `tests/fixtures/` alongside the Stage-A
   hand-written ones (keep both — the hand-written ones still validate the
   general parsing logic; the real ones validate against actual device
   output).
4. Re-run the full test suite and confirm everything still passes.
5. Update `PENDING_REAL_DEVICE_DATA.md` to remove resolved items, so it
   always reflects what's still actually outstanding.
6. Do not start Stage B work until real dump files are actually present in
   the repo — do not simulate this stage with invented data.

Work through the tasks in the order listed (1 → 6) for Stage A, and run the
test suite after completing each of Tasks 2-5 rather than only at the very
end, so issues surface close to where they're introduced. Stop after Stage A
is complete and `PENDING_REAL_DEVICE_DATA.md` is written — do not attempt
Stage B until I explicitly provide real dump files.
