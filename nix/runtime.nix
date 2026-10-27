{ pkgs }:
with pkgs; [
  bash bc brightnessctl cliphist coreutils curl ddcutil eza ffmpeg file findutils
  fontconfig fuzzel gawk geoclue2 gettext glib gnugrep gnused gnutar gzip
  hypridle hyprpicker hyprshot hyprsunset imagemagick jq libqalculate matugen
  networkmanager nodejs playerctl ripgrep slurp songrec sox starship swappy
  tesseract translate-shell uv wget wf-recorder wl-clipboard wlogout wtype
  xdg-user-dirs ydotool
  bibata-cursors adw-gtk3 material-symbols rubik twemoji-color-font readexpro
  nerd-fonts.jetbrains-mono
  kdePackages.bluedevil kdePackages.dolphin kdePackages.plasma-nm
  kdePackages.systemsettings kdePackages.kconfig
  kdePackages.plasma-workspace procps
]
