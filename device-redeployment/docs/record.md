# Record

Living notes file for findings from real-device connection sessions that are
relevant to the `device-redeployment` code/config (YAML schemas, automation
tap paths, wizard detection, orchestration assumptions, etc.).

**How to add to this file:**
- If the device model already has a section below, add a new dated bullet
  under the relevant category heading (or add a new category heading if none
  fits).
- If it's a new model, copy the "Template for a new device section" block at
  the bottom and fill it in.
- Each finding should note *why it matters* (which file/behavior it affects),
  not just the raw observation.

---

## SHG10 (SHARP AQUOS sense7, KDDI branding, Android 14)

**Serial:** 352063910272451
**Confirmed identity string (from adb):** `[SHARP] KDDI SHG10 (Android 14)`

### Test Log — exactly what was run against this unit

| Date | Test | Command | Result |
|---|---|---|---|
| 2026-09-04 | USB/ADB detection | `adb devices` | Device recognized: `352063910272451 device` |
| 2026-09-04 | scrcpy connect, default H.264 encoder | `scrcpy --render-driver=software -s 352063910272451 --ignore-video-encoder-constraints` | Encoder crashed (`MediaCodec` `IllegalArgumentException`/`CodecException`) at every attempted resolution during automatic downsize retry (1920→1600→1280→1024→800); server process killed, window stayed black |
| 2026-09-04 | List device video/audio encoders | `scrcpy --list-encoders -s 352063910272451` | Hardware: H.264 (`c2.qti.avc.encoder`), H.265 (`c2.qti.hevc.encoder`). AV1/VP8/VP9 software-only. Audio (opus/aac/flac) all software-only |
| 2026-09-04 | scrcpy connect, H.265 encoder (1st run) | `scrcpy --video-codec=h265 -s 352063910272451` | Succeeded after 2 automatic downsize retries (1920→1600→1280→1024), reached `Texture: 354x800`; screen visible briefly then went black (device screen timeout, not an encoder failure) |
| 2026-09-04 | scrcpy connect, H.265 encoder (2nd run) | `scrcpy --video-codec=h265 -s 352063910272451` | Succeeded immediately, no retries, full native resolution `Texture: 852x1920`; stable live mirroring confirmed (home screen visible and interactive) |
| 2026-09-04 | Wake device from screen-off | `adb -s 352063910272451 shell input keyevent 26` | Screen woke to swipe-unlock (no PIN/pattern) |
| 2026-09-08 | scrcpy connect, default H.264, **after factory reset** | `scrcpy --render-driver=software -s 352063910272451` | Reached `Texture: 852x1920` after only 1 initial error — far better than pre-reset behavior. H.264 may be usable post-reset; single observation only, not yet reproduced |
| 2026-09-08 | Verify ADB auth restored after client re-enabled USB debugging | `adb devices` | `352063910272451 device` — client's re-authorization successful |
| 2026-09-08 | Keep screen awake while cabled | `adb -s ... shell svc power stayon usb` | Worked; screen no longer times out during sessions |
| 2026-09-08 | Restore provisioning flags + reboot after destabilization | `settings put secure user_setup_complete 1` / `put global device_provisioned 1` / `reboot` | Device recovered fully; both flags read back `1`, no crash dialog, nav bar normal |

**Conclusion for this unit:** `--video-codec=h265` is the safe default —
H.264 failed completely pre-reset. Post-reset H.264 worked once, suggesting
the failure may be state-dependent rather than purely a hardware-encoder bug,
but this is a single observation. Keep using h265 unless further evidence
accumulates.

### Carrier / SIM — relevant to `apn_setup.py`, `PENDING_REAL_DEVICE_DATA.md`
- *2026-09-04:* Lock screen displayed **"Rakuten"** as the active carrier, not
  au/KDDI, despite the KDDI model branding (SHG10).
- Implication: do not assume model branding (KDDI) implies KDDI APN defaults
  — the SIM actually installed per device in the farm may not match the
  model's carrier branding. Confirm actual SIM/carrier per device before
  applying any APN default.

### First-run wizard — relevant to `wizard_walkthrough.py`
- *2026-09-04 (initial guess — SUPERSEDED, see below):* Notification shade
  showed a persistent **「セットアップを完了させて」(Complete Setup)** banner.
  Initially assumed to be the OOBE wizard entry point.
- *2026-09-04 (CORRECTED):* Tapping that banner opened a **「楽しいアプリを発見
  しましょう」(Discover fun apps)** Play Store promo screen — skip top-right,
  「続行」bottom. This is a **post-setup nudge, not the real SetupWizard.**
  This unit had already completed its OOBE long before (home screen, installed
  apps, configured SIM all present).
- Conclusion: the genuine OOBE wizard screens (language → terms → Wi-Fi →
  account) exist **only** in the window between a factory reset and first
  reaching a home screen. They cannot be reached on an already-provisioned
  device. Real dumps for `wizard_walkthrough.py` require a reset.
- Also seen in the shade: **「最新Androidへようこそ!」** and **「画面ロックを
  設定・1日」** — the latter independently confirms no screen lock is set on
  this unit (see Lock state below).

### UI hazard — relevant to tap-path safety in automation
- *2026-09-04:* Notification shade also showed a live **「USBデバッグが接続さ
  れました — 無効にするにはここをタップ」(USB debugging connected — tap here
  to disable)** affordance.
- Hazard: any `tap_by_text` / coordinate-based tap near this must not hit it —
  doing so would disable USB debugging and kill adb access to that device
  mid-run. Worth an explicit exclusion/guard in the tap-path logic, or at
  least a regression test case.

### Lock state — relevant to `model_profile.py` / orchestration pre-checks
- *2026-09-04:* Waking the device (`input keyevent 26`) showed an
  open-padlock swipe icon, not a PIN/pattern pad — this unit unlocks without
  credentials.
- Independently corroborated by the 「画面ロックを設定」 notification still
  pending in the shade.
- Confirms (for at least this unit) the assumption that devices in the farm
  can be unlocked without credential entry. Worth verifying this holds across
  all four models before relying on it in orchestration.

### Wi-Fi network list — relevant to `wifi_setup.py`, `ui_automator.py`
- *2026-09-04:* Navigation path confirmed on this SHARP skin:
  **設定 → ネットワークとインターネット → Wi-Fi とモバイルネットワーク**.
  Wi-Fi toggle must be switched ON before the SSID list renders at all.
- Real SSIDs visible at the client site, including **near-duplicate pairs**:
  `ARIZASU-WiFi-6F_2.4GHz` / `ARIZASU-WiFi-6F_5G`, and
  `SPWH_L13_72E834` / `SPWH_L13_72E834_5G`. Others: `HR02b-BA15BA`,
  `earth2.4_6`, `earth5_1`.
- Implication: these are concrete real-world cases for the
  `AmbiguousResourceIdError` / text-disambiguation logic — replace the
  hypothetical example in `PENDING_REAL_DEVICE_DATA.md` with these.
- Note: the PC's own active network is `earth5_6` (Windows classifies it as
  a **Public** network — see Windows environment section below).
- *2026-09-08:* Client supplied real credentials for one of the above:
  `earth5_1` / `earth5_1` (SSID/password identical). Set in
  `config/network.yaml` (gitignored, local to the client PC).
- *2026-09-08:* First live test with real credentials — the shell path
  (`cmd wifi connect-network`) confirmed blocked by the same
  `SecurityException` as every prior attempt (shell user, uid 2000, lacks
  the wifi permission on this build). The UI fallback correctly navigated
  (`WIFI_SETTINGS` intent) and reached the real join-network dialog for
  `earth5_1` — but the password field stayed **completely empty**, no
  errors logged. Root cause: `inject_text()`'s ADB Keyboard broadcast was
  going nowhere — consistent with ADB Keyboard not actually being
  installed/set as the active IME on this device (always a manual,
  unautomated prerequisite — see README.md). Since `input_text_direct()`
  (`adb shell input text`) was already proven working on this same device
  for APN's MCC/MNC, switched Wi-Fi password entry to it too — see
  PENDING_REAL_DEVICE_DATA.md ("Resolved — text input mechanism") for the
  full writeup, which also covers broadening the same fix to APN's
  Name/APN fields (same device, same underlying dependency, so almost
  certainly the same silent failure waiting there too).
- *2026-09-08 (second live test, after the `input_text_direct()` fix):*
  Password entry now works — confirmed by the client screenshot showing
  「接続」/「キャンセル」 as the join-network dialog's two buttons. But
  `wifi_setup.py` still couldn't tap Connect: `connect_button_resource_id`
  was (like `password_field_resource_id`) an unconfirmed Stage A
  placeholder, and the tap's return value was never even checked. Fixed by
  adding `connect_button_text: "接続"` — plain text, same 保存/キャンセル
  pattern already proven for the APN save dialog — tried first, with the
  placeholder resource-id kept only as a secondary fallback.
- *2026-09-08 (third live test, after the connect-button fix):* **Wi-Fi
  connects end-to-end on real hardware** — client screenshot confirmed
  `earth5_1` / 接続済み (Connected), WPA3-Personal, 5GHz. First fully
  working Phase 2 step, real device to real network. (The connect-button
  tap only worked on the first of three attempts in that run — later
  retries saw a "connect button not found" warning, correctly: once
  already connected, the same network's row opens a "Network Details"
  screen instead of the join dialog, which has no 接続 button at all.)
- *2026-09-08 (fourth live test — safety issue, corrects the note above):*
  "Nothing to fix there" was wrong. On the retries where the device was
  already connected, the client caught the automation via screen-share
  repeatedly tapping near **削除** (Forget) on that Network Details screen —
  a live screenshot with the tap location visible confirmed it. Root
  cause: `connect_wifi()` never checked whether the device was already
  connected before running the whole UI flow. It tapped the SSID's row
  (landing on Network Details, not the join dialog), found no password
  field or 接続 button (both correctly logged as "not found"), but had
  already called `input_text_direct()` to type the password — with
  nothing actually focused as a text field on that screen, those
  keystrokes went to whatever had default focus instead, consistent with
  landing on 削除. Deleting the just-established connection would have
  been actively destructive, not just a wasted retry. Fixed:
  `connect_wifi()` now checks `_is_wifi_connected()` FIRST, before
  touching the UI (or even attempting the shell command) at all — if
  already connected, it returns immediately and touches nothing.
  `削除`/`接続を解除` also added to `ui_automator._NEVER_TAP_TEXT` as
  defense-in-depth (doesn't address this specific root cause, since
  `input_text_direct()` doesn't go through `tap_by_text()`'s guard, but
  costs nothing and blocks any future path that might target them
  explicitly).

### APN settings — relevant to `apn_setup.py`
- *2026-09-04:* Navigation path confirmed:
  **設定 → ネットワークとインターネット → Wi-Fi とモバイルネットワーク →
  (gear icon next to the carrier name "Rakuten") → アクセス ポイント名**.
  Note this is reached via a **gear icon**, not a text menu item.
- APN list screen shows existing entry `rakuten.jp` with a radio selector.
  The "add new APN" control is a **`+` icon in the top-right with no visible
  text label** — implication: `add_button_resource_id` cannot be resolved via
  `find_by_text`; it must use a resource-id.
- Entry form 「アクセスポイントの編集」 fields observed (top of form):
  名前 / APN / プロキシ / ポート / ユーザー名 / パスワード / サーバー / MMSC.
  **MCC/MNC not visible in the top portion** — unresolved whether they exist
  further down or are absent on this build.
- **No Save button visible on the form** — may live in the ⋮ overflow menu
  (top-right) or be triggered by the back arrow. Unresolved;
  `save_button_resource_id` still needs this answered.
- Separate finding: **「モバイル ネットワークへの接続」/ eSIM download screen**
  exists on this model (reached via SIM settings). This is NOT the APN entry
  screen — do not confuse the two when writing navigation paths.
- *2026-09-08 (SUPERSEDES the 2026-09-04 MCC/MNC note above):* MCC/MNC ARE
  present on this build — the earlier note was wrong, they're just further
  down the scrollable form than the initial look covered. Confirmed via
  `apn_entry_middle_SHG10.xml`, `apn_entry_bottom_SHG10.xml`, and now also
  `apn_entry_filled_SHG10.xml`. They are **mandatory**, not optional: the
  device's own save validation rejects an entry without them.
- *2026-09-08:* **APN save flow confirmed.** Save is NOT a button on the
  form — it's in the overflow "⋮" menu (content-desc `その他のオプション`,
  no resource-id — same icon-only pattern noted above for the "+" add
  control). Opening it shows two items sharing `android:id/title`: `保存`
  (Save) and `キャンセル` (Cancel) — same generic-id-plus-text-disambiguation
  pattern as the field rows and the Wi-Fi list. The earlier `上へ移動`
  (navigate-up) candidate was tested and is **not** the save trigger on
  this build — don't use it.
- *2026-09-08:* **Save validation is sequential and blocking.** Saving with
  a required field empty/invalid shows a modal `AlertDialog` and does NOT
  save — confirmed real messages, in the order they appear:
  `APNは必ず指定してください。` (APN field empty) →
  `MCC欄は3桁で指定してください。` (`apn_mcc_validation_SHG10.xml`) →
  `MNC欄は2桁か3桁で指定してください。` (`apn_mnc_validation_SHG10.xml`).
  Each dialog: message at `android:id/message`, single OK at
  `android:id/button1` — real confirmation that `button1` really is this
  build's standard AlertDialog positive-button id (raises confidence in
  the earlier best-guess for the per-field entry dialog's own confirm
  button, which uses the same assumption but is still not directly
  captured).
- *2026-09-08:* **Numeric field entry needs a different mechanism.** The
  device's default IME is Japanese kana mode; the on-screen keyboard can't
  reach digits for MCC/MNC without an explicit mode switch that UI
  automation has no reliable way to trigger. `adb shell input text "440"`
  (Android's built-in text-injection, bypassing the IME) works instead of
  the ADB Keyboard broadcast used for the other (alphanumeric) fields.
- Implication for all of the above: `apn_setup.py` was rewritten
  accordingly (`_save_apn()`, `_MCC_PATTERN`/`_MNC_PATTERN` pre-validation,
  `input_text_direct()` for MCC/MNC specifically) and
  `config/models/sharp_aquos_sense7.yaml` updated
  (`overflow_menu_content_desc`, `save_menu_item_text`). See
  `PENDING_REAL_DEVICE_DATA.md` for the full before/after.
- *2026-09-08/09 (root cause of "apn menu navigation failed"):* Hand-tested
  and confirmed `adb shell am start -a android.settings.APN_SETTINGS`
  reaches the APN list screen in a single step. This also explains — and
  fixes — every "apn menu navigation failed" error seen in prior real
  runs: `menu_path`'s final step tried `tap_by_text()` on
  「アクセスポイント名」, but that string is the *destination screen's own
  title*, rendered via `content-desc` on the toolbar (the exact same
  pattern already confirmed for the edit form's 「アクセスポイントの編集」)
  — never a `text` node at all. There was nothing there to tap; the bug
  wasn't a wrong id, it was a step that could never have succeeded.
  `menu_path` (kept as a fallback if the intent ever fails) now correctly
  ends at the gear icon instead.
- *2026-09-08/09:* **[+] add-new-APN button confirmed icon-only, top-right
  of the APN list**, matching the earlier finding — position confirmed by
  hand, but its resource-id still isn't (no dump of the APN *list* screen
  itself exists, only the edit *form* reached after tapping it/an existing
  entry). Still `null`/TODO in config.
- *2026-09-08/09:* **MCC/MNC rows confirmed below the fold** — scrolling is
  required to reach them, not just theoretically possible. `apn_setup.py`'s
  field-row lookup now tries once, scrolls once, and retries if the row
  isn't found — same `scroll_then_tap_by_text` pattern already used for the
  wizard's scrollable terms screen.
- *2026-09-08/09:* **Success state confirmed**: after a save with no
  validation dialog, the new entry reappears on the APN list with its
  `名前` value as the first line (e.g. "TEST_SAVE_A / test.apn" — name then
  APN string). `_save_apn()` now makes a soft, best-effort positive check
  for this (`find_by_text(ui_xml, apn_name)`) — logged only (info if found,
  warning if not), never turned into a failure on its own, since e.g. list
  scroll position could make this check miss a genuinely successful save
  the validation-dialog check already accepted.
- *2026-09-11 (real run — `_looks_like_apn_list_screen` was too narrow):*
  Client's log showed `android.settings.APN_SETTINGS` repeatedly logging
  "didn't land on a recognizable APN list screen; falling back to
  menu_path" followed by `apn menu navigation failed`, even though the
  intent *was* landing correctly. Root cause: the landing-check only
  accepted the SHARP-skinned title rendered via `content-desc`
  ("アクセスポイント名", the pattern confirmed 09-08/09 above) — but on
  this device the screen reached via the *intent* instead shows a different
  title, "APN", which the check didn't recognize at all.
  `_looks_like_apn_list_screen()` now accepts either title variant (at
  first fixed based on the client's screenshot alone, which read as a
  plain `text` heading — a real dump captured shortly after, see below,
  corrected this to `content-desc` too, same pattern as everywhere else on
  this screen). The same screenshot also showed a warning banner,
  「このユーザーはアクセスポイント名設定を利用できません」("this user
  cannot use APN name settings") — client confirmed by hand that this does
  **not** block the "+" button from working with a normal tap; it's just
  informational text on this screen, not an access restriction to route
  around.
- *2026-09-11 (client correction, [+] tap mechanism):* My first read of the
  client's screenshot/caption (mentioning "you must press the Tab key")
  was wrong — I initially built keyboard-focus-cycling (`KEYCODE_TAB`/
  `KEYCODE_ENTER`) on the theory the "+" button was touch-disabled. Client
  corrected this directly: "Tab" referred to the on-screen "+" icon itself
  (translation artifact), not a keyboard key — the intended flow is a
  normal tap on "+", then fill 名前/APN/MCC/MNC one at a time via the
  already-implemented per-row dialog mechanism, OK each one, then the
  already-implemented two-tap overflow→保存 save. The keyboard mechanism
  was fully reverted (no trace left in `ui_automator.py`).
- *2026-09-11:* **[+] add-new-APN button still has no captured id of its
  own** (still true from 09-08/09 above — no dump of the list screen with
  a known-empty/known-count APN set exists, only a hand photo). Rather than
  leave the tap silently skipped, `configure_apn()` now falls back to a new
  primitive, `tap_left_of_content_desc()`: it taps an ESTIMATED position
  immediately left of the confirmed "その他のオプション" (⋮ overflow menu)
  icon, assuming a same-width icon occupies that adjacent space with no
  gap — consistent with the real screenshot's layout (+ and ⋮ both
  top-right, adjacent). This is explicitly an estimate, not a confirmed
  value: if wrong, it fails loudly a few steps later (the expected field
  rows won't be found), never silently misfires into a different action.
  Needs real-hardware confirmation before `add_button_resource_id` can be
  marked resolved in `PENDING_REAL_DEVICE_DATA.md`.
- *2026-09-11 (same day, client attached a real dump — supersedes both
  entries above):* Client attached `tests/fixtures/apn_restricted_SHG10.xml`
  — the first-ever real `uiautomator dump` of the APN *list* screen itself
  (every prior APN capture was the edit *form*, reached after tapping an
  entry). This settles both open questions from earlier today with real
  evidence instead of a screenshot-derived guess or a positional estimate:
  - The screen's "APN" title renders via `content-desc` on
    `com.android.settings:id/collapsing_toolbar` — **not** a plain `text`
    node as the earlier fix (based on the screenshot alone) assumed.
    `_looks_like_apn_list_screen()` corrected to check `content-desc`
    "APN" instead of `text` "APN" — the previous version would never have
    matched this actual screen.
  - The "+" button **does** have its own identifier after all: `content-desc`
    "新しい APN" ("New APN") — genuinely unambiguous, no resource-id (that
    part of the earlier guess was right: confirmed by the same dump, a
    plain `android.widget.Button` with `resource-id=""`). Its bounds,
    `[837,83][969,215]`, sit exactly adjacent to the "⋮" overflow icon's
    `[969,83][1080,215]` (sharing the x=969 edge) — this also retroactively
    confirms the position-estimate fallback added earlier today would have
    landed within ~11px of the real center (914 vs. the real 903), close
    enough it likely would have worked, but there's no need to rely on an
    estimate now. `configure_apn()` now taps `"新しい APN"` directly via
    `tap_by_content_desc()`, ahead of both `add_button_resource_id` and the
    `tap_left_of_content_desc()` fallback (which stays in the code for any
    model/screen without a captured identifier).
  - The dump also shows this screen has **no existing APN entries** at all
    under this restricted/SIM state — just the warning message — consistent
    with a genuinely blank "add new" flow, not a list to scroll through
    first.
  Still not confirmed by a live run: the dump proves what's on screen, not
  that tapping "新しい APN" actually opens the expected blank entry form.
  See `tests/test_real_shg10_fixtures.py` for the new fixture-backed tests.
- *2026-09-11 (live client run — confirms the above, surfaces the next
  bug):* Client ran the fully-updated automation. **Navigation, the "+"
  tap, and field entry through MNC all worked** — the first real
  confirmation of any of today's fixes. But the entry never actually
  saved. Client's description ("input works up to MNC, then it's not
  saved") plus two more real dumps
  (`apn_accesshost_SHG10.xml`/`apn_accesshost_save_SHG10.xml`, captured
  around the ⋮/保存 steps) pointed at the save step — but both dumps
  turned out **byte-identical** to fixtures already captured and already
  correctly handled (`apn_entry_top_SHG10.xml`,
  `apn_overflow_menu_SHG10.xml`), so they don't show a bug in the ⋮/保存
  taps themselves. The actual root cause was upstream: `_fill_labeled_field()`
  (`src/phase2/apn_setup.py`), when the (best-guess, never-directly-captured)
  `dialog_confirm_button_resource_id` ("android:id/button1") isn't found
  after typing, only logged a *warning* and returned `True` anyway. If
  that id is even slightly wrong for this specific dialog (it was only
  ever inferred from the *validation-error* dialog's real ids, not
  captured from the per-field dialog itself), the field's edit dialog is
  left open with the typed value never committed — and every tap after
  that (the next field's row, "その他のオプション", "保存") lands on or is
  swallowed by that stuck modal instead of its intended target. The
  eventual symptom several steps later — "apn save menu item not found"
  — reads like a save-flow bug but actually originates here, at the very
  first field. Same fix applied to the edit-field tap
  (`dialog_edit_field_resource_id`) for the same reason: it also only
  warned before typing into whatever happened to have focus. Both are now
  hard failures — see `_fill_labeled_field()`'s docstring. This makes a
  wrong id fail loud and immediately, at the exact field it's wrong for,
  instead of cascading into a confusing late failure — but does **not**
  resolve what the correct id actually is (still genuinely unconfirmed;
  see PENDING_REAL_DEVICE_DATA.md — capturing a real dump of this dialog,
  e.g. mid-way through tapping 名前 and before confirming, would settle it
  for real). Not yet re-verified against a live run.
- *2026-09-11 (client attached the dialog dump itself — rules out the
  hypothesis above):* Client captured exactly the requested dump:
  `tests/fixtures/apn_accesshost_okbtn_SHG10.xml`, taken while the 名前
  field's edit dialog was open (EditText focused, per `focused="true"`).
  This settles the question directly instead of by inference: it's a
  plain standard AOSP AlertDialog — title at
  `com.android.settings:id/alertTitle` (reading "名前", confirming which
  field was open), EditText at `android:id/edit`, and two buttons, "OK"
  at `android:id/button1` and "キャンセル" at `android:id/button2`. **Both
  ids `_fill_labeled_field()` already used were exactly right** — the
  best-guess wasn't a guess gone wrong, it was correct all along.
  `apn_setup.py`'s docstrings, the YAML's comments, and
  PENDING_REAL_DEVICE_DATA.md's "Best-guess"/"Not resolved" framing for
  these two ids are all updated to "Resolved" accordingly.

  This means the confirm-button hypothesis from the entry above — the
  leading theory for why a real run typed all four fields but the entry
  never saved — **is ruled out**. The hardening (hard failure instead of
  a silent warning when either dialog tap isn't found) stays, since it's
  correct defensive practice regardless, but it almost certainly won't be
  what fires on the next run, since both ids check out. The actual root
  cause of "not saving" is still open. **Next need: the exact terminal
  log output from a run with the current code** — whatever `_save_apn()`
  logs (a validation dialog's real message text, or "save menu item not
  found", or something else) will point directly at it, rather than
  guessing further from dumps of screens already confirmed correct. One
  concrete alternate hypothesis worth checking: `configure_apn()` fills
  both 名前 and APN with the identical value (`apn_name`) — plausible,
  since many real carrier profiles do use matching name/APN strings, but
  unconfirmed whether this specific device's validation is fine with that.
- *2026-09-11 (client's own direct observation — a genuine root-cause
  candidate, not another inference):* Client reported that MCC/MNC are
  being entered as **full-width digits** (４４０) instead of
  half-width/ASCII (440), and asked for this to be fixed. This is a much
  stronger lead than anything guessed from dumps so far: this device's
  on-device MCC/MNC validation ("MCC欄は3桁で指定してください") almost
  certainly checks for ASCII digits, and a full-width "４４０" is a
  different Unicode range entirely (U+FF10-FF19 vs. U+0030-U+0039) — it
  may not register as "digits" to that validation at all. That would
  explain exactly the reported symptom: field entry completes with no
  errors (typing, the OK tap, even the overflow/save taps all "work"),
  yet the entry never actually saves, because a validation dialog is
  legitimately appearing and blocking the save every time — just not one
  that's currently visible in what's been reported/dumped so far, since
  no one had reason yet to suspect the *typed value itself* was wrong
  rather than the mechanics of typing it.

  Root cause of the conversion itself: `input_text_direct()` ("input
  text") is documented (and was verified, 2026-09-08) to bypass the
  active IME entirely — but real evidence now shows that's not fully true
  for digits on this device; the Japanese IME's zenkaku/hankaku
  conversion apparently still intercepts committed text somewhere in the
  pipeline. Fix: new primitive `input_digits_direct()`
  (`src/device/ui_automator.py`) sends each digit as its own `adb shell
  input keyevent KEYCODE_N` — individual number-row keyevents map to
  hardware key semantics directly, a different code path than committing
  a text string, and aren't expected to go through the same IME
  conversion. `_fill_labeled_field()` (`src/phase2/apn_setup.py`) now
  takes a `numeric_only` flag; MCC/MNC pass `numeric_only=True` and route
  through this new function, while 名前/APN (arbitrary text, not just
  digits) keep using `input_text_direct()` exactly as before. Not yet
  re-verified against a live run — see PENDING_REAL_DEVICE_DATA.md.
- *2026-09-11 (client attached a before/after dump pair — confirms "no
  entry created", surfaces an unrelated real hazard):* Client attached
  `tests/fixtures/apn_failure_setting_SHG10.xml` (landed here after
  tapping 保存 — still failing) and `apn_success_setting_SHG10.xml`
  (client's own manual save, for comparison). The failure dump is
  **byte-identical** to `apn_restricted_SHG10.xml`, the pristine
  zero-entries list — direct confirmation the save produces no new entry
  at all (consistent with a validation dialog blocking it, matching the
  full-width-digit theory above, though it's unconfirmed whether this
  particular failing run already had that fix applied).

  The success dump — showing the entry list with 2 items — incidentally
  revealed something else: alongside the client's own manually-created
  "test"/"test_apn" entry (checked/active), there's a second, *unchecked*
  entry literally named **"<APN value from client>"** — the exact
  placeholder string from `config/network.yaml.example`. Real proof that
  at some point an automation run silently fell back to that example file
  (the old behavior in `main_phase2._load_network_config()`, previously
  just a warning) instead of a real `config/network.yaml`, and created a
  garbage APN entry on the device without ever erroring. Unrelated to
  today's specific save failure (that entry is inactive, a leftover from
  a different run), but real, concrete evidence the old silent fallback
  was a genuine hazard on real hardware, not a theoretical one — this
  always runs against real hardware, there's no dry-run mode. Fixed:
  `_load_network_config()` now raises `NetworkConfigError` (main_phase2.py
  exits 1 with a clear message) if `config/network.yaml` is missing, or if
  any value inside it still matches one of the example file's known
  placeholder strings verbatim — catches both "never copied the example"
  and "copied it but left one field unedited."
- *2026-09-11 (same day — the guard above immediately caused a real
  false-positive):* Client ran the actual automation with both fixes in
  place; it refused to start at all:
  `config/network.yaml['apn.carrier'] is still the placeholder value
  '<carrier name>' ...`. Root cause: the guard walked the *entire* config
  file recursively, checking every key — but `apn.carrier` is
  documentation-only and never read by any code path
  (`src/orchestration/slot.py` only ever reads `apn_name`/`mcc`/`mnc` from
  `apn_cfg` and `ssid`/`password` from `wifi_cfg`). The client's actual
  config was correctly filled in for everything that matters; the check
  blocked a good run over a field nothing depends on. Fixed same-day:
  narrowed to an explicit whitelist, `_REQUIRED_CONFIG_PATHS`, matching
  exactly what `slot.py` consumes — `apn.carrier` is now intentionally
  never checked, regardless of its value. New regression test,
  `test_load_network_config_ignores_placeholder_in_unread_field`, pins
  this exact scenario down directly so it can't silently regress if the
  check is ever broadened again without checking what's actually
  consumed first.
- *2026-09-11 (same day — the guard fires correctly, on a real gap):*
  After the `carrier` false positive was fixed, the client's next run hit
  the guard again — this time correctly: `config/network.yaml`'s
  `apn.apn_name` was itself still the literal placeholder text `<APN
  value from client>` (wifi ssid/password, carrier, mcc, and mnc had all
  been filled in with real values; only `apn_name` was missed). **Not a
  code bug** — no fix needed here, this is exactly what the guard exists
  to catch. Genuinely significant in hindsight, though: it means every
  real automation run so far, across this entire investigation (the
  full-width-digit finding included), was attempting to save this literal
  string — spaces, angle brackets, and all — as the real APN value. That's
  independently very plausible as a contributor to "produces zero
  entries": Android's APN validation may reasonably reject a value with
  those characters even before reaching the MCC/MNC check. Left as an
  open question exactly how much of the "not saving" mystery this alone
  explains vs. the digit-encoding fix, since both were wrong
  simultaneously on every real run tested until now — but with both fixed
  now, the next run is the first genuinely clean attempt.

### 🎉 MILESTONE (2026-09-11): first successful end-to-end Phase 2 run on real SHG10 hardware

Client ran the automation with a real `apn_name` in place (fixing the
placeholder-value gap above). Full log:

```
2026-09-11 21:53:25,224 INFO     main_phase2: loading model profiles from ...
2026-09-11 21:53:25,248 INFO     main_phase2: starting Phase 2 run: serial=352063910272451 model=SHG10 (AQUOS sense7) [skip_wizard]
2026-09-11 21:53:26,417 WARNING  src.orchestration.slot: slot 352063910272451: skip_wizard=True - ...
2026-09-11 21:53:26,417 INFO     src.orchestration.slot: slot 352063910272451: connecting wifi
2026-09-11 21:53:26,956 INFO     src.phase2.wifi_setup: already connected to 'earth5_1'; nothing to do
2026-09-11 21:53:26,956 INFO     src.orchestration.slot: slot 352063910272451: configuring apn
2026-09-11 21:53:29,529 INFO     src.phase2.apn_setup: reached APN list via android.settings.APN_SETTINGS intent
2026-09-11 21:54:17,722 WARNING  src.phase2.apn_setup: apn: save reported no validation error, but 'rakuten.jp' wasn't spotted back on the APN list (soft check only — not treated as a failure; could be scroll position or list truncation)
2026-09-11 21:54:17,723 INFO     src.phase2.apn_setup: apn 'rakuten.jp' configured successfully
2026-09-11 21:54:17,723 INFO     src.orchestration.slot: slot 352063910272451: reached LOGIN_INSTALL (Phase 2 success condition)
2026-09-11 21:54:17,723 INFO     main_phase2: SUCCESS: device 352063910272451 reached LOGIN_INSTALL
```

**This is the first time the full Wi-Fi + APN chain has completed
end-to-end on real hardware.** The client independently confirmed it by
manually reopening the APN list a moment later — `rakuten.jp` was there,
selected (checked radio button), matching exactly what a real save is
supposed to look like.

One discrepancy, resolved same-day: the client's own screenshot taken
*immediately* after the script finished still showed the empty
"アクセスポイント名設定を利用できません" list (matching the WARNING
above), which is why the client initially read this as a failure — only
their *manual* re-check a moment later showed the entry. Root cause: the
APN list's RecyclerView doesn't refresh in place right after 保存 — the
very next `uiautomator dump` (used for `_save_apn()`'s soft post-save
check) can still capture the pre-save state even though the save already
genuinely succeeded on-device. Fixed: `_save_apn()` now retries the
check once, after a `_POST_SAVE_RECHECK_DELAY_SECONDS` (2s) delay, before
logging its "wasn't spotted" warning — this was already a *soft* check
(never itself a hard failure — `configure_apn()` correctly returned
`True` and the run correctly reached `LOGIN_INSTALL` even with the false
negative), so nothing about the actual success/failure determination
changes; this only removes a misleading warning line and the confusion
it caused.

This run also retroactively confirms, in one shot, everything tracked in
PENDING_REAL_DEVICE_DATA.md's old "Highest priority" re-verify list:
the destructive-tap safety fix (already-connected Wi-Fi correctly
detected and skipped, no stray taps), the `dump_ui()` pull-failure fix
(no crash through a long real session), the APN navigation root-cause
fix, the screen-recognition fix, the add-button content-desc fix, the
per-field dialog ids, the MCC/MNC digit-entry fix, and the network-config
placeholder guard — see PENDING_REAL_DEVICE_DATA.md's "Resolved — full
Phase 2 run confirmed end-to-end" for the consolidated list. The wizard
(2 of 9 screens' button labels still unverified) and SOG08/SOG07/SHG07
(entirely untouched) are now the real remaining priorities.

### 2026-09-14: SHG07 switched to inherit SHG10's values; multi-device parallel mode added

Client asked to begin SHG07 (AQUOS sense6s, Android 13) work, explicitly
requesting that no new dumps be captured for it — reasoning that SHG07 and
SHG10 (AQUOS sense7, Android 14) are the same SHARP AQUOS lineup, closely
enough related to reuse SHG10's confirmed real dump-derived values
directly. Also requested all devices be run in parallel, at the same
timing, rather than one at a time.

**SHG07 config change**: `config/models/sharp_aquos_sense6s.yaml` rewritten
from Stage A's from-scratch invented placeholders to SHG10's exact schema
and real values (screen-driven wizard, labeled APN fields, all the
resolved dialog/add-button/overflow/save ids). This is a reasoned
improvement over pure invention, but explicitly not independent
confirmation — flagged at length in the file's own header and in
PENDING_REAL_DEVICE_DATA.md's new "SHG07 (AQUOS sense6s)..." section,
which also carries forward this project's own repeated real lesson: SHG10
itself had multiple real surprises (APN screen title, MCC/MNC digit
encoding, per-field dialog ids) found only once actual hardware was
touched, all on the *same* unit/OS build — a different model on a
different Android version carries meaningfully more of that same risk,
not less. Recommended a supervised, one-device-at-a-time first pass
before trusting this config in the new parallel mode or leaving it
unattended.

**Parallel multi-device mode**: `main_phase2.py` gained `--device
SERIAL:MODEL` (repeatable), replacing `--serial`/`--model` for this mode —
dispatches every listed device to its own thread via
`concurrent.futures.ThreadPoolExecutor`, all starting at the same time,
sharing only the loaded model profiles and `config/network.yaml`. Built
directly on `run_slot_with_retries()` (same function the existing
single-device path already used) rather than
`orchestration/scheduler.py`'s `run_phase2_batch()`, specifically to keep
`--skip-wizard` available — `run_phase2_batch()` deliberately omits it so
a real production batch run can never skip the wizard by accident; this
is a manual/testing tool in the same spirit as `--skip-wizard` itself, not
a replacement for that production path. `--serial`/`--model` still works
unchanged for a single device (no thread pool, identical behavior/logs to
before). See README.md, PENDING_REAL_DEVICE_DATA.md's new `--device`
entry, and `tests/test_main_phase2.py` for the new tests.

**Fixture reorganization**: `tests/fixtures/` was reorganized (outside
this session, found already done when tests were next run) into one
subfolder per model — e.g. every `*_SHG10.xml` file moved into
`tests/fixtures/AQUOS sense7（SHG10）/` — with matching empty folders
reserved for SHG07/SOG07/SOG08's own future real dumps.
`tests/test_real_shg10_fixtures.py`'s `FIXTURES_DIR` updated to match;
`.gitkeep` files added to the three currently-empty model folders so the
structure survives being committed.

### 2026-09-15: SHG10 also opted into SHG07's keyevent-based text entry

Client asked for the same input method to be applied across every device,
not just SHG07 (where the active IME was found, 2026-09-14, to interfere
with plain alphanumeric `input text` entry into 名前/APN). SHG10's profile
now also sets `apn_settings.use_keyevent_text_entry: true`, routing
名前/APN through `input_ascii_direct()` (per-character keyevents) there
too — even though SHG10 never showed this specific symptom itself: its
own real, confirmed end-to-end success (2026-09-11) used
`input_text_direct()` for these exact two fields. The underlying
mechanism isn't new to SHG10 — the same per-keyevent strategy already
fixed this device's own MCC/MNC full-width-digit bug — but this precise
combination (keyevents for 名前/APN specifically, on SHG10) hasn't itself
been run against real hardware. Assessed at the time as low risk (proven
primitive, "rakuten.jp" fits the supported character set, fails loud on
anything it doesn't).

**⚠️ Correction, same day, see SHG07's section below**: that risk
assessment turned out to be wrong. A subsequent SHG07 finding proved
per-keyevent text entry does NOT actually bypass a Japanese-conversion
IME for *letters* (only digits) — it silently transformed "rakuten.jp"
into 「らくてん。」 there. Since SHG10's own MCC/MNC issue was also
IME-driven, this flag may cause the same failure on SHG10's next run, not
a no-op as assessed here. The 2026-09-15 read-back-verification fix means
this would now fail loud rather than silently regress, but it would still
be a real functional break on a path proven working 2026-09-11. **Resolved
same day** (see the SHG07 section's "round 5" entry below): reverted —
SHG10 is back to exactly its 2026-09-11 known-working configuration.

### Real-device bugs found running the automation — relevant to `adb_client.py`, `main_phase2.py`
- *2026-09-08:* `config/settings.yaml`'s `adb.platform_tools_path` is a
  *directory* (`C:\platform-tools`), but was being passed straight through
  as the `adb` executable path itself. Every `AdbClient` call then failed
  with `OSError`, silently swallowed by `is_connected()` into a plain
  `False` — indistinguishable in the logs from a genuinely disconnected
  device, even though `adb devices` worked fine in a normal shell. Fixed by
  joining the directory with the executable name
  (`main_phase2._resolve_adb_path()`) and making `is_connected()` raise
  `AdbCommandError` instead of swallowing this specific failure class.
- *2026-09-08:* `subprocess.run(..., text=True, ...)` decodes `adb` output
  using the OS locale codepage — `cp932` on the client PC's Japanese-locale
  Windows install — instead of UTF-8, which is what `adb`'s actual output
  uses. Real device output (`dumpsys wifi`, containing real Wi-Fi SSIDs)
  crashed a background thread *inside* `subprocess.run()` itself, invisible
  to any `try`/`except` in this codebase, leaving `stdout=None` and
  surfacing several calls later as a confusing
  `TypeError: argument of type 'NoneType' is not iterable`. Fixed with
  explicit `encoding="utf-8", errors="replace"`. Neither of these two bugs
  was a device-data gap — both were pure code bugs that only a real
  Windows client PC with real non-ASCII device output could have surfaced;
  the fake/mock ADB layer never exercised either condition.
- *2026-09-08:* Real client-PC run showed the SHG10 test unit was already
  past OOBE (landed on a home screen, not any wizard screen) — it had been
  provisioned in an earlier session. Added `main_phase2.py --skip-wizard`
  for testing against an already-provisioned device without a fresh
  factory reset each time. Deliberately not exposed on `run_phase2_batch()`
  (the production batch path).
- *2026-09-08:* Real run also showed `wifi_setup.py`'s/`apn_setup.py`'s
  `menu_path` text navigation (tapping `設定`) fails whenever the device
  isn't already showing that text — true for `--skip-wizard` testing
  (starts from the home screen) and plausibly other real-world states too.
  Both now try the standard `android.settings.WIFI_SETTINGS` intent first
  (confirmed working — reaches the screen regardless of starting point),
  with a read-only landing check before committing to skip any menu_path
  steps, falling back to the original behavior unchanged otherwise.
- *2026-09-08:* First real run to reach APN navigation crashed with
  `[Errno 2] No such file or directory` on a local temp path, immediately
  after `apn_setup.py` logged a successful screen transition. Root cause:
  `ui_automator.dump_ui()` never checked `client.pull()`'s return value —
  when the pull silently failed (uiautomator dump is known to
  intermittently fail to produce a readable file right after a screen
  transition, which is exactly what had just happened), the code read a
  local file that was never written, crashing with a raw
  `FileNotFoundError` instead of a clear, retriable error. Fixed: `pull()`
  failure now raises `AdbCommandError` with a clear message, and the whole
  dump+pull is retried up to 3 times with a 1s delay before giving up —
  this is a well-known class of `uiautomator dump` flakiness, not specific
  to this device, so the fix is in the shared `dump_ui()` used by every
  tap/find call, not just the APN path that happened to surface it.

### Windows/client-PC environment — relevant to deployment & setup docs
- *2026-09-04:* Freshly-extracted executables on the client PC are **silently
  blocked** — scrcpy hung with no error until fixed via
  `Get-ChildItem -Path C:\scrcpy -Recurse | Unblock-File` **and** adding the
  exe to Windows Defender Firewall.
- The PC's active network is classified **Guest/Public**, and inbound
  connections for non-allowlisted apps are blocked. When adding an app via
  "Allow another app", Windows ticks **Private only by default** — Public must
  be ticked manually or the rule won't apply.
- Implication: any new executable delivered for Phase 2/3 will hit the same
  silent block on first run. Document unblock + firewall allowlist as a
  required setup step.
- Also: PowerShell requires `.\` prefix to run a local exe (unlike cmd) —
  relevant if delivered scripts assume cmd-style invocation.

---

## SHG07 (SHARP AQUOS sense6s, Android 13)

**Serial:** 353681650397052
**Confirmed identity string (from adb):** not yet confirmed — no `adb
devices`/`adb shell getprop` output recorded for this unit yet.

**🎉 Phase 2's Wi-Fi + APN flow is CONFIRMED WORKING end-to-end on this
unit as of 2026-09-15** — see the MILESTONE entry below. Config
(`config/models/sharp_aquos_sense6s.yaml`) still mostly holds values
*inherited from SHG10* for navigation/dialog structure (not independently
confirmed for this unit — see the 2026-09-14 entry under SHG10's section
above and the file's own header comment), but the fields that actually
mattered for getting a real save working —
`keyboard_mode_toggle_tap`/`navigate_up_content_desc` — are real SHG07
data, found and confirmed on this exact unit.

### Test Log — exactly what was run against this unit

| Date | Test | Command | Result |
|---|---|---|---|
| | | | |

### APN field text entry — relevant to `apn_setup.py`, `ui_automator.py`
- *2026-09-14:* First real contact with this unit. Client reported: the
  active Japanese input method activates when entering APN dialog fields
  and prevents the intended alphanumeric/digit characters from being
  entered — for 名前/APN specifically, not just MCC/MNC (MCC/MNC already
  went through `input_digits_direct()`'s keyevent workaround regardless,
  inherited from SHG10). Client also supplied a real dump of the field
  dialog itself,
  `tests/fixtures/AQUOS sense6s（SHG07）/apn_input_dialog_SHG07.xml`
  (captured with the "APN" field's dialog open) — structurally identical
  to SHG10's own confirmed dialog: title at
  `com.android.settings:id/alertTitle` ("APN"), EditText at
  `android:id/edit` (focused), "OK" at `android:id/button1`, "キャンセル"
  at `android:id/button2`. So the *inherited ids* for this dialog are
  right; the problem is specifically that `input_text_direct()` ("input
  text"), which works fine for SHG10's 名前/APN, is affected by SHG07's
  IME the same way `input text` affected SHG10's MCC/MNC (full-width
  digits, 2026-09-11) — just for alphanumeric text too here, not only
  digits.
- Implication: `input_ascii_direct()` added to `ui_automator.py` —
  generalizes `input_digits_direct()`'s per-character-keyevent strategy
  (`adb shell input keyevent KEYCODE_<X>`) to lowercase a-z/0-9/`.`/`-`,
  the character set every real APN value seen in this project fits.
  `apn_settings.use_keyevent_text_entry: true` set on SHG07's profile only
  (not SHG10's, where `input_text_direct()` is already proven working for
  these two fields) routes 名前/APN through it. Uppercase deliberately
  unsupported (raises `ValueError`) — a per-keyevent shift chord isn't
  reliably achievable through `adb shell input keyevent`'s one-press-per-
  call model.
- Deliberately NOT implemented: detecting and switching the device's
  active input method directly. No real IME component id is confirmed for
  this device, and guessing one risks silently switching to the wrong (or
  no) keyboard — a global, hard-to-undo device-state change, worse than
  the problem it would fix. Added `get_current_ime()` instead — a
  read-only diagnostic (`dumpsys input_method`, parses `mCurMethodId=`)
  now logged on every `configure_apn()` call, so a future run's log
  carries real evidence if this class of problem shows up on another
  device, rather than needing to guess again.
- Not yet re-verified against a live SHG07 run with this fix applied.
- *2026-09-15:* Client requested the same input method be applied across
  every device, not just SHG07 where the problem first surfaced. See the
  matching entry under SHG10's section — `use_keyevent_text_entry: true`
  is now also set on SHG10's profile.
- *2026-09-15 (same day — the fix above was wrong, proven by a client
  screenshot):* Client typed "rakuten.jp" into the 名前 field with
  `use_keyevent_text_entry` active and the dialog showed **「らくてん。」**
  instead — hiragana "rakuten" plus a Japanese full-width period, not the
  intended half-width ASCII text. This disproves 2026-09-14's core
  assumption: individual keyevents for *letters* are NOT immune to this
  device's IME the way keyevents for *digits* are. Real mechanism: Gboard's
  Japanese input mode performs live romaji-to-kana conversion on Latin
  letter keys as they arrive (`a`/`k`/`u`/etc. are romaji syllable input,
  so the IME intercepts and converts them) — this happens whether the
  letters arrive via `input text` (already known broken) or via individual
  `KEYCODE_A`/`KEYCODE_K`/`KEYCODE_U` events (2026-09-14's "fix" — turns
  out equally affected). Digit keycodes are immune only because digits
  aren't romaji syllables, which is why `input_digits_direct()` has never
  actually failed on any device tested — but `input_ascii_direct()`'s
  promise for *letters* never held.

  Also settles why `get_current_ime()` didn't already reveal this: the
  run's log showed `mCurMethodId=com.google.android.inputmethod.latin/
  com.android.inputmethod.latin.LatinIME` (Gboard) at the exact moment
  this happened — that's Gboard's **package id**, constant across every
  language it supports, not the currently active **subtype** (language/
  layout). A future diagnostic would need subtype/locale info too, not
  just `mCurMethodId`.

  **The serious part**: every step up to this point — the row tap, the
  edit-field tap, the typing call itself, even the confirm-button tap —
  reported success with no error. The *previous* run (before this was
  caught) actually logged `SUCCESS: reached LOGIN_INSTALL` while silently
  saving 「らくてん。」 as the real APN name — a genuine instance of the
  "silent wrong action" this project has tried hardest to avoid throughout.
  Fixed: `_fill_labeled_field()` now reads back the field's actual
  committed text immediately after typing, before ever tapping confirm —
  if it doesn't match what was intended, this is now a hard failure
  (logged with both the intended and actual value) instead of proceeding.
  This does not solve the underlying "how do we type correct text on
  SHG07" problem — it only guarantees a wrong value can no longer be
  silently saved; the automation still cannot successfully save a real
  APN entry on SHG07 as of this entry. New regression test,
  `test_fill_labeled_field_fails_loudly_when_typed_text_is_transformed`,
  pins this exact scenario down directly.

  **Consequence for SHG10**: since `use_keyevent_text_entry` was just set
  there too (previous entry, same day) on the assumption it was safe, and
  SHG10's own MCC/MNC problem was also IME-driven, there's real reason to
  suspect SHG10 may hit the same letter-conversion issue on its next real
  run — which would now fail loud (safe, thanks to the fix above) rather
  than silently regress, but would still be a real functional regression
  on a device whose 名前/APN entry was previously proven working
  (2026-09-11). Flagged in PENDING_REAL_DEVICE_DATA.md as the top
  priority — recommending confirming with the client whether to revert
  SHG10's flag until SHG07's actual fix is found. **Resolved same day,
  round 5 below: reverted.**

  Real options for an actual SHG07 fix, none yet attempted: (1) `adb
  shell ime list -a` (read-only, safe) to find a genuinely available
  non-converting input method/subtype on this device — real data this
  project doesn't have yet; (2) writing the APN directly via Android's
  Telephony ContentProvider (`content insert/update --uri
  content://telephony/carriers`), bypassing UI text entry (and the IME)
  entirely — whether the plain `shell` UID has permission for this on a
  non-rooted device is unconfirmed, needs a real test; (3) some other
  injection path not yet identified. Blindly guessing an IME/subtype id
  to switch to remains explicitly ruled out — round 1 of this same
  investigation already showed once that a plausible-sounding "bypass"
  theory can be wrong in a way only real hardware reveals.
- *2026-09-15 (round 3, same day — the round-2 fix caused a new cascading
  failure):* Client ran the automation again with the read-back check
  active. It correctly failed loud at the 名前 mismatch on the first
  attempt — but then **every subsequent attempt** (the scheduler's 3
  retries, then a fresh invocation afterward) failed differently:
  `android.settings.APN_SETTINGS` reported "didn't land on a recognizable
  APN list screen" every single time, including the very first try of the
  next run, not just the retries. Root cause: returning `False` on the
  mismatch left the field's dialog genuinely *open* on the device — never
  dismissed. A fresh `am start -a android.settings.APN_SETTINGS` intent
  doesn't dismiss an unrelated already-open dialog, so every following
  dump kept showing the stuck dialog instead of the expected list,
  explaining the navigation failures completely. Fixed: new
  `apn_settings.dialog_cancel_button_resource_id` (real, confirmed —
  "キャンセル"/`android:id/button2`, already seen in both devices' real
  dumps) is now tapped to back out of a mismatched dialog cleanly before
  `_fill_labeled_field()` returns `False`. Best-effort only (its own
  failure only logs a warning, never masks the real underlying error) —
  new test, `test_fill_labeled_field_taps_cancel_to_back_out_of_mismatched_dialog`.

  **This fix is forward-looking only** — it does not retroactively clean
  up whatever the SHG07 unit's screen currently shows from before this fix
  existed. Client needs to check the actual device (or a fresh dump) and
  manually dismiss anything unexpected before the next attempt.
- *2026-09-15 (round 4, same day — three more real options investigated
  and ruled out):* Followed up on round 2's "real options" list with
  actual commands against the device, one at a time, each with concrete
  evidence:
  - `adb -s 353681650397052 shell ime list -a` — only one real text-input
    IME exists: `com.google.android.inputmethod.latin` (Gboard). The other
    two entries are an autofill proxy (`enabled=false`) and voice input
    (not usable for typed text). No alternative keyboard to switch to.
  - Same output showed `mSubtypeId=0 mSubtypeName=null` for Gboard — no
    distinct per-locale subtype data to target. `adb shell dumpsys
    input_method | findstr /I "curmethodid subtype locale"` (needed
    because the full dump was too long to paste) additionally showed
    `System locales = [ja-JP]` / `currentLocale = ja_JP` twice — suggests
    Gboard's language follows the device's system locale rather than an
    independently switchable subtype/hash, so `settings put secure
    selected_input_method_subtype` isn't applicable here.
  - `adb -s 353681650397052 shell content query --uri
    content://telephony/carriers` → `SecurityException: No permission to
    access APN settings`. Confirms the Telephony ContentProvider
    direct-write idea is blocked for the plain `shell` user on this
    non-rooted device — ruled out with a real error, not an assumption.
  - `adb -s 353681650397052 shell settings put system system_locales
    en-US` succeeded (confirmed via `settings get`, value round-tripped
    ja-JP → en-US → ja-JP correctly) — but a follow-up screenshot showed
    **no actual effect**: Settings app labels and the keyboard both stayed
    in Japanese. Writing the setting doesn't propagate to already-running
    apps/IME without them reloading. Proposed next: force-stop
    `com.android.settings` and `com.google.android.inputmethod.latin`
    after the setting change, to force a fresh read — not yet tried.
  - A client screenshot also pointed directly at the visible keyboard's
    own かな/英数 mode-toggle key ("あ1") as the likely real fix. A real
    dump captured at that exact moment
    (`apn_kana_toggle_SHG07.xml`) confirmed the on-screen keyboard isn't
    in the accessibility tree `uiautomator dump` captures at all — only
    the app's own dialog window is present (confirmed by listing every
    widget class in the dump: all `android.widget.*`/Settings-app
    classes, nothing keyboard-related). No resource-id or bounds exist
    for this key to target safely.
- *2026-09-15 (round 5, same day — reconsidered SHG10's own method):*
  Client asked directly whether SHG10's method (`input_text_direct()`)
  would fare any better than the keyevent approach. Real technical
  answer: `input text` and `input keyevent` are both implemented via
  synthesized KeyEvents under the hood — `input text` converts the string
  through `KeyCharacterMap` before injecting, the same underlying
  event-injection path `input keyevent` uses directly — so neither
  actually bypasses whatever mode the keyboard is in when the events
  arrive; they're just two ways of sending the same kind of event. This
  also gives the likely explanation for SHG10's 2026-09-11 success: that
  unit's keyboard was probably just already in alphanumeric mode at the
  time, not because `input_text_direct()` itself resists conversion.
  `use_keyevent_text_entry` reverted to unset on **both** SHG07 and SHG10
  (the SHG10 flag had been set earlier the same day, "same input method
  across every device" — see above; this closes that regression risk by
  restoring SHG10's exact known-working 2026-09-11 configuration) so the
  next SHG07 run is a direct, apples-to-apples comparison against SHG10's
  method rather than resting on the theory alone. Not yet re-verified.
- *2026-09-15 (round 6, live re-test of round 5's revert):* Client ran
  the automation with `input_text_direct()` restored. Confirms round 5's
  hypothesis directly: typed `rakuten.jp` into 名前, field read back
  `らくてん。ｊｐ` — the exact same failure as the keyevent approach.
  Proves the injection method was never the variable. Also surfaced a
  second cascading-failure gap beyond round 3's fix: cancelling the
  *field* dialog leaves the device on the "アクセスポイントの編集" edit
  *form* for the abandoned new entry, not back on the APN *list* — the
  retry's `APN_SETTINGS` intent landed on that leftover form again,
  failing navigation the same way round 3's bug did. Fixed the same way:
  a second best-effort cleanup tap, `apn_settings.navigate_up_content_desc`
  (real, confirmed — the standard AOSP toolbar "上へ移動" back-arrow, seen
  in SHG10's real dumps; inherited/unconfirmed for SHG07, whose own dumps
  have only ever captured a dialog's foreground window) — tapped after
  Cancel to fully exit the abandoned entry.
- *2026-09-15 (rounds 7-9, same day — 🎉 the real fix, found by the
  client):* Pushed back on the dead-end framing and pursued the
  on-screen keyboard's mode-toggle key a different way: **Android's own
  Settings > Developer options > Input > "Pointer location"**, which
  overlays real X/Y touch coordinates on screen — rather than continuing
  to rely on `uiautomator dump`, which had already been confirmed twice to
  never capture the keyboard at all. This produced a real coordinate for
  the かな/英数 toggle key: **(106, 2239)**. First manual touch there
  showed a small popup (settings gear + another icon) rather than a clean
  toggle — but the actually decisive test was scripted:
  `adb shell input tap 106 2239` (run twice — the key appears to cycle
  through more than two states) followed by `adb shell input text "a"`
  produced a correctly committed half-width `a` in the field. First
  correct ASCII character to ever land in an SHG07 APN field in this
  entire investigation.

  Implemented: `tap_at_coordinates()` (`src/device/ui_automator.py`) — a
  new, deliberately different kind of primitive from every other tap in
  this codebase: it does NOT resolve a resource-id/text/content-desc from
  a dump first, because for this element there is nothing to resolve —
  confirmed by two separate real dumps, the keyboard simply never appears
  in the accessibility tree at all (most likely Gboard deliberately hides
  its own UI from accessibility services, a real, known keyboard-privacy
  behavior). The coordinate is real, direct, on-device confirmation
  (Pointer Location + a scripted verification), never a screenshot
  pixel-proportion estimate — that was explicitly considered and rejected
  earlier for being too risky on this device's dense keyboard rows.
  `apn_settings.keyboard_mode_toggle_tap: [106, 2239]` (SHG07 only) is
  tapped twice before typing into each non-numeric field
  (`_fill_labeled_field()`); MCC/MNC are untouched (`input_digits_direct()`
  already works regardless of keyboard mode).

  **Confirmed so far**: the isolated tap+type sequence, via direct `adb
  shell` commands. **Not yet confirmed**: a full `configure_apn()` run
  using this mechanism end-to-end — that's the next real test, and what
  actually proves whether SHG07 can save a complete APN entry for the
  first time. This coordinate is tied to SHG07's exact screen
  resolution/orientation; re-confirm via Pointer Location before ever
  reusing it on a different model.

  New tests: `test_configure_apn_taps_keyboard_toggle_twice_before_every_
  field` (renamed same day, round 10 — see below), `test_configure_apn_
  keyboard_toggle_tap_is_opt_in`, `test_tap_at_coordinates_sends_a_raw_
  input_tap`, `test_tap_at_coordinates_does_not_dump_or_look_up_anything_
  first`.
- *2026-09-15 (round 10, same day — live re-test finds one more gap, MCC
  full-width digits):* Client ran the full `configure_apn()` flow with
  the round 7-9 fix in place. **Real progress**: 名前 and APN both went
  through with no mismatch error — the toggle fix worked for the two
  fields it was built for, the first time either has ever committed
  correctly on SHG07. Failure moved to MCC: `typed '440' but the field
  now reads '４４０'` — the same full-width-digit pattern SHG10 hit,
  except here it happened *with* `input_digits_direct()`, which had been
  assumed universally immune to conversion (that assumption held on
  SHG10, where `keyboard_mode_toggle_tap` isn't set, but not here). Root
  cause: the toggle tap was scoped to non-numeric fields only, on the
  theory digit keyevents never needed it — wrong on SHG07, whose 12-key
  keyboard apparently full-width-converts digit keyevents too when left
  in kana mode, not just letters. Fixed: `keyboard_mode_toggle_tap` now
  applies unconditionally, before every field including MCC/MNC (test
  renamed to `..._before_every_field`, asserts 8 taps — 4 fields × 2 —
  instead of 4). Not yet re-verified against a full live run with this
  latest fix; two of four fields are now proven working live, MCC/MNC's
  fix is implemented but untested.

### 🎉 MILESTONE (2026-09-15, round 11): first successful end-to-end Phase 2 run on real SHG07 hardware

Client ran the automation with the MCC/MNC fix from round 10 applied.
Full log:

```
2026-09-15 15:32:24 INFO  main_phase2: starting Phase 2 run: serial=353681650397052 model=SHG07 (AQUOS sense6s) [skip_wizard]
2026-09-15 15:32:25 WARNING src.orchestration.slot: skip_wizard=True - ...
2026-09-15 15:32:25 INFO  src.phase2.wifi_setup: already connected to 'earth5_1'; nothing to do
2026-09-15 15:32:26 INFO  src.phase2.apn_setup: apn: current input method is 'com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME'
2026-09-15 15:32:29 INFO  src.phase2.apn_setup: reached APN list via android.settings.APN_SETTINGS intent
2026-09-15 15:33:39 WARNING src.phase2.apn_setup: apn: save reported no validation error, but 'rakuten.jp' wasn't spotted back on the APN list (soft check only — not treated as a failure; could be scroll position or list truncation)
2026-09-15 15:33:39 INFO  src.phase2.apn_setup: apn 'rakuten.jp' configured successfully
2026-09-15 15:33:39 INFO  src.orchestration.slot: reached LOGIN_INSTALL (Phase 2 success condition)
2026-09-15 15:33:39 INFO  main_phase2: SUCCESS: device 353681650397052 reached LOGIN_INSTALL
```

**No field-mismatch error at 名前, APN, MCC, or MNC** — the first time
all four have ever committed correctly on this device in this entire
investigation. Client independently confirmed: the saved APN list
appeared empty immediately after the run, but re-checking Settings
confirmed `rakuten.jp` was genuinely registered — matching exactly the
`'rakuten.jp' wasn't spotted back on the APN list` soft-check warning
above. Same class of finding as SHG10's own milestone (2026-09-11): a
slow list refresh, not a data-correctness problem — except here the
existing single delay+re-dump retry (added for SHG10's version of this
same issue) still wasn't reliably enough on SHG07's list. Fixed:
`_save_apn()`'s soft post-save check now tries a third time via a fresh
`android.settings.APN_SETTINGS` re-navigation (forces a genuine screen
reload) if the delay+re-dump retry still doesn't find the entry — real
evidence, from this exact client report, that waiting on the same
already-open screen isn't always sufficient but a full re-navigation is.
Still soft either way, never a hard failure — new test,
`test_configure_apn_falls_back_to_renavigation_when_waiting_alone_is_
not_enough`.

This closes out the SHG07 text-entry investigation that began 2026-09-14:
round 1's per-keyevent theory (wrong), round 2's proof it was wrong,
rounds 3-4's cascading-failure fixes, round 5's reconsideration of
SHG10's own method (also wrong, same reason), rounds 6's confirmation,
and rounds 7-11's actual fix (Pointer Location → keyboard-toggle
coordinate → applying it to all four fields → this end-to-end success).
SHG07's Wi-Fi + APN flow is now confirmed working end-to-end on real
hardware, the same milestone SHG10 reached 2026-09-11.

---

## SOG07 (Sony Xperia 10 IV, Android 14)

**Serial:** HQ632M1012
**Confirmed identity string (from adb):** not yet confirmed — client
identified the serial via `adb devices` + `getprop ro.product.model`, no
full session logged for this unit yet.

Config (`config/models/sony_xperia_10iv.yaml`) got real `wifi_settings`/
`apn_settings` data 2026-09-16 from client-supplied dumps. `wizard_steps`
remains 100% Stage A placeholder — no wizard data of any kind exists for
this unit.

### Test Log — exactly what was run against this unit

| Date | Test | Command | Result |
|---|---|---|---|
| | | | |

### Wi-Fi + APN screens — relevant to `wifi_setup.py`, `apn_setup.py`
- *2026-09-16:* Client supplied the same capture set SHG10 has:
  `wifi_list_SOG07.xml`, `apn_list_SOG07.xml`, `apn_entry_{top,middle,
  bottom}_SOG07.xml`, `apn_overflow_menu_SOG07.xml`. Every id/content-desc
  checked (Wi-Fi toggle, generic row title id, settings gear icon, APN
  list title, add button, overflow menu, navigate-up, save/cancel) is
  byte-identical to SHG10's real values — real, direct confirmation these
  are the plain, unskinned AOSP `com.android.settings` screens, not
  OEM-specific, now seen on a third real device and a second
  manufacturer.
- Implication: `config/models/sony_xperia_10iv.yaml`'s `wifi_settings`/
  `apn_settings` rewritten from Stage A's from-scratch invented
  placeholders to these real values, using the same labeled APN shape
  SHG10/SHG07 use (real dumps directly disprove the original per-field
  `name_field_resource_id`-style Stage A assumption for this device too).
- *2026-09-16:* One real, confirmed difference from SHG10: this device's
  combined Wi-Fi/mobile-network screen title renders via content-desc
  「インターネット」 ("Internet"), not SHARP's 「Wi-Fi とモバイルネットワーク」
  — evidently a SHARP-skin rename, not stock/Sony wording.
- Implication: `wifi_settings.menu_path`'s final fallback step uses this
  real value instead of copying SHG10's SHARP-specific title text.
- *2026-09-16:* Per-field dialog ids (`dialog_edit_field_resource_id`/
  `dialog_confirm_button_resource_id`/`dialog_cancel_button_resource_id`)
  remain genuinely unresolved for this device specifically — no dump of
  that dialog open exists. Inherited from SHG10's confirmed values
  (android:id/edit/button1/button2), better-justified than SHG07's
  original inheritance given the cross-device pattern above, but still
  not independently confirmed.
- *2026-09-17:* First live run hit the exact same kana-conversion IME
  symptom SHG07 had (full-width/kana characters typed into the APN
  fields instead of plain ASCII). Client confirmed this device's Gboard
  also needs the mode-toggle-key workaround. Coordinate found the same
  way as SHG07's: enabled Pointer Location, captured the toggle key's
  touch position (`[850, 0]` from an initial capture was rejected as
  unreliable — Y=0 didn't match the key's visible bottom-of-screen
  position, most likely a post-release reset reading, not a real touch;
  a redo holding the touch down for the screenshot gave `X:145.0
  Y:2308.0`), then confirmed via a scripted `adb shell input tap 145
  2308` (twice) + `input text "rakuten.jp"` test — client confirmed the
  field read back plain `rakuten.jp`, not a converted string.
- Implication: `keyboard_mode_toggle_tap: [145, 2308]` added to
  `config/models/sony_xperia_10iv.yaml`, tapped twice before every field
  (same pattern as SHG07 — applies to numeric fields too, since SHG07's
  MCC/MNC bug proved digits aren't universally immune). This is SOG07's
  own confirmed coordinate, tied to this exact unit's screen — never to
  be copied to another device.
- *2026-09-17 (same day, second finding):* A full run with the fix above
  in place still failed — every retry (3/3) hit the identical error at
  MCC: `typed '440' but the field now reads '４４０'`, 名前/APN
  unaffected. Root cause: MCC/MNC open a genuinely **different keyboard**
  than 名前/APN on this device — a client screenshot of the MCC field's
  keyboard showed a numeric-only keypad (1-9/0 grid), not the かな/英数
  text keyboard 名前/APN uses. It still has an "あ1"-style toggle key in
  the same bottom-left corner, but at a different X — Pointer Location
  read `X:93.0 Y:2300.0` while touching it, versus `X:145.0 Y:2308.0` for
  the text keyboard's toggle. The client's first instinct (reuse SHG07's
  approach of one shared coordinate) doesn't hold here: on SHG07 one
  coordinate happened to work for both keyboards; on this device it does
  not, and the existing log already showed what happens without a
  working numeric-keypad toggle (full-width digits) — proof that simply
  omitting the toggle (SHG10's approach) isn't a fix either, since
  SHG10's numeric keypad defaults to half-width and this device's
  evidently doesn't.
- Confirmed via the same scripted-test standard as every other
  coordinate: `adb shell input tap 93 2300` (twice) + `input text "440"`
  — client screenshot showed the field read back plain `440` and the
  keyboard had switched to an ABC/alphanumeric layout.
- Implication: `_fill_labeled_field()` (`src/phase2/apn_setup.py`) now
  reads a SEPARATE `keyboard_mode_toggle_tap_numeric` key for
  `numeric_only` fields, falling back to the shared
  `keyboard_mode_toggle_tap` when unset (keeps SHG07's profile, which
  only sets the one shared key, working unchanged).
  `config/models/sony_xperia_10iv.yaml` now has
  `keyboard_mode_toggle_tap_numeric: [93, 2300]`.
- Still not yet run to full end-to-end completion against real hardware
  with both coordinates in place — only the single-field scripted tests
  (name/APN and now MCC) have been confirmed so far.
- *2026-09-17 (third finding, same day):* A full automated run with
  `keyboard_mode_toggle_tap_numeric` in place still failed MCC —
  identically, on all 3/3 retries: `typed '440' but the field now reads
  '４４０'`. This time 名前/APN succeeded on every retry too (no longer a
  factor). Root cause: the numeric-keypad toggle coordinate itself IS
  correct (already independently confirmed via the scripted
  `input text "440"` test), but the *automated code's typing mechanism
  for MCC/MNC* is `input_digits_direct()` (per-digit `KEYCODE_<n>`
  keyevents), not `input text` — and on this specific keypad, the toggle
  only actually takes effect for `input text`; keyevent-typed digits kept
  committing full-width even after the identical toggle sequence. This is
  the exact mirror image of SHG10's original 2026-09-11 finding (there,
  `input text` was the broken mechanism for MCC/MNC and keyevents were
  the fix) — genuinely device/keyboard-dependent in both directions, not
  something to assume either way.
- Implication: `_fill_labeled_field()` now reads a new
  `use_text_entry_for_numeric` flag — when set, MCC/MNC use
  `input_text_direct()` instead of `input_digits_direct()`. Opt-in, so
  SHG10/SHG07 (proven correct with the original keyevent mechanism) are
  unaffected. `config/models/sony_xperia_10iv.yaml`:
  `use_text_entry_for_numeric: true`.
- Client also requested `--max-retries` be overridable from the CLI
  (previously hardcoded to config/settings.yaml's `retry.max_retries`,
  always 3) — useful while iterating on a real, repeatable failure like
  this one, where 3 identical retries just repeat the same result and
  waste time before the log is even visible. Added `--max-retries N` to
  `main_phase2.py` (`--max-retries 0` = a single attempt, no retries);
  defaults to the config value when omitted, and never modifies the
  config file itself.
- Still not yet run to full end-to-end completion against real hardware
  with all three fixes in place (numeric toggle coordinate + numeric
  text-entry mechanism + text-keyboard coordinate) — next real-hardware
  milestone.
- *2026-09-17 (fourth finding, same day):* with `use_text_entry_for_numeric`
  in place, the client reported the SAME full-width symptom persisting
  on MCC/MNC, and separately observed (watching the device live) what
  looked like the toggle key never being tapped at all before typing.
  Traced the exact shell-command sequence configure_apn() sends for the
  real SOG07 profile directly (`ModelProfile.load()` +
  `EchoingFakeAdbClient`, no guessing) — confirmed
  `input tap 93 2300` / `input tap 93 2300` / `input text "440"` fires
  exactly as expected; the toggle logic is genuinely present and
  executing, not missing. The likely explanation for what looked like
  "nothing happens": `adb shell input tap` produces no visible
  ripple/indicator at all unless Android's separate "Show taps"
  developer option is enabled (distinct from "Pointer location", which
  was already on) — a real, successful synthetic tap can be completely
  invisible on screen.
- The underlying full-width symptom, though, is real and still
  unexplained by anything in the code itself. Hypothesis (not yet
  confirmed): the toggle taps fire immediately after the field's edit
  dialog opens, with no pause for the on-screen keyboard's slide-in
  animation — unlike the manual scripted confirmation, where a human
  naturally pauses between commands. Added
  `_KEYBOARD_TOGGLE_TAP_DELAY_SECONDS = 0.5` — a deliberate wait
  immediately before every pair of toggle taps. Explicitly documented in
  code as a hypothesis pending real-hardware confirmation, not a proven
  fix — if a retest still shows the same symptom, this should be treated
  as ruled out, not kept "just in case."
- Also requested by the client: since `main_phase2.py` now retries the
  whole flow up to 3 times by default, and the SOG07 debugging in this
  session showed how that can hide/repeat an identical failure 3 times
  before it's visible, they were reminded to use `--max-retries 0` while
  iterating on a specific, repeatable issue like this one.
- **🎉 *2026-09-17 (fifth finding, same day): the client identified the
  actual real root cause.** From watching the automated run closely, the
  client determined the on-screen keyboard's mode-toggle key does NOT
  reset to a known state for each new field's dialog — it carries over
  from wherever the PREVIOUS field's typing left it. Their own account:
  名前 (starting from the dialog's initial state) lands correctly after
  the usual two taps; APN's two taps, applied on top of whatever state
  名前's typing left the keyboard in, still happens to land correctly;
  but by MCC (the third field typed into), the same fixed "tap exactly
  twice" overshoots past the correct mode, landing back in Japanese
  input and producing full-width digits. This is a coherent, real
  explanation for every previous SOG07 MCC/MNC finding this session —
  the numeric-keypad coordinate and the input_text_direct() mechanism
  fix were both real and necessary, but neither could succeed reliably
  while the code also assumed a fixed starting state that doesn't hold
  past the first field.
- There is no way to directly read the keyboard's actual current mode —
  confirmed unreachable via `uiautomator dump` (invisible keyboard,
  SHG07 finding) and `get_current_ime()` only reports the IME package,
  not its subtype. So instead of tracking or predicting the toggle's
  state machine, `_fill_labeled_field()` (`src/phase2/apn_setup.py`) now
  PROBES it empirically: type, read the field back (the verification
  that already existed), and if it doesn't match, clear the field (one
  backspace per character actually committed) and advance the toggle by
  one more single tap before retrying — up to
  `_KEYBOARD_TOGGLE_MAX_ATTEMPTS = 4` total attempts (the proven initial
  2-tap recipe, then up to 3 single-tap corrections) before giving up
  through the existing cancel/navigate-up cleanup path. Self-correcting
  regardless of the toggle's actual cycle length or starting state,
  without needing to inspect anything the accessibility tree can't see.
- Two new tests in `tests/test_apn_setup.py` using a new
  `_CyclingKeyboardModeClient` fake (models a toggle that persists its
  mode across separate field dialogs, unlike the existing
  `_EchoingEditFieldMixin`'s always-correct happy path): one confirms a
  field that starts in the wrong carried-over mode self-corrects and
  succeeds; the other confirms a toggle that never reaches the correct
  mode within the attempt budget still fails loudly rather than looping
  forever or accepting a wrong value.
- *2026-09-17 (sixth finding, same day): efficiency feedback from the
  client.* Retyping the ENTIRE MCC/MNC value on every toggle-correction
  attempt was needlessly slow — the client asked whether the keyboard's
  current mode could be detected directly to avoid this. Confirmed (again)
  that it can't: the on-screen keyboard is invisible to `uiautomator
  dump`, and `get_current_ime()` only reports the active IME package, not
  its internal mode — this かな/英数 toggle is Gboard's own private UI
  state, not something Android's IME-subtype framework tracks at all, so
  there's no system API surface left to query. Instead, `_fill_labeled_field()`
  now probes with only the value's OWN FIRST DIGIT for numeric_only
  fields — digits commit immediately per keystroke, with no multi-key
  romaji composing delay the way letters can have, so a single digit
  reliably reveals the current mode. Only once that probe is confirmed
  correct is the rest of the value typed, once, for real — cutting a
  wrong attempt's cost from "retype + clear the whole value" down to
  "retype + clear one digit." Deliberately NOT applied to 名前/APN:
  romaji-based composing can delay when a character actually commits, so
  a single-letter probe wouldn't be as reliable, and neither field has
  needed a second attempt in any real run so far.
- Refactored the retry loop into a reusable `_toggle_and_type_with_retry()`
  closure and factored the cancel/navigate-up cleanup into a shared
  `_cleanup_mismatched_field_dialog()` helper, so the new probe-based
  numeric path and the existing full-value path (still used for
  non-numeric fields) share the same tested mechanics rather than
  duplicating them.
- Fixed a real bug this surfaced in the TEST DOUBLES (not production
  code): `_EchoingEditFieldMixin` and `_CyclingKeyboardModeClient` both
  modeled `input text` as REPLACING the field's content, which was
  harmless when a field was only ever typed into once but wrong for two
  separate `input text` calls on the same field (the new probe-then-rest
  design) — a real device's `input text` appends at the cursor, it never
  clears first. Fixed both to append; three existing test assertions
  that had baked in the old (now-corrected) per-numeric-field call counts
  were updated to match.
- New dedicated test,
  `test_fill_labeled_field_numeric_probe_only_retypes_first_digit_on_wrong_attempt`,
  confirms MCC only retypes/clears its first digit on a wrong attempt,
  never the whole value.

### 🎉 First successful end-to-end Phase 2 run on real SOG07 hardware (2026-09-17)

Client run: `SUCCESS: device HQ632M1012 reached LOGIN_INSTALL` — Wi-Fi
(already connected, correctly detected and skipped), APN navigation, all
four fields (including MCC/MNC with the self-correcting toggle + single-digit
probe), and the save itself all completed successfully, with no
field-mismatch errors of any kind. Only the existing soft post-save
list-visibility warning appeared (`'rakuten.jp' wasn't spotted back on
the APN list` — same known, harmless list-refresh-timing quirk as
SHG10/SHG07, not a real failure). This is the first full success on
SOG07 in the whole project, confirming every fix from this session
(numeric-keypad toggle coordinate, `use_text_entry_for_numeric`,
self-correcting retry loop, single-digit probe) together on real
hardware.

**Follow-up client feedback, same day:** asked whether the brief visible
"wrong value, then corrected" flicker during a toggle-correction could
be avoided by validating the keyboard's mode internally instead of on
the visible field. Confirmed this isn't achievable: there is no signal
available to check the mode without actually typing into the real field
and reading back what landed — the keyboard (including its own toggle
key's label) is invisible to `uiautomator dump`, and no other system API
exposes this Gboard-internal state. The only way to eliminate the
flicker entirely would be clipboard-based paste entry (bypasses
composing altogether, so there's never a "wrong" value to type in the
first place), which needs a helper app or substantial custom code —
presented as an option; **client chose to keep the current behavior**
(the flicker is a single character, visible for about one ADB
round-trip, and is never saved/confirmed either way).

**SOG07 is now considered CONFIRMED WORKING end-to-end**, on par with
SHG10 and SHG07. Not yet done: the same full treatment for SOG08 (its
own MCC/MNC toggle coordinate and typing-mechanism confirmation — see
PENDING_REAL_DEVICE_DATA.md).

## SOG08 (Sony Xperia Ace III, Android 13)

**Serial:** HQ63460161
**Confirmed identity string (from adb):** not yet confirmed — same as
SOG07, serial identified via `adb devices` + `getprop ro.product.model`,
no full session logged for this unit yet.

Config (`config/models/sony_xperia_ace3.yaml`) got the same treatment as
SOG07, same day, from its own real dumps. `wizard_steps` remains 100%
Stage A placeholder.

### Test Log — exactly what was run against this unit

| Date | Test | Command | Result |
|---|---|---|---|
| | | | |

### Wi-Fi + APN screens — relevant to `wifi_setup.py`, `apn_setup.py`
- *2026-09-16:* Same capture set and same finding as SOG07: every
  id/content-desc checked in `wifi_list_SOG08.xml`, `apn_list_SOG08.xml`,
  `apn_entry_{top,middle,bottom}_SOG08.xml`, `apn_overflow_menu_SOG08.xml`
  is byte-identical to SHG10's and SOG07's real values — the same plain
  AOSP screens confirmed on a fourth real device now.
- Implication: `config/models/sony_xperia_ace3.yaml` rewritten the same
  way as SOG07's, same labeled APN shape, same real values.
- *2026-09-16:* Same confirmed Wi-Fi screen title difference from SHG10:
  「インターネット」, not 「Wi-Fi とモバイルネットワーク」.
- *2026-09-16:* This capture's MCC/MNC fields show 「未設定」 (not set) —
  a blank entry, not evidence the fields are absent; confirms they exist
  and are readable either way, same as every other model checked.
- *2026-09-16:* Per-field dialog ids remain unresolved for this device
  specifically too, inherited from SHG10 with the same cross-device
  justification as SOG07's identical note.
- *2026-09-17:* Same symptom as SOG07 hit on the first live run (kana
  conversion in the APN fields). Coordinate found the same way: a
  Pointer Location capture gave `X:78.0 Y:1356.0`, a redo (holding the
  touch during the screenshot) gave a consistent `X:73.0 Y:1352.0` —
  close agreement between the two independent captures, a good sign the
  reading is real. Confirmed via a scripted `adb shell input tap 73
  1352` (twice) + `input text "rakuten.jp"` test — client confirmed the
  field read back plain `rakuten.jp`.
- Implication: `keyboard_mode_toggle_tap: [73, 1352]` added to
  `config/models/sony_xperia_ace3.yaml`, same unconditional
  tap-twice-before-every-field pattern as SOG07/SHG07. This device's own
  confirmed coordinate — never to be copied elsewhere.
- Not yet run to full end-to-end completion with this fix in place —
  same caveat as SOG07 above.

---

## Dump capture status (all models)

| Model | Wi-Fi list | APN list | APN entry | APN save flow | Wizard (OOBE) |
|---|---|---|---|---|---|
| SHG10 (352063910272451) | ✅ `wifi_list_SHG10.xml` (31,516 B) | ✅ `apn_restricted_SHG10.xml` (6,104 B), `apn_failure_setting_SHG10.xml` (6,104 B, identical), `apn_success_setting_SHG10.xml` (10,009 B, 2 entries) | ✅ `apn_entry_top_SHG10.xml` (17,785 B), `apn_entry_middle_SHG10.xml` (21,981 B), `apn_entry_bottom_SHG10.xml` (20,608 B), `apn_entry_filled_SHG10.xml` (21,988 B), `apn_accesshost_okbtn_SHG10.xml` (per-field dialog, open) | ✅ `apn_overflow_menu_SHG10.xml` (3,839 B), `apn_mcc_validation_SHG10.xml` (5,085 B), `apn_mnc_validation_SHG10.xml` (5,092 B) | ❌ **not obtainable remotely** — see constraint analysis below. Photos only. |
| Xperia Ace III (SOG08) | ✅ `wifi_list_SOG08.xml` (31,228 B) | ✅ `apn_list_SOG08.xml` (6,443 B) | ✅ `apn_entry_top_SOG08.xml` (16,057 B), `apn_entry_middle_SOG08.xml` (18,786 B), `apn_entry_bottom_SOG08.xml` (19,544 B) | ✅ `apn_overflow_menu_SOG08.xml` (3,826 B) | ❌ same constraint applies |
| Xperia 10 IV (SOG07) | ✅ `wifi_list_SOG07.xml` (40,051 B) | ✅ `apn_list_SOG07.xml` (6,458 B) | ✅ `apn_entry_top_SOG07.xml` (19,518 B), `apn_entry_middle_SOG07.xml` (22,347 B), `apn_entry_bottom_SOG07.xml` (22,351 B) | ✅ `apn_overflow_menu_SOG07.xml` (3,839 B) | ❌ same constraint applies |
| AQUOS sense6s (SHG07, 353681650397052) | ❌ not started | ❌ not started | ✅ `apn_input_dialog_SHG07.xml` (APN field dialog, open) | ❌ not started | ❌ same constraint applies |

Original 4 SHG10 files captured 2026-09-04. 4 more (save flow + a filled
entry form) captured 2026-09-08, same session as the Save flow findings
above. `apn_restricted_SHG10.xml` (the APN *list* screen itself — the
piece missing from every earlier capture, which only ever reached the edit
*form*) added 2026-09-11 — see the dated entry above for what it resolved.
`apn_accesshost_okbtn_SHG10.xml` (the per-field entry dialog itself, open
mid-edit) also added 2026-09-11 — resolved `dialog_edit_field_resource_id`/
`dialog_confirm_button_resource_id` for real. `apn_accesshost_SHG10.xml`/
`apn_accesshost_save_SHG10.xml`, supplied the same day, are byte-identical
to `apn_entry_top_SHG10.xml`/`apn_overflow_menu_SHG10.xml` respectively —
kept for provenance, not listed separately above. `apn_failure_setting_
SHG10.xml`/`apn_success_setting_SHG10.xml` added 2026-09-11 (later the
same day) — a before/after pair for a still-failing save attempt; the
"failure" file is itself byte-identical to `apn_restricted_SHG10.xml`
(confirms no entry was created), and the "success" file (a manual save,
for comparison) surfaced the `config/network.yaml.example` placeholder-
leak finding — see the dated entry above.

Capture pattern used:
```
adb -s <serial> shell uiautomator dump /sdcard/<name>.xml
adb -s <serial> pull /sdcard/<name>.xml <name>_<MODEL>.xml
```
Files collected in `C:\scrcpy\dumps` on the client PC; destined for
`tests/fixtures/` in the repo via git.

---

## Wizard capture — RESOLVED AS NOT REMOTELY POSSIBLE (2026-09-08)

**Status: all remote methods exhausted. Do not re-test these.**

### The real OOBE sequence (confirmed by client photos, 2026-09-08)

The client factory-reset the unit and photographed every screen. Confirmed
order:

1. SHARP logo → AQUOS logo → SIM/microSD tray warning screen
2. **「ようこそ」** — language (日本語(日本)), 視覚補助, start button
3. **「キャリア設定中」** — carrier config spinner (carrier-injected)
4. **「Wi-Fiに接続」** — 「すべてのWi-Fiネットワークを表示」/「新しいネットワーク
   を追加」/「設定時にモバイルネットワークを使用」, **「オフラインで設定」**
   bottom-left
5. **「オフラインで設定しますか?」** dialog — 戻る / 続行
6. **「セットアップを続けますか?」** — 続行 /「中断し、リマインダーを受け取る」
7. Google services / terms (scrollable) → 「同意する」
8. **「ソフトウェア更新について」** — SHARP-specific
9. **「スマートフォンを設定しています」** — provisioning spinner
10. **「AQUOS Homeの通知アクセス」** — SHARP-specific dialog, OK
11. Home screen

**Key finding — account sign-in is NOT a blocking screen.** The client took
the 「オフラインで設定」 path and Google account login never appeared. This
matches the client's real workflow (manual login ~5 days after
initialization). `wizard_walkthrough.py` likely only needs the offline path.
**Confirm with client that offline-setup is standard for all devices** — it
substantially narrows what needs automating.

### Confirmed reset menu path (SHARP skin)
**設定 → システム → リセット オプション → すべてのデータを消去（初期設定に
リセット）→ すべてのデータを消去** (confirm dialog 「すべてのデータを消去
しますか?」).
Note: **開発者向けオプション sits directly above リセット オプション under
システム** on this model — not a top-level item.

### Why remote dumping is impossible — 4 methods tested, all failed

| # | Method | Result |
|---|---|---|
| 1 | `settings put global device_provisioned 0` + `user_setup_complete 0` + reboot | Flags accepted, but SHARP's build ignores them — boots straight to home screen. Tried twice. |
| 2 | `am start com.google.android.setupwizard/.deferred.DeferredSetupWizardActivity` | `SecurityException: Permission Denial ... requires com.google.android.setupwizard.SETUP`. `SETUP` is a **signature-level** permission — cannot be granted via `pm grant`, no non-root workaround. (XDA reports of this working are Android 10–13; A14 tightened it.) |
| 3 | `am start` on SHARP's `jp.co.sharp.android.setupwizard` activities | **No SecurityException** — SHARP's package is not permission-guarded. But every activity exits silently without rendering. Tried: `CheckDeferrendSetupActivity`, `GotaConsentToUseActivity`, `GmsSetupWizardActivity`, `SettingDefaultHomeActivity`, `SkipFaceUnlockActivity`. |
| 4 | Flags at `0` **combined with** activity launch (the untested gap) | Flags verified as `0`, nav bar lost home/recents buttons (system genuinely treated device as unprovisioned) — but **「Androidの設定」が繰り返し停止しています**: Settings entered a crash loop. No wizard. Had to restore flags + reboot to recover. |

**Structural reason:** `WizardManagerActivity` orchestrates the flow and only
runs at genuine first boot. Individual activities check state, find setup
complete, and exit. Forcing the state destabilizes the system rather than
re-entering the flow.

**And the deeper constraint:** even a real factory reset doesn't help, because
the reset wipes ADB authorization. `uiautomator dump` requires ADB. From wipe
until someone manually re-enables USB debugging and taps 「許可」 on-device,
there is no ADB channel — and by then the device has reached the home screen
and the wizard is gone. ADB access and wizard visibility cannot coexist.

### Discovered activity names (useful for detection logic even without ids)

`jp.co.sharp.android.setupwizard/` — `SettingDefaultHomeActivity`,
`GotaConsentToUseActivity` (likely 「ソフトウェア更新について」),
`CheckDeferrendSetupActivity`, `GmsSetupWizardActivity`,
`SkipFaceUnlockActivity`, `CheckBYODActivity`

`com.google.android.setupwizard/` — `WizardManagerActivity`,
`user.WelcomeActivity` (=「ようこそ」), `user.GestureIntroActivity`,
`carrier.SlotsSelectionActivity`, `carrier.MobileDataActivity`
(=「キャリア設定中」), `update.OtaUpdateActivity`,
`provision.*`, `portal.PortalProgressActivity`, `restore.GetRestoreFlowActivity`

### Chosen approach for `wizard_walkthrough.py`
1. Build navigation logic from the photographed screen order above — order,
   labels, and button positions are all known.
2. Use standard Google SetupWizardLib ids as best guesses, tagged
   **`TODO(real-device, best-guess-standard-id)`** to distinguish "probably
   right, unverified" from "pure placeholder".
3. **Fail loudly** on a missed match rather than tapping blindly — consistent
   with the existing `AmbiguousResourceIdError` philosophy, and important
   given the USB-debugging-disable notification hazard.
4. Resolve real ids during Phase 2 on-site testing: the walkthrough will fail
   at the first mismatched screen and log which one, replacing placeholders
   device by device. This costs nothing extra — it happens during testing
   that's needed anyway.

**Caveat on standard ids:** screens 3, 8, and 10 above are SHARP/carrier-
specific and will NOT match generic SetupWizardLib ids. Expect these to need
resolution via method 4. Also expect the sequence to differ on the Xperia
models.

### Operational note for Phase 2/3
`adb shell svc power stayon usb` prevents screen timeout while cabled. Devices
sitting idle mid-workflow would otherwise sleep and interrupt UI automation —
worth doing as part of device prep in the orchestration layer.

---

## IMPLEMENTATION SPEC — wizard via text matching (2026-09-08)

Everything below is code-ready. Derived from the client's screen photos, so
**visible text is known and reliable; resource-ids are not available.**

### Why text matching, not resource-ids

A resource-id (e.g. `com.google.android.setupwizard:id/start_button`) is an
internal view-hierarchy identifier. It is **never rendered on screen**, so no
photo of any quality contains it. `uiautomator dump` reads it via the
accessibility layer, which needs ADB — unavailable during OOBE (see constraint
analysis above).

Visible **text labels** are in the photos, and `ui_automator.py` already has
`find_by_text` / `tap_by_text` (added in Stage A for Settings menu
navigation). So the wizard is driven by text where labels are unique, with
best-guess ids only as fallback.

### Per-screen strings (SHG10, offline path)

| # | Screen identifier text | Action target text | Notes |
|---|---|---|---|
| 1 | (SIM/microSD tray warning) | — | Transient; may auto-dismiss. Treat as skippable. |
| 2 | `ようこそ` | (start button) | **Button label not legible in photo — needs verification.** Language already 日本語(日本) by default. |
| 3 | `キャリア設定中` | — | Spinner, no interaction. Wait-for-disappear. |
| 4 | `Wi-Fiに接続` | `オフラインで設定` | Bottom-left. **This is the branch point** that keeps the flow offline. |
| 5 | `オフラインで設定しますか?` | `続行` | Dialog. Other button is `戻る` — do NOT tap. |
| 6 | `セットアップを続けますか?` | `続行` | Other button is `中断し、リマインダーを受け取る` — do NOT tap. |
| 7 | (Google services / terms) | `同意する` | **Scrollable** — may need scroll-to-bottom before the button is reachable. |
| 8 | `ソフトウェア更新について` | (confirm button) | SHARP-specific. **Button label not legible in photo — needs verification.** |
| 9 | `スマートフォンを設定しています` | — | Spinner, no interaction. Wait-for-disappear. |
| 10 | `AQUOS Homeの通知アクセス` | `OK` | SHARP-specific dialog. |
| 11 | (home screen) | — | Terminal state — detect and exit. |

**Unverified items (flag as TODO in code):** screens 2 and 8 button labels.
The photos show the buttons but the text is not readable. Either confirm with
the client on the next reset, or match by position/index as a fallback.

### Proposed YAML schema addition

```yaml
wizard:
  screens:
    - name: welcome
      identify_by_text: "ようこそ"
      action: tap_by_text
      target_text: "開始"        # TODO(verify) — not legible in photo
    - name: carrier_setup
      identify_by_text: "キャリア設定中"
      action: wait_for_disappear
      timeout_sec: 120
    - name: wifi_connect
      identify_by_text: "Wi-Fiに接続"
      action: tap_by_text
      target_text: "オフラインで設定"
    - name: offline_confirm
      identify_by_text: "オフラインで設定しますか?"
      action: tap_by_text
      target_text: "続行"
    - name: continue_setup
      identify_by_text: "セットアップを続けますか?"
      action: tap_by_text
      target_text: "続行"
    - name: google_terms
      identify_by_text: "同意する"
      action: scroll_then_tap_by_text
      target_text: "同意する"
    - name: software_update
      identify_by_text: "ソフトウェア更新について"
      action: tap_by_text
      target_text: "TODO(verify)"
    - name: provisioning
      identify_by_text: "スマートフォンを設定しています"
      action: wait_for_disappear
      timeout_sec: 300
    - name: aquos_notify
      identify_by_text: "AQUOS Homeの通知アクセス"
      action: tap_by_text
      target_text: "OK"
```

### Design requirements for `wizard_walkthrough.py`

- **Screen-driven, not sequence-driven.** Identify which screen is present by
  text, then act. Do not assume a fixed order — carrier/OTA screens may appear
  conditionally depending on network state.
- **Fail loudly on unrecognized screens.** Log the full text content of the
  unknown screen so the label can be added to config. Never tap blindly.
  Consistent with the existing `AmbiguousResourceIdError` philosophy.
- **Never tap near the USB-debugging notification** (see UI hazard section) —
  a mistap disables ADB and strands the device.
- **Spinner screens need wait-for-disappear, not tap.** Screens 3 and 9.
- **The 「戻る」/「中断」 buttons must never be tapped** — they reverse or abort
  the flow. Explicitly exclude these strings from any fuzzy matching.
- Text matching should be exact or prefix-based, not substring — 「続行」
  appears on multiple screens and must be disambiguated by the screen
  identifier, not matched globally.

### Screenshot storage (reference material, not test fixtures)

Photos are **not** test fixtures (no test parses them). Store under docs:

```
docs/
├── record.md
└── screens/
    └── shg10/
        └── wizard/
            ├── 01_welcome.jpg
            ├── 02_carrier_setup.jpg
            ├── 03_wifi_connect.jpg
            ├── 04_offline_confirm.jpg
            ├── 05_continue_setup.jpg
            ├── 06_google_terms.jpg
            ├── 07_software_update.jpg
            ├── 08_provisioning.jpg
            └── 09_aquos_notify.jpg
```

Numbering matches the sequence above so the two cross-reference.

**Privacy caution before committing:** several client photos show clear
reflections of the person holding the camera in the phone's screen. Crop
before committing, or keep the photos out of git entirely and rely on this
file's text description.

---

## Overall status (as of 2026-09-08, end of day)

- **Stage A: complete.** All config YAMLs, `src/device/`, `src/phase2/`,
  `src/orchestration/`, `src/main_phase2.py`, plus `PENDING_REAL_DEVICE_DATA.md`
  and `README.md`. Test suite has grown well past the original 30 as Stage B
  work landed (110 passing as of this entry, still ~1s, no real device needed).
- **Stage B for SHG10: Wi-Fi and APN (including Save) resolved and tested
  against real captures.** Wizard remains on the photograph-derived
  screen-driven config, blocked only on the two button labels noted above —
  everything else about it is implemented and tested.
- **Completed since the "ready to start" entry above:**
  1. ✅ 8 real dumps now in `tests/fixtures/` (the original 4 plus
     `apn_overflow_menu_SHG10.xml`, `apn_mcc_validation_SHG10.xml`,
     `apn_mnc_validation_SHG10.xml`, `apn_entry_filled_SHG10.xml`).
  2. ✅ `PENDING_REAL_DEVICE_DATA.md` updated with real SSID pairs, then
     updated again as Save/MCC/MNC resolved.
  3. ✅ Wi-Fi + APN resource-ids resolved and tested (`tests/test_real_shg10_fixtures.py`,
     `tests/test_wifi_setup.py`, `tests/test_apn_setup.py`).
  4. ✅ MCC/MNC confirmed mandatory; Save flow fully resolved (two-tap
     overflow menu, sequential blocking validation) — see the APN settings
     section above.
  5. ⏳ `wizard_walkthrough.py` built (screen-driven, text-matching,
     best-guess ids where needed) — implemented and tested, but 2 of 9
     screens' button labels are still unverified, so a real end-to-end
     wizard run hasn't happened yet.
  6. ⏳ Still not confirmed with the client: is 「オフラインで設定」 standard
     for all devices?
  7. ⏳ Not started: dump capture for SOG08/SOG07/SHG07.
- **New since this entry started:** real hardware surfaced two pure code
  bugs (adb path resolution, UTF-8 decoding — see "Real-device bugs" above)
  neither of which was a device-data gap; both are fixed. Also added
  `--skip-wizard` (testing convenience) and the `WIFI_SETTINGS` intent
  navigation shortcut (robustness improvement, not device-data).
- **Actual current blocker for a full SHG10 run:** real Wi-Fi credentials —
  see "Highest priority" in `PENDING_REAL_DEVICE_DATA.md`. Everything else
  in the Wi-Fi → APN chain is implemented, tested, and has gotten as far as
  it can without a real network to join.
- **Schema note (carried from Stage A, now fully resolved for SHG10):** the
  6 fields added in Stage A plus several more added during Stage B are all
  documented in `PENDING_REAL_DEVICE_DATA.md`'s "Schema additions" section.
  MCC/MNC turned out to exist and be mandatory (not absent, as an earlier
  entry above speculated) — see the APN settings section.

---

## Template for a new device section

## <MODEL> (<manufacturer>, <carrier branding>, Android <version>)

**Serial:**
**Confirmed identity string (from adb):**

### Test Log — exactly what was run against this unit

| Date | Test | Command | Result |
|---|---|---|---|
| | | | |

### <Category> — relevant to `<file or component>`
- *<date>:* <what was observed>
- Implication: <why it matters for the code/config>
