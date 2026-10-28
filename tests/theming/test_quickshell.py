"""Quickshell root/import regression tests using the installed runtime.

Validation mode executes the actual entrypoints and shared imports. Wayland-only
windows are preprocessed out because the sandbox denies compositor connections.
No launcher test sends a real signal or runs a dashboard backend/theme apply.
"""
import json
from copy import deepcopy
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / 'dotfiles/quickshell'
APPS = ('dashboard', 'theme-picker')
IMPORT_ERRORS = ('outside of the config folder', 'ThemeStore unavailable',
                 'qs-blackhole', 'module "qs.shared" is not installed')
sys.path.insert(0, str(REPO/'scripts'))
from theming.adapters import render
from theming.model import read_toml


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='qs-regression-')
        self.root = Path(self.tmp.name)
        self.runtime = self.root / 'run'
        self.runtime.mkdir(mode=0o700)
        self.config = self.root / 'config with spaces'
        self.config.mkdir()
        (self.config / 'quickshell').symlink_to(CONFIG, target_is_directory=True)
        self.env = {k:v for k,v in os.environ.items()
                    if not k.startswith(('XDG_', 'MIHAO_', 'QS_', 'QT_'))
                    and k not in ('DISPLAY', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS')}
        self.env.update(HOME=str(self.root), XDG_CONFIG_HOME=str(self.config),
                        XDG_CACHE_HOME=str(self.root/'cache'), XDG_STATE_HOME=str(self.root/'state'),
                        XDG_RUNTIME_DIR=str(self.runtime), TMPDIR=str(self.root),
                        MIHAO_THEME_CACHE=str(self.root/'cache/theme'),
                        QT_QPA_PLATFORM='offscreen', QML_DISABLE_DISK_CACHE='1',
                        QS_DISABLE_CRASH_HANDLER='1', MIHAO_QS_VALIDATE='1', NO_COLOR='1')
        active = self.root/'cache/theme/active.json'
        active.parent.mkdir(parents=True)
        active.write_text(json.dumps({'colors': {'primary':'#123456', 'accent':'#123456'}}))

    def tearDown(self):
        self.tmp.cleanup()

    def no_import_errors(self, text):
        for message in IMPORT_ERRORS:
            self.assertNotIn(message, text)


@unittest.skipUnless(shutil.which('quickshell') and shutil.which('qs'), 'Quickshell unavailable')
class NativeEntrypoints(Fixture):
    def test_dashboard_visible_colors_follow_repeated_theme_replacements(self):
        # Keep the actual dashboard properties, layouts and visual children.
        # Substitute only the compositor surface with offscreen Items. Backend
        # processes remain disabled via the existing validation environment.
        fixture = self.root/'dashboard fixture'
        fixture.mkdir()
        (fixture/'shared').mkdir()
        shutil.copyfile(CONFIG/'shared/ThemeStore.qml', fixture/'shared/ThemeStore.qml')
        source = (CONFIG/'dashboard.qml').read_text()
        begin = source.index('  // Native import checks')
        end = source.index('      Rectangle {', begin)
        source = source[:begin] + '  Item {\n    Item {\n      id: surface\n      width: 1200; height: 800\n' + source[end:]
        # Keep both code paths in the fixture, so the real visual tree loads.
        source = '\n'.join(line for line in source.splitlines() if not line.strip().startswith('//@'))
        begin = source.index('  Timer {\n    interval: 200\n')
        source = source[:begin] + '''
  function visualColors(item) {
    let result = []
    if (item.color !== undefined) result.push(String(item.color))
    if (item.border !== undefined) result.push(String(item.border.color))
    for (const child of item.children) result = result.concat(visualColors(child))
    return result
  }
  property int ticks: 0
  Timer {
    interval: 50; running: true; repeat: true
    onTriggered: {
      ticks += 1
      const properties = {}
      for (const key of ['dashboardBg', 'cardBg', 'cardHover', 'borderColor',
          'inactiveBorderColor', 'primaryText', 'secondaryText', 'mutedText',
          'accentColor', 'accentAltColor', 'successColor', 'warningColor',
          'errorColor', 'infoColor']) properties[key] = String(root[key])
      console.log('SNAPSHOT', JSON.stringify({id: theme.themeId, ticks: ticks,
          properties: properties, colors: theme.colors, visibleColors: visualColors(surface)}))
      if (ticks > 180) Qt.quit()
    }
  }
}
'''
        (fixture/'dashboard.qml').write_text(source)
        active = self.root/'cache/theme/active.json'
        default = read_toml(REPO/'scripts/theming/default.toml')
        themes = []
        for i in range(3):
            theme = deepcopy(default)
            theme['meta'].update(name=f'theme {i}', mode='light' if i == 1 else 'dark')
            # Every role changes; assertions cover all dashboard color properties.
            theme['ui'] = {key: f'#{(i+1)*0x304050+j*0x010203:06x}'
                           for j, key in enumerate(default['ui'])}
            text, _, _ = render('quickshell', theme, fixture/f'{i}.toml')
            themes.append(json.loads(text))

        def replace(data):
            temp = active.with_suffix('.tmp')
            temp.write_text(json.dumps(data) if isinstance(data, dict) else data)
            temp.replace(active)

        replace(themes[0])
        output = []
        messages = queue.Queue()
        process = subprocess.Popen(['quickshell', '--no-color', '--path', str(fixture/'dashboard.qml')],
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        def collect():
            for line in process.stdout:
                output.append(line)
                if 'SNAPSHOT ' in line:
                    messages.put(json.loads(line.split('SNAPSHOT ', 1)[1]))
            messages.put(None)

        reader = threading.Thread(target=collect)
        reader.start()

        def snapshot(theme_id, after=0):
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline:
                try:
                    value = messages.get(timeout=max(.01, deadline-time.monotonic()))
                except queue.Empty:
                    break
                if value is None:
                    break
                if value['id'] == theme_id and value['ticks'] > after:
                    return value
            self.fail('No dashboard snapshot for ' + theme_id + '\n' + ''.join(output))

        color_properties = dict(dashboardBg=('background', 'c7'), cardBg=('surface', 'e0'),
            cardHover=('hover', 'f0'), borderColor=('border', ''),
            inactiveBorderColor=('border_inactive', ''), primaryText=('foreground', ''),
            secondaryText=('foreground_alt', ''), mutedText=('muted', ''),
            accentColor=('primary', ''), accentAltColor=('secondary', ''),
            successColor=('success', ''), warningColor=('warning', ''),
            errorColor=('error', ''), infoColor=('info', ''))
        try:
            for i, data in enumerate(themes):
                if i:
                    # Canonical-only JSON exposed the stale dashboard aliases.
                    canonical = {key: data['colors'][key] for key in default['ui']}
                    replace(dict(data, colors=canonical))
                value = snapshot(data['id'])
                self.assertEqual(value['colors'], data['colors'])
                for prop, (role, alpha) in color_properties.items():
                    self.assertEqual(value['properties'][prop], '#' + alpha + data['colors'][role][1:])
                for role in ('foreground', 'muted', 'primary', 'border'):
                    self.assertIn(data['colors'][role], value['visibleColors'])
                self.assertIn('#c7' + data['colors']['background'][1:], value['visibleColors'])
                # Invalid JSON/shapes/colors must retain the last complete theme.
                for invalid in ('{invalid', {'colors': []}, {'colors': {}},
                                {'colors': {'primary': None}},
                                {'colors': {'primary': 'wrongcolor'}}):
                    replace(invalid)
                    value = snapshot(data['id'], after=value['ticks'] + 3)
                    self.assertEqual(value['colors'], data['colors'])

            # Legacy alias-only accent input still drives canonical bindings.
            legacy = dict(themes[0], id='legacy')
            legacy['colors'] = dict(legacy['colors'])
            del legacy['colors']['primary']
            del legacy['colors']['secondary']
            replace(legacy)
            value = snapshot('legacy')
            self.assertEqual(value['properties']['accentColor'], themes[0]['colors']['primary'])
            self.assertEqual(value['properties']['accentAltColor'], themes[0]['colors']['secondary'])
        finally:
            # This is only the offscreen test process created above.
            process.terminate()
            process.wait(timeout=5)
            reader.join(timeout=5)
            process.stdout.close()
        text = ''.join(output)
        for error in ('ReferenceError', 'TypeError', 'Binding loop', 'Unable to assign'):
            self.assertNotIn(error, text)
        self.no_import_errors(text)

    def test_both_actual_entrypoints_load_from_common_root(self):
        for app in APPS:
            with self.subTest(app=app):
                result = subprocess.run(['quickshell','--no-color','--path',str(CONFIG/(app+'.qml'))],
                                        env=self.env, capture_output=True, text=True, timeout=8)
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, output)
                self.assertIn('Configuration Loaded', output)
                self.assertIn(f'VALIDATED {app} {CONFIG} #123456', output)
                self.no_import_errors(output)
                self.assertNotIn('ReferenceError', output)
                self.assertNotIn('TypeError', output)

    def test_actual_launchers_use_deployed_entrypoints_with_spaces(self):
        for app in APPS:
            with self.subTest(app=app):
                # Empty fixture PID directory prevents the toggle/kill branch.
                result = subprocess.run(['bash',str(REPO/'scripts/bin'/app)],env=self.env,
                                        capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                log = self.runtime/f'mihao-{app}.log'
                deadline = time.monotonic()+8
                text = ''
                while time.monotonic() < deadline:
                    if log.exists():
                        text = log.read_text()
                    if f'VALIDATED {app}' in text or 'Failed to load configuration' in text:
                        break
                    time.sleep(.05)
                self.assertIn('Configuration Loaded',text,text)
                self.assertIn(f'VALIDATED {app}',text,text)
                self.assertIn('#123456',text,text)
                self.no_import_errors(text)
        self.assertNotEqual((self.runtime/'mihao-dashboard.pid').read_text(),
                            (self.runtime/'mihao-theme-picker.pid').read_text())

    def test_old_nested_root_is_rejected_by_actual_runtime(self):
        # This negative control would have caught the original regression. It
        # uses a symlink to the authoritative implementation, never a copy.
        nested = self.root/'broken/dashboard'
        nested.mkdir(parents=True)
        shared = self.root/'broken/shared'
        shared.mkdir()
        (shared/'ThemeStore.qml').symlink_to(CONFIG/'shared/ThemeStore.qml')
        (nested/'shell.qml').write_text('''import Quickshell
import "../shared" as Shared
Scope { Shared.ThemeStore {} }
''')
        result = subprocess.run(['quickshell','--no-color','--path',str(nested/'shell.qml')],
                                env=self.env,capture_output=True,text=True,timeout=8)
        output = result.stdout+result.stderr
        self.assertNotEqual(result.returncode,0,output)
        self.assertIn('outside of the config folder',output)
        self.assertIn('qs-blackhole',output)

    def test_normal_entrypoint_imports_resolve_before_offscreen_backend_limit(self):
        env=dict(self.env)
        env.pop('MIHAO_QS_VALIDATE')
        for app in APPS:
            with self.subTest(app=app):
                result = subprocess.run(['quickshell','--no-color','--path',str(CONFIG/(app+'.qml'))],
                                        env=env,capture_output=True,text=True,timeout=8)
                output = result.stdout+result.stderr
                # A genuine Wayland backend cannot run with Qt's offscreen
                # platform. This is a backend limit, not a successful UI test.
                self.assertNotEqual(result.returncode,0,output)
                self.assertIn('No PanelWindow backend loaded',output)
                self.no_import_errors(output)


class LauncherTests(Fixture):
    def test_launcher_arguments_preserve_distinct_entrypoints(self):
        bindir = self.root/'bin'
        bindir.mkdir()
        log = self.root/'launch.jsonl'
        executable = bindir/'qs'
        executable.write_text('''#!/usr/bin/env python3
import json,os,sys
with open(os.environ['LAUNCH_LOG'],'a') as stream:
    stream.write(json.dumps(sys.argv[1:])+'\\n')
''')
        executable.chmod(0o755)
        env=dict(self.env,PATH=str(bindir)+os.pathsep+os.environ['PATH'],LAUNCH_LOG=str(log))
        for app in APPS:
            result = subprocess.run(['bash',str(REPO/'scripts/bin'/app)],env=env,
                                    capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if log.exists() and len(log.read_text().splitlines()) == 2:
                break
            time.sleep(.02)
        calls=[json.loads(row) for row in log.read_text().splitlines()]
        self.assertCountEqual(calls,[['--path',str(self.config/'quickshell'/f'{app}.qml')] for app in APPS])

    def test_toggle_only_targets_its_own_pid_with_signals_mocked(self):
        log=self.root/'signals'
        helper=self.root/'bash-env'
        helper.write_text('''kill() {
  printf '%s\\n' "$*" >> "$SIGNAL_LOG"
  return 0
}
''')
        env=dict(self.env,BASH_ENV=str(helper),SIGNAL_LOG=str(log))
        for app in APPS:
            pid=self.runtime/f'mihao-{app}.pid'
            other=self.runtime/f'mihao-{APPS[1] if app == APPS[0] else APPS[0]}.pid'
            pid.write_text('12345\n')
            other.write_text('54321\n')
            result=subprocess.run(['bash',str(REPO/'scripts/bin'/app)],env=env,
                                  capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse(pid.exists())
            self.assertEqual(other.read_text(),'54321\n')
        self.assertEqual(log.read_text().splitlines(),['-0 12345','12345']*2)

    def test_mod_z_and_mod_t_bindings_are_preserved(self):
        lua=(REPO/'dotfiles/hypr/hyprland.lua').read_text()
        self.assertIn('hl.bind(mod .. " + Z", hl.dsp.exec_cmd("/home/mihao/.local/bin/dashboard"))',lua)
        self.assertIn('hl.bind(mod .. " + T", hl.dsp.exec_cmd("/home/mihao/.local/bin/theme-picker"))',lua)
        theme_files=list(CONFIG.rglob('ThemeStore.qml'))
        self.assertEqual(theme_files,[CONFIG/'shared/ThemeStore.qml'])


if __name__ == '__main__':
    unittest.main()
