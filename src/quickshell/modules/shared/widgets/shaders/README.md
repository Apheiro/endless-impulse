# Color tint

`color-tint.frag` uses the non-separable Color blend (`SetLum` / `ClipColor`):
https://www.w3.org/TR/compositing-1/#blendingnonseparable

It preserves original per-pixel luminosity and alpha, applying the theme tint's
chrominance. Premultiplied alpha is removed before blending and restored afterward.
Tint alpha controls blend strength; a transparent tint retains the original colors.

The checked-in QSB allows source checkouts and native installations to use the
shader without installing a compiler. Regenerate after editing the GLSL source:

```sh
/usr/lib/qt6/bin/qsb --qt6 -o color-tint.frag.qsb color-tint.frag
```

Use the project's Qt 6 shader baker. The Qt 6 preset includes OpenGL, Vulkan,
Direct3D and Metal variants. Nix rebuilds the QSB from source during packaging.
