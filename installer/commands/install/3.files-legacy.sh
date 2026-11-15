# This script is meant to be sourced.
# It's not for directly running.

# shellcheck shell=bash

#####################################################################################
# MISC (For config/xdg/config/* but not quickshell, not fish, not Hyprland, not fontconfig)
case "${SKIP_MISCCONF}" in
  true) true;;
  *)
    for i in $(find config/xdg/config/ -mindepth 1 -maxdepth 1 ! -name 'quickshell' ! -name 'fish' ! -name 'hypr' ! -name 'fontconfig' -exec basename {} \;); do
#      i="config/xdg/config/$i"
      echo "[$0]: Found target: config/xdg/config/$i"
      if [ -d "config/xdg/config/$i" ];then install_dir__sync "config/xdg/config/$i" "$XDG_CONFIG_HOME/$i"
      elif [ -f "config/xdg/config/$i" ];then install_file "config/xdg/config/$i" "$XDG_CONFIG_HOME/$i"
      fi
    done
    install_dir "config/xdg/data/konsole" "${XDG_DATA_HOME}"/konsole
    ;;
esac

case "${SKIP_QUICKSHELL}" in
  true) true;;
  *)
     # Install this source as the ii configuration without replacing other Quickshell configurations.
    install_dir__sync src/quickshell "$XDG_CONFIG_HOME"/quickshell/endless-Impulse
    ;;
esac

case "${SKIP_FISH}" in
  true) true;;
  *)
    install_dir__sync_exclude config/xdg/config/fish "$XDG_CONFIG_HOME"/fish "conf.d"
    ;;
esac

case "${SKIP_FONTCONFIG}" in
  true) true;;
  *)
    case "$FONTSET_DIR_NAME" in
      "") install_dir__sync config/xdg/config/fontconfig "$XDG_CONFIG_HOME"/fontconfig ;;
      *) install_dir__sync config/variants/fontsets/$FONTSET_DIR_NAME "$XDG_CONFIG_HOME"/fontconfig ;;
    esac;;
esac

# For Hyprland
case "${SKIP_HYPRLAND}" in
  true) true;;
  *)
    install_dir__sync config/xdg/config/hypr/hyprland "$XDG_CONFIG_HOME"/hypr/hyprland
    if [ -f "${XDG_CONFIG_HOME}/hypr/hyprland.conf" ]; then
      mv "${XDG_CONFIG_HOME}/hypr/hyprland.conf" "${XDG_CONFIG_HOME}/hypr/hyprland.conf.old" # disable old config
      echo 'hyprland.conf has been renamed to hyprland.conf.old. This is to allow the new lua config to load.'
    fi
    for i in hyprlock.conf ; do
      install_file__auto_backup "config/xdg/config/hypr/$i" "${XDG_CONFIG_HOME}/hypr/$i"
    done
    for i in hyprland.lua ; do
      case "${SKIP_HYPRLAND_ENTRY}" in
        true) true;;
        *) install_file "config/xdg/config/hypr/$i" "${XDG_CONFIG_HOME}/hypr/$i" ;;
      esac
    done
    for i in hypridle.conf ; do
      if [[ "${INSTALL_VIA_NIX}" == true ]]; then
        install_file__auto_backup "config/variants/via-nix/$i" "${XDG_CONFIG_HOME}/hypr/$i"
      else
        install_file__auto_backup "config/xdg/config/hypr/$i" "${XDG_CONFIG_HOME}/hypr/$i"
      fi
    done
    # Native Quickshell Polkit needs no separate exec-once agent.

    install_dir__ignore_existing "config/xdg/config/hypr/custom" "${XDG_CONFIG_HOME}/hypr/custom"
    ;;
esac

install_file "config/xdg/data/icons/illogical-impulse.svg" "${XDG_DATA_HOME}"/icons/illogical-impulse.svg
