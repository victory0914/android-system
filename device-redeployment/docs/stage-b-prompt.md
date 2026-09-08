# Stage B Prompt — device-redeployment

Copy everything below the line into your coding agent (Claude Code etc.),
running with the repo root as working directory.

**Before running:** copy the 4 XML dumps from the client PC
(`C:\scrcpy\dumps\`) into `tests/fixtures/` in the repo, and place the wizard
photos into `docs/screens/shg10/wizard/`. The agent cannot start without the
XML files present.

---

## Task: Stage B — resolve real device data

Repo root: `e:\Other-Task\SDO\android\coding\device-redeployment\`

Stage A is complete. All modules, config schema, and 30 passing tests exist
and are structurally correct. Your job is to replace placeholder
resource-ids with real values now that real device data is available, and to
implement the wizard walkthrough using text matching.

### Read these first, in this order

1. `docs/record.md` — the authoritative record of every real-device finding
   from the capture sessions. **Read this fully before writing any code.**
   The section "IMPLEMENTATION SPEC — wizard via text matching" is the
   specification for Task 3 below.
2. `PENDING_REAL_DEVICE_DATA.md` — the Stage A list of what was pending.
3. `README.md`, then the existing source under `src/`.

### Available real data

**UI dumps (real `uiautomator dump` output from SHG10, serial
352063910272451):**
- `tests/fixtures/wifi_list_SHG10.xml` — Wi-Fi network list screen
- `tests/fixtures/apn_entry_top_SHG10.xml` — APN edit form, scrolled to top
- `tests/fixtures/apn_entry_middle_SHG10.xml` — APN edit form, mid-scroll
- `tests/fixtures/apn_entry_bottom_SHG10.xml` — APN edit form, scrolled to
  bottom

Three APN dumps exist because the form is a scrollable/recycled view —
off-screen fields may be absent from the hierarchy until scrolled into view.
Check all three when resolving APN field ids.

**Wizard reference photos (no resource-ids — see constraint below):**
- `docs/screens/shg10/wizard/01_welcome.jpg` through `09_aquos_notify.jpg`

**Target config file:** `config/models/` — the SHG10 model YAML.

### Hard constraint on the wizard

There are **no XML dumps for the OOBE wizard screens and there never will
be**. `docs/record.md` documents four separate remote capture methods that
were tested and failed, and explains the structural reason: ADB
authorization is wiped by factory reset, and `uiautomator dump` requires ADB,
so ADB access and wizard visibility cannot coexist on these devices.

Do **not** attempt to work around this, invent wizard resource-ids, or write
code that assumes a wizard dump will arrive later. Wizard automation must be
built on visible text matching per the spec in `docs/record.md`.

---

## Task 1 — Wi-Fi (`src/phase2/wifi_setup.py`, model YAML)

Parse `tests/fixtures/wifi_list_SHG10.xml` and resolve the real resource-ids
for the Wi-Fi settings block in the model YAML. Replace the
`TODO(real-device)` placeholders with real values.

Then update `PENDING_REAL_DEVICE_DATA.md`: replace the hypothetical
disambiguation example with the real near-duplicate SSID pairs observed at
the client site — `ARIZASU-WiFi-6F_2.4GHz` / `ARIZASU-WiFi-6F_5G`, and
`SPWH_L13_72E834` / `SPWH_L13_72E834_5G`.

Add a test fixture built from the **real** XML that exercises the
`AmbiguousResourceIdError` path against these actual duplicate pairs, in
addition to the existing hand-written fixture.

Navigation path confirmed on this device (already in `docs/record.md`):
設定 → ネットワークとインターネット → Wi-Fi とモバイルネットワーク. The Wi-Fi
toggle must be ON before the SSID list renders at all — make sure the code
handles the toggle-off case rather than assuming a list is present.

## Task 2 — APN (`src/phase2/apn_setup.py`, model YAML)

Parse the three APN XML dumps and resolve the real resource-ids.

**Two open questions that these dumps should settle. Answer them from the XML
and report your findings:**

1. **Do MCC/MNC fields exist on this build?** The fields visible in the top
   portion were 名前 / APN / プロキシ / ポート / ユーザー名 / パスワード /
   サーバー / MMSC — no MCC/MNC. Search all three dumps. If MCC/MNC are
   genuinely absent, **delete `apn_settings.mcc_field_resource_id` and
   `apn_settings.mnc_field_resource_id` from the YAML schema** and simplify
   `configure_apn()`'s signature accordingly (it currently takes `mcc` and
   `mnc` parameters that would have nowhere to go). Update the tests to
   match. Do not leave dead parameters.
2. **Where is the Save action?** No save button was visible on the form. It
   may be in the ⋮ overflow menu (top-right) or triggered by the back arrow.
   Resolve `apn_settings.save_button_resource_id` from the dumps if possible;
   if the dumps don't contain it, say so explicitly rather than guessing, and
   leave it marked TODO.

Also note: the "add new APN" control is a **`+` icon with no visible text
label**, so `add_button_resource_id` must be resolved by resource-id —
`find_by_text` will not work for it.

Navigation path confirmed: 設定 → ネットワークとインターネット → Wi-Fi と
モバイルネットワーク → **gear icon next to the carrier name** → アクセス
ポイント名. Note this is reached via an icon, not a text menu item.

Carrier caution: this KDDI-branded unit had a **Rakuten** SIM installed. Do
not hardcode carrier assumptions based on model branding.

## Task 3 — Wizard (`src/phase2/wizard_walkthrough.py`, model YAML)

Implement per the "IMPLEMENTATION SPEC — wizard via text matching" section of
`docs/record.md`. That section contains the per-screen text table, a draft
YAML schema, and the design requirements. Follow it.

Key requirements, restated so they are not missed:

- **Screen-driven, not sequence-driven.** Identify the current screen by its
  visible text, then act. Do not assume fixed ordering — carrier and OTA
  screens appear conditionally.
- **Fail loudly on an unrecognized screen.** Log the screen's full text
  content so the label can be added to config. Never tap blindly.
- **Never tap `戻る` or `中断し、リマインダーを受け取る`.** These reverse or
  abort the flow. Exclude these strings explicitly from any matching.
- **`続行` appears on multiple screens.** Disambiguate by screen identifier;
  do not match it globally.
- **Two spinner screens need wait-for-disappear, not tap:** 「キャリア設定中」
  and 「スマートフォンを設定しています」.
- **Two button labels are unverified** (screens 「ようこそ」 and 「ソフトウェア
  更新について」 — not legible in the photos). Mark these
  `TODO(verify-on-device)` in the YAML. Do not invent plausible labels.
- The 「同意する」 screen is scrollable — the button may need a scroll before
  it is reachable.

Tag any best-guess value distinctly, e.g.
`TODO(real-device, best-guess-standard-id)`, so it is distinguishable from
verified values and from pure placeholders.

## Task 4 — Safety guard (`src/device/ui_automator.py`)

A live notification 「USBデバッグが接続されました — 無効にするにはここをタップ
してください」 sits in the notification shade during automation. A mistargeted
tap on it **disables USB debugging and permanently strands the device**
mid-run — a severe failure mode at 200 devices/hour.

Add an explicit guard so tap paths cannot hit this, and a regression test for
it.

## Task 5 — Device prep

`adb shell svc power stayon usb` prevents screen timeout while cabled.
Devices idling mid-workflow would otherwise sleep and interrupt UI
automation. Add this to device prep in the orchestration layer (or wherever
setup belongs given the existing structure).

---

## Rules

- **Do not invent data.** If a dump does not contain what you need, say so
  explicitly and leave the placeholder marked TODO. A clearly-flagged gap is
  correct; a plausible-looking guess is not.
- Keep the existing fail-loud philosophy (`AmbiguousResourceIdError`).
- All existing tests must still pass. Add tests for new behavior.
- Update `PENDING_REAL_DEVICE_DATA.md` to reflect what is now resolved and
  what remains.
- Only SHG10 data exists. The other three models (Xperia Ace III / SOG08,
  Xperia 10 IV / SOG07, AQUOS sense6s / SHG07) still have placeholders and
  are out of scope for this pass — leave them untouched and clearly pending.

## Report at the end

- Which resource-ids were resolved, per file.
- The MCC/MNC answer and what you changed as a result.
- The Save button answer.
- Anything you could not resolve, and why.
- Any place where you had to make a judgment call.
