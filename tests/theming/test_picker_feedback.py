"""Real picker Process/collector feedback in offscreen Items, never live panels."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

import test_quickshell

REPO = test_quickshell.REPO
CONFIG = test_quickshell.CONFIG


class PickerPreservation(unittest.TestCase):
    def test_layout_fonts_and_keybindings_are_unchanged(self):
        source = (CONFIG/'theme-picker.qml').read_text()
        original = subprocess.check_output(['git', '-C', str(REPO), 'show',
                                             'HEAD:dotfiles/quickshell/theme-picker.qml'], text=True)
        for start, end in (('        Keys.onPressed:', '        // Clicking outside'),
                           ('          property real previewRatio:', '              AnimatedImage {')):
            self.assertEqual(source[source.index(start):source.index(end)],
                             original[original.index(start):original.index(end)])
        self.assertEqual(re.findall(r'^\s*(?:font\.|Layout\.|anchors\.|height:|width:|radius:|spacing:).*$',source,re.M),
                         re.findall(r'^\s*(?:font\.|Layout\.|anchors\.|height:|width:|radius:|spacing:).*$',original,re.M))
        self.assertNotIn('root.errorText = this.text', source)
        self.assertIn('maximumLineCount: 3', source)


@unittest.skipUnless(shutil.which('quickshell'), 'Quickshell unavailable')
class PickerFeedback(test_quickshell.Fixture):
    def run_picker(self, code, action='apply'):
        executable = self.root/'.local/bin/theme'
        executable.parent.mkdir(parents=True, exist_ok=True)
        diagnostic = 'BEGIN FULL DIAGNOSTIC\n' + ''.join(
            f'include check /fixture/absolute/path/{i}: recovery detail\n' for i in range(80)) + 'END FULL DIAGNOSTIC'
        stdout = 'complete stdout diagnostic'
        executable.write_text('#!/usr/bin/env python3\nimport sys\n'
                             f'print({stdout!r})\nprint({diagnostic!r}, file=sys.stderr)\n'
                             f'raise SystemExit({code})\n')
        executable.chmod(0o755)
        fixture = self.root/f'picker-{action}-{code}'
        fixture.mkdir()
        (fixture/'shared').mkdir()
        shutil.copyfile(CONFIG/'shared/ThemeStore.qml', fixture/'shared/ThemeStore.qml')
        source = (CONFIG/'theme-picker.qml').read_text()
        # Use the actual Process handlers, preview and list, replacing only the
        # compositor surfaces and exit/pidfile side effects with a test marker.
        start = source.index('  function cleanupAndQuit()')
        end = source.index('  function applySelected()', start)
        source = source[:start] + '  property bool completed: false\n  function cleanupAndQuit() { completed = true; }\n\n' + source[end:]
        start = source.index('  // Native import checks')
        end = source.index('      Item {\n        id: keyArea', start)
        source = source[:start] + '  Item {\n    id: fixtureSurface\n    Item {\n      width: 1200; height: 800\n' + source[end:]
        source = '\n'.join(line for line in source.splitlines() if not line.strip().startswith('//@'))
        start = source.index('  Timer {\n    interval: 200\n')
        harness = '''
  property int ticks: 0
  function feedback(item) {
    let result = []
    if (item.text !== undefined && String(item.text) === root.errorText && root.errorText.length > 0)
      result.push({text: String(item.text), lines: item.lineCount, maximum: item.maximumLineCount})
    for (const child of item.children) result = result.concat(feedback(child))
    return result
  }
  Timer {
    interval: 30; running: true; repeat: true
    onTriggered: {
      ticks += 1
      if (ticks === 1) {
        root.themes = [{name: 'Fixture', path: '/fixture/wallpaper.png', explicit: false}];
        if (ACTION === 'apply') root.applySelected();
        else if (ACTION === 'list') themeListProc.exec([themeCommand, 'list', '--json']);
        else root.loadThemes('{invalid');
      }
      if (ticks > 5 && !root.applying && !themeListProc.running) {
        console.log('FEEDBACK', JSON.stringify({error: root.errorText, completed: root.completed,
                    visible: feedback(fixtureSurface)}));
        Qt.quit();
      }
      if (ticks > 100) Qt.quit();
    }
  }
}
'''.replace('ACTION', json.dumps(action))
        (fixture/'theme-picker.qml').write_text(source[:start]+harness)
        log = self.runtime/'mihao-theme-picker.log'
        with log.open('w') as stream:
            result = subprocess.run(['quickshell', '--no-color', '--path', str(fixture/'theme-picker.qml')],
                env=self.env, stdout=stream, stderr=subprocess.STDOUT, text=True, timeout=8)
        output = log.read_text()
        self.assertEqual(result.returncode, 0, output)
        self.no_import_errors(output)
        self.assertNotIn('ReferenceError', output)
        self.assertNotIn('TypeError', output)
        rows = [json.loads(line.split('FEEDBACK ',1)[1]) for line in output.splitlines() if 'FEEDBACK ' in line]
        self.assertEqual(len(rows), 1, output)
        return rows[0], output, diagnostic, stdout

    def test_success_with_warnings_keeps_preview_clean_and_logs_both_streams(self):
        value, log, diagnostic, stdout = self.run_picker(0)
        self.assertTrue(value['completed'])
        self.assertEqual(value['error'], '')
        self.assertEqual(value['visible'], [])
        self.assertIn(diagnostic, log)
        self.assertIn(stdout, log)

    def test_partial_failure_is_concise_detectable_and_fully_logged(self):
        value, log, diagnostic, stdout = self.run_picker(3)
        self.assertFalse(value['completed'])
        self.assertEqual(value['error'], 'Some colors could not be applied. Run theme status.')
        self.assertLess(len(value['error']), 80)
        self.assertNotIn('/fixture', value['error'])
        self.assertEqual(len(value['visible']), 1)
        self.assertLessEqual(value['visible'][0]['lines'], 3)
        self.assertEqual(value['visible'][0]['maximum'], 3)
        self.assertIn(diagnostic, log)
        self.assertIn(stdout, log)

    def test_apply_failure_has_short_message_and_full_log(self):
        value, log, diagnostic, _ = self.run_picker(1)
        self.assertFalse(value['completed'])
        self.assertEqual(value['error'], 'Could not apply wallpaper theme. See picker log.')
        self.assertIn(diagnostic, log)

    def test_registry_stderr_and_invalid_json_do_not_become_preview_diagnostics(self):
        value, log, diagnostic, _ = self.run_picker(1, 'list')
        self.assertEqual(value['error'], 'Could not load wallpaper list. See picker log.')
        self.assertIn(diagnostic, log)
        value, log, _, _ = self.run_picker(0, 'invalid')
        self.assertEqual(value['error'], 'Could not load wallpaper list. See picker log.')
        self.assertIn('Wallpaper registry diagnostics:', log)
