# Lock screen authentication

The Quickshell lock screen authenticates the current OS user with the host's
`login` PAM service. Renaming Endless Impulse does not change that service or
the user's password.

On non-NixOS hosts, the Nix launcher selects `/usr/bin/python3` to run
`scripts/lock/authenticate.py` in an isolated process with host PAM. It needs
the host Python standard library and PAM, without additional Python packages.
Credentials travel through a private stdin pipe, never command arguments or
environment variables. Only successful PAM authentication unlocks the screen;
errors, crashes and malformed input fail closed. Traditional installations and
NixOS continue using Quickshell's native PAM context.

Do not preload host PAM into Nix Qt or change `/etc/pam.d` to permit access.
Nix PAM on Arch can look for unavailable modules in `/nix/store` and for the
NixOS privileged helper under `/run/wrappers/bin`, causing correct passwords
to fail. Repeated failures may also trigger the host's temporary account lock.

After updating the checkout, launch with `./dev run` (or `./dev restart` if this
checkout is already running). Do not restart a shell while its screen is locked.
If previous attempts locked the account, wait for the host's configured timeout;
`faillock --user "$USER"` displays the failure records on Arch. A successful
real-password unlock must be verified by the user; automated checks do not
attempt authentication against their account.
