# Host installation and integration

This directory contains installation code; the application source lives in
`src/quickshell/`. Do not place runtime UI code in the installer.

- `commands/`: subcommands of the root `./setup` entry point. The main
  installation sequence uses `commands/install/`.
- `distros/`: host-specific package and service setup for Arch, Fedora,
  Gentoo and Nix-based installs. Some legacy distribution variants may need
  additional testing.
- `dependencies/` and `dependencies.py`: reference dependency manifests
  and package lookup logic.
- `lib/`: shared Bash functions and environment setup.

The installer maps `src/quickshell` to the user's
`$XDG_CONFIG_HOME/quickshell/endless-Impulse`, and maps `config/xdg/config` and
`config/xdg/data` to their XDG destinations. Nix packaging under
`packaging/nix/` handles the immutable runtime independently.

Do not run `./setup install` as part of automated tests: it may overwrite
user configurations or change system services.
