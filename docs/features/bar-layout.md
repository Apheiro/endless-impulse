# Bar layout

Right-click an empty part of the horizontal bar, then choose **Edit bar**.
Drag panels along the single row. Drag new panels from the catalog onto the bar,
or click a catalog entry to append it. Select a panel to move it with the arrows
or remove it. Panels keep their real appearance; an input overlay handles dragging
without activating their controls. Tooltips follow the hovered entry.

**Fixed space** reserves an editable width (4–600 logical pixels). Select it and
edit the width field, then confirm with Enter or leave the field.
**Flexible space** expands to occupy the available room; multiple flexible
spaces share that room equally (within each side when a module is pinned). Spaces and separators can repeat.

Select a module and toggle **Center on screen** to pin its midpoint to the
exact monitor center. Only one module is pinned. Neighboring modules stay beside
it, regardless of the opposite side's width; a flexible space separates these
neighbors from modules toward the screen edges. Toggle the button again to
return to a fully free row. Spaces and separators cannot be pinned. If contents
no longer fit, each side scrolls horizontally without overlapping or moving the
pinned module. Use the wheel or the small scrollbar while editing.

**Save** persists the row, fixed-space widths and center anchor together.
**Cancel**, Escape or an outside click discards the draft. **Reset** restores
the default draft. Settings → Bar → Panel layout also offers **Restore original
layout**. The original renderer remains active while `bar.layout` is `null`;
the vertical bar keeps its existing layout.

Existing three-zone layouts are read into the free row in their original order,
with flexible spaces at the former boundaries. The previous center's clock (or
first eligible center module) becomes the anchor. This conversion does not write
preferences until Save. New saved layouts have the shape
`{version: 2, items: [{key, type, size?}], centerKey}`. Removing the pinned module
also removes the anchor.

Hardware-dependent modules may disappear outside edit mode when unavailable;
they show placeholders in the editor. Saving a layout containing weather enables
weather. Updates use the existing service and do not install packages. Sound,
network, Bluetooth, recording and tray entries retain their usual context menus
outside edit mode. Active recording remains visible even if the row omits both
recording and utility panels.

`services/BarLayout.qml` owns migration, validation and draft changes.
`ConfiguredBarContent.qml` uses Qt layouts to distribute flexible spaces and
clipping viewports around the optional center anchor. `BarWidget.qml` resolves
entries to existing components. Network speed samples `/proc/net/dev` only while
visible, without launching subprocesses per sample. The catalog was informed by
[end4-pC](https://github.com/pctrade/end4-pC), using the local theme and services.

Focused check, in the development environment:
`python3 -m unittest installer.tests.test_bar_layout -v`.
It uses isolated preferences, real bar windows and pointer events on Wayland.
