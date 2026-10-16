import Quickshell
import Quickshell.Io
import Quickshell.Wayland

import QtQuick
import QtQuick.Layouts

Scope {
  id: root

  ThemeStore {
    id: theme
  }

  property var themes: []
  property int selectedIndex: 0
  property bool applying: false

  // Theme-driven colors. Layout and behavior remain static.
  property color bg:
    theme.withAlpha(theme.colors.background, 0.72)

  property color bgSoft:
    theme.withAlpha(theme.colors.surface, 0.58)

  property color border:
    theme.colors.accent

  property color text:
    theme.colors.foreground

  property color muted:
    theme.colors.muted

  property color selectedBg:
    theme.withAlpha(theme.colors.accent, 0.20)

  property color selectedText:
    theme.colors.foreground

  property color accent:
    theme.colors.accent

  property color overlayBg:
    theme.withAlpha(theme.colors.background_deep, 0.36)

  property color previewFallback:
    theme.colors.background_deep

  property color previewLabelBg:
    theme.withAlpha(theme.colors.background_deep, 0.72)

  function themeName(i) {
    if (i < 0 || i >= themes.length)
      return "";

    return themes[i].name;
  }

  function themePath(i) {
    if (i < 0 || i >= themes.length)
      return "";

    return themes[i].path;
  }

  function themeId(i) {
    if (i < 0 || i >= themes.length)
      return "catppuccin-macchiato";

    return themes[i].themeId || "catppuccin-macchiato";
  }

  function move(delta) {
    if (themes.length === 0)
      return;

    selectedIndex =
      (selectedIndex + delta + themes.length) % themes.length;
  }

  function cleanupAndQuit() {
    Quickshell.execDetached([
      "rm",
      "-f",
      "/tmp/theme-picker.pid"
    ]);

    Qt.quit();
  }

  function applySelected() {
    if (applying || themes.length === 0)
      return;

    applying = true;

    const path = themePath(selectedIndex);
    const selectedThemeId = themeId(selectedIndex);

    if (path.length > 0) {
      Quickshell.execDetached([
        "/home/mihao/.local/bin/theme",
        path,
        selectedThemeId
      ]);
    }

    cleanupAndQuit();
  }

  function cancel() {
    cleanupAndQuit();
  }

  function loadThemes(text) {
    const lines = text.trim().split("\n");
    const parsed = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();

      if (line.length === 0 || line.startsWith("#"))
        continue;

      const parts = line.split("|");

      if (parts.length < 2)
        continue;

      const name = parts[0].trim();
      const path = parts[1].trim();
      const selectedThemeId =
        parts.length >= 3 && parts[2].trim().length > 0
          ? parts[2].trim()
          : "catppuccin-macchiato";

      if (name.length > 0 && path.length > 0) {
        parsed.push({
          name: name,
          path: path,
          themeId: selectedThemeId
        });
      }
    }

    themes = parsed;
    selectedIndex = 0;
  }

  Process {
    id: themeListProc

    stdout: StdioCollector {
      onStreamFinished: {
        root.loadThemes(this.text);
      }
    }
  }

  Component.onCompleted: {
    themeListProc.exec([
      "bash",
      "-lc",
      "cat \"$HOME/.config/themes/wallpapers\" 2>/dev/null || true"
    ]);
  }

  Variants {
    model: Quickshell.screens

    PanelWindow {
      id: win

      required property var modelData

      screen: modelData

      WlrLayershell.namespace: "theme-picker"

      anchors {
        top: true
        bottom: true
        left: true
        right: true
      }

      exclusionMode: ExclusionMode.Ignore
      aboveWindows: true
      focusable: true

      color: root.overlayBg

      Item {
        id: keyArea

        anchors.fill: parent
        focus: true

        Component.onCompleted: forceActiveFocus()

        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Escape) {
            root.cancel();
            event.accepted = true;
          } else if (
            event.key === Qt.Key_Down ||
            event.key === Qt.Key_J
          ) {
            root.move(1);
            event.accepted = true;
          } else if (
            event.key === Qt.Key_Up ||
            event.key === Qt.Key_K
          ) {
            root.move(-1);
            event.accepted = true;
          } else if (
            event.key === Qt.Key_Return ||
            event.key === Qt.Key_Enter ||
            event.key === Qt.Key_Space
          ) {
            root.applySelected();
            event.accepted = true;
          }
        }

        // Clicking outside the picker closes it.
        MouseArea {
          anchors.fill: parent

          onClicked: root.cancel()
        }

        Rectangle {
          id: box

          property real previewRatio: 1.22
          property real listRatio: 0.55
          property int outerBorderWidth: 2
          property int dividerWidth: 2
          property real contentHeight:
            height - 2 * outerBorderWidth

          anchors.centerIn: parent

          height: Math.min(
            parent.height * 0.44,
            480,
            (
              parent.width * 0.58 -
              dividerWidth -
              2 * outerBorderWidth
            ) / (previewRatio + listRatio) +
            2 * outerBorderWidth
          )

          width:
            contentHeight * (previewRatio + listRatio) +
            dividerWidth +
            2 * outerBorderWidth

          radius: 4
          clip: true
          color: root.bg
          border.width: outerBorderWidth
          border.color: root.border

          // Consume clicks inside the box so the background MouseArea
          // does not close the picker.
          MouseArea {
            anchors.fill: parent

            onClicked: keyArea.forceActiveFocus()
          }

          RowLayout {
            anchors.fill: parent
            anchors.margins: box.outerBorderWidth
            spacing: 0

            Rectangle {
              id: previewPane

              Layout.preferredWidth:
                box.contentHeight * box.previewRatio
              Layout.fillHeight: true

              color: root.previewFallback
              clip: true

              AnimatedImage {
                id: wallpaperPreview

                anchors.fill: parent

                source: root.themes.length > 0
                  ? encodeURI(
                      "file://" +
                      root.themePath(root.selectedIndex)
                    )
                  : ""

                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                cache: false
                smooth: true
                playing: status === Image.Ready
                paused: !visible

                onStatusChanged: {
                  console.log(
                    "Wallpaper preview:",
                    "status =", status,
                    "frames =", frameCount,
                    "source =", source
                  );

                  if (status === Image.Ready)
                    currentFrame = 0;
                }
              }

              Text {
                anchors.centerIn: parent

                visible:
                  wallpaperPreview.status === Image.Loading

                text: "Loading preview..."
                color: root.text
                font.family: "JetBrainsMono Nerd Font"
                font.pixelSize: 14
              }

              Text {
                anchors.centerIn: parent

                visible:
                  wallpaperPreview.status === Image.Error

                text: "Could not load wallpaper preview"
                color: root.text
                font.family: "JetBrainsMono Nerd Font"
                font.pixelSize: 13
                horizontalAlignment: Text.AlignHCenter
              }

              Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom

                height: 42
                color: root.previewLabelBg

                Text {
                  anchors.fill: parent
                  anchors.leftMargin: 14
                  anchors.rightMargin: 14

                  text: root.themes.length > 0
                    ? root.themeName(root.selectedIndex)
                    : "No themes"

                  color: root.selectedText
                  font.family: "JetBrainsMono Nerd Font"
                  font.pixelSize: 15
                  font.bold: true
                  horizontalAlignment: Text.AlignLeft
                  verticalAlignment: Text.AlignVCenter
                  elide: Text.ElideRight
                }
              }
            }

            Rectangle {
              Layout.preferredWidth: box.dividerWidth
              Layout.fillHeight: true

              color: root.border
              opacity: 0.65
            }

            Rectangle {
              id: listPane

              Layout.preferredWidth:
                box.contentHeight * box.listRatio
              Layout.fillHeight: true

              color: root.bgSoft
              clip: true

              Text {
                visible: root.themes.length === 0
                anchors.fill: parent

                text: "No themes"
                color: root.muted
                font.family: "JetBrainsMono Nerd Font"
                font.pixelSize: 14
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
              }

              ListView {
                id: themeList

                visible: root.themes.length > 0
                anchors.fill: parent
                anchors.margins: 8

                clip: true
                model: root.themes
                currentIndex: root.selectedIndex
                spacing: 4
                boundsBehavior: Flickable.StopAtBounds
                highlightMoveDuration: 80

                Connections {
                  target: root

                  function onSelectedIndexChanged() {
                    if (root.themes.length > 0) {
                      themeList.currentIndex =
                        root.selectedIndex;

                      themeList.positionViewAtIndex(
                        root.selectedIndex,
                        ListView.Contain
                      );
                    }
                  }
                }

                delegate: Rectangle {
                  id: row

                  required property int index
                  required property var modelData

                  width: themeList.width
                  height: 38

                  radius: 2
                  color:
                    row.index === root.selectedIndex
                      ? root.selectedBg
                      : "transparent"

                  Text {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10

                    text: row.modelData.name
                    color:
                      row.index === root.selectedIndex
                        ? root.selectedText
                        : root.text

                    font.family: "JetBrainsMono Nerd Font"
                    font.pixelSize: 15
                    font.bold:
                      row.index === root.selectedIndex

                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                  }

                  MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor

                    onClicked: {
                      root.selectedIndex = row.index;
                      keyArea.forceActiveFocus();
                    }

                    onDoubleClicked: {
                      root.selectedIndex = row.index;
                      root.applySelected();
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}

