# Arch Linux dependencies

The installer uses ordinary repository/AUR packages listed explicitly in
`../dependencies/arch.json`. It does not build or install `illogical-impulse-*`
packages. `quickshell` comes from Arch Extra; `bibata-cursor-theme-bin` is the
upstream cursor package from AUR. Formula rendering uses upstream MathJax and
its locally installed font package, locked by `../math/package-lock.json`.

List or check dependencies:

```bash
python3 installer/dependencies.py all
python3 installer/dependencies.py all --missing
```

`./setup install-deps` installs these packages and the formula runtime. The
normal full installer also configures services and copies files; it is not a
preview. Uninstallation retains shared dependency packages.

For an existing installation, preserve the dependencies of the old metapackages
as explicit packages before removing the wrappers. Do not use recursive removal
or disable dependency checks. Back up installable packages before replacing
Quickshell or cursor packages. Legacy package names remain in the manifest only
as a migration inventory.

Hyprland, GPU drivers, audio/network services, authentication agents and screen
locking remain host responsibilities. See `../dist-nix/README.md` for the
separate, locked application runtime.
