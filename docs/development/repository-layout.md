# Repository layout and deployment

| Source | Installed/used as |
| --- | --- |
| `src/quickshell/` | Quickshell source, deployed to `$XDG_CONFIG_HOME/quickshell/endless-Impulse` |
| `config/xdg/config/*` | `$XDG_CONFIG_HOME/*` |
| `config/xdg/data/*` | `$XDG_DATA_HOME/*` |
| `config/variants/*` | Optional replacement selected by installer |
| `installer/commands/*` | Implementation of root `./setup` subcommands |
| `installer/distros/{arch,fedora,gentoo,nix}/` | Host-specific dependencies |
| `installer/dependencies/` | Arch reference manifest |
| `runtime/python/` | Legacy/host Python runtime requirements |
| `runtime/math/` | MathJax and npm lock |
| `packaging/nix/` | Nix derivation, locked runtime and service helper |
| `tests/` | Automated test suite invoked by `./dev check` |

The repository root retains `flake.nix`, `flake.lock`, `dev` and `setup`
as stable command entry points. The source tree does **not** need to mirror
`~/.config/`. Installers and Nix are responsible for translating paths.

For local development: `./dev run`, `./dev settings`, `./dev check`.
`./dev restart` prepares the new package before stopping the registered active
shell, even when it was started from another checkout or a backup. It then starts
this checkout. `./dev stop` also targets the registered active shell. A failed
package build leaves the running desktop intact.
The installed Quickshell configuration is named `endless-Impulse`.
The desktop integration helper resolves its Lua module from the repository's
`config/xdg/config/hypr/` tree in development, or from the sibling `hypr/` tree
under the installation's XDG config root, including inside the Nix bundle.
Deployment tests load copies of the helper from all three layouts with temporary
user configuration and mocked compositor calls.
The old `ii` and `waffle` values remain recognized as **saved shell-family
preferences**, not folder names: migrating those values is a separate
compatibility change. Keep existing `docs/features/` documents next to
this guide rather than the installer.
