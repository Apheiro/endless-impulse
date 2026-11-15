# Native Polkit authentication

The desktop uses the upstream Quickshell 0.3.2 `Quickshell.Services.Polkit`
backend. The host Polkit daemon remains the authorization authority. There is no
privileged helper, custom PAM implementation or automatic approval. AuthFlow
owns queueing, retries, identity selection and successive challenges; input is
enabled only while `isResponseRequired` is true. Waiting for response validation
does not end a conversation or unmap the card. A rejected response keeps the
same card and displays an error even when an earlier supplementary informational
message remains. State-only debug messages distinguish request start, rejection
and completion without logging input, identity, prompt or cookie. Responses go directly to
AuthFlow in the same process. Fields are cleared on submit, cancellation,
completion, flow/identity/prompt changes and retry; credentials never enter the
focus transport or logs. Clearing a QML field is not a guarantee of memory zeroing.

Both layouts share `PolkitPanel` and `PolkitPrompt`. The presentation host lives
outside the layout loaders in `shell.qml`, so switching layout does not register
another agent or destroy a conversation. A single transparent layer surface
appears on the focused monitor at request start (first screen is the fallback).
It ignores exclusive zones, reserves no workspace area, and stays bottom-center.
Only the card accepts pointer input. Its keyboard-exclusive focus lasts for the
conversation, not the exit animation; the window is card-sized, not fullscreen.
A scrollable body handles small screens. The translation from below the screen
uses the same curve/duration in reverse on exit, without animating on retries.
Timing uses the existing Appearance duration, already scaled by animationSpeed.
`appearance.reducedMotion: true` makes this panel transition immediate; setting
`appearance.animationDurations.smallMove` to zero also disables its movement.
The existing `quickshell:polkit` no-animation compositor rule is retained.

## Focus suspension across shell and Settings

`AuthenticationFocusState` protects local grabs synchronously when AuthFlow
starts. Its Python standard-library bridge publishes a boolean and revision
through a Unix socket inside an owned 0700 XDG runtime directory, scoped to
`HYPRLAND_INSTANCE_SIGNATURE` (or `WAYLAND_DISPLAY`). Socket peers must have the
same UID. An exclusive flock allows only one publisher/session; only that
publisher's private stdin accepts visibility changes. Socket clients can only
read state and acknowledge revisions. No generic IPC method can enable the gate.
The trust boundary is the session user; this is not isolation from malicious code
already executing as that same user, which can also modify their QML sources.

Consumers briefly suspend grabs while their initial subscription is unresolved
(two-second startup deadline, then a diagnostic and normal focus behavior).
Existing connected subscribers acknowledge after applying QML bindings. The card takes
focus after those acknowledgements. To keep authentication usable if a client is
unresponsive, presentation proceeds after one second with a warning. Thus a
hung subscriber, an unavailable transport, another user/session, third-party
clients and toolkit-native popup auto-dismissal are **not covered by a global
guarantee**. Native grabs in this repository use `AuthenticationFocusGrab`:
GlobalFocusGrab consumers (sidebars, quick panels, overview, media, bar editor,
etc.), overlay, tray/recording menus, Windows-style start/action/notification
centers and bar popups, plus Settings. Explicit controls/shortcuts remain active.
The wrapper disarms clears caused by release and rearms on the next QML turn;
it does not close preexisting windows when authentication ends.

The local gate stays set through the entire inverse transition and unmapping.
A request arriving during exit reverses that transition and retains protection.
The bridge refreshes a 15-second lease every five seconds only while active;
these service times do not depend on animationSpeed. EOF, owner death or lease
expiry releases remote state. Subscribers use inotify for publisher replacement,
without an idle polling loop, and have their own lease if the publisher freezes.
Publisher loss destroys the native agent loader rather than leaving a registered
agent without UI. A subscriber process failure clears its local state and logs a
diagnostic; reopening that Settings/shell process restores its subscription.

Firewalld's `authorizing` flag is a separate, local pre-pkcheck handshake. Settings
releases its grab before acknowledging permission to launch the challenge. It
also consumes actual session authentication state, including its animated exit.
Cancellation/denial retains the page and requires a manual retry. Background
reads never create another interactive challenge. See [Firewalld](firewalld.md).

## Startup, dependencies and recovery

Arch requires host `polkit`, plus upstream Quickshell built with its Polkit
module. Nix already uses upstream Quickshell and declares host Polkit in its
service manifest; no new package, lock or privileged service is needed. Fedora
uses `polkit` explicitly. The legacy Gentoo Quickshell ebuild already has the
`policykit` USE dependency; enable it. Its legacy KDE metapackage still bundles
an optional agent and must not autostart that agent alongside Quickshell.

KDE is optional manual recovery (`polkit-kde-agent` on Arch, `polkit-kde` on
Fedora). Hyprland/Fedora startup and the legacy installer no longer launch it.
Installing KDE's executable alone does not override the native agent, but any
external systemd/autostart agent can win Polkit's session registration. We do not
kill those processes or change personal startup configuration automatically.
Inspect Quickshell logs for `Polkit: native agent is not registered` or a focus
transport diagnostic. PolkitService exposes `registered` for in-process diagnosis.

The existing desktop IPC also exposes read-only registration diagnosis and
explicit native-host stop/start, without stopping the rest of the desktop:

```bash
python3 src/quickshell/scripts/shell/control.py ipc authentication status
python3 src/quickshell/scripts/shell/control.py ipc authentication stop
# After stopping any fallback/competing agent yourself:
python3 src/quickshell/scripts/shell/control.py ipc authentication start
```

`stop` closes the publisher and destroys the native listener; its lock is released
asynchronously. Wait for that completion before fallback (the helper refuses an
occupied lock safely). `start` is a manual recovery attempt, without a restart
loop or terminating other agents. These methods cannot set authentication active.
They exist only in the desktop presentation host, not in Settings.

For KDE recovery, first stop the native authentication host via IPC (or stop the
whole desktop yourself). Then, if KDE is installed, run:

```bash
bash ~/.config/hypr/hyprland/scripts/start_polkit_agent.sh --fallback
# From a development checkout:
bash config/xdg/config/hypr/hyprland/scripts/start_polkit_agent.sh --fallback
```

The helper refuses an occupied native host lock, respects existing known agents,
and keeps its own lock while KDE runs. Do not run it as root, with sudo or pkexec.
It does not start unless `--fallback` is explicit. Return to native mode by
stopping the fallback and starting the native host again via IPC (or starting
one desktop instance). Native registration
failure does not silently start another competing listener; it logs recovery
instructions. Until recovery, a competing agent handles requests if registered;
if no agent registered successfully, interactive authorization is unavailable.

## Validation and limits

`tests/test_polkit_qml.py` executes the real service, prompt, animation and guard
with isolated AuthFlow, compositor-window and grab fixtures. No real listener,
password or system authorization is involved. `tests/test_authentication_focus.py`
also validates the production publisher state machine through pipe fixtures
without sockets. Its separate host integration tests exercise the actual session
bridge with separate processes, revisions, owner
exclusion, read-only clients, lease, owner death and replacement. It skips where
Unix socket bind is denied. Firewalld tests cover the existing handshake,
denial/timeout/manual recovery and Settings navigation has its separate suite.

This implementation environment denied Unix socket bind and Wayland access;
actual cross-process transport and compositor rendering need validation on the
host. Offscreen QML validates bindings and animation state, not Wayland input,
monitor routing, compositor masks, visual contrast, assistive technology or PAM.
The user remains the primary tester for those checks. Nix evaluation/build also
requires access to its writable cache/store; locks and installed packages were
not changed. Test incorrect response/retry, Esc/cancel, multifactor, consecutive
requests, monitor removal, small monitors, light/dark/transparency, reduced motion,
Settings opened before a request, and process death before declaring host QA done.

Upstream API: [Polkit module](https://quickshell.org/docs/v0.3.2/types/Quickshell.Services.Polkit/),
[AuthFlow](https://quickshell.org/docs/v0.3.2/types/Quickshell.Services.Polkit/AuthFlow/).

Verification in the implementation sandbox (2026-11-04): Qt 6 parsing of all 28
changed/new QML files, Bash syntax, Python compilation, `git diff --check`, the
21 Firewalld tests, four Polkit QML/startup tests, publisher state-machine fixture
and dependency-map tests passed. Static qmllint retains warnings for Quickshell's
dynamic `qs.*` imports and backend-specific types, so it is not a clean semantic
lint result. Two real socket transport tests were skipped. A general local run
executed 241 tests: 200 passed, 39 skipped, two environment failures (private
Bluetooth D-Bus socket denied; host Python missing `loguru`). Subsequent targeted
startup tests also passed. Direct Settings navigation failed before QML loading
because Wayland/runtime access is denied. `./dev check` was blocked first by the
read-only Nix cache, then by denied Nix daemon access with a temporary cache.
