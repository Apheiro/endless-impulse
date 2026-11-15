# Install scripts for Fedora Linux

Note:
- The scripts here are **not** meant to be executed directly.
- This folder should reflect the equivalents of `/installer/distros/arch/` but under Fedora.
  - **When `/installer/distros/arch/` is newer than this folder, an update on this folder is very likely needed.**
  - Useful link: [Commit history on installer/distros/arch/](https://github.com/end-4/dots-hyprland/commits/main/installer/distros/arch)
- See also [Install scripts | illogical-impulse](https://ii.clsty.link/en/dev/inst-script/)

## Contributors
- Author: [ririko6z](https://github.com/ririko6z)

## Tested
- It has been tested on Fedora Everything 44 on the `x86_64` platform.

## Post installation

Bluetooth and networking open native Endless Impulse panels. BlueDevil and
Plasma-NM overrides are no longer needed. See [network integration](../network.md)
for NetworkManager plugins and hotspot support.

Set the update application in `~/.config/endless-Impulse/config.json` to the
preferred Fedora update command, for example:

```json
{"apps":{"update":"kitty -1 --hold=yes fish -i -c 'sudo dnf update'"}}
```
