#!/usr/bin/env bash
# Session startup only: also safe to invoke manually from a Wayland terminal.
# Keep the lock in this parent while the agent runs, including under UWSM.
set -eu
: "${XDG_RUNTIME_DIR:?A graphical user session is required}"
if [[ "${1:-}" != --fallback ]]; then
    printf '%s\n' 'Native Quickshell Polkit is preferred. Stop the native shell before explicitly using --fallback.' >&2
    exit 2
fi
# A running native host must never compete with the fallback. Check its session lock.
session="${HYPRLAND_INSTANCE_SIGNATURE:-${WAYLAND_DISPLAY:-}}"
if [[ -n "$session" ]]; then
    session_hash="$(printf '%s' "$session" | sha256sum)"
    session_hash="${session_hash:0:16}"
    transport_dir="$XDG_RUNTIME_DIR/ai-auth-$session_hash"
    mkdir -m 700 -p "$transport_dir"
    exec 8>"$transport_dir/owner.lock"
    flock -n 8 || { printf '%s\n' 'Native authentication host is running; stop it before fallback recovery.' >&2; exit 1; }
fi
: "${XDG_RUNTIME_DIR:?A graphical user session is required}"
exec 9>"$XDG_RUNTIME_DIR/endless-Impulse-polkit-agent.lock"
flock -n 9 || exit 0

# Respect agents supplied by a user's session or distribution. Polkit itself
# arbitrates registration if an unrelated launcher races this startup hook.
if pgrep -u "$(id -u)" -f '(^|/)(hyprpolkitagent|polkit-kde-authentication-agent-1|polkit-gnome-authentication-agent-1)( |$)' >/dev/null; then
    exit 0
fi
for agent in /usr/lib/polkit-kde-authentication-agent-1 /usr/libexec/kf6/polkit-kde-authentication-agent-1; do
    if [[ -x "$agent" ]]; then
        "$agent" &
        agent_pid=$!
        trap 'kill "$agent_pid" 2>/dev/null || true' TERM INT HUP
        wait "$agent_pid"
        exit $?
    fi
done
printf '%s\n' 'Polkit agent unavailable: expected the session polkit-kde-agent executable.' >&2
exit 1
