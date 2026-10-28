import Quickshell
import Quickshell.Io
import QtQuick

Scope {
  id: root

  // Used only if active.json is missing, empty, or malformed.
  readonly property var fallbackColors: ({
    background: "#24273a",
    background_alt: "#1e2030",
    background_deep: "#181926",

    surface: "#363a4f",
    surface_alt: "#494d64",
    surface_high: "#5b6078",

    foreground: "#cad3f5",
    foreground_alt: "#b8c0e0",
    muted: "#a5adcb",
    disabled: "#6e738d",

    primary: "#c6a0f6",
    secondary: "#b7bdf8",
    accent: "#c6a0f6",
    accent_alt: "#b7bdf8",
    on_accent: "#181926",

    selection: "#5b6078",
    selection_text: "#cad3f5",

    hover: "#363a4f",
    pressed: "#494d64",
    focus: "#c6a0f6",

    border: "#6e738d",
    border_inactive: "#363a4f",
    shadow: "#181926",

    success: "#a6da95",
    warning: "#eed49f",
    error: "#ed8796",
    critical: "#ee99a0",
    info: "#8aadf4",

    link: "#7dc4e4",
    link_visited: "#c6a0f6",
    match: "#f5a97f",
    highlight: "#eed49f"
  })

  FileView {
    id: activeThemeFile

    path: (Quickshell.env("MIHAO_THEME_CACHE") ||
      ((Quickshell.env("XDG_CACHE_HOME") || Quickshell.env("HOME") + "/.cache") + "/theme")) + "/active.json"

    blockLoading: true
    watchChanges: true

    onFileChanged: reload()
    onLoaded: root.acceptTheme(activeThemeFile.text())
  }

  property var data: ({
    id: "catppuccin-macchiato",
    name: "Catppuccin Macchiato",
    variant: "dark",
    colors: fallbackColors
  })

  property string lastThemeText: ""

  function acceptTheme(text) {
    if (text === lastThemeText)
      return
    try {
      const parsed = JSON.parse(text)
      if (!parsed || !parsed.colors || typeof parsed.colors !== "object" ||
          Array.isArray(parsed.colors) || Object.keys(parsed.colors).length === 0)
        return
      for (const key in parsed.colors) {
        if (!/^#[0-9a-fA-F]{6}$/.test(parsed.colors[key]))
          return
      }
      const merged = Object.assign({}, fallbackColors, parsed.colors)
      // active.json exposes canonical UI roles. Older/manual files may only
      // expose dashboard aliases. Derive missing aliases from THIS palette,
      // rather than retaining Catppuccin colors from the fallback object.
      merged.primary = parsed.colors.primary || parsed.colors.accent || fallbackColors.primary
      merged.secondary = parsed.colors.secondary || parsed.colors.accent_alt || fallbackColors.secondary
      const aliases = {
        background_alt: "surface", background_deep: "background",
        surface_high: "surface_alt", foreground_alt: "foreground",
        disabled: "muted", accent: "primary", accent_alt: "secondary",
        on_accent: "background", selection: "surface_alt",
        selection_text: "foreground", hover: "surface", pressed: "surface_alt",
        focus: "primary", border_inactive: "border", shadow: "background",
        critical: "error", info: "secondary", link: "primary",
        link_visited: "secondary", match: "primary", highlight: "warning"
      }
      for (const alias in aliases) {
        if (parsed.colors[alias] === undefined)
          merged[alias] = merged[aliases[alias]]
      }
      for (const key in merged) {
        if (!/^#[0-9a-fA-F]{6}$/.test(merged[key]))
          return
      }
      parsed.colors = merged
      lastThemeText = text
      data = parsed
    } catch (error) {
      // Keep the last valid appearance during a missing/invalid replacement.
      console.warn("Failed to read active theme:", error)
    }
  }

  // Recheck the pathname to cover file creation and atomic replacement even
  // when a platform watcher remains attached to the previous inode.
  Timer {
    interval: 1500
    running: true
    repeat: true
    onTriggered: activeThemeFile.reload()
  }

  readonly property color background: colors.background
  readonly property color surface: colors.surface
  readonly property color surfaceAlt: colors.surface_alt
  readonly property color foreground: colors.foreground
  readonly property color muted: colors.muted
  readonly property color primary: colors.primary || colors.accent
  readonly property color secondary: colors.secondary || colors.accent_alt
  readonly property color border: colors.border
  readonly property color success: colors.success
  readonly property color warning: colors.warning
  readonly property color error: colors.error

  readonly property var colors: data.colors
  readonly property string themeId: data.id || ""
  readonly property string themeName: data.name || ""
  readonly property string variant: data.variant || "dark"

  // Converts #RRGGBB plus an opacity into a QML color.
  function withAlpha(hex, opacity) {
    const value = String(hex).replace("#", "")

    if (value.length !== 6)
      return hex

    const red = parseInt(value.substring(0, 2), 16) / 255
    const green = parseInt(value.substring(2, 4), 16) / 255
    const blue = parseInt(value.substring(4, 6), 16) / 255

    return Qt.rgba(red, green, blue, opacity)
  }
}
