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

  // colors:
  // Main translucent dashboard background.
  property color dashboardBg:
    theme.withAlpha(theme.colors.background, 0.78)

  // Cards and secondary regions.
  property color cardBg:
    theme.withAlpha(theme.colors.surface, 0.88)

  property color cardHover:
    theme.withAlpha(theme.colors.hover, 0.94)

  // Lines and borders.
  property color borderColor:
    theme.colors.border

  property color inactiveBorderColor:
    theme.colors.border_inactive

  // Text hierarchy.
  property color primaryText:
    theme.colors.foreground

  property color secondaryText:
    theme.colors.foreground_alt

  property color mutedText:
    theme.colors.muted

  // Highlights.
  property color accentColor:
    theme.colors.accent

  property color accentAltColor:
    theme.colors.accent_alt

  // Status colors.
  property color successColor:
    theme.colors.success

  property color warningColor:
    theme.colors.warning

  property color errorColor:
    theme.colors.error

  property color infoColor:
    theme.colors.info



  // ── Backend scripts ───────────────────────────────────────────────────────
  property string scriptDir: "/home/mihao/.local/bin"

  // ── Compact terminal-like sizing ──────────────────────────────────────────
  property int cardWidth: 390
  property int cardHeight: 215

  // Side padding
  property int padX: 16
  // Top padding
  property int padTop: 14
  // Bottom padding: match side padding
  property int padBottom: 16

  // ── Fonts ─────────────────────────────────────────────────────────────────
  // If you don't have 0xProto installed, switch back to JetBrainsMono Nerd Font.
  property string textFont: "0xProto Nerd Font"
  property string iconFont: "Symbols Nerd Font Mono"

  // ── Dynamic state ─────────────────────────────────────────────────────────
  property string timeText: "--:--"
  property string dateText: ""

  property string weatherIcon: "󰖗"
  property string weatherLine: "weather loading..."

  property string networkIcon: "󰤭"
  property string networkLine: "network loading..."

  property bool vpnActive: false
  property string vpnIcon: "󰖂"
  property string vpnLine: ""

  property bool bluetoothActive: false
  property string bluetoothIcon: "󰂯"
  property string bluetoothLine: ""

  property bool mediaActive: false
  property bool mediaPlaying: false
  property string mediaIcon: "󰎈"
  property string mediaLine: ""

  property string batteryIcon: "󰂑"
  property string batteryPercent: "--%"
  property string batteryPower: ""

  // ── Tiny equalizer ────────────────────────────────────────────────────────
  property int eqFrame: 0
  property var eqFrames: [
    "▁▂▃▂▁",
    "▁▂▄▃▁",
    "▁▃▅▃▂",
    "▂▄▆▄▂",
    "▃▅▇▅▃",
    "▂▄▆█▄",
    "▁▃▅▇▅",
    "▁▂▃▅▃",
    "▁▂▄▆█",
    "▁▂▃▅▇",
    "▁▁▂▄▆",
    "▁▂▃▅▃",
    "▂▄▆▄▂",
    "▃▅▇▅▃",
    "▂▄▆▄▂",
    "▁▃▅▃▁",
    "▁▂▄▂▁"
  ]

  Timer {
    interval: 145
    repeat: true
    running: root.mediaActive && root.mediaPlaying
    onTriggered: root.eqFrame = (root.eqFrame + 1) % root.eqFrames.length
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  function pad(n) {
    return n < 10 ? "0" + n : "" + n;
  }

  function parseJson(text, source) {
    const trimmed = text.trim();

    if (trimmed.length === 0) {
      console.log(source + ": empty output");
      return null;
    }

    try {
      return JSON.parse(trimmed);
    } catch (e) {
      console.log(source + ": failed to parse JSON: " + e);
      console.log(trimmed);
      return null;
    }
  }

  function formatWatts(data) {
    let watts = null;

    if (data.power_direction === "charging") {
      watts = data.charge_power_w;
    } else if (data.power_direction === "discharging") {
      watts = data.power_draw_w;
    }

    if (watts === null || watts === undefined) {
      watts = data.power_w;
    }

    if (watts === null || watts === undefined) {
      return "";
    }

    const value = Number(watts);

    if (isNaN(value) || value <= 0) {
      return "";
    }

    return Math.round(value) + "W";
  }

  function updateTime() {
    const now = new Date();

    const months = [
      "一月", "二月", "三月", "四月", "五月", "六月",
      "七月", "八月", "九月", "十月", "十一月", "十二月"
    ];

    root.timeText = pad(now.getHours()) + ":" + pad(now.getMinutes());
    root.dateText = months[now.getMonth()] + "" + now.getDate() + "日" + now.getFullYear();
  }

  function refreshWeather() {
    weatherProc.exec([root.scriptDir + "/weather", "json"]);
  }

  function refreshBattery() {
    batteryProc.exec([root.scriptDir + "/battery", "json"]);
  }

  function refreshNetwork() {
    networkProc.exec([root.scriptDir + "/network", "json"]);
  }

  function refreshBluetooth() {
    bluetoothProc.exec([root.scriptDir + "/bluetooth", "json"]);
  }

  function refreshMedia() {
    mediaProc.exec([root.scriptDir + "/media", "json"]);
  }

  function refreshAll() {
    root.updateTime();
    root.refreshWeather();
    root.refreshBattery();
    root.refreshNetwork();
    root.refreshBluetooth();
    root.refreshMedia();
  }

  // ── Backend processes ─────────────────────────────────────────────────────
  Process {
    id: weatherProc

    stdout: StdioCollector {
      onStreamFinished: {
        const data = root.parseJson(this.text, "weather");
        if (data === null) return;

        root.weatherIcon = data.icon || root.weatherIcon;
        root.weatherLine = data.line || root.weatherLine;
      }
    }
  }

  Process {
    id: batteryProc

    stdout: StdioCollector {
      onStreamFinished: {
        const data = root.parseJson(this.text, "battery");
        if (data === null) return;

        root.batteryIcon = data.icon || root.batteryIcon;
        root.batteryPercent = (data.percent !== null && data.percent !== undefined)
          ? data.percent + "%"
          : root.batteryPercent;
        root.batteryPower = root.formatWatts(data);
      }
    }
  }

  Process {
    id: networkProc

    stdout: StdioCollector {
      onStreamFinished: {
        const data = root.parseJson(this.text, "network");
        if (data === null) return;

        root.networkIcon = data.icon || root.networkIcon;
        root.networkLine = data.line || root.networkLine;

        const vpn = data.vpn || {};
        root.vpnActive = vpn.visible === true;
        root.vpnIcon = vpn.icon || "󰖂";
        root.vpnLine = vpn.line || "";
      }
    }
  }

  Process {
    id: bluetoothProc

    stdout: StdioCollector {
      onStreamFinished: {
        const data = root.parseJson(this.text, "bluetooth");
        if (data === null) return;

        root.bluetoothActive = data.visible === true;
        root.bluetoothIcon = data.icon || "󰂯";
        root.bluetoothLine = data.line || "";
      }
    }
  }

  Process {
    id: mediaProc

    stdout: StdioCollector {
      onStreamFinished: {
        const data = root.parseJson(this.text, "media");
        if (data === null) return;

        root.mediaActive = data.visible === true;
        root.mediaPlaying = data.playing === true;
        root.mediaIcon = data.icon || "󰎈";
        root.mediaLine = data.line || "";
      }
    }
  }

  // ── Timers ────────────────────────────────────────────────────────────────
  Timer {
    interval: 1000
    repeat: true
    running: true
    onTriggered: root.updateTime()
  }

  // Weather script caches by itself, so polling every 5 minutes is fine.
  Timer {
    interval: 300000
    repeat: true
    running: true
    onTriggered: root.refreshWeather()
  }

  Timer {
    interval: 15000
    repeat: true
    running: true
    onTriggered: root.refreshBattery()
  }

  Timer {
    interval: 10000
    repeat: true
    running: true
    onTriggered: root.refreshNetwork()
  }

  Timer {
    interval: 15000
    repeat: true
    running: true
    onTriggered: root.refreshBluetooth()
  }

  Timer {
    interval: 2000
    repeat: true
    running: true
    onTriggered: root.refreshMedia()
  }

  Component.onCompleted: root.refreshAll()

  // ── Reusable row component ────────────────────────────────────────────────
  component StatusRow: RowLayout {
    property string icon: ""
    property string value: ""

    Layout.fillWidth: true
    spacing: 7

    Text {
      text: parent.icon
      color: root.mutedText
      font.family: root.iconFont
      font.pixelSize: 15
      Layout.preferredWidth: 18
      horizontalAlignment: Text.AlignHCenter
      verticalAlignment: Text.AlignVCenter
    }

    Text {
      text: parent.value
      color: root.primaryText
      font.family: root.textFont
      font.pixelSize: 15
      elide: Text.ElideRight
      Layout.fillWidth: true
      verticalAlignment: Text.AlignVCenter
    }
  }

  Variants {
    model: Quickshell.screens

    PanelWindow {
      id: win

      required property var modelData
      screen: modelData

      WlrLayershell.namespace: "dashboard"
      WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

      anchors {
        top: true
        bottom: true
        left: true
        right: true
      }

      exclusionMode: ExclusionMode.Ignore
      aboveWindows: true
      focusable: false
      color: "transparent"

      // Make the entire dashboard click-through.
      // This prevents the fullscreen layer surface from stealing mouse/scroll input.
      mask: Region {}

      Rectangle {
        id: card

        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: Math.round(parent.height * 0.04)

        width: root.cardWidth
        height: root.cardHeight

        color: root.dashboardBg
        border.color: root.borderColor
        border.width: 1
        radius: 5

        ColumnLayout {
          id: content

          anchors.fill: parent
          anchors.leftMargin: root.padX
          anchors.rightMargin: root.padX
          anchors.topMargin: root.padTop
          anchors.bottomMargin: root.padBottom

          spacing: 3

          // ── Header ────────────────────────────────────────────────────────
          RowLayout {
            Layout.fillWidth: true
            spacing: 16   // fixes the clock/date cramming

            Text {
              text: root.timeText
              color: root.primaryText
              font.family: root.textFont
              font.pixelSize: 25
              verticalAlignment: Text.AlignVCenter
            }

            Text {
              text: root.dateText
              color: root.primaryText
              font.family: root.textFont
              font.pixelSize: 22
              verticalAlignment: Text.AlignVCenter
            }
          }

          Item { Layout.preferredHeight: 6 }

          // ── Main rows ─────────────────────────────────────────────────────
          StatusRow {
            icon: root.weatherIcon
            value: root.weatherLine
          }

          StatusRow {
            icon: root.networkIcon
            value: root.networkLine
          }

          StatusRow {
            visible: root.vpnActive
            icon: root.vpnIcon
            value: root.vpnLine
          }

          StatusRow {
            visible: root.bluetoothActive
            icon: root.bluetoothIcon
            value: root.bluetoothLine
          }

          // Push footer down a bit
          Item {
            Layout.fillHeight: true
            Layout.minimumHeight: 8
          }

          // ── Footer ────────────────────────────────────────────────────────
          RowLayout {
            Layout.fillWidth: true
            spacing: 7

            Text {
              visible: root.mediaActive
              text: root.mediaIcon
              color: root.mutedText
              font.family: root.iconFont
              font.pixelSize: 15
              Layout.preferredWidth: 18
              horizontalAlignment: Text.AlignHCenter
              verticalAlignment: Text.AlignVCenter
            }

            Text {
              visible: root.mediaActive
              text: root.mediaLine
              color: root.primaryText
              font.family: root.textFont
              font.pixelSize: 15
              verticalAlignment: Text.AlignVCenter
              elide: Text.ElideRight
              Layout.maximumWidth: 190
            }

            Text {
              visible: root.mediaActive && root.mediaPlaying
              text: root.eqFrames[root.eqFrame]
              color: root.accentColor
              opacity: 0.85
              font.family: root.textFont
              font.pixelSize: 10
              verticalAlignment: Text.AlignVCenter
              Layout.alignment: Qt.AlignVCenter
            }

            Item {
              Layout.fillWidth: true
            }

            RowLayout {
              spacing: 5

              Text {
                text: root.batteryPercent
                color: root.primaryText
                font.family: root.textFont
                font.pixelSize: 15
                verticalAlignment: Text.AlignVCenter
              }

              Text {
                text: root.batteryIcon
                color: root.mutedText
                font.family: root.iconFont
                font.pixelSize: 15
                verticalAlignment: Text.AlignVCenter
              }

              Text {
                visible: root.batteryPower.length > 0
                text: root.batteryPower
                color: root.primaryText
                font.family: root.textFont
                font.pixelSize: 15
                verticalAlignment: Text.AlignVCenter
              }
            }
          }
        }
      }
    }
  }
}

