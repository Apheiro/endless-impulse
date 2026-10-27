# Sourced by setup. Use the independent root flake; never switch Home Manager.
command -v nix >/dev/null || {
  echo 'Install and initialize Nix first; see nix/README.md.' >&2
  return 1
}
v nix --extra-experimental-features 'nix-command flakes' profile install "$REPO_ROOT#default"
