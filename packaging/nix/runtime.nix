{ pkgs }:
with pkgs; [
  bash bc brightnessctl cliphist coreutils curl ddcutil eza ffmpeg file findutils
  fontconfig fuzzel gawk geoclue2 gettext glib gnugrep gnused gnutar gzip
  hypridle hyprpicker hyprshot hyprsunset imagemagick jq libqalculate matugen
  networkmanager nodejs pipewire pulseaudio wireplumber playerctl ripgrep slurp songrec sox starship swappy
  tailscale tesseract translate-shell uv wget gpu-screen-recorder wl-clipboard wlogout wtype
  xdg-user-dirs ydotool
  bibata-cursors adw-gtk3 material-symbols rubik twemoji-color-font readexpro
  nerd-fonts.jetbrains-mono
  kdePackages.dolphin
  kdePackages.systemsettings kdePackages.kconfig
  kdePackages.plasma-workspace procps
]
