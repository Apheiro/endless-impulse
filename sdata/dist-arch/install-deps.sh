# Sourced by setup. Install ordinary upstream packages; no local metapackages.
# shellcheck shell=bash

command -v pacman >/dev/null || { echo 'Arch Linux with pacman is required.' >&2; exit 1; }

if [[ "$SKIP_SYSUPDATE" != true ]]; then
  v sudo pacman -Syu
fi

# Bootstrap only the tools needed to read the manifest and build AUR packages.
v sudo pacman -S --needed base-devel git python npm
readarray -t repo_packages < <(python3 "$REPO_ROOT/sdata/dependencies.py" repository --missing)
if ((${#repo_packages[@]})); then v sudo pacman -S --needed "${repo_packages[@]}"; fi

if ! command -v yay >/dev/null; then
  x mkdir -p "$REPO_ROOT/cache"
  x git clone https://aur.archlinux.org/yay-bin.git "$REPO_ROOT/cache/yay-bin"
  x pushd "$REPO_ROOT/cache/yay-bin"
  x makepkg -si
  x popd
fi
readarray -t aur_packages < <(python3 "$REPO_ROOT/sdata/dependencies.py" aur --missing)
if ((${#aur_packages[@]})); then v yay -S --needed "${aur_packages[@]}"; fi
install-math-runtime

# Service-specific packages are optional on non-systemd Arch derivatives.
if command -v dinitctl >/dev/null; then
  dinit_packages=()
  for pkg in userspawn-dinit bluez-dinit networkmanager-dinit pipewire-dinit pipewire-pulse-dinit wireplumber-dinit power-profiles-daemon-dinit; do
    pacman -Si "$pkg" >/dev/null 2>&1 && dinit_packages+=("$pkg")
  done
  if ((${#dinit_packages[@]})); then v sudo pacman -S --needed "${dinit_packages[@]}"; fi
fi
