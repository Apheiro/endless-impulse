# GPU Screen Recorder

Endless Impulse uses the GPU Screen Recorder CLI directly. The existing
`record.sh` entry point and Hyprland shortcuts remain compatible. The host binary
(`/run/wrappers/bin` or `/usr/bin`) takes precedence over the pinned Nix fallback;
`DOTS_GSR_BINARY` can explicitly select another executable. Host GSR commands run
without Nix/Qt graphics library overrides so they use the matching host drivers.

Settings → Recording includes video, audio, output naming and advanced capture,
encoding, replay, streaming, plugin and FFmpeg options. The menu checks the
installed CLI's flags and detected GPU codecs. Source composition accepts GSR's
native `|` and `;key=value` syntax, including positioning, scaling, alignment,
flipping and V4L2 camera options. Unsupported hardware/format combinations produce
an actionable error rather than silently switching encoders.

Preferences: `$XDG_CONFIG_HOME/endless-Impulse/recorder.json` (mode 0600).
Before the first save, the old `config.json → screenRecord.savePath` is read as
the output directory. Other preferences in that file are untouched.

Normal/audio filenames and subfolders accept strftime patterns, for example:

- Folder: `%Y/%m/%A`
- Name: `recording_%Y-%m-%d_%H-%M-%S`
- `%a` / `%A`: abbreviated/full weekday, `%d`: day, `%H` / `%M` / `%S`: time.
- `%f`: microseconds, `%%`: a literal percent sign.

The container extension is added automatically; existing files receive a numeric
suffix. Subfolders cannot escape the chosen output directory. A preview shows the
result without creating files. Replay filenames/date folders and parallel captures
follow GSR's native naming; the custom normal-recording pattern does not rename
files already produced by GSR callbacks. Streaming uses the configured URL.
Authentication uses `GSR_AUTH`, not a command-line token.

Right-click the bar's recorder button to choose a region or full-screen recording
on that bar's monitor. Left-click starts the saved default target or stops the
active session. The menu also offers pause/resume, replay saving, and parallel
recording when those session modes are configured. The recorder button becomes a themed pill with a blinking red dot and the elapsed
recording time in the current theme text color; paused time is excluded. The clock
and calendar remain separate. Auto-hidden
horizontal bars remain visible during capture.

Regions use global **logical** desktop coordinates, including negative offsets,
monitor scaling and rotation. The selector closes before capture starts. A
persistent input-transparent layer draws a static dashed border in the wallpaper
palette’s light accent color just outside the
captured rectangle, so the border does not appear inside the selected video area.
Tiny regions may be padded to the encoder's minimum supported dimensions.

A detached supervisor owns each recording. QML reloads and Settings closure do not
stop it. State and diagnostic logs live under
`$XDG_STATE_HOME/endless-Impulse/recorder/`; a private GSR IPC socket lives under
`$XDG_RUNTIME_DIR/artificial-recorder-UID/`. Only the session's tracked PID and
process-start identity can be controlled. Stopping waits for GSR to finalize the
file; no process-name-wide kill is used.

IPC target `recording` exposes `fullscreen`, `stop`, `pause`, `saveReplay` and
`refresh` in the active shell. Existing `region.record` and `region.recordWithSound`
remain available. Standalone `record.sh --fullscreen`, `--region 'X,Y WxH'` and
`--sound` use the same supervisor and state.

Upstream references:
[GPU Screen Recorder](https://git.dec05eba.com/gpu-screen-recorder/about/),
[CLI manual](https://man.archlinux.org/man/gpu-screen-recorder.1.en).
Direct monitor capture requires the platform's GSR KMS permissions. Nix bundles
GSR without updating `flake.lock`; it cannot grant host capabilities itself.

Validation uses temporary XDG roots and a solid-color window owned by the test.
The real capture test checks finalized video dimensions and frame content,
pause/resume timing, the region overlay and status updates from a separate process.
It records no audio and removes its temporary video afterward. The user remains
the primary tester for everyday capture and hardware-specific options.
