# UI foundations and bar modules

There is one foundation directory: `src/quickshell/modules/shared/primitives/`.
A primitive defines a reusable visual or interaction contract, or a content slot
for higher-level components. It must not implement application or system actions.
Composite controls, application-specific widgets and service-backed views remain
in `widgets/` or their feature directory. Reuse alone is not a reason to move a
component to primitives.

| Scope | Responsibility |
| --- | --- |
| `common/` | Text, input controls, buttons, groups, shapes, visual effects, layout and animation foundations |
| `settings/` | Settings cards, page and section surfaces and layout slots |
| `dialogs/` | Dialog surface, actions and structural text/layout elements |
| `bar/` | Module surface, simple action module, separators and non-content layout entries |

Import the specific scope, for example
`import qs.modules.shared.primitives.common`. Existing shared widgets continue to
live in `modules/shared/widgets`; shader assets and the upstream shapes submodule
remain there. Their consumers use explicit imports and updated resource paths;
there are no duplicate implementations or compatibility forwarding QML files.

## Bar responsibilities

- `bar/BarModuleRegistry.qml` maps stable saved IDs to QML module URLs. It has no
  styling or feature behavior.
- `bar/BarWidget.qml` lazily loads the selected module and passes the shared host
  properties. It also displays editor placeholders for unavailable modules.
- `bar/widgets/*Module.qml` supplies content, service state and actions. A content
  module derives from `BarModuleBase`; a simple icon/text action uses
  `BarActionModuleBase`. Fixed/flexible spaces and explicit separators derive
  from `BarLayoutItemBase` and do not draw module surfaces.
- `BarLayoutTile`, `BarLayoutFlow` and `ConfiguredBarContent` retain ordering,
  centering, clipping, selection and drag/drop. Saved IDs and preferences keep
  their existing format.

`BarModuleBase` owns the background, padding, complete pill ends, foreground,
hover/pressed/active/disabled treatment and theme animation. Capabilities are
explicit (`interactive`, `hoverable`, `surfaceEnabled`, `available`). Modules do
not set private background colors or select styling based on their catalog ID.
Content can retain semantic graphics such as battery progress, workspace state
or the red recording indicator.

In Pills mode each module gets one shared surface. In Line-separated mode the
normal surface is transparent and adjacent content modules are separated by a
line; spaces delimit groups and explicit separators are not doubled. Hover and
active feedback use the same theme states in both modes. Embedded controls can
set the generic `RippleButton.surfaceVisible` capability to false so they retain
their actions without painting another layer. Empty content reserves no pill
padding. Flow viewports clip only when contents overflow.

The original renderer remains available while `bar.layout` is null. Its
`BarGroup` delegates its surface to the same primitive while retaining original
grouping and the vertical layout API.

## Inventory

### bar

`BarActionModuleBase`, `BarLayoutItemBase`, `BarModuleBase`, `BarSeparator`.

### common

`Box`, `BoxLayout`, `ButtonGroup`, `ButtonMouseArea`, `Circle`, `CircularProgress`, `ClippedFilledCircularProgress`, `ClippedProgressBar`, `ColorTint`, `Colorizer`, `CustomIcon`, `DashedBorder`, `ErrorShakeAnimation`, `FadeLoader`, `FlowButtonGroup`, `FocusedScrollMouseArea`, `Graph`, `GroupButton`, `KeyboardKey`, `MaskMultiEffect`, `MaterialCookie`, `MaterialLoadingIndicator`, `MaterialShape`, `MaterialShapeWrappedMaterialSymbol`, `MaterialSymbol`, `MaterialTextArea`, `MaterialTextField`, `NavigationRailButton`, `OptionalMaterialSymbol`, `Pill`, `PointingHandInteraction`, `PointingHandLinkHover`, `PopupToolTip`, `Revealer`, `RippleButton`, `RoundCorner`, `ScrollEdgeFade`, `SecondaryTabBar`, `SecondaryTabButton`, `SegmentedControl`, `SidebarReveal`, `SineCookie`, `StateLayer`, `StateOverlay`, `StyledBlurEffect`, `StyledComboBox`, `StyledDropShadow`, `StyledFlickable`, `StyledImage`, `StyledIndeterminateProgressBar`, `StyledListView`, `StyledProgressBar`, `StyledRadioButton`, `StyledRectangle`, `StyledRectangularShadow`, `StyledScrollBar`, `StyledSlider`, `StyledSpinBox`, `StyledSwitch`, `StyledText`, `StyledTextArea`, `StyledTextInput`, `StyledToolTip`, `StyledToolTipContent`, `Toolbar`, `ToolbarButton`, `ToolbarTabButton`, `ToolbarTextField`, `VerticalButtonGroup`, `WavyLine`.

### dialogs

`DialogButton`, `DialogListItem`, `WindowDialog`, `WindowDialogButtonRow`, `WindowDialogParagraph`, `WindowDialogSectionHeader`, `WindowDialogSeparator`, `WindowDialogTitle`.

### settings

`ConfigRow`, `ContentPage`, `ContentSection`, `ContentSubsection`, `ContentSubsectionLabel`, `SettingsCard`.

## Verification

`test_primitives.py` compiles all foundations and both shell variants, then loads
every registered bar module and checks both group styles, rounded ends and active
foreground/background pairs. `test_bar_layout.py` exercises actual pointer input,
spaces, centering and persistence with isolated preferences. Settings, recording,
status navigation and tint rendering have targeted regression tests.
