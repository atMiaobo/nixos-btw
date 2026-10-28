import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.shared

import QtQuick
import QtQuick.Layouts

Scope {
  id: root

  readonly property bool validateOnly: Quickshell.env("MIHAO_QS_VALIDATE") === "1"

  ThemeStore {
    id: theme
  }

  property var themes: []
  property int selectedIndex: 0
  property bool applying: false
  property string errorText: ""
  readonly property string themeCommand: Quickshell.env("HOME") + "/.local/bin/theme"

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

  function move(delta) {
    if (applying || themes.length === 0)
      return;

    selectedIndex =
      (selectedIndex + delta + themes.length) % themes.length;
  }

  function cleanupAndQuit() {
    Quickshell.execDetached([
      "rm",
      "-f",
      (Quickshell.env("XDG_RUNTIME_DIR") || Quickshell.env("TMPDIR") || "/tmp") + "/mihao-theme-picker.pid"
    ]);

    Qt.quit();
  }

  function applySelected() {
    if (applying || themes.length === 0)
      return;

    applying = true;

    errorText = "";
    const entry = themes[selectedIndex];
    const command = [themeCommand, "apply", entry.path, "--name", entry.name];
    if (entry.explicit)
      command.push("--theme", entry.theme);
    applyProc.exec(command);
  }

  Process {
    id: applyProc
    stderr: StdioCollector {
      onStreamFinished: root.errorText = this.text.trim()
    }
    onExited: (exitCode) => {
      root.applying = false;
      if (exitCode === 0) {
        root.cleanupAndQuit();
      } else if (root.errorText.length === 0) {
        root.errorText = "Theme application failed (exit " + exitCode + "). Run theme status.";
      }
    }
  }

  function cancel() {
    if (applying)
      return;
    cleanupAndQuit();
  }

  function loadThemes(text) {
    try {
      themes = JSON.parse(text);
      selectedIndex = 0;
    } catch (error) {
      errorText = "Could not load wallpaper registry: " + error;
    }
  }

  Process {
    id: themeListProc
    stdout: StdioCollector {
      onStreamFinished: root.loadThemes(this.text)
    }
    stderr: StdioCollector {
      onStreamFinished: {
        if (this.text.trim().length > 0)
          root.errorText = this.text.trim();
      }
    }
  }

  Component.onCompleted: {
    if (!root.validateOnly)
      themeListProc.exec([themeCommand, "list", "--json"])
  }

  // Native import checks can run without a compositor or popup side effects.
  //@ if env("MIHAO_QS_VALIDATE") !== "1"
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
      WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

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
                  wallpaperPreview.status === Image.Error || root.errorText.length > 0

                text: root.errorText || "Could not load wallpaper preview"
                width: parent.width - 24
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
                color: root.text
                font.family: "JetBrainsMono Nerd Font"
                font.pixelSize: 13
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
                    ? (root.applying ? "Applying: " : "") + root.themeName(root.selectedIndex)
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
                    enabled: !root.applying
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
  //@ endif

  //@ if env("MIHAO_QS_VALIDATE") === "1"
  Timer {
    interval: 200
    running: true
    onTriggered: {
      console.log("VALIDATED theme-picker", Quickshell.shellDir, theme.primary)
      Qt.quit()
    }
  }
  //@ endif

}

