import Quickshell
import Quickshell.Io

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

    path: Quickshell.env("HOME") + "/.cache/theme/active.json"

    blockLoading: true
    watchChanges: true

    onFileChanged: reload()
  }

  readonly property var data: {
    try {
      const parsed = JSON.parse(activeThemeFile.text())

      if (parsed && parsed.colors)
        return parsed
    } catch (error) {
      console.warn("Failed to read active theme:", error)
    }

    return {
      id: "catppuccin-macchiato",
      name: "Catppuccin Macchiato",
      variant: "dark",
      colors: fallbackColors
    }
  }

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
