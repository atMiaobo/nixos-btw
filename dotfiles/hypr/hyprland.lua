local mod = "ALT"

-- Generated desktop colors.
local theme = require("theme")

-- Terminal
hl.bind(mod .. " + Return", hl.dsp.exec_cmd("kitty"))

-- General
hl.bind(mod .. " + Q", hl.dsp.window.close())
hl.bind(mod .. " + backslash", hl.dsp.exec_cmd("uwsm stop"))
hl.bind(mod .. " + W", hl.dsp.exec_cmd("pkill fuzzel || fuzzel"))


--exec-once = waybar
hl.on("hyprland.start", function()
    hl.exec_cmd("awww-daemon")
    hl.exec_cmd("awww img /home/mihao/Pictures/Wallpapers/mononoke.png")
    hl.exec_cmd("dunst")
end)

-- Basic resizing:
hl.bind(mod .. " + mouse:272", hl.dsp.window.drag(), { mouse = true })
hl.bind(mod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

-- Workspaces
for i = 1, 10 do
    local key = tostring(i % 10)
    hl.bind(mod .. " + " .. key, hl.dsp.focus({ workspace = i }))
end

--bind = $mod, -, workspace, 11
--bind = $mod, =, workspace, 12

-- Special workspace / minimize-like scratchpad
hl.bind(mod .. " + S", hl.dsp.workspace.toggle_special("minimized"))

--move windows to workspace
for i = 1, 10 do
    local key = tostring(i % 10)
    hl.bind(mod .. " + SHIFT + " .. key, hl.dsp.window.move({ workspace = i, follow = true }))
end

--bind = $mod SHIFT, -, movetoworkspace, 11
--bind = $mod SHIFT, =, movetoworkspace, 12
hl.bind(mod .. " + SHIFT + S", hl.dsp.window.move({ workspace = "special:minimized" }))
-- Toggle floating on the active window
hl.bind(mod .. " + V", hl.dsp.window.float({ action = "toggle" }))


--move focuus with arrow
hl.bind(mod .. " + j", hl.dsp.focus({ direction = "l" }))
hl.bind(mod .. " + l", hl.dsp.focus({ direction = "r" }))
hl.bind(mod .. " + i", hl.dsp.focus({ direction = "u" }))
hl.bind(mod .. " + k", hl.dsp.focus({ direction = "d" }))

--move windows in workspace
hl.bind(mod .. " + SHIFT + j", hl.dsp.window.move({ direction = "l" }))
hl.bind(mod .. " + SHIFT + l", hl.dsp.window.move({ direction = "r" }))
hl.bind(mod .. " + SHIFT + i", hl.dsp.window.move({ direction = "u" }))
hl.bind(mod .. " + SHIFT + k", hl.dsp.window.move({ direction = "d" }))

--resize tiled window
hl.bind("ALT + CTRL + SHIFT + h", hl.dsp.window.resize({ x = -40, y = 0, relative = true }), { repeating = true })
hl.bind("ALT + CTRL + SHIFT + l", hl.dsp.window.resize({ x = 40, y = 0, relative = true }), { repeating = true })
hl.bind("ALT + CTRL + SHIFT + j", hl.dsp.window.resize({ x = 0, y = -40, relative = true }), { repeating = true })
hl.bind("ALT + CTRL + SHIFT + k", hl.dsp.window.resize({ x = 0, y = 40, relative = true }), { repeating = true })

--move floating window
hl.bind("ALT + CTRL + j", hl.dsp.window.move({ x = -40, y = 0, relative = true }), { repeating = true })
hl.bind("ALT + CTRL + l", hl.dsp.window.move({ x = 40, y = 0, relative = true }), { repeating = true })
hl.bind("ALT + CTRL + i", hl.dsp.window.move({ x = 0, y = -40, relative = true }), { repeating = true })
hl.bind("ALT + CTRL +k", hl.dsp.window.move({ x = 0, y = 40, relative = true }), { repeating = true })

--System binds

-- ASUS volume special keys
hl.bind("code:122", hl.dsp.exec_cmd("/home/mihao/.local/bin/volume down"), { repeating = true })
hl.bind("code:123", hl.dsp.exec_cmd("/home/mihao/.local/bin/volume up"), { repeating = true })

-- Brightness on F7/F8
hl.bind("code:73", hl.dsp.exec_cmd("/home/mihao/.local/bin/brightness down"), { repeating = true })
hl.bind("code:74", hl.dsp.exec_cmd("/home/mihao/.local/bin/brightness up"), { repeating = true })


-- browser
hl.bind(mod .. " + d", hl.dsp.exec_cmd("firefox"))

-- file manager
hl.bind(mod .. " + e", hl.dsp.exec_cmd("kitty -e yazi"))

-- reload config
hl.bind(mod .. " + SHIFT + r", hl.dsp.exec_cmd("hyprctl reload"))

-- lock screen (later)
hl.bind(mod .. " + SHIFT + l", hl.dsp.exec_cmd("hyprlock"))

-- screenshot
hl.bind("code:72", hl.dsp.exec_cmd("/home/mihao/.local/bin/mihao-screenshot-area"))
hl.bind("code:75", hl.dsp.exec_cmd("/home/mihao/.local/bin/mihao-screenshot-full"))

hl.bind("F10", hl.dsp.exec_cmd("hyprpicker -a"))

-- Custom apps binds
hl.bind(mod .. " + Z", hl.dsp.exec_cmd("/home/mihao/.local/bin/dashboard"))
hl.bind(mod .. " + X", hl.dsp.exec_cmd("/home/mihao/.local/bin/mihao-asus"))
hl.bind(mod .. " + T", hl.dsp.exec_cmd("/home/mihao/.local/bin/theme-picker"))

-- Gestures:
-- Swipe horizontally with 3 fingers to switch between workspaces
hl.gesture({
    fingers = 3,
    direction = "horizontal",
    action = "workspace",
})

-- Optional: Swipe vertically with 3 fingers to interact with special workspaces
hl.gesture({
    fingers = 3,
    direction = "vertical",
    action = "special",
    workspace_name = "minimized",
})

--Window styling
hl.monitor({
    output = "eDP-1",
    mode = "preferred",
    position = "0x0",
    scale = 1.6,
})

--Fix blurry apps:
hl.config({
    xwayland = {
        force_zero_scaling = true,
        use_nearest_neighbor = false,
    },
})

hl.config({
    general = {
        gaps_in = 3,      -- Tiny gap between windows
        gaps_out = 7,     -- Tiny gap at screen edges
        border_size = 1,  -- Thin window borders

        col = {
            active_border = theme.accent,
            inactive_border = theme.border_inactive,
        },

        -- Keep your existing non-color settings here.
    },

    decoration = {
        rounding = 4, --7

        active_opacity = 0.95,
        inactive_opacity = 0.85,

        blur = {
            enabled = true,
            size = 6, --6 defualt
            passes = 2, --2 default
            vibrancy = 0.2,
        },
        shadow = {
            color = theme.shadow,
        },
    },
})

--Animations
hl.config({
    animations = {
        enabled = true,
    },
})

-- Define a custom bezier curve
hl.curve("myBezier", {
    type = "bezier",
    points = {
        { 0.05, 0.9 },
        { 0.1, 1.05 },
    },
})

-- Apply the curve to different animation trees
hl.animation({ leaf = "windows", enabled = true, speed = 7, bezier = "myBezier" })
hl.animation({ leaf = "windowsOut", enabled = true, speed = 7, bezier = "default", style = "popin 80%" })
hl.animation({ leaf = "border", enabled = true, speed = 10, bezier = "default" })
hl.animation({ leaf = "fade", enabled = true, speed = 7, bezier = "default" })

-- Normal workspace switching, still left/right
hl.animation({ leaf = "workspaces", enabled = true, speed = 6, bezier = "default", style = "slide" })

-- Special workspace / scratchpad animation
hl.animation({ leaf = "specialWorkspace", enabled = true, speed = 6, bezier = "myBezier", style = "slidefadevert 40%" })



--MONITORS
-- Laptop display
hl.monitor({
    output = "eDP-1",
    mode = "2560x1600@240",
    position = "0x0",
    scale = 1.6,
})

-- Samsung Odyssey G5
hl.monitor({
    output = "desc:Samsung Electric Company Odyssey G5",
    mode = "2560x1440@144",
    position = "auto-center-up",
    scale = 1,
})

-- Fallback for random monitors/projectors
hl.monitor({
    output = "",
    
    mode = "preferred",
    position = "auto",
    scale = 1,
})


-- HEADLESS MODE settings:
hl.bind(
    "switch:on:Lid Switch",
    hl.dsp.exec_cmd("nix-headless lid-close"),
    { locked = true }
)

hl.bind(
    "switch:off:Lid Switch",
    hl.dsp.exec_cmd("nix-headless lid-open"),
    { locked = true }
)

hl.bind(
    "XF86Sleep",
    hl.dsp.exec_cmd("nix-headless sleep-key"),
    { locked = true }
)

-- Permanence
-- hl.dsp.exec_once("nix-headless boot")




--Custom settings

--Dashboard
hl.layer_rule({
    match = { namespace = "dashboard" },
    blur = true,
    ignore_alpha = 0.7,
})

--Asus Dashboard:
--hl.layer_rule({
--    match = { namespace = "mihao-asus" },
--    blur = true,
--    ignore_alpha = 0.0,
--})

-- Theme picker
hl.layer_rule({
    match = { namespace = "theme-picker" },
    blur = true,
    ignore_alpha = 0.4,
})
