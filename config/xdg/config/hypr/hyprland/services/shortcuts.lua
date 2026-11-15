-- Keep callbacks and bind options intact; remap only their trigger.
local M = {}
local home = os.getenv("HOME")
local config = (os.getenv("XDG_CONFIG_HOME") or home .. "/.config") .. "/endless-Impulse"
local state = (os.getenv("XDG_STATE_HOME") or home .. "/.local/state") .. "/endless-Impulse"
local original_bind, original_submap = hl.bind, hl.define_submap
local entries, order, submap = {}, {}, ""
local overrides = {}

local function quote(value)
    return '"' .. value:gsub('[%z\1-\31\\"]', function(c)
        return string.format('\\u%04x', string.byte(c))
    end) .. '"'
end

local function identity(keys)
    local parts = {}
    for part in keys:gmatch("[^+]+") do
        table.insert(parts, part:match("^%s*(.-)%s*$"):upper())
    end
    local key = table.remove(parts)
    table.sort(parts)
    table.insert(parts, key)
    return submap .. "|" .. table.concat(parts, "+")
end

local category_cache = {}
local function source_category()
    if not debug or not debug.getinfo then return "Other" end
    local info = debug.getinfo(3, "Sl")
    if not info or info.source:sub(1, 1) ~= "@" then return "Other" end
    local path = info.source:sub(2)
    if not category_cache[path] then
        local categories, category = {}, path:match("/hyprland/keybinds%.lua$") and "Shell" or "Other"
        local file = io.open(path, "r")
        if file then
            for line in file:lines() do
                local heading = line:match("^%s*%-%-##!%s*(.-)%s*$")
                if heading and heading ~= "" then category = heading end
                table.insert(categories, ({Apps = "App", Workspaces = "Workspace", Windows = "Window"})[category] or category)
            end
            file:close()
        end
        category_cache[path] = categories
    end
    return category_cache[path][info.currentline] or "Other"
end

function M.start()
    local load = loadfile(config .. "/shortcuts.lua", "t", {})
    if load then
        local ok, result = pcall(load)
        if ok and type(result) == "table" then overrides = result end
    end
    hl.define_submap = function(name, callback, ...)
        return original_submap(name, function(...)
            local previous = submap
            submap = name
            local result = table.pack(pcall(callback, ...))
            submap = previous
            if not result[1] then error(result[2]) end
            return table.unpack(result, 2, result.n)
        end, ...)
    end
    hl.bind = function(keys, dispatcher, options)
        local id = identity(keys)
        local entry = entries[id]
        if not entry then
            entry = { id = id, default = keys, submap = submap, descriptions = {}, count = 0,
                universal = false, ignore_mods = false, category = source_category() }
            if keys:find("XF86Audio", 1, true) then entry.category = "Media" end
            if keys:find("XF86MonBrightness", 1, true) then entry.category = "Screen" end
            entries[id] = entry
            table.insert(order, id)
        end
        entry.count = entry.count + 1
        entry.universal = entry.universal or (options and options.submap_universal) or false
        entry.ignore_mods = entry.ignore_mods or (options and options.ignore_mods) or false
        if options and options.description then
            entry.descriptions[options.description] = true
            local category = options.description:match("^([^:]+):")
            if category and not entry.explicit_category then
                entry.category = category
                entry.explicit_category = true
            end
        end
        local replacement = overrides[id]
        return original_bind(type(replacement) == "string" and replacement or keys, dispatcher, options)
    end
end

function M.finish()
    hl.bind, hl.define_submap = original_bind, original_submap
    local function shell_quote(value) return "'" .. value:gsub("'", "'\\''") .. "'" end
    os.execute("mkdir -p " .. shell_quote(state))
    local file = io.open(state .. "/shortcuts-catalog.json.tmp", "w")
    if not file then return end
    local rows = {}
    for _, id in ipairs(order) do
        local entry = entries[id]
        local descriptions = {}
        for description in pairs(entry.descriptions) do table.insert(descriptions, description) end
        table.sort(descriptions)
        table.insert(rows, '{"id":' .. quote(id) .. ',"default":' .. quote(entry.default)
            .. ',"category":' .. quote(entry.category) .. ',"submap":' .. quote(entry.submap) .. ',"description":'
            .. quote(table.concat(descriptions, " / ")) .. ',"count":' .. entry.count
            .. ',"universal":' .. tostring(entry.universal) .. ',"ignore_mods":'
            .. tostring(entry.ignore_mods) .. '}')
    end
    file:write("[", table.concat(rows, ","), "]\n")
    file:close()
    os.rename(state .. "/shortcuts-catalog.json.tmp", state .. "/shortcuts-catalog.json")
end

return M
