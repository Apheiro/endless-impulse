-- Load only Artificial Impulse's own overrides, after user configuration.
local M = {}
function M.load()
    local home = os.getenv("HOME")
    local config = os.getenv("XDG_CONFIG_HOME") or (home .. "/.config")
    local state = (os.getenv("XDG_STATE_HOME") or (home .. "/.local/state")) .. "/artificial-impulse/desktop"
    local path = config .. "/artificial-impulse/hyprland.lua"
    local preview = io.open(state .. "/preview-session", "r")
    if preview then
        local session = preview:read("*l")
        local deadline = tonumber(preview:read("*l")) or 0
        preview:close()
        -- An interrupted preview must never become the next session's display layout.
        if session ~= os.getenv("HYPRLAND_INSTANCE_SIGNATURE") or os.time() >= deadline then
            path = state .. "/last-good.lua"
        end
    end
    local file = io.open(path, "r")
    if not file then return end
    file:close()
    assert(loadfile(path))()
end
return M
