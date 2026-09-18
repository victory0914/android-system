# Pending Real-Device Data

Tracks every placeholder value and open assumption still needing real-device
confirmation, so work can resume cleanly without re-deriving what's
outstanding. See `docs/record.md` for the full session notes (test logs,
navigation paths, capture methodology, judgment calls) behind every entry
here — this file is the checklist; that one is the evidence.

**🎉🎉🎉 Status as of 2026-09-17: ALL FOUR MODELS (SHG10, SHG07, SOG07,
SOG08) are CONFIRMED WORKING end-to-end on real hardware.** SOG08's first
live run succeeded on the very first attempt, no field-mismatch errors —
notably without needing SOG07's MCC/MNC-specific
`keyboard_mode_toggle_tap_numeric`/`use_text_entry_for_numeric` fixes
(unconfirmed whether that's a real device difference or this run just
got lucky — see docs/record.md's SOG08 section).

**Client decision, same day: the setup wizard is permanently out of
scope.** It cannot be automated via ADB at all (factory reset wipes ADB
authorization until a human completes the wizard). The client performs
factory reset + the wizard manually for every device; this automation
covers everything after that via `--skip-wizard`, now the standard way
to invoke a real run — see README.md and `docs/record.md`'s SOG08
section for the full account. Every wizard-related "still outstanding"
item below (SHG10's 2 unverified button labels, wizard data for
SOG07/SOG08/SHG07) is now moot — kept in this file for history, not
because it's still being pursued.

**Multi-device parallel processing already exists** (`--device
SERIAL:MODEL`, repeatable, built 2026-09-14) — confirmed working for all
4 devices at once with one command:
```
python src\main_phase2.py --skip-wizard \
  --device 352063910272451:SHG10 --device 353681650397052:SHG07 \
  --device HQ632M1012:SOG07 --device HQ63460161:SOG08
```

**🎉 Update, same day (2026-09-17): running that exact 4-device parallel
command surfaced a real finding — SHG10 was never actually immune to
the かな-conversion symptom.** It hit the identical `名前` full-width
failure SHG07/SOG07/SOG08 needed fixes for, on all 3/3 retries, while
the other three devices in the same run succeeded. Confirmed this
wasn't a parallel-execution bug first (checked `dump_ui()`'s
UUID-unique temp paths and `AdbClient`'s per-serial subprocess calls —
nothing shared across threads). Real conclusion: SHG10's keyboard mode
is persistent, drift-able state, and its 2026-09-11 success only proved
it was in the right mode *that day* — not that this device is
structurally different from the others. Found and confirmed its own
`keyboard_mode_toggle_tap: [119, 2223]` the same way as every other
device (Pointer Location + scripted `adb shell input tap` +
`input text` test); the existing self-correcting retry/probe mechanism
picked it up automatically, no other code changes needed. **Every other
"confirmed working" device should be read as "confirmed working that
day," not permanently immune** — worth remembering if any of them show
this symptom on a future run. See docs/record.md's SHG10 section for
the full account.

**🎉 Update, 2026-09-18: fixed a real bug in the post-save soft check
itself.** After the SHG10 fix above, a re-run of that same 4-device
parallel command logged the `'rakuten.jp' wasn't spotted back on the APN
list` warning for all 4 devices again — but this time the client
independently checked all 4 devices' actual APN lists and confirmed the
entry genuinely wasn't there, the first time this known-since-2026-09-11
warning turned out to be a real problem, not a false negative. Client
diagnosis (confirmed correct): the `_save_apn()` re-navigation step
(re-sending `android.settings.APN_SETTINGS` to force a reload) most
likely just re-foregrounds the already-running, possibly stale Settings
Activity rather than actually reloading it. Fixed: `am force-stop
com.android.settings` now runs immediately before that re-navigation
intent. Shared code, applies to every model. See docs/record.md's "Real
hardware bugs found running the automation" section for the full
account. **Not yet re-confirmed on real hardware with this fix in
place** — next thing to retest.

**🎉🎉 Update, 2026-09-18: found the ACTUAL root cause — wrong screen,
not a refresh-timing issue.** The force-stop fix above didn't help,
because the real problem was never about staleness: `android.settings.
APN_SETTINGS` reaches a DIFFERENT, non-authoritative APN screen than the
one the client sees when manually checking (Settings > Network &
internet > SIM > Rakuten > "アクセス ポイント名"). Client supplied a real
dump of that carrier-specific screen (`mobile_network_SHG07.xml`),
proving "アクセス ポイント名" (with a space) is a genuinely real,
tappable row — distinct from "アクセスポイント名" (no space, the
destination screen's own title), which an earlier version of this
project mistakenly concluded wasn't tappable at all. Fixed:
`apn_settings.reach_via_wifi_settings_intent: true` (SHG07, SHG10) now
routes navigation through `android.settings.WIFI_SETTINGS` + the real
gear-icon + "アクセス ポイント名" taps instead of the old intent. See
docs/record.md's new SHG07 subsection for the full account.

**🎉 Update, same day: SOG07/SOG08 fixed too.** Client supplied a real
dump of SOG08's own carrier-settings screen (`mobile_network_SOG08.xml`)
confirming the identical byte-for-byte pattern as SHG07's — "アクセス
ポイント名" (with a space) is real and tappable there too.
`reach_via_wifi_settings_intent` now set on all 4 models
(`sony_xperia_ace3.yaml` directly confirmed; `sony_xperia_10iv.yaml`
inherited from SOG08's confirmation, same basis as every other
SOG07↔SOG08 shared value).

**🎉 Update, same day: fixed why the final tap wasn't landing even on
SHG07/SHG10.** Client reported "not possible to click on アクセス
ポイント名" even where navigation otherwise reached the right screen.
Root cause, confirmed by the SOG08 dump: this row sits right at the very
bottom screen edge — `android:id/navigationBarBackground` starts at the
EXACT y-coordinate where the row's own bounds end, so a tap at its
center risks being consumed by the system nav bar instead of the app.
Fixed: `_navigate_apn_menu()` now scrolls down once before tapping this
final step, for every model using `reach_via_wifi_settings_intent`.

**🎉 Update, same day: navigation + scroll fix both confirmed working on
all 4 devices in a real parallel run** — every device logged
`reached APN list via the SIM-scoped menu_path` and reached
`LOGIN_INSTALL`. **But** the client then found all 4 devices sitting on
the OLD, wrong, restricted screen afterward — root cause: `_save_apn()`'s
post-save recheck still hardcoded the old `android.settings.APN_SETTINGS`
intent in its own fallback, completely independent of
`_navigate_apn_menu()`'s fix, silently undoing it right at the end of
every run. Fixed: that fallback now calls `_navigate_apn_menu()` itself
instead of a second, hardcoded copy of the old intent — can't drift out
of sync again. See docs/record.md's new dated entry for the full
account.

**🎉 Update, same day, next real test: navigation is fully confirmed
correct on all 4 devices** — the log showed `reached APN list via the
SIM-scoped menu_path` exactly twice per device (initial + post-save
recheck) and all 4 reached `LOGIN_INSTALL`. **SHG10, SHG07, and SOG08 all
genuinely saved the entry correctly** (client confirmed manually) — the
soft "wasn't spotted" warning on those three was just the original,
harmless 2026-09-11 list-refresh timing gap, now confirmed real on the
*correct* screen.

**REMOVED the 3rd-tier force-stop+re-navigate fallback entirely**
(client feedback): even reaching the correct screen, the visible
round-trip (leaving the APN list, flashing through intermediate
navigation screens, landing back on it) wasn't worth the disruption for
a check that's soft either way. `_save_apn()` is back to the simpler
2-tier check (immediate + one delay+re-dump retry, no navigation).

**⚠️ SOG07 is the one exception — the entry genuinely does not save,
confirmed missing by the client's manual check, even though manual
by-hand entry works fine.** No error anywhere in the log; every field's
own read-back check passed. SOG07 is the only model using
`use_text_entry_for_numeric` (a probe-then-rest, two separate
`input text` calls into the same MCC/MNC field) — every other model
uses `input_digits_direct()` keyevents there instead.

**Update, same day: real evidence obtained from an isolated single-device
SOG07 run.** Log showed no errors, normal timing, `reached LOGIN_INSTALL`
— but the client's screenshot afterward showed the APN list with only
the two pre-existing carrier entries and **no `rakuten.jp` at all**
(genuinely absent, not corrupted; neither pre-existing entry was
overwritten either). Consistent with Android's own save-time validation
silently rejecting the whole entry.

**RULED OUT, same day**: the commit-delay hypothesis
(`_NUMERIC_TEXT_ENTRY_COMMIT_DELAY_SECONDS`) — client retested, identical
result. Removed, per this project's standing rule not to keep an
unconfirmed fix once it's been directly disproven.

**New lead, same day: possible SIM/carrier mismatch.** `config/
network.yaml` supplies ONE shared APN/MCC/MNC value set for all 4
devices — no per-device carrier config exists. SOG07's APN list already
shows **OCNモバイルONE** and **docomo** entries, not Rakuten — raising
the question of whether SOG07's real installed SIM is a different
carrier than the Rakuten values (`rakuten.jp`, MCC 440, MNC 11) being
entered for every device. If Android validates a new APN's MCC/MNC
against the active SIM's own MCC/MNC and they don't match, that alone
would explain a silent, no-dialog rejection — consistent with every
other observation so far. Asked the client to check via
`adb shell getprop gsm.sim.operator.alpha` /
`getprop gsm.sim.operator.numeric` on SOG07 (ideally compared against a
working device). Not yet confirmed either way. See docs/record.md's
SOG07 section for the full account.

**Status as of 2026-09-11 (Stage B): 🎉 SHG10's Phase 2 flow (Wi-Fi + APN)
is CONFIRMED WORKING end-to-end on real hardware.** Client run:
`SUCCESS: device 352063910272451 reached LOGIN_INSTALL` — Wi-Fi (already
connected, correctly detected and skipped), APN navigation, the "+" tap,
all four fields, and the save itself all completed successfully in one
real run, and the client independently confirmed by manually reopening
the APN list that `rakuten.jp` was genuinely saved and selected. This is
the first time the full chain has worked all the way through — every
"re-verify against real hardware" entry that used to be tracked here is
now confirmed (see "Resolved — full Phase 2 run confirmed end-to-end"
below for the complete account of what got this here).

One wrinkle, fixed same-day: the automation's own post-save soft check
warned `'rakuten.jp' wasn't spotted back on the APN list`, even though the
save had genuinely succeeded — the list can take a moment to actually
refresh after 保存, and the very next dump can still show the pre-save
state. Not a real failure (the check is soft — it never blocks success on
its own), but misleading. `_save_apn()` now retries the check once after
a short delay before giving up. See "Resolved" below.

**Update, 2026-09-15: SHG10's known-working state above is restored.**
`use_keyevent_text_entry: true` was briefly set on SHG10 too (client
request, "same input method across every device"), then reverted the same
day once further investigation showed the theory behind it was wrong (see
below) — SHG10's config is back to exactly what it was during the
2026-09-11 success (`input_text_direct()` for 名前/APN, no regression
risk remains).

**🎉 Update, 2026-09-15: SHG07's Phase 2 APN flow is CONFIRMED WORKING
end-to-end on real hardware too.** Client run:
`SUCCESS: device 353681650397052 reached LOGIN_INSTALL` — 名前/APN/MCC/MNC
all committed correctly (the keyboard-mode-toggle fix, this same day) and
`rakuten.jp` was genuinely saved. The client-reported "list appears
empty right after saving, but re-checking settings confirms it's really
there" is the same list-refresh-timing quirk already known from SHG10
(2026-09-11) — not a data-correctness problem, just a slower refresh than
the existing retry accounted for; `_save_apn()`'s soft post-save check now
also re-navigates (a fresh `APN_SETTINGS` intent) if waiting alone still
doesn't find the entry. See "🎉 SHG07 text entry: real fix found..." below
for the full account of how SHG07's text-entry problem was actually
solved.

SHG10's wizard is on a photograph-derived, text-matching config — real
dumps for the wizard are **not obtainable on any model, ever** (structural
ADB/factory-reset constraint, see docs/record.md); 2 of 9 screens' button
labels are still unverified.

**🎉 Update, 2026-09-16: SOG07 and SOG08's Wi-Fi + APN data is now real,
not Stage A placeholders.** Client supplied real dumps for both (wifi_list,
apn_list, apn_entry at 2-3 scroll positions, apn_overflow_menu — the same
capture set SHG10 has). Every id/content-desc checked turned out
byte-identical to SHG10's real values across a THIRD real device now
(Sony, not SHARP) — direct confirmation this is the plain, unskinned AOSP
`com.android.settings` APN editor and Wi-Fi screen, not something
OEM-specific, strengthening the basis for every "inherited" value used
throughout this file. Neither has been run against real hardware yet —
this is config+test work from real dumps, not a live-tested flow like
SHG10/SHG07. See "🎉 SOG07/SOG08: real Wi-Fi + APN data from client dumps"
below. **Wizard data for both remains 100% Stage A placeholders** — no
OOBE photos or dumps exist for either, same structural constraint as
every other model.

**🎉 Update, 2026-09-17: both SOG07 and SOG08 hit SHG07's exact
kana-conversion text-entry symptom on their first live runs, and both are
now fixed the same way for 名前/APN.** Real, Pointer-Location-confirmed
`keyboard_mode_toggle_tap` coordinates found and verified via scripted
`adb shell input tap` + a plain-ASCII text-entry test on each unit:
SOG07 `[145, 2308]`, SOG08 `[73, 1352]` — each device's own coordinate,
never copied from another device. See docs/record.md's SOG07/SOG08
sections for the full account, including a rejected first SOG07 reading
(`[850, 0]`) whose Y value didn't match the key's visible position and
was correctly not trusted.

**Second finding, same day: MCC/MNC need their OWN toggle coordinate,
not the same one as 名前/APN.** A full SOG07 run still failed at MCC —
turned out MCC/MNC open a genuinely different numeric-only keypad on
Sony hardware (unlike SHG07, where one coordinate covered every field).
`_fill_labeled_field()` now reads a separate
`keyboard_mode_toggle_tap_numeric` (falling back to
`keyboard_mode_toggle_tap` when unset, so SHG07 is unaffected). SOG07's
numeric coordinate is confirmed: `[93, 2300]`. **SOG08's numeric
coordinate is still outstanding** — its MCC/MNC keypad hasn't been
captured yet.

**Third finding, same day: the numeric coordinate alone wasn't enough —
MCC/MNC also needed a different typing mechanism.** A full SOG07 run
with the numeric toggle coordinate in place still failed MCC identically
on all 3/3 retries, even though the coordinate itself was independently
confirmed correct via the scripted test. Turned out the toggle only
actually took effect for `input text`, not for
`input_digits_direct()`'s per-keyevent mechanism (the one MCC/MNC
normally use, proven correct on SHG10/SHG07) — the mirror image of
SHG10's original finding, where `input text` was the broken mechanism
and keyevents were the fix. New opt-in flag
`use_text_entry_for_numeric` switches MCC/MNC to `input_text_direct()`;
SOG07's config now sets it. **SOG08 needs the same
capture-and-confirm treatment for MCC/MNC (both the toggle coordinate
and possibly this same typing-mechanism issue) before its APN flow can
be trusted.**

**Fourth finding, same day: the symptom persisted even with the
mechanism fix, and it looked (to the client, watching live) like the
toggle wasn't being tapped at all.** Traced the real SOG07 profile's
exact shell-command sequence directly (not a guess) — confirmed the
toggle taps genuinely fire, correctly, every time; likely explanation
for the visual "nothing happens": Android's "Show taps" developer
option (separate from "Pointer location") needs to be on for a
synthetic `adb shell input tap` to show any visible indicator at all.
The underlying full-width symptom is still real and unexplained by
anything wrong in the code, though. Added (2026-09-17), as an explicitly
**unconfirmed hypothesis**: `_KEYBOARD_TOGGLE_TAP_DELAY_SECONDS = 0.5`,
a short wait immediately before every pair of toggle taps, on the theory
that the automated path fires them before the on-screen keyboard's
slide-in animation finishes (unlike the manual scripted confirmation,
which was naturally paced by a human). **If a retest still shows the
same symptom, this delay should be treated as ruled out, not kept.**
Neither device has completed a full end-to-end `configure_apn()` run
with all fixes in place yet — that's the next real-hardware milestone to
watch for.

Also added, same day at the client's request: `--max-retries` CLI flag
on `main_phase2.py` (default: config's value, 3; `--max-retries 0` = a
single attempt) — useful for iterating on a real, repeatable failure
without waiting through 3 identical retries each time.

**🎉 Fifth finding, same day: the client identified the actual real root
cause.** The on-screen keyboard's mode-toggle key does NOT reset to a
known state for each new field's dialog — it carries over from wherever
the PREVIOUS field's typing left it. A fixed "always tap exactly twice"
only reliably works for the first field opened in a fresh dialog session;
every field after that can start from an unpredictable carried-over
state, which is exactly why 名前/APN worked but MCC (the third field
typed into) didn't. There is no way to directly read the keyboard's
actual mode (confirmed unreachable via `uiautomator dump` and
`get_current_ime()`), so `_fill_labeled_field()` now probes it
empirically instead: type, read back, and if wrong, clear the field and
advance the toggle by one more single tap before retrying, up to
`_KEYBOARD_TOGGLE_MAX_ATTEMPTS = 4` total attempts before giving up
through the existing cancel/navigate-up cleanup. Self-correcting
regardless of the toggle's actual cycle length, applies automatically to
any model with `keyboard_mode_toggle_tap`/`keyboard_mode_toggle_tap_numeric`
set — no new per-model config needed. Two new tests confirm both the
self-correction and the bounded give-up behavior with a fake client that
models persisting toggle state across fields. **Still not yet run to full
end-to-end completion on real hardware with this in place** — the next
real-hardware milestone.

**Sixth finding, same day: efficiency feedback.** The client asked
whether retyping the whole MCC/MNC value on every toggle-correction
attempt could be avoided by detecting the keyboard's current mode
directly instead. Re-confirmed it can't (invisible to `uiautomator dump`;
`get_current_ime()` only reports the IME package, not this Gboard-internal
UI state) — so instead, numeric fields now probe with only the value's
own FIRST DIGIT (digits commit immediately, no romaji composing delay to
worry about), and only type the rest once that's confirmed correct.
Deliberately not applied to 名前/APN (romaji composing makes a
single-letter probe unreliable there, and neither field has needed a
retry in any real run so far). This also surfaced and fixed a real bug in
the TEST DOUBLES (not production code): both fake clients modeled
`input text` as replacing the field instead of appending, which broke
once a field could legitimately be typed into twice (probe, then rest).

**🎉 Update, 2026-09-17: SOG07's Phase 2 APN flow is CONFIRMED WORKING
end-to-end on real hardware.** Client run:
`SUCCESS: device HQ632M1012 reached LOGIN_INSTALL` — all four fields
(including MCC/MNC via the self-correcting toggle + single-digit probe)
and the save completed with no field-mismatch errors; only the known,
harmless soft post-save list-visibility warning appeared (same as
SHG10/SHG07). SOG07 is now on par with SHG10/SHG07's confirmed status.
Client also asked whether the brief visible flicker during a
toggle-correction (a wrong digit shown, then corrected) could be
eliminated by validating the keyboard's mode internally — confirmed not
achievable without a different mechanism (paste-based entry, needing a
helper app); **client chose to keep the current behavior** given the
flicker is minimal (one character, ~one ADB round-trip) and never
actually saved.

**Same-day follow-up:** double-checking on real hardware, the client
found 名前/APN still retyped the whole value on a wrong attempt (MCC/MNC
were already confirmed using the single-digit probe) — this was expected
at the time (名前/APN were deliberately excluded, on a concern that
romaji composing could make a single-letter probe unreliable), but the
client asked for the same treatment there too. Extended: the probe
optimization now applies to EVERY field with a toggle configured, not
just numeric ones — the retry loop's own read-back check is robust to
whatever length the probe's actual committed text turns out to be, so
this generalizes safely even though the romaji-composing reliability
question remains unconfirmed on real hardware (worth watching on the
next 名前/APN correction). See docs/record.md's SOG07 section for the
full account.

Not yet done: the same treatment for SOG08.

## Highest priority

### 🎉 SHG07 text entry: real fix found, confirmed end-to-end (2026-09-15)

After several dead ends (all preserved below, in "SHG07 text entry: root
cause now confirmed, still NOT actually solved" — worth keeping since each
rules out a real avenue with real evidence), the client found the actual
fix by using **Android's own Pointer Location developer tool**
(Settings > Developer options > Input > "Pointer location") to get a real
screen coordinate for the on-screen keyboard's かな/英数 mode-toggle key,
rather than relying on `uiautomator dump` (which never captured the
keyboard at all — confirmed twice). That coordinate, **(106, 2239)**, was
then directly confirmed via a scripted `adb shell input tap` (not just
manual touch): tapping it twice, then `adb shell input text "a"`,
produced a correctly committed half-width `a` — the first correct ASCII
character to ever land in an SHG07 APN field in this whole investigation.

Implemented: `apn_settings.keyboard_mode_toggle_tap: [106, 2239]`
(SHG07's profile only), tapped twice via the new `tap_at_coordinates()`
primitive before typing into each field. This is a deliberate, documented
exception to how every other tap in this codebase works — it doesn't
resolve a resource-id/text/content-desc first, because there is nothing
in the accessibility tree to resolve; the coordinate came from real
on-device confirmation, not a guess.

**Live re-test, same day — real progress, one more gap found and
fixed.** First attempt: 名前 and APN both went through with **no
mismatch error** — the toggle fix worked for the two fields it was built
for. Failure moved to MCC: `typed '440' but the field now reads '４４０'`
— the exact full-width-digit pattern from SHG10, except here it happened
*with* `input_digits_direct()`, which had been assumed universally immune
to conversion (true on SHG10, where `keyboard_mode_toggle_tap` isn't
set). That assumption doesn't hold on SHG07: the toggle tap was
originally scoped to non-numeric fields only, on the theory digit
keyevents never needed it — wrong here, since the keyboard was left in
kana mode for MCC/MNC and this specific keyboard's kana mode also
full-width-converts digit keyevents, not just letters. Fixed: the toggle
tap now applies unconditionally, before every field including MCC/MNC.

**🎉 Confirmed end-to-end, same day (round 11):** with the MCC/MNC fix
applied, a full live run reached `SUCCESS: reached LOGIN_INSTALL` with no
field-mismatch errors at any of the four fields. Client reported the
saved list appeared empty immediately after, but re-checking settings
confirmed `rakuten.jp` genuinely registered — the same list-refresh-
timing quirk already known from SHG10 (2026-09-11), not a data-
correctness problem. Fixed: `_save_apn()`'s soft post-save check now
tries a third time via a fresh `android.settings.APN_SETTINGS`
re-navigation if the delay+re-dump retry still doesn't find the entry —
real evidence (this client report) that waiting on the same already-open
screen isn't always enough, but a full screen reload is. Still a soft
check either way, never a hard failure.

This coordinate is tied to SHG07's exact screen resolution/orientation —
do not reuse it on another model without re-confirming via Pointer
Location on that device first.

<details>
<summary>Dead ends ruled out along the way (real evidence each time, kept for reference)</summary>

- **Per-keyevent typing instead of `input text`** — disproven: both are
  implemented via synthesized KeyEvents under the hood (`input text`
  converts through `KeyCharacterMap` before injecting — the same
  underlying path `input keyevent` uses directly), so neither bypasses
  the keyboard's current mode. `apn_settings.use_keyevent_text_entry` was
  reverted to unset on both SHG07 and SHG10 as a result.
- **Switch to a different installed keyboard** — `adb shell ime list -a`
  showed only one real text-input IME exists (`com.google.android.
  inputmethod.latin`/Gboard); the other two entries are an autofill proxy
  (disabled) and voice input (not usable for typed text).
- **Switch Gboard's language via an IME subtype id** — no distinct
  per-locale subtype/hash data exists for Gboard on this build
  (`mSubtypeId=0`, `mSubtypeName=null`); `dumpsys input_method` showed
  `System locales = [ja-JP]`, suggesting Gboard follows the device's
  system locale rather than an independently switchable subtype.
- **Write the APN directly to Android's database** — `content query --uri
  content://telephony/carriers` returned `SecurityException: No
  permission to access APN settings`. Confirmed blocked for the plain
  `shell` user on this non-rooted device.
- **Temporarily switch the device's system language to English** —
  `settings put system system_locales en-US` succeeded at the settings
  layer (confirmed via `get`), but a live screenshot showed no actual
  effect on the already-running Settings app/keyboard.
- **Estimating the toggle key's position from a screenshot** — rejected
  in favor of Pointer Location specifically because a pixel-proportion
  estimate on this device's dense keyboard rows risked hitting an
  unrelated adjacent key.
</details>

### Other priorities (unchanged, kept in their original sections below)

- ~~"Two wizard button labels — still the only wizard gap"~~ (under
  "SHG10 (AQUOS sense7...)" below) — **MOOT (2026-09-17): the wizard is
  now permanently out of scope**, client decision — see the status update
  at the top of this file. Kept here for history only.
- ~~A full end-to-end `configure_apn()` run on SOG08~~ — **DONE
  (2026-09-17): SOG08 is now CONFIRMED WORKING end-to-end**, first
  attempt, no field-mismatch errors — see docs/record.md's SOG08
  section. All four models are now confirmed.

### Re-verify the destructive-tap safety fix's retry path specifically

The single item from the old "re-verify" list not exercised by the
successful run above: `connect_wifi()`'s already-connected check was
exercised (it correctly detected `earth5_1` was already connected and did
nothing), but the specific *retry-after-a-later-step-fails* scenario the
original bug was found in (Wi-Fi succeeds, APN fails, the whole flow
retries from the top) hasn't been deliberately re-exercised since the
fix. Low urgency now — the underlying bug (connect_wifi() re-running its
full UI flow when already connected) is structurally fixed regardless of
which step triggers a retry — but worth a deliberate test (e.g. run twice
in a row) for full confidence.

### Wi-Fi scan results vary run to run at this location

Not a bug, just worth remembering: a real client-PC scan (2026-09-08)
showed the device's in-range networks were, at that moment, different from
both `wifi_list_SHG10.xml`'s original capture and from `earth5_1`
(`cityroam`, `JBCshoji`, `GatewayIkebukuro5fWifi1`, `USPOT_7407541_2.4G`,
`FREE_Wi-Fi_and_TOKYO`, `USPOT02_MESH_132119436_001`, `rv440m-34a2c1-1/-2`,
`iPhone`) — a "not found in scanned list" result doesn't automatically mean
the credentials are wrong.

**Wi-Fi passwords cannot be extracted via adb, ever, on a non-rooted
device** (confirmed: the shell user lacks the wifi permissions needed even
to reconnect a saved network — same `SecurityException` blocks
`cmd wifi connect-network` entirely, and reading `WifiConfigStore.xml`
needs root) — noted here in case a *different* network needs credentials
later; real ones are already in hand for `earth5_1`.

### Two wizard button labels — still the only wizard gap

**MOOT (2026-09-17): the wizard is now permanently out of scope** —
client decision, see the status update at the top of this file. Kept
below for history only; no longer being pursued.

`welcome` and `software_update` screens' button text remain illegible in
the client's photos (glare on one, cropped at the frame edge on the other)
— confirmed by a second independent review of all 19 photos, not just the
original transcription. One new observation: the `welcome` screen's button
may be icon-only (no text at all), which would mean the fix isn't just
"read the label" but potentially switching that one screen's action to
`tap_by_content_desc`. Needs a live look or a fresh photo during the next
factory reset.

### 🎉 SOG07/SOG08: real Wi-Fi + APN data from client dumps (2026-09-16)

Client supplied the same capture set used for SHG10 — `wifi_list`,
`apn_list`, `apn_entry` at 2-3 scroll positions, `apn_overflow_menu` — for
both SOG07 (Xperia 10 IV, Android 14) and SOG08 (Xperia Ace III, Android
13). `config/models/sony_xperia_10iv.yaml`/`sony_xperia_ace3.yaml`
rewritten from Stage A's from-scratch invented placeholders to real
values throughout `wifi_settings`/`apn_settings`.

**The headline finding: every id/content-desc checked is byte-identical
to SHG10's real values.** `android:id/switch_widget` (Wi-Fi toggle),
`android:id/title` (generic row id, Wi-Fi SSIDs and APN fields alike),
`com.android.settings:id/settings_button` (gear icon), content-desc "APN"
(list title), "新しい APN" (add button), "その他のオプション" (overflow),
"上へ移動" (navigate up), "保存"/"キャンセル" (save/cancel) — all exactly
the same across THREE real devices now (SHG10, SOG07, SOG08) and TWO
manufacturers (SHARP, Sony). This is real, direct confirmation of
something this file could previously only guess at: the plain,
unskinned AOSP `com.android.settings` Wi-Fi screen and APN editor are
genuinely shared, unmodified components — not something each OEM
reskins — at least for these specific screens. This also retroactively
strengthens confidence in SHG07's SHG10-inherited values (never
independently confirmed for SHG07 itself, but now backed by a pattern
seen identically on a third, unrelated device too).

**One real, confirmed difference from SHG10**: both Sony devices' Wi-Fi
screen title renders via content-desc **"インターネット"** ("Internet"),
not SHARP's "Wi-Fi とモバイルネットワーク" — evidently SHARP's skin
renames this screen, stock/Sony doesn't. `wifi_settings.menu_path`'s
final step uses this real value for both Sony models.

**Still genuinely unresolved for both**:
- `dialog_edit_field_resource_id`/`dialog_confirm_button_resource_id`/
  `dialog_cancel_button_resource_id` — inherited from SHG10 (android:id/
  edit, button1, button2), not independently captured for either Sony
  device's own per-field dialog (no dump of one open exists for either).
  Better-justified than SHG07's inheritance was, given the cross-device
  confirmation above, but still not itself confirmed.
- `wifi_settings.password_field_resource_id`/`connect_button_resource_id`/
  `connect_button_text` — same gap SHG10 has; no dump of the "Connect to
  network" dialog exists for either device.
- **The wizard remains 100% Stage A placeholders for both** — no OOBE
  photos or dumps exist for either device, same structural constraint
  (factory reset wipes ADB authorization before the wizard is reachable)
  that applies to every model.
- ~~Whether either device's IME has SHG07's kana-conversion problem is
  completely unknown~~ — **RESOLVED (real, 2026-09-17): both do.** First
  live runs on both hit the identical symptom, and both now have their
  own Pointer-Location-confirmed `keyboard_mode_toggle_tap` coordinates
  for 名前/APN (SOG07 `[145, 2308]`, SOG08 `[73, 1352]`), each verified
  via a scripted `adb shell input tap` + plain-ASCII text-entry test. See
  docs/record.md and the update note near the top of this file for the
  full account.
- **NEW, still outstanding: SOG08's MCC/MNC keyboard-toggle coordinate
  AND typing mechanism.** A full SOG07 run revealed MCC/MNC use a
  different numeric-only keypad than 名前/APN, with its own toggle key at
  a different position, AND that even the correct toggle coordinate
  isn't enough — MCC/MNC also need `input_text_direct()` instead of the
  usual per-keyevent mechanism on this keypad. SOG07's both are now
  confirmed (`keyboard_mode_toggle_tap_numeric: [93, 2300]`,
  `use_text_entry_for_numeric: true`). SOG08's equivalents haven't been
  captured/tested yet; until they are, SOG08's MCC/MNC will fall back to
  its 名前/APN coordinate (`[73, 1352]`) and the original keyevent
  mechanism, neither confirmed correct for that keypad — likely to repeat
  the same bugs SOG07 just hit.

**Both devices' keyboard-toggle fix is confirmed at the single-field
level, but neither has completed a full end-to-end `configure_apn()` run
yet** — that's the next real-hardware milestone. Recommended: the same
supervised, one-device-at-a-time, `--skip-wizard` first pass used for
every other model's first real test. New test files,
`tests/test_real_sog07_fixtures.py`/`test_real_sog08_fixtures.py`, mirror
`test_real_shg10_fixtures.py`'s pattern against these real dumps.

## Resolved — full Phase 2 run confirmed end-to-end (2026-09-11)

Every fix below was previously tracked as "not yet re-verified against
real hardware" — a single successful client run confirmed all of them at
once, reaching `LOGIN_INSTALL`:

- **APN navigation root-cause fix**: `menu_path`'s old final step tried
  `tap_by_text()` on 「アクセスポイント名」, which was always the destination
  screen's own title (rendered via `content-desc`, never a `text` node) —
  there was nothing there to tap. Replaced with
  `adb shell am start -a android.settings.APN_SETTINGS` as the primary
  path, hand-confirmed to reach the APN list in one step; `menu_path` kept
  only as a fallback.
- **Screen-recognition fix**: `_looks_like_apn_list_screen()` initially
  only recognized the SHARP-skinned title (`content-desc`
  「アクセスポイント名」), not this device's actual intent-landing screen
  title (`content-desc` "APN" on `com.android.settings:id/collapsing_
  toolbar`). Now accepts either.
- **Add-button fix**: the "+" button has a real, unambiguous content-desc,
  `"新しい APN"`, confirmed by a real dump
  (`tests/fixtures/apn_restricted_SHG10.xml`) — tapped directly via that
  content-desc, no longer via the position-estimate fallback (which
  remains in the code for any model/screen without a captured identifier).
- **Per-field dialog ids confirmed real**, not just best-guessed:
  `dialog_edit_field_resource_id` ("android:id/edit") and
  `dialog_confirm_button_resource_id` ("android:id/button1") — confirmed
  by a real dump of the dialog itself, open
  (`tests/fixtures/apn_accesshost_okbtn_SHG10.xml`). This ruled out an
  earlier hypothesis (a wrong confirm-button id leaving dialogs stuck
  open) as the cause of a since-resolved save failure — the hardening
  added for that hypothesis (hard failure instead of a silent warning on
  either dialog tap) stays regardless, as correct defensive practice.
- **MCC/MNC full-width-digit fix** — the actual, client-observed root
  cause of "typed through MNC but never saves": MCC/MNC were being
  entered as full-width digits (４４０) instead of half-width/ASCII (440)
  via `input_text_direct()` ("input text"), which is meant to bypass the
  active IME but evidently didn't fully do so for digits on this device.
  New primitive `input_digits_direct()` sends each digit as its own
  `adb shell input keyevent KEYCODE_N` instead — `_fill_labeled_field()`
  uses this for MCC/MNC (`numeric_only=True`), 名前/APN keep using
  `input_text_direct()`.
- **Network-config placeholder guard**: `config/network.yaml.apn_name`
  turned out to still be the literal placeholder text `<APN value from
  client>` on the client's machine — meaning every real run before this
  one was attempting to save that exact string (spaces, angle brackets,
  and all) as the actual APN value, independently plausible as a
  contributor to every "not saving" symptom seen throughout this whole
  investigation. Not a code bug (the guard correctly caught it) — the
  client edited their own `config/network.yaml` to fix it. The guard
  itself was narrowed same-day after an unrelated false positive (see
  "Network-config placeholder safety" below).
- **Post-save soft-check retry**: the list can take a moment to refresh
  after 保存 — the check now retries once after a short delay before
  logging its "wasn't spotted" warning, avoiding a false-negative warning
  on a save that actually succeeded.
- **`dump_ui()` pull-failure fix**: a real run crashed with a raw
  `FileNotFoundError` from `dump_ui()` never checking whether its `pull()`
  call succeeded — fixed with a clear error + automatic retry.

## SHG10 (AQUOS sense7, SHARP/KDDI, Android 14) — Stage B, most of the way there

**Corrected finding:** real `adb` identification reported Android 14
(`[SHARP] KDDI SHG10 (Android 14)`), not Android 12 as the original task
spec assumed. Config and tests now reflect 14.

### Resolved — Wi-Fi (`tests/fixtures/wifi_list_SHG10.xml`, plus live testing 2026-09-08)
- `wifi_settings.toggle_resource_id` = `android:id/switch_widget` (unambiguous,
  single match) — checked via `node_is_checked()` before tapping (see
  "Toggle-tap safety" below)
- `wifi_settings.network_list_resource_id` = `android:id/title` (generic,
  must be paired with `text=<SSID>`)
- `wifi_settings.menu_path`: 設定 → ネットワークとインターネット →
  Wi-Fi とモバイルネットワーク — and as of 2026-09-08, `wifi_setup.py` tries
  `android.settings.WIFI_SETTINGS` first (confirmed working on real
  hardware: reaches the screen regardless of starting point, including from
  a bare home screen via `--skip-wizard`), falling back to this menu_path
  only if that intent doesn't land correctly
- `wifi_settings.connect_button_text` = `接続` (real — confirmed via
  screenshot, not a dump) — join-network dialog buttons are plain text
  (`キャンセル`/`接続`), tried before the still-unresolved
  `connect_button_resource_id` placeholder
- **Password entry mechanism**: real testing found `inject_text()` (ADB
  Keyboard broadcast) silently does nothing on this device — switched to
  `input_text_direct()` (`adb shell input text`); see "Resolved — text
  input mechanism" below
- **End-to-end connection confirmed on real hardware** (2026-09-08):
  `earth5_1` / 接続済み, WPA3-Personal, 5GHz — the full chain (shell attempt
  fails as expected → UI fallback → intent navigation → SSID tap → toggle
  check → password entry → connect tap → `dumpsys wifi` poll confirms) all
  worked together against a real network

### Resolved — APN navigation & fields (`tests/fixtures/apn_entry_{top,middle,bottom,filled}_SHG10.xml`, `apn_restricted_SHG10.xml`)
- **Navigation, primary path (real, hand-confirmed 2026-09-08/09, screen
  title confirmed by dump 2026-09-11):** `adb shell am start -a
  android.settings.APN_SETTINGS` reaches the APN list screen in one step.
  `apn_setup.py` tries this first, verifying landing via
  `_looks_like_apn_list_screen()`, which accepts **either** real title
  variant, both rendered via `content-desc` on the toolbar (never a plain
  `text` node — same pattern as the edit form's title): `アクセスポイント名`
  (the SHARP-skinned screen reached via manual `menu_path` navigation) or
  `APN` (the stock/AOSP-style screen this device's `APN_SETTINGS` intent
  actually lands on — confirmed by `apn_restricted_SHG10.xml`,
  resource-id `com.android.settings:id/collapsing_toolbar`; only the first
  variant was recognized before this, causing false "didn't land
  correctly" fallbacks). **Confirmed end-to-end on real hardware,
  2026-09-11** — see "Resolved — full Phase 2 run confirmed end-to-end"
  below.
- **Navigation, fallback `menu_path`** (only used if the intent fails or
  doesn't land correctly): same as Wi-Fi's, then the gear icon
  (`com.android.settings:id/settings_button` — real, unambiguous
  resource-id). **Correctly ends at the gear icon** — an earlier version of
  this file had it continue to `tap_by_text()` on `アクセスポイント名`, which
  was a confirmed bug: that string is the destination screen's own title
  (rendered via `content-desc` on the toolbar, not a `text` node), so that
  step could never find anything to tap. This was the actual root cause of
  every "apn menu navigation failed" seen in real runs before this fix —
  not a wrong id, a step that never had a valid target at all.
- `apn_settings.field_row_resource_id` = `android:id/title` (generic, shared
  by every field on the edit form — 名前/APN/プロキシ/ポート/ユーザー名/
  パスワード/サーバー/MMSC/MMSプロキシ/MMSポート/MCC/MNC/認証タイプ/APNタイプ/
  APNプロトコル/APNローミングプロトコル/ベアラー/MVNOの種類/MVNO値 all share it)
- `apn_settings.name_field_label` = `名前`, `apn_field_label` = `APN`
- **MCC/MNC confirmed mandatory, not optional** (real on-device validation,
  2026-09-08 — supersedes the earlier "might be absent" note, which was
  wrong: they're just further down the scrollable form than first assumed).
  `mcc_field_label` = `MCC` (real value seen: `440`, Japan), `mnc_field_label`
  = `MNC` (real value seen: `11`, Rakuten Mobile). The device itself
  validates format (MCC exactly 3 digits, MNC 2 or 3) and refuses to save
  otherwise — `apn_setup.py` checks the same constraint before ever
  touching the device (`_MCC_PATTERN`/`_MNC_PATTERN`).
- **MCC/MNC rows confirmed below the fold** (real, 2026-09-08/09) — the
  field-row lookup now scrolls once and retries if a row isn't immediately
  found, same pattern as the wizard's `scroll_then_tap_by_text`.
- **Success state confirmed** (real, 2026-09-08/09): a successful save
  shows the new entry back on the APN list with its `名前` value as the
  first line (e.g. "TEST_SAVE_A / test.apn"). `_save_apn()` makes a soft,
  best-effort positive check for this now (logged only — info if found,
  warning if not — never turned into a failure on its own, since e.g. list
  scroll position could make it miss a genuinely successful save the
  validation-dialog check already accepted).
- **`apn_settings.add_button_content_desc` = `新しい APN`** ("New APN") —
  the "+ add new APN" icon, resolved from a real dump
  (`apn_restricted_SHG10.xml`, 2026-09-11) of the APN *list* screen itself
  (the missing piece before this — only the edit *form* had ever been
  captured). Has no resource-id at all on this build (confirmed by the same
  dump, not just absent data — `add_button_resource_id` stays `null`
  permanently). Sits immediately left of the confirmed "⋮" overflow icon,
  same height, sharing the exact x=969 edge — this also retroactively
  confirms the 2026-09-08/09 position-estimate fallback
  (`tap_left_of_content_desc()`) would have landed within ~11px of the
  real center, though it's no longer needed for this model now that the
  real value is known. `configure_apn()` prefers this content-desc over
  both `add_button_resource_id` and the position-estimate fallback.
  **Confirmed against a live run, 2026-09-11** — see "Resolved — full
  Phase 2 run confirmed end-to-end" below.

### Resolved — Save flow (real, confirmed on-device 2026-09-08 — see
`tests/fixtures/apn_overflow_menu_SHG10.xml`,
`apn_mcc_validation_SHG10.xml`, `apn_mnc_validation_SHG10.xml`,
`apn_entry_filled_SHG10.xml`)

This was the previous highest-priority blocker — now closed:
- Save is **two taps**, not one: open the overflow "⋮" menu
  (`overflow_menu_content_desc` = `その他のオプション` — content-desc only,
  no resource-id, confirmed across three separate captures now), then tap
  `保存` inside it (`save_menu_item_text` — shares `android:id/title` with
  the menu's other item, `キャンセル`, disambiguated by text, same pattern
  as everywhere else on this screen).
- The two earlier unconfirmed candidates are **resolved**: the overflow
  menu was the right one; `上へ移動` (navigate-up) was never actually the
  save trigger on this build — don't use it, `apn_settings.yaml` no longer
  references it.
- **Validation is sequential and blocking**: saving with any required field
  empty/invalid shows a modal `AlertDialog` instead of returning to the APN
  list, and does not save. Real messages, verbatim: `APNは必ず指定してください。`
  (APN empty), `MCC欄は3桁で指定してください。`, `MNC欄は2桁か3桁で指定してください。`
  Each is a standard AOSP dialog: message at `android:id/message`, single OK
  at `android:id/button1`. `apn_setup.py._save_apn()` checks for
  `android:id/message` after tapping `保存`; if present, logs the real
  message and fails loudly — **does not tap OK and retry blindly**, since a
  silent failure here would leave a device with no APN configured and no
  error surfaced.
- This also **indirectly confirms** the earlier best-guess
  `dialog_confirm_button_resource_id = "android:id/button1"` — real evidence
  now exists that this id is genuinely SHG10's standard AlertDialog
  positive-button id (from the validation dialog), raising confidence
  (though still not directly proven) that the same id is correct for the
  per-field entry dialog's own confirm button too.

### Resolved — text input mechanism (broadened three times, all from real evidence)
First finding: the device's default IME is Japanese kana mode, and the
on-screen keyboard can't reach digits without an explicit mode switch that
UI automation has no reliable way to trigger — `input_text_direct()`
(Android's built-in `adb shell input text`, bypassing the IME entirely)
fixed APN's MCC/MNC entry.

Second finding, same day: a live test of Wi-Fi password entry (SSID
`earth5_1`) showed the join-network dialog's password field stayed
**completely empty** after `wifi_setup.py` ran, with no errors logged —
`inject_text()`'s ADB Keyboard broadcast was silently going nowhere,
consistent with ADB Keyboard not actually being installed/set as the
active IME on this device (a prerequisite that was always manual/
unautomated — see README.md). Since `input_text_direct()` needs no extra
app and is already proven working on this device, both `wifi_setup.py`'s
password entry and **all four** of `apn_setup.py`'s labeled fields (not
just MCC/MNC) now use it — not because Name/APN specifically needed the
IME workaround, but because the ADB Keyboard path itself can't be trusted
on this device at all. `input_text_direct()`'s escaping was also hardened
at the same time (backslash/quote/`$`/backtick, not just spaces) since
passwords are far more likely than "440" to contain shell-special
characters.

Third finding, 2026-09-11: client directly observed `input_text_direct()`
("input text") committing MCC/MNC as **full-width digits** (４４０)
instead of half-width/ASCII (440) — apparently `input text`, despite being
meant to bypass the IME, still picks up this device's Japanese-IME
zenkaku conversion for digits specifically. New primitive,
`input_digits_direct()` (per-digit `adb shell input keyevent KEYCODE_N`),
routes around it — MCC/MNC use this now; 名前/APN (arbitrary text) keep
using `input_text_direct()`. This is the client's own direct observation
of the actual bytes typed, not an inference — see "Highest priority"
above for the theory of why this explains "typed through MNC but never
saves": the device's own MCC/MNC digit-count validation likely doesn't
recognize full-width digits as digits at all.

Legacy-shape models (the 3 untouched by Stage B) still default to
`inject_text()` — this finding is specific to this real device, not
generalized to models with no data of their own yet.

Fourth finding, 2026-09-14 (SHG07, a *different* device): unlike SHG10, on
SHG07 the active IME was reported to affect plain alphanumeric `input
text` entry too — not just digits. `input_ascii_direct()` generalizes
`input_digits_direct()`'s per-keyevent strategy to lowercase a-z/0-9/./- ;
`apn_settings.use_keyevent_text_entry: true` opts a model's 名前/APN
fields into it. Set on SHG07 (where the problem was found) and, per
client request 2026-09-15, on SHG10 too (see "Highest priority" above) for
consistency across every device — even though SHG10 itself never showed
this specific symptom for 名前/APN.

### Not resolved (genuinely absent from available data — not guessed)
- `wifi_settings.password_field_resource_id` / `connect_button_resource_id`
  — the "Connect to network" dialog (shown after tapping an unsaved SSID)
  was never captured; only the network list screen was. Unchanged Stage A
  placeholders. Also structurally can't ever contain the *value* of a saved
  password (see "Real Wi-Fi credentials" above) — this is about the
  dialog's field/button *ids*, a separate and solvable gap.

### Resolved — per-field entry dialog (`tests/fixtures/apn_accesshost_okbtn_SHG10.xml`, 2026-09-11)
- `apn_settings.dialog_edit_field_resource_id` = `android:id/edit` and
  `dialog_confirm_button_resource_id` = `android:id/button1` — previously
  only best-guess standard-framework ids (inferred from the
  *validation-error* dialog, never captured from this dialog directly).
  **Now directly confirmed**: a real dump of the per-field dialog itself,
  captured while open (mid-edit on 名前, before confirming), shows a plain
  standard AOSP AlertDialog — title at
  `com.android.settings:id/alertTitle` ("名前"), EditText at
  `android:id/edit` (focused, as expected), and two buttons: "OK" at
  `android:id/button1` and "キャンセル" (Cancel) at `android:id/button2`.
  The guess was exactly right on every point, including which of the two
  buttons is genuinely OK. This **rules out** the leading hypothesis for
  why a real 2026-09-11 run typed all four fields but the entry never
  saved — see "Highest priority" above for what's still actually unknown.

### Toggle-tap safety (fixed, not just data)
Real capture showed the Wi-Fi toggle is a plain `Switch` with a `checked`
attribute — Stage A's original code tapped it unconditionally every time,
which would have **turned Wi-Fi off** on any device where it was already on
(true in the captured dump). `wifi_setup.py` now checks `checked` via
`node_is_checked()` before deciding whether to tap.

### Network-config placeholder safety (fixed, not just data — 2026-09-11)
`main_phase2.py._load_network_config()` used to silently fall back to
`config/network.yaml.example`'s placeholder values (just a warning) if
`config/network.yaml` didn't exist. Real proof this is a genuine hazard,
not theoretical: `tests/fixtures/apn_success_setting_SHG10.xml` (a real
dump) shows a leftover APN entry on the device literally named "<APN
value from client>" — the example file's exact placeholder text, from
some earlier run that took this fallback path. There is no dry-run mode
(`main_phase2.py` always runs against real hardware), so this is now a
hard failure: `NetworkConfigError` if the file is missing, and the same
if any value inside it still matches a known placeholder string verbatim
(`_PLACEHOLDER_VALUES`) — catches both "never copied the example" and
"copied it but forgot to fill in one field."

**Self-correction, same day:** the first version of the placeholder check
walked the *entire* config recursively, and immediately blocked a real
client run — `config/network.yaml`'s `apn.carrier` still had its
placeholder text, even though `carrier` is documentation-only and never
read by any code path (`src/orchestration/slot.py` only ever reads
`apn_name`/`mcc`/`mnc` and `wifi.ssid`/`wifi.password`). A real, correctly
filled-in config got refused over a field nothing depends on. Narrowed to
an explicit whitelist, `_REQUIRED_CONFIG_PATHS`, matching exactly what
`slot.py` consumes — `apn.carrier` (and any other future documentation-
only field) is intentionally never checked.

### Wizard — hard constraint, not a temporary gap
No `uiautomator dump` exists or ever will for OOBE wizard screens on any of
the four models: factory reset wipes ADB authorization, and by the time ADB
is available again the wizard has already finished. Four separate remote
workarounds were tried on SHG10 and all failed (see docs/record.md for the
full list and the structural explanation). SHG10's wizard is instead driven
by visible text from the client's photographed reset session — see
`config/models/sharp_aquos_sense7.yaml`'s `wizard:` block and
`src/phase2/wizard_walkthrough.py`'s screen-driven implementation.

Two button labels remain genuinely unverified — see "Highest priority" above.

**Open question for the client**: is 「オフラインで設定」 (offline setup) the
standard path for all devices? The client's photographed session took this
path and Google account sign-in never appeared, which — if standard —
substantially narrows what the wizard needs to automate. Not yet confirmed
as the universal case.

**Judgment call — "wizard complete" detection**: there is no reliable
captured signal for "we've reached the home screen" (it varies by
launcher/wallpaper). A real `--skip-wizard` run (2026-09-08) landed on an
actual home screen and its dump (greeting widget, date widget, app icons)
confirms this variability firsthand — nothing in it would generalize as a
stable detector. `wizard_walkthrough.py` instead treats successfully
handling the *last* configured screen (`aquos_notify` /
「AQUOS Homeの通知アクセス」) as completion. Deliberate simplification, not
an oversight.

### `--skip-wizard` / `--skip-wifi` testing flags (infrastructure, not device data)
`--skip-wizard` added 2026-09-08 after discovering the SHG10 test unit was
already provisioned from an earlier session (landed on the home screen
instead of any wizard screen). Bypasses `run_wizard()` entirely for manual
testing against an already-provisioned device. Deliberately **not**
exposed on `run_phase2_batch()` (the production batch path) — only
`Slot.run_init_apn()` and `scheduler.run_slot_with_retries()` accept it,
both requiring an explicit, per-call opt-in. (`--skip-wifi` was proposed
the same day, same pattern, but wasn't ultimately needed once Wi-Fi
started working — not wired up.)

### `--device` multi-device parallel mode (infrastructure, not device data — 2026-09-14)
Client asked for all devices to be run "at the same timing" rather than
one `main_phase2.py` invocation per device in sequence.
`main_phase2.py --device SERIAL1:MODEL1 --device SERIAL2:MODEL2 ...`
(repeatable, replaces `--serial`/`--model` for this mode) dispatches every
device to its own thread via `concurrent.futures.ThreadPoolExecutor`, all
starting at once, each with its own `Slot`/`AdbClient`/retry loop sharing
only the loaded model profiles and `config/network.yaml` — one device's
failure or retry can't block or delay the others. `--serial`/`--model`
still works unchanged for the single-device case (runs inline, no thread
pool). Distinct from `orchestration/scheduler.py`'s existing
`run_phase2_batch()` (used by Phase 3's eventual production dashboard,
out of scope here): that function deliberately has no `skip_wizard`
parameter so a real batch run can never accidentally skip the wizard —
`--device` is for manual/testing use exactly like `--skip-wizard` already
was, so it's built directly on `run_slot_with_retries()` instead, keeping
that same opt-in safety property. See README.md's usage section.

### `dump_ui()` retry on transient pull failure (infrastructure, not device data)
Added 2026-09-08 after a real crash: `uiautomator dump`'s pull is known to
intermittently fail right after a screen transition, and `dump_ui()` never
checked `client.pull()`'s return value — a failed pull crashed with a raw
`FileNotFoundError` from reading a file that was never written. Now raises
a clear `AdbCommandError` and retries up to 3 times (1s delay) before
giving up. Fixed in the shared `dump_ui()`, so it protects every
tap/find call across wizard, Wi-Fi, and APN — not specific to where it
happened to first surface (APN menu navigation).

## SOG08 (Xperia Ace III), SOG07 (Xperia 10 IV) — Wi-Fi + APN now real (2026-09-16)

**Serials (client-supplied, 2026-09-16):** SOG07 (Xperia 10 IV)
`HQ632M1012`, SOG08 (Xperia Ace III) `HQ63460161` — see docs/record.md's
SOG07/SOG08 sections. Confirmed identity strings not yet recorded — client
identified both via `adb devices` + `getprop ro.product.model`, no full
`adb`/log session logged for either unit yet.

Updated from the original "entirely untouched" status: client supplied
the same capture set used for SHG10 (Wi-Fi list, APN list, APN entry form
at multiple scroll positions, APN overflow menu) for both. `wifi_settings`
and `apn_settings` in both YAML files now hold real values throughout —
see "🎉 SOG07/SOG08: real Wi-Fi + APN data from client dumps" above for
the full account, including the notable finding that every id checked is
byte-identical to SHG10's.

**`wizard_steps` remains 100% Stage A placeholder for both** — every
value there is still an invented `TODO(real-device)` marker, no wizard
data of any kind exists for either device, and (same structural
constraint as every other model, see docs/record.md's "Wizard capture —
RESOLVED AS NOT REMOTELY POSSIBLE") never will via a real dump. Unlike
SHG10, there are also no client photos of either unit's OOBE flow to
derive a screen-driven config from — that would need its own capture
effort if/when pursued.

**Update, 2026-09-17:** first live runs on both devices hit SHG07's
kana-conversion text-entry symptom; both now have their own
Pointer-Location-confirmed `keyboard_mode_toggle_tap` (SOG07
`[145, 2308]`, SOG08 `[73, 1352]`), verified via scripted tap + text
test. See docs/record.md's SOG07/SOG08 sections and the update note near
the top of this file. A full end-to-end `configure_apn()` run with the
fix in place hasn't happened yet for either device — see "🎉
SOG07/SOG08..." above for what's still genuinely unresolved (the
per-field dialog ids specifically) and the recommended next-test
procedure.

## SHG07 (AQUOS sense6s) — switched from Stage A placeholders to values inherited from SHG10 (2026-09-14)

**Serial:** 353681650397052 (see docs/record.md's new SHG07 section).
Confirmed identity string not yet recorded — no `adb`/log output from this
specific unit exists yet, only the config change below.

**Status change, client-directed:** previously in the same "entirely
untouched" state as SOG08/SOG07 above. On 2026-09-14 the client asked to
skip capturing new SHG07 dumps and instead reuse SHG10's confirmed real
values directly, reasoning that SHG07 and SHG10 are the same SHARP AQUOS
lineup, in order to test all devices in parallel at once. Done —
`config/models/sharp_aquos_sense6s.yaml` now uses SHG10's exact schema and
real values throughout (screen-driven wizard, labeled APN fields, the
resolved dialog/add-button/overflow ids) instead of Stage A's from-scratch
invented placeholders.

**This is a reasoned starting point, explicitly NOT independent
confirmation for SHG07.** The paragraph this replaced said, in almost
these exact words: *"Don't assume SHG07 will behave identically to SHG10
just because both are SHARP/AQUOS — confirm independently."* That caution
was correct and is still true — it's being overridden by the client's
explicit choice to accept the risk for the sake of moving faster, not
because the underlying uncertainty went away. Concretely, from this
project's own history *on SHG10 itself*: the APN screen's title, MCC/MNC's
digit encoding, and the per-field dialog's ids all had real surprises
between "looks like it should work" and "confirmed correct" — all found on
the exact same unit, same Android version, same APK builds. SHG07 is a
different model on a different Android version (13 vs 14), which
routinely means different Settings/SetupWizard APK builds with their own
resource-ids. The setup wizard specifically is the least likely part to
carry over unchanged — Android's OOBE flow is known to change meaningfully
between major versions (screens added/removed/reordered), and SHG10's own
wizard config was never fully confirmed even for SHG10 itself (2 of 9
button labels still unknown).

**Recommended before any unattended or batch run against a real SHG07
unit:** a supervised first pass — `--skip-wizard` only, one device at a
time, client watching every screen exactly like the SHG10 process in
docs/record.md — before trusting this config in the parallel multi-device
mode (`--device`, see README.md) or leaving it unattended. A wrong
resource-id fails loud (a tap that finds nothing) rather than silently
misfiring, by this project's design throughout — but "fails loud" still
means watching for it.

See `config/models/sharp_aquos_sense6s.yaml`'s file-level comment for the
full reasoning, and `tests/test_model_profile.py::test_load_shg07_model_file_inherited_from_shg10`
for what's pinned down.

Package-name note, carried over from before this change: SHG10's real
data showed the Settings/Phone app package names (`com.android.settings`,
`com.android.phone`) were right for SHG10, but the *setup-wizard* package
assumption was moot there (text-matching replaced it entirely) and
SHARP-specific screens needed SHARP-specific handling regardless of
package name — there's no strong reason to expect SHG07's package names
to differ from SHG10's, but it hasn't been checked.

### SHG07 text entry: root cause now confirmed, still NOT actually solved (2026-09-14/15)

**Status: real APN entries on SHG07 still cannot be correctly saved.**
This took two rounds to get right — the first "fix" below was itself
wrong, caught only because a second real screenshot proved it.

**Round 1 (2026-09-14):** client's first real dump/report — the active
Japanese IME prevents entering intended half-width alphanumeric
characters into 名前/APN, not just MCC/MNC as on SHG10. Structure was
confirmed matching SHG10 (same dialog ids throughout). Hypothesis at the
time: `input_ascii_direct()` (per-character `adb shell input keyevent
KEYCODE_<X>`) would bypass the IME the same way it already does for
digits, since that's exactly what fixed SHG10's MCC/MNC full-width-digit
bug. `apn_settings.use_keyevent_text_entry: true` was set on SHG07 (and
later, per a separate client request, on SHG10 too — see the
"Highest priority" entry above) on that theory.

**Round 2 (2026-09-15) — the theory was wrong, proven by a client
screenshot:** with the "fix" from round 1 active, the client typed
"rakuten.jp" into the 名前 field and the dialog showed **「らくてん。」**
instead — hiragana "rakuten" plus a Japanese full-width period. This
directly disproves the round-1 assumption: individual key**events**
for *letters* are NOT immune to the IME's conversion the way key**events**
for *digits* are. The real mechanism: Gboard's Japanese input mode
performs live romaji-to-kana conversion on Latin letter keys as they
arrive — `a`, `k`, `u` etc. are romaji syllable input, so the IME
intercepts and converts them regardless of whether they arrive via
`input text` (already known broken, round 1) or via individual
`KEYCODE_A`/`KEYCODE_K`/`KEYCODE_U` keyevents (the round-1 "fix" — turns
out equally affected). Digit keycodes are immune only because digits
aren't romaji syllables, so the IME's conversion table has nothing to do
with them — this is why `input_digits_direct()` has never actually failed
on any device tested so far, but `input_ascii_direct()`'s promise for
*letters* never held.

**Confirms `get_current_ime()` alone isn't enough of a diagnostic**: the
run's own log showed `mCurMethodId=com.google.android.inputmethod.latin/
com.android.inputmethod.latin.LatinIME` (Gboard) at the exact moment this
happened — that's Gboard's **package id**, which stays constant across
every language it supports; it says nothing about which **subtype**
(language/layout — Japanese kana vs. English) is currently active, which
is what actually matters here. A future diagnostic would need
`dumpsys input_method`'s subtype/locale info too, not just
`mCurMethodId`.

**What's actually fixed vs. still broken:**
- ✅ **Fixed**: `_fill_labeled_field()` now reads back the field's actual
  committed text right after typing, before ever tapping confirm — if it
  doesn't match what was intended, this is a hard failure (see
  "Resolved" below for the mechanism). Before this, the entire
  configure_apn() call reported `SUCCESS`/`reached LOGIN_INSTALL` with
  「らくてん。」 silently saved as the APN name — a real instance of
  exactly the "silent wrong action" this project has tried hardest to
  avoid throughout. This is now impossible for this specific failure
  mode: a transformed value fails loudly instead.
- ❌ **NOT fixed**: there is still no known way to get correct half-width
  alphanumeric text into an SHG07 APN field at all. Real APN entries on
  SHG07 cannot currently be saved by this automation.

**Round 3 (2026-09-15, same day): the round-2 fix caused a new cascading
failure, also fixed.** A live client run (with the read-back check active)
correctly failed loud on the 名前 mismatch — but then **every subsequent
run/retry** failed differently: `android.settings.APN_SETTINGS` "didn't
land on a recognizable APN list screen" on every single attempt, including
the very first of the next invocation, not just retries. Root cause:
returning `False` on the mismatch left the field's dialog *open* on the
device — a fresh intent doesn't dismiss an unrelated open dialog, so every
subsequent dump kept showing the stuck dialog instead of the expected
list. Fixed: `apn_settings.dialog_cancel_button_resource_id` (real,
confirmed — "キャンセル"/`android:id/button2`, seen in both devices' real
dumps) is now tapped to back out of a mismatched dialog cleanly before
`_fill_labeled_field()` returns `False`. Best-effort only — its own
failure only logs a warning, never masks the real underlying error.

**Round 4 (2026-09-15): three more real options investigated and ruled
out, each with concrete evidence** — see "Highest priority" above for the
full list: no alternative keyboard app exists (`ime list -a`); no
switchable subtype id exists, Gboard's language appears to follow system
locale instead (same command + `dumpsys input_method`); the Telephony
ContentProvider write is permission-denied
(`SecurityException: No permission to access APN settings`); and
temporarily changing `system_locales` to `en-US` succeeds at the settings
layer but has no live effect on the already-running Settings app/keyboard
(confirmed via a follow-up screenshot showing no change) — force-stopping
both apps after the setting change was proposed as a next test, not yet
tried.

**Round 5 (2026-09-15): reconsidered whether SHG10's own method
(`input_text_direct()`) would fare any better** — client asked directly.
Technical answer, not yet re-verified on real hardware: `input text` and
`input keyevent` are both implemented via synthesized KeyEvents under the
hood (`input text` converts the string through `KeyCharacterMap` before
injecting — the same underlying event-injection path `input keyevent`
uses directly), so both are equally exposed to whatever mode the keyboard
is in when they arrive — switching *methods* alone was assessed as
unlikely to help, since the real variable is the keyboard's *current
mode* (kana vs. 英数), not which ADB command sends the keystrokes. This
also gives the likely explanation for why SHG10's 2026-09-11 success
worked: that unit's keyboard was probably just already in alphanumeric
mode at the time, not because `input_text_direct()` itself resists
conversion. `use_keyevent_text_entry` reverted to unset on SHG07 (matching
SHG10 exactly) specifically to test this via a real, direct,
apples-to-apples comparison rather than resting on the theory alone.

**Deliberately still not attempted**: blindly switching the device's
default IME/subtype via a guessed id (e.g. `settings put secure
default_input_method`) — round 1 already showed once that a
plausible-sounding "bypass" theory can be wrong in a way only real
hardware reveals; guessing an id here risks a worse, harder-to-diagnose
failure than the one it would replace.

**Round 6 (2026-09-15, live re-test of round 5's revert):** confirms
round 5's hypothesis directly. `input_text_direct()` (SHG10's own,
previously-untouched method) failed on SHG07 in the exact same way as the
keyevent approach: typed `rakuten.jp`, field read back
`らくてん。ｊｐ`. Proves the injection method was never the variable —
the keyboard's current mode is. Real APN entries on SHG07 still cannot be
saved; this is not yet solved.

Also surfaced a second cascading-failure gap in the round-3 cleanup:
cancelling the *field* dialog (`dialog_cancel_button_resource_id`) backs
out of that dialog, but leaves the device sitting on the
"アクセスポイントの編集" edit *form* for the abandoned new entry — not
back on the APN *list*. The retry's `android.settings.APN_SETTINGS`
intent landed on that leftover form again, failing navigation exactly
like round 3's original bug. Fixed the same way: a second best-effort
cleanup tap, `apn_settings.navigate_up_content_desc` (real, confirmed —
the standard AOSP toolbar "上へ移動" back-arrow, seen in SHG10's real
dumps; inherited/unconfirmed for SHG07, whose own dumps have only ever
captured a dialog's foreground window, never the toolbar behind it) —
tapped after Cancel to fully exit the abandoned entry.

**Round 7-9 (2026-09-15, same day): 🎉 real fix found and directly
confirmed.** Client pushed back on the dead-end conclusion above and
pursued the on-screen keyboard's mode-toggle key further, using a
different, more direct tool than `uiautomator dump`: Android's own
**Settings > Developer options > Input > "Pointer location"**, which
overlays real X/Y coordinates on screen for any touch. This produced a
real, confirmed coordinate for the かな/英数 toggle key: **(106, 2239)**.
Directly confirmed via a scripted `adb shell input tap`, not just manual
touch — `adb shell input tap 106 2239` (run twice — the key appears to
cycle through more than two states) followed by `adb shell input text
"a"` produced a correctly committed half-width `a` in the field, not
hiragana. This is the first time in this entire investigation that
correct ASCII text has actually landed in an SHG07 APN field.

Implemented: `tap_at_coordinates()` (`src/device/ui_automator.py`) — a
deliberate, documented exception to every other tap in this codebase
(which always resolves a real resource-id/text/content-desc from the
current dump first): taps a raw screen coordinate with no lookup at all,
because there is nothing in the accessibility tree to look up — the
keyboard genuinely never appears in any dump, confirmed twice. New
`apn_settings.keyboard_mode_toggle_tap: [106, 2239]` (SHG07 only — tied
to this device's exact screen resolution, must be re-confirmed via
Pointer Location on any other device before reuse) is tapped twice before
typing into each non-numeric field (名前/APN); MCC/MNC are unaffected and
untouched (`input_digits_direct()` already works regardless of keyboard
mode).

**This is the strongest evidence found so far in this whole
investigation** — not a theory, not a dump, but a scripted `adb shell`
command directly producing the correct character. Not yet re-verified
against a full live `configure_apn()` run (only the isolated tap+type
sequence has been confirmed) — the next real run is what confirms
whether this actually gets a full APN entry saved end-to-end on SHG07 for
the first time.

## Schema additions beyond the original task prompt's illustrative example

Stage A already added 6 fields beyond the prompt's illustrative schema
(`wifi_settings.password_field_resource_id`,
`wifi_settings.connect_button_resource_id`,
`apn_settings.add_button_resource_id`, `apn_settings.mcc_field_resource_id`,
`apn_settings.mnc_field_resource_id`) because the specified function
signatures needed somewhere to put that data. Stage B adds more, all driven
by what real captures actually showed rather than by further guessing:

- `wifi_settings.menu_path`, `apn_settings.menu_path` steps can now be
  `{"type": "text"|"resource_id"|"content_desc", "value": "..."}` (or a bare
  string, still supported, for menu_path lists — the shape legacy models
  keep using) — needed once real data showed some navigation steps are
  icons with a resource-id (the APN gear icon) rather than text menu items.
- `apn_settings.field_row_resource_id` + `*_field_label` — replaces the
  literal-resource-id-per-field assumption for any model where real data
  shows fields don't have dedicated ids (confirmed true for SHG10; unknown
  for the other 3 until their own dumps exist).
- `apn_settings.dialog_edit_field_resource_id` /
  `dialog_confirm_button_resource_id` — the per-field edit dialog's own
  ids, resolved (see "Resolved — per-field entry dialog" above).
- `apn_settings.overflow_menu_content_desc` / `save_menu_item_text` — the
  real, confirmed two-tap save flow (replaces the earlier
  `save_action_candidates` list, which recorded two unconfirmed guesses;
  one turned out right, one wrong — see "Resolved — Save flow" above).
- `ui_automator.py` gained `find_by_content_desc`/`tap_by_content_desc`
  (icon-only controls), `node_is_checked` (toggle/switch state),
  `get_node_text` (reading dialog/message content, not just detecting
  presence), `scroll_down` + `wait_for_text_to_disappear` (wizard
  spinner/scroll screens), `input_text_direct` (numeric field entry
  bypassing the IME), `tap_left_of_content_desc` (2026-09-11: estimates a
  same-width adjacent icon's position from a confirmed neighbor's real
  bounds — generic fallback for any icon-only control with no identifier
  of its own captured yet), and a `HazardousScreenError` guard (see below).
- `apn_settings.add_button_content_desc` (2026-09-11) — the "+ add new
  APN" icon's own content-desc, once real data showed it has one (unlike
  `add_button_resource_id`, which this icon genuinely lacks on this
  build). Takes priority over both `add_button_resource_id` and the
  `tap_left_of_content_desc()` fallback when set.

## Safety guard added (Stage B Task 4)

A live notification — 「USBデバッグが接続されました — 無効にするにはここを
タップしてください」 (USB debugging connected — tap here to disable) — sits
in the notification shade during automation on SHG10 (docs/record.md).
Confirmed only by direct observation during a live session, not a captured
dump (its exact bounds are unknown). `ui_automator.py` now refuses to tap
*anything* on a screen whose dump contains this text at all (rather than
computing an exclusion zone from bounds we don't have) — see
`HazardousScreenError`, `tests/test_ui_automator.py`'s hazard tests. This
is a whole-screen refusal, deliberately conservative; it hasn't been tested
against a real capture of the notification itself, only against the
transcribed text.

## Real-device bugs found and fixed (infrastructure, not device data)

- **`adb.platform_tools_path` misconfiguration**: it's a directory, but was
  being passed straight through as the `adb` executable path itself, so
  every `AdbClient` call failed with `OSError`, silently swallowed into a
  plain `False` by `is_connected()` — indistinguishable from a genuinely
  disconnected device. Fixed: `main_phase2._resolve_adb_path()` joins the
  directory with the executable name and verifies it exists;
  `AdbClient.is_connected()` now raises `AdbCommandError` instead of
  swallowing this class of failure into `False`.
- **UTF-8 decode crash**: `subprocess.run(..., text=True, ...)` decodes
  using the OS locale codepage (`cp932` on the client PC's Japanese-locale
  Windows) rather than UTF-8, which is what `adb`'s actual output uses.
  Real device output (`dumpsys wifi`, containing real Wi-Fi SSIDs) crashed
  a background thread inside `subprocess.run()` itself — invisible to any
  `try`/`except` in this codebase — leaving `stdout=None` and surfacing
  several calls later as a confusing `TypeError`. Fixed: explicit
  `encoding="utf-8", errors="replace"`.

Neither of these were device-data gaps — both were pure code bugs, found
only because real hardware surfaced conditions (a real Windows locale, real
non-ASCII device output) that the fake/mock ADB layer never exercised.
