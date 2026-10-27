# Artificial Impulse

Artificial Impulse is a customizable Hyprland/Wayland shell and a fork of
[illogical-impulse](https://github.com/end-4/dots-hyprland).
It uses ordinary upstream packages and an independent, locked Nix runtime.

## Develop

With a functioning Hyprland session and Nix initialized:

```bash
./dev build
./dev restart
./dev settings
./dev check
```

QML changes reload from the repository. Dependencies are fixed by `flake.lock`;
formulas use locally installed MathJax assets rather than the MicroTeX fork.
Do not run another shell configuration alongside this one.

See [nix/README.md](nix/README.md) for installation, host requirements, graphics,
updates and rollback. Installations from a private repository require access to
that repository. The package does not overwrite your personal configurations.

For native Arch dependencies, see [sdata/dist-arch/README.md](sdata/dist-arch/README.md).
For shortcut editing, see [sdata/shortcuts-development.md](sdata/shortcuts-development.md).
Feature priorities and validation status are tracked in [ROADMAP.md](ROADMAP.md).
The user is the principal acceptance tester. Changes accumulate until a commit
is explicitly requested.

## Preferences

Settings are stored in `$XDG_CONFIG_HOME/artificial-impulse` and shortcut state
in `$XDG_STATE_HOME/artificial-impulse`. Launchers migrate the old directories
without overwriting existing destinations and retain legacy path aliases.
Existing keyring entries remain readable; new entries use `artificial-impulse`.
The `ii` source directory and legacy Python environment variable remain runtime
compatibility identifiers. External package names and license notices are unchanged.
