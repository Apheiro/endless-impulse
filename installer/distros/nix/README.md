# Nix runtime

Use the root `flake.nix`, `flake.lock` and `packaging/nix/README.md`.
The previous experimental Home Manager installer has been replaced. The current
runtime neither overwrites Home Manager configuration nor installs a compositor
or system services. Dependencies come from ordinary Nixpkgs packages and the
locked upstream MathJax npm packages.

Development: `./dev build`, `./dev restart`, `./dev settings`, `./dev check`.
