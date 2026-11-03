# Native Tailscale integration

The right sidebar includes a Tailscale toggle in Android and classic styles.
Left-click connects/disconnects; right-click opens a centered panel.
The management panel stays open across sidebar/menu dismissal and status
refreshes. Close it with its close button or Escape; locking the session also
closes it. Existing
Android toggle layouts are preserved; add Tailscale through the toggle editor.
New layouts include it by default.

Connections shows saved accounts, account switching, browser login, health and
exit nodes. Devices lists peer addresses, online state and a bounded ping.
Preferences edits only explicitly applied values through `tailscale set`.
Advanced discovers commands and options from the installed CLI's `--help`,
including nested commands. Enable each desired option, choose its value and add
one field per positional argument. Review and confirm before running. An empty
included text field explicitly clears a value; an omitted option stays unchanged.
CLI help descriptions remain in the language supplied by Tailscale.

Operations can change networking, publish services, expire keys or remove saved
accounts. Administrator mode uses the existing Polkit prompt. SSH and netcat
open the configured terminal; that terminal owns their lifetime. Other operations
remain in the panel, with output, a masked response field for stdin prompts and
Stop. Cancellation and shell shutdown terminate the managed process group, with
a forced stop after two seconds if needed. Browser login URLs come from daemon
status. A failed operation displays an error and can be retried manually.

The bridge passes argument arrays without a shell. Snapshots allowlist preference
fields and never send raw debug preferences or persistent keys to QML. Known key
formats, explicit secret option values and positional values are redacted from
output. Debug, configure, cert and lock output is suppressed because those
commands can produce arbitrary credential dumps or private keys; use explicit
file destination options when appropriate. Output is bounded and stays in memory.
Avoid putting credentials in generic non-secret options.

Arch installs `tailscale` and enables `tailscaled` on systemd. The Nix runtime
bundles the CLI, and its host-service manifest declares `tailscaled.service`.
The daemon, accounts and operator permissions belong to the host. Installing or
opening the panel does not log in, switch accounts or connect automatically.
For non-systemd hosts, enable the distribution's Tailscale service separately.

Validation: `./dev check -p test_tailscale.py` uses a disposable simulated CLI,
isolated XDG directories and a hidden QML window. It does not change real accounts,
preferences or connectivity. User validation of live networking and visual
appearance remains separate from these automated checks.

The panel adapts between one and two columns, with a connection summary,
account selection, routing controls, searchable devices and grouped preferences.
Addresses have copy actions. Advanced tools use searchable command tiles and
compact option forms; CLI help is available on demand. The Administration button
opens `https://login.tailscale.com/admin` in the default browser.

The symbolic mark is extracted from the upstream Tailscale web client asset:
https://github.com/tailscale/tailscale/blob/main/client/web/src/assets/icons/tailscale-logo.svg
Its upstream license is retained in `assets/icons/tailscale.LICENSE`. Tailscale's
name and mark remain the property of their respective owners.
