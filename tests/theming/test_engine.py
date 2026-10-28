"""Isolated CLI integration tests: no desktop executable is ever invoked."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
from theming.model import ANSI, UI, association, dumps, read_toml, validate
from theming.palette import contrast
from desktop_fixture import deploy_desktop

MOCK = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['MOCK_LOG'], 'a') as f:
    f.write(json.dumps([name] + args) + '\n')
if name == os.environ.get('MOCK_FAIL'):
    print('injected adapter failure', file=sys.stderr)
    sys.exit(7)
if name == 'matugen':
    config = pathlib.Path(args[args.index('--config')+1]).read_text()
    assert '[templates]' in config and '--dry-run' in args
    colors = dict(background='#182025', surface_container='#283035', surface_container_high='#384045',
      on_surface='#ddeeff', on_surface_variant='#aabbcc', primary='#99ccaa', secondary='#aaccdd',
      outline='#667788', error='#ffaaaa')
    print(json.dumps({'colors': {'dark':colors, 'light':colors}}))
elif name == 'kitten':
    if args[0] == 'themes':
        assert '--dump-theme' in args and '--cache-age=-1' in args
        preset = args[-1]
        if preset == 'Default':
            print('# native defaults'); sys.exit(0)
        if preset not in ('Tokyo Night', 'Gruvbox Dark'):
            print('theme unavailable offline', file=sys.stderr)
            sys.exit(1)
        print('background ' + ('#1a1b26' if preset == 'Tokyo Night' else '#282828'))
        print('foreground #eeeeee\ncolor1 #ff8888')
elif name == 'kitty':
    assert args[0] == '+runpy'
    if 'parse_config' in args[1]:
        data = sys.stdin.read()
        print(json.dumps(['invalid native color'] if 'wrongcolor' in data else []))
    elif 'theming.kitty_runtime' in args[1]:
        if os.environ.get('MOCK_KITTY_PALETTE_MISMATCH'):
            print('Kitty effective palette differs: background', file=sys.stderr)
            sys.exit(1)
        print(json.dumps({'signaled': json.loads(os.environ.get('MOCK_KITTY_PIDS', '[12345]')),
                          'skipped': [], 'vanished': []}))
elif name == 'pgrep':
    if os.environ.get('MOCK_NO_DUNST'):
        sys.exit(1)
    print('12345')
elif name == 'ps':
    print(os.environ.get('MOCK_DUNST_COMMAND', 'dunst'))
elif name == 'hyprctl':
    if args[0] == 'eval':
        print(os.environ.get('MOCK_HYPR_REPLY', 'ok'))
    elif 'getoption' in args:
        data = json.loads((pathlib.Path(os.environ.get('MIHAO_THEME_CACHE', pathlib.Path.home()/'.cache/theme'))/'generated/hyprland.json').read_text())
        key = args[-1].replace('general.col.', 'general:col.')
        value = data[key]
        colors = value['colors'] if isinstance(value, dict) else [value]
        angle = value['angle'] if isinstance(value, dict) else 0
        gradient = ' '.join('ff'+c[1:] for c in colors) + ' ' + str(int(angle)) + 'deg'
        print(json.dumps({'option': args[-1], 'gradient': os.environ.get('MOCK_HYPR_GRADIENT', gradient), 'set':True}))
    else:
        raise AssertionError('legacy hyprctl command: ' + repr(args))
elif name == 'ffmpeg':
    pathlib.Path(args[-1]).write_bytes(b'PNG mock')
'''


class ThemeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='theming test ')
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.config = self.home / '.config/themes'
        self.config.mkdir(parents=True)
        self.mockbin = self.root / 'bin'
        self.mockbin.mkdir()
        for name in ('matugen', 'kitten', 'kitty', 'awww', 'awww-daemon', 'ffmpeg', 'hyprctl', 'dunstctl', 'pgrep', 'ps', 'fuzzel'):
            path = self.mockbin / name
            path.write_text(MOCK)
            path.chmod(0o755)
        self.log = self.root / 'commands.jsonl'
        self.env = {k:v for k,v in os.environ.items() if not (k.startswith('XDG_') or k.startswith('MIHAO_THEME_') or k.startswith('KITTY_'))}
        self.env.update(HOME=str(self.home), PATH=str(self.mockbin)+os.pathsep+os.environ['PATH'], MOCK_LOG=str(self.log), PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(self.root))
        self.image = self.home / 'Pictures with spaces/mononoke art.png'
        self.image.parent.mkdir()
        self.image.write_bytes(b'wallpaper')
        self.video = self.image.with_name('animated preview.webp')
        frame = bytes(16) + b'VP8 ' + (4).to_bytes(4, 'little') + b'mock'
        payload = b'ANMF' + len(frame).to_bytes(4, 'little') + frame
        self.video.write_bytes(b'RIFF' + (len(payload)+4).to_bytes(4, 'little') + b'WEBP' + payload)
        self.registry = self.config / 'wallpapers'
        self.registry.write_text(f'Princess Mononoke|{self.image}\nRain live|{self.video}\n')
        self.cache = self.home / '.cache/theme'
        self.statefile = self.home / '.local/state/mihao/theme/state.json'
        self.saved = association(self.image, self.config / 'generated')
        self.default = read_toml(REPO / 'scripts/theming/default.toml')
        self.deploy_configs()

    def deploy_configs(self):
        self.checkout, _, _ = deploy_desktop(self.home, self.home / '.config', self.cache)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, code=0, env=None):
        r = subprocess.run([sys.executable, '-B', str(REPO / 'scripts/bin/theme'), *map(str,args)], env=env or self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return r

    def calls(self, name=None):
        rows = [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []
        return [r for r in rows if not name or r[0] == name]

    def state(self):
        return json.loads(self.statefile.read_text())

    def apply(self):
        self.cli('apply', 'Princess Mononoke')

    def test_legacy_registry_and_spaces(self):
        rows = json.loads(self.cli('list', '--json').stdout)
        self.assertEqual(rows[0]['name'], 'Princess Mononoke')
        self.assertEqual(rows[0]['path'], str(self.image))
        self.assertFalse(rows[0]['explicit'])
        self.assertFalse(self.statefile.exists())
        self.assertFalse(self.log.exists())

    def test_explicit_relative_and_shared_themes(self):
        theme = self.config / 'shared theme.toml'
        theme.write_text(dumps(self.default))
        self.registry.write_text(f'Princess Mononoke|{self.image}|./shared theme.toml\nRain live|{self.video}|./shared theme.toml\n')
        self.apply()
        self.cli('apply', 'Rain live')
        self.assertFalse(self.calls('matugen'))
        self.assertEqual(self.state()['selection']['theme'], str(theme))
        self.assertEqual(len(self.calls('awww')), 4)

    def test_explicit_missing_does_not_fallback(self):
        self.registry.write_text(f'Princess Mononoke|{self.image}|missing.toml\n')
        self.assertIn('Explicit theme file not found', self.cli('apply', 'Princess Mononoke', code=1).stderr)
        self.assertFalse(self.saved.exists())
        self.assertFalse(self.calls())

    def test_generation_persistent_and_never_repeated(self):
        self.apply()
        before = self.saved.read_bytes()
        self.cli('apply', 'Princess Mononoke')
        self.assertEqual(before, self.saved.read_bytes())
        self.assertEqual(len(self.calls('matugen')), 1)
        self.assertEqual(len(self.calls('awww')), 4)
        self.assertEqual(len(self.calls('dunstctl')), 2)
        self.assertEqual(self.state()['selection']['theme'], str(self.saved))
        validate(read_toml(self.saved), self.saved)

    def test_edited_existing_theme_is_authoritative(self):
        self.apply()
        data = read_toml(self.saved)
        data['ui']['primary'] = '#abcdef'
        self.saved.write_text(dumps(data))
        self.apply()
        self.assertEqual(json.loads((self.cache/'active.json').read_text())['colors']['primary'], '#abcdef')
        self.assertEqual(len(self.calls('matugen')), 1)

    def test_native_preset_temporary_does_not_change_other_apps(self):
        self.apply()
        before = self.saved.read_bytes()
        other = (self.cache/'active.json').read_bytes()
        self.cli('kitty', 'Tokyo Night')
        self.assertIn('background #1a1b26', (self.cache/'generated/kitty.conf').read_text())
        self.assertEqual(before, self.saved.read_bytes())
        self.assertEqual(other, (self.cache/'active.json').read_bytes())
        self.assertEqual(self.state()['temporary']['kitty']['name'], 'Tokyo Night')
        self.assertEqual(len(self.calls('dunstctl')), 1)

    def test_saved_preset_restored_on_same_wallpaper(self):
        self.apply()
        self.cli('kitty', 'Tokyo Night', '--save')
        self.cli('kitty', 'Gruvbox Dark')
        self.apply()
        self.assertIn('background #1a1b26', (self.cache/'generated/kitty.conf').read_text())
        self.assertNotIn('kitty', self.state()['temporary'])
        self.assertEqual(read_toml(self.saved)['apps']['kitty']['name'], 'Tokyo Night')
        self.assertEqual(len(list(self.saved.parent.glob('*.bak.*'))), 1)

    def test_custom_file_save_and_noncolor_filtering(self):
        self.apply()
        conf = self.home / 'My custom Kitty.conf'
        conf.write_text('background #112233\nfont_size 500\nmap ctrl+a quit\n')
        r = self.cli('kitty', '--file', conf, '--save')
        self.assertIn('ignored non-color', r.stderr)
        output = (self.cache/'generated/kitty.conf').read_text()
        self.assertIn('background #112233', output)
        self.assertNotIn('font_size', output)
        self.assertNotIn('quit', output)
        self.assertEqual(read_toml(self.saved)['apps']['kitty']['path'], str(conf))

    def test_universal_save(self):
        self.apply()
        self.cli('kitty', 'Tokyo Night', '--save')
        self.cli('kitty', '--universal', '--save')
        self.assertEqual(read_toml(self.saved)['apps']['kitty'], {'source':'universal'})
        self.assertIn('background #182025', (self.cache/'generated/kitty.conf').read_text())

    def test_save_creates_missing_implicit_theme(self):
        self.apply()
        self.saved.unlink()
        self.cli('kitty', 'Tokyo Night', '--save')
        self.assertTrue(self.saved.exists())
        self.assertEqual(len(self.calls('matugen')), 2)
        self.assertEqual(read_toml(self.saved)['apps']['kitty']['source'], 'preset')

    def test_save_imports_legacy_wallpaper_marker(self):
        marker = self.home/'.cache/mihao/current-wallpaper'
        marker.parent.mkdir(parents=True)
        marker.write_text(str(self.image))
        self.cli('kitty', 'Tokyo Night', '--save')
        self.assertTrue(self.saved.exists())
        self.assertFalse(self.calls('awww'))

    def test_reset_kitty_only(self):
        self.apply()
        self.cli('kitty', 'Tokyo Night')
        self.cli('reset', 'kitty')
        self.assertNotIn('kitty', self.state()['temporary'])
        self.assertIn('background #182025', (self.cache/'generated/kitty.conf').read_text())
        self.assertEqual(len(self.calls('awww')), 2)
        self.assertEqual(len(self.calls('dunstctl')), 1)

    def test_full_reset_no_wallpaper(self):
        self.apply()
        self.cli('kitty', 'Tokyo Night')
        self.cli('reset')
        self.assertEqual(len(self.calls('awww')), 2)
        self.assertEqual(len(self.calls('dunstctl')), 2)
        self.assertFalse(self.state()['temporary'])

    def test_invalid_toml_preserves_runtime_and_state(self):
        self.apply()
        before = self.statefile.read_bytes()
        active = (self.cache/'active.json').read_bytes()
        self.saved.write_text('[invalid')
        self.cli('apply', 'Princess Mononoke', code=1)
        self.assertEqual(self.statefile.read_bytes(), before)
        self.assertEqual((self.cache/'active.json').read_bytes(), active)
        self.assertEqual(len(self.calls('awww')), 2)

    def test_invalid_color_before_wallpaper(self):
        self.apply()
        data = read_toml(self.saved)
        data['ui']['background'] = 'wrongcolor'
        self.saved.write_text(dumps(data))
        self.assertIn('expected #RRGGBB', self.cli('reset', code=1).stderr)
        self.assertEqual(len(self.calls('dunstctl')), 1)

    def test_missing_custom_file_preserves_theme(self):
        self.apply()
        before = self.saved.read_bytes()
        self.cli('kitty', '--file', self.home/'missing.conf', '--save', code=1)
        self.assertEqual(before, self.saved.read_bytes())

    def test_failed_adapter_retains_previous_file_and_reports_partial(self):
        self.apply()
        path = self.cache/'generated/dunst.conf'
        before = path.read_bytes()
        data = read_toml(self.saved)
        data['ui']['primary'] = '#aabbcc'
        self.saved.write_text(dumps(data))
        self.cli('reset', code=3, env=dict(self.env, MOCK_FAIL='dunstctl'))
        self.assertEqual(before, path.read_bytes())
        state = self.state()
        self.assertEqual(state['applications']['dunst']['status'], 'failed')
        self.assertIn('dunst', state['temporary'])
        self.assertEqual(json.loads((self.cache/'active.json').read_text())['colors']['primary'], '#aabbcc')

    def test_unknown_offline_preset_no_mutation(self):
        self.apply()
        before = self.saved.read_bytes()
        old = (self.cache/'generated/kitty.conf').read_bytes()
        self.assertIn('unavailable offline', self.cli('kitty', 'Unknown preset', '--save', code=1).stderr)
        self.assertEqual(before, self.saved.read_bytes())
        self.assertEqual(old, (self.cache/'generated/kitty.conf').read_bytes())

    def test_animated_path_unchanged_frame_extracted_once(self):
        self.cli('apply', 'Rain live')
        self.cli('apply', 'Rain live')
        self.assertEqual(len(self.calls('ffmpeg')), 0)
        self.assertEqual(len(self.calls('matugen')), 1)
        self.assertTrue(self.calls('matugen')[0][-1].endswith('preview.webp'))
        self.assertEqual([c[-1] for c in self.calls('awww') if c[1]=='img'], [str(self.video)]*2)

    def test_state_recovered_after_cache_loss_without_live_actions(self):
        self.apply()
        self.cli('kitty', 'Tokyo Night')
        before = self.calls()
        shutil.rmtree(self.cache)
        self.cli('init')
        self.assertEqual(before, self.calls())
        self.assertIn('background #1a1b26', (self.cache/'generated/kitty.conf').read_text())
        self.assertTrue((self.cache/'generated/hyprland.lua').is_file())

    def test_init_upgrades_old_dunst_cache_and_snapshot_without_live_actions(self):
        from theming.adapters import parse_ini
        self.apply()
        output = self.cache/'generated/dunst.conf'
        old = output.read_text().replace('[urgency_normal]',
                                        '[urgency_normal]\nseparator_color="#010203"')
        output.write_text(old)
        calls = self.calls()
        self.cli('init')
        self.assertEqual(self.calls(), calls)
        parsed = parse_ini(output.read_text())
        self.assertNotIn('separator_color', parsed['urgency_normal'])
        self.assertIn('separator_color', parsed['global'])
        state = self.state()
        state['runtime']['dunst'] = old
        self.statefile.write_text(json.dumps(state))
        output.unlink()
        self.cli('init')
        self.assertEqual(self.calls(), calls)
        self.assertEqual(parse_ini(output.read_text()), parsed)

    def test_session_restores_wallpaper_without_resetting_temporary(self):
        self.apply()
        self.cli('kitty', 'Tokyo Night')
        self.cli('restore-session')
        self.assertEqual(len(self.calls('awww')), 4)
        self.assertEqual(len(self.calls('dunstctl')), 2)
        self.assertEqual(self.state()['temporary']['kitty']['name'], 'Tokyo Night')

    def test_regeneration_backup_preserves_overrides_and_does_not_apply(self):
        self.apply()
        self.cli('kitty', 'Tokyo Night', '--save')
        before = self.saved.read_bytes()
        calls = len(self.calls('awww'))
        self.cli('regenerate')
        self.assertEqual(read_toml(self.saved)['apps']['kitty']['name'], 'Tokyo Night')
        self.assertTrue(any(p.read_bytes()==before for p in self.saved.parent.glob('*.bak.*')))
        self.assertEqual(len(self.calls('matugen')), 2)
        self.assertEqual(len(self.calls('awww')), calls)

    def test_no_unexpected_persistent_writes(self):
        image = self.image.read_bytes()
        registry = self.registry.read_bytes()
        self.apply()
        self.cli('kitty', 'Tokyo Night', '--save')
        self.cli('reset')
        allowed = [self.home/'.cache', self.home/'.local/state', self.config/'generated']
        existing = {self.image, self.video, self.registry}
        existing.update(self.checkout.rglob('*'))
        existing.update((self.home/'.config/kitty').rglob('*'))
        existing.update((self.home/'.config/fuzzel').rglob('*'))
        existing.update((self.home/'.config/dunst').rglob('*'))
        for path in self.home.rglob('*'):
            if path.is_file() and path not in existing:
                self.assertTrue(any(path.is_relative_to(p) for p in allowed), path)
        self.assertEqual(image, self.image.read_bytes())
        self.assertEqual(registry, self.registry.read_bytes())
        self.assertFalse(list(self.root.glob('mihao-palette-*')))

    def test_shared_quickshell_contract(self):
        self.apply()
        colors = json.loads((self.cache/'active.json').read_text())['colors']
        self.assertTrue(set(UI).issubset(colors))
        self.assertEqual(colors['accent'], colors['primary'])
        self.assertIn('selection_text', colors)
        for app in ('dashboard', 'theme-picker'):
            entry = (REPO/f'dotfiles/quickshell/{app}.qml').read_text()
            self.assertIn('import qs.shared', entry)
            self.assertNotIn('../shared', entry)
        picker = (REPO/'dotfiles/quickshell/theme-picker.qml').read_text()
        self.assertIn('[themeCommand, "apply", entry.path, "--name", entry.name]', picker)
        self.assertIn('command.push("--theme", entry.theme)', picker)
        self.assertNotIn('catppuccin-macchiato', picker)

    def test_all_partial_adapter_overrides(self):
        data = self.default.copy()
        data['apps'] = {
          'kitty': {'source':'partial','colors': {'background':'#112233'}},
          'quickshell': {'source':'partial','colors': {'primary':'#123456'}},
          'fuzzel': {'source':'partial','colors': {'border':'#123456'}},
          'dunst': {'source':'partial','colors': {'urgency_critical.frame_color':'#123456'}},
          'hyprland': {'source':'partial','colors': {'general:col.active_border':'#123456'}}}
        self.saved.parent.mkdir(parents=True)
        self.saved.write_text(dumps(data))
        self.apply()
        self.assertIn('background #112233', (self.cache/'generated/kitty.conf').read_text())
        self.assertIn('border=123456ff', (self.cache/'generated/fuzzel.ini').read_text())
        self.assertIn('frame_color="#123456"', (self.cache/'generated/dunst.conf').read_text())
        self.assertIn('rgb(123456)', (self.cache/'generated/hyprland.lua').read_text())
        self.assertEqual(json.loads((self.cache/'active.json').read_text())['colors']['accent'], '#123456')

    def test_invalid_source_and_unsupported_preset_rejected(self):
        for source in ('bogus', 'preset'):
            data = read_toml(REPO/'scripts/theming/default.toml')
            data['apps'] = {'fuzzel': {'source':source,'name':'Tokyo Night'}}
            self.saved.parent.mkdir(parents=True, exist_ok=True)
            self.saved.write_text(dumps(data))
            self.cli('apply', 'Princess Mononoke', code=1)
        self.assertFalse(self.calls('awww'))

    def test_relative_file_override_and_native_adapter_files(self):
        (self.config/'overrides').mkdir()
        f = self.config/'overrides/fuzzel.ini'
        f.write_text('[colors]\nborder=123456ff\n')
        data = read_toml(REPO/'scripts/theming/default.toml')
        data['apps'] = {'fuzzel': {'source':'file','path':'./overrides/fuzzel.ini'}}
        theme = self.config/'explicit.toml'
        theme.write_text(dumps(data))
        self.registry.write_text(f'Princess Mononoke|{self.image}|explicit.toml\n')
        self.apply()
        self.assertIn('border=123456ff', (self.cache/'generated/fuzzel.ini').read_text())
        f.write_text('[main]\nfont=bad\n')
        self.cli('reset', code=1)

    def test_generated_terminal_contrast(self):
        self.apply()
        data = read_toml(self.saved)
        self.assertGreaterEqual(contrast(data['terminal']['foreground'], data['terminal']['background']), 4.5)
        self.assertGreaterEqual(contrast(data['terminal']['selection_fg'], data['terminal']['selection_bg']), 4.5)
        for key in ANSI:
            if key not in ('black',):
                self.assertGreaterEqual(contrast(data['ansi'][key], data['terminal']['background']), 3)

    def test_configurable_generation_and_deterministic_collision_resistance(self):
        target = self.home/'themes elsewhere'
        self.cli('apply', 'Princess Mononoke', env=dict(self.env, MIHAO_THEME_GENERATED_DIR=str(target)))
        self.assertTrue(association(self.image, target).exists())
        self.assertNotEqual(association(self.image, target), association(self.video, target))

    def test_cli_legacy_path_and_optional_theme(self):
        explicit = self.config/'explicit.toml'
        explicit.write_text(dumps(self.default))
        self.cli(self.image, explicit)
        self.assertEqual(self.state()['selection']['theme'], str(explicit))
        self.assertFalse(self.calls('matugen'))

    def test_status_and_readonly_commands_do_not_create_state(self):
        self.cli('help')
        self.cli('status')
        self.cli('list')
        self.assertFalse(self.statefile.parent.exists())
        self.assertFalse(self.calls())

    def test_status_contains_overrides_and_deviations(self):
        self.apply()
        self.cli('kitty', 'Tokyo Night', '--save')
        self.cli('kitty', 'Gruvbox Dark')
        status = json.loads(self.cli('status', '--json').stdout)
        self.assertEqual(status['saved_overrides']['kitty']['name'], 'Tokyo Night')
        self.assertEqual(status['temporary']['kitty']['name'], 'Gruvbox Dark')

    def test_default_native_preset_does_not_substitute_universal(self):
        self.apply()
        self.cli('kitty', 'Default')
        self.assertNotIn('#182025', (self.cache/'generated/kitty.conf').read_text())

    def test_dunst_stopped_stages_appearance_for_future_launch(self):
        self.cli('apply', 'Princess Mononoke', env=dict(self.env, MOCK_NO_DUNST='1'))
        self.assertTrue((self.cache/'generated/dunst.conf').is_file())
        self.assertFalse(self.calls('dunstctl'))
        self.assertIn('staged', self.state()['applications']['dunst']['status'])

    def test_regenerate_named_wallpaper_before_first_selection(self):
        self.cli('regenerate', 'Princess Mononoke')
        self.assertTrue(self.saved.is_file())
        self.assertFalse(self.statefile.exists())
        self.assertFalse(self.calls('awww'))

    def test_missing_wallpaper_does_not_run_adapters(self):
        self.image.unlink()
        self.cli('apply', 'Princess Mononoke', code=1)
        self.assertFalse(self.calls())
        self.assertFalse(self.statefile.exists())

    def test_wallpaper_command_failure_preserves_selected_state(self):
        self.apply()
        before = self.statefile.read_bytes()
        self.cli('apply', 'Princess Mononoke', env=dict(self.env, MOCK_FAIL='awww'), code=1)
        self.assertEqual(self.statefile.read_bytes(), before)
        self.assertEqual(len(self.calls('dunstctl')), 1)

    def test_theme_created_during_extraction_is_not_overwritten(self):
        from unittest.mock import patch
        from theming.engine import Engine
        customized = dict(self.default, meta=dict(name='Created by editor', mode='dark', schema=1))
        def generating(*args):
            self.saved.parent.mkdir(parents=True)
            self.saved.write_text(dumps(customized))
            return self.default
        with patch.dict(os.environ, self.env, clear=True), patch('theming.engine.generate', side_effect=generating):
            engine = Engine()
            result = engine.load(engine.find('Princess Mononoke'))
        self.assertEqual(result['meta']['name'], 'Created by editor')
        self.assertEqual(read_toml(self.saved)['meta']['name'], 'Created by editor')

    def test_authoritative_cli_theme_path_without_extension(self):
        self.assertIn('Explicit theme file not found', self.cli('apply','Princess Mononoke','--theme','missing theme',code=1).stderr)
        self.assertFalse(self.calls())

    def test_invalid_custom_json_fails_before_wallpaper(self):
        custom = self.config/'quickshell.json'
        custom.write_text('{invalid')
        data = dict(self.default, apps={'quickshell':{'source':'file','path':str(custom)}})
        self.saved.parent.mkdir(parents=True)
        self.saved.write_text(dumps(data))
        self.cli('apply','Princess Mononoke',code=1)
        self.assertFalse(self.calls('awww'))

    def test_registry_and_paths_are_never_shell_evaluated(self):
        special = self.image.with_name('image $(touch NEVER_CREATED).png')
        special.write_bytes(b'image')
        name = 'A name; touch NEVER_CREATED'
        self.registry.write_text(f'{name}|{special}\n')
        self.cli('apply',name)
        self.assertEqual(self.calls('awww')[-1], ['awww','img',str(special)])
        self.assertFalse((REPO/'NEVER_CREATED').exists())
        self.assertFalse((self.home/'NEVER_CREATED').exists())

    def test_legacy_theme_apply_without_active_wallpaper(self):
        presets = self.config/'presets'
        presets.mkdir()
        (presets/'sample.toml').write_text(dumps(self.default))
        result = subprocess.run([sys.executable,'-B',str(REPO/'scripts/bin/theme-apply'),'sample'],env=self.env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(self.calls('awww'))
        self.assertEqual(self.state()['selection']['path'],'')


    def test_preset_name_cannot_override_offline_options(self):
        self.apply()
        self.cli('kitty','--name-is-not-an-option',code=2)
        data = read_toml(self.saved)
        data['apps'] = {'kitty': {'source':'preset','name':'--cache-age=0'}}
        self.saved.write_text(dumps(data))
        self.cli('reset',code=1)
        self.assertEqual(self.calls('kitten')[-1][-2:], ['--','--cache-age=0'])

    def test_invalid_active_state_has_useful_error(self):
        self.statefile.parent.mkdir(parents=True)
        self.statefile.write_text('{"selection": "bad"}')
        self.assertIn('Invalid active state',self.cli('status',code=1).stderr)


    def test_picker_identity_disambiguates_shared_wallpaper_path(self):
        first=self.config/'first.toml'
        second=self.config/'second.toml'
        first.write_text(dumps(self.default))
        data=read_toml(first)
        data['meta']['name']='Second variant'
        second.write_text(dumps(data))
        self.registry.write_text(f'First variant|{self.image}|first.toml\nSecond variant|{self.image}|second.toml\n')
        self.cli('apply',self.image,'--name','Second variant','--theme',second)
        self.assertEqual(self.state()['selection']['name'],'Second variant')
        self.assertEqual(self.state()['selection']['theme'],str(second))
        self.assertFalse(self.calls('matugen'))

    def test_hyprland_lua_borders_no_legacy_or_unrelated_settings(self):
        self.apply()
        calls = self.calls('hyprctl')
        self.assertEqual([c[1] for c in calls], ['eval', '-j', '-j'])
        code = calls[0][2]
        self.assertIn('hl.config({ general = { col = {', code)
        self.assertIn('active_border = "rgb(99ccaa)"', code)
        self.assertIn('inactive_border = "rgb(667788)"', code)
        for forbidden in ('keyword', 'border_size', 'rounding', 'animations', 'gaps_in'):
            self.assertNotIn(forbidden, code)
        self.assertEqual(calls[1][-1], 'general.col.active_border')
        self.assertEqual(calls[2][-1], 'general.col.inactive_border')

    def test_hyprland_zero_exit_error_retains_both_files(self):
        self.apply()
        paths = [self.cache/'generated/hyprland.json', self.cache/'generated/hyprland.lua']
        before = [p.read_bytes() for p in paths]
        data = read_toml(self.saved)
        data['ui']['primary'] = '#abcdef'
        self.saved.write_text(dumps(data))
        result = self.cli('reset', 'hyprland', code=3,
                          env=dict(self.env, MOCK_HYPR_REPLY='error: invalid color'))
        self.assertIn('hyprctl eval hl.config: error: invalid color', result.stderr)
        self.assertIn(str(paths[0]), result.stderr)
        self.assertIn('previous generated files preserved', result.stderr)
        self.assertEqual([p.read_bytes() for p in paths], before)
        self.assertEqual(self.state()['applications']['hyprland']['status'], 'failed')

    def test_hyprland_getoption_detects_silent_rejection(self):
        self.apply()
        result = self.cli('reset', 'hyprland', code=3,
                          env=dict(self.env, MOCK_HYPR_GRADIENT='ff000000 0deg'))
        self.assertIn('getoption general.col.active_border: colors differ', result.stderr)

    def test_gradient_saved_temporary_reset_and_wallpaper_reselection(self):
        self.apply()
        self.cli('hyprland', '--gradient', '45', '--save')
        saved = read_toml(self.saved)
        self.assertEqual(saved['apps']['hyprland']['active_border']['colors'], ['primary', 'secondary'])
        expected = {'colors': ['#99ccaa', '#aaccdd'], 'angle': 45}
        self.assertEqual(json.loads((self.cache/'generated/hyprland.json').read_text())['general:col.active_border'], expected)
        self.assertIn('angle = 45', (self.cache/'generated/hyprland.lua').read_text())
        self.cli('hyprland', '--universal')
        self.assertIn('hyprland', self.state()['temporary'])
        self.cli('reset', 'hyprland')
        self.assertNotIn('hyprland', self.state()['temporary'])
        self.cli('hyprland', '--gradient', '90')
        self.apply()
        self.assertEqual(json.loads((self.cache/'generated/hyprland.json').read_text())['general:col.active_border'], expected)
        self.assertFalse(self.state()['temporary'])

    def test_invalid_gradients_rejected_before_live_commands(self):
        self.apply()
        before = self.calls()
        for angle in ('-1', '361', 'nan', 'inf'):
            self.cli('hyprland', '--gradient', angle, code=1)
        self.assertEqual(before, self.calls())

    def test_kitty_missing_effective_include_is_failure_without_reload(self):
        self.apply()
        include = self.home/'.local/share/mihao-theme'
        include.unlink()
        before = len(self.calls('kitty'))
        result = self.cli('kitty', 'Tokyo Night', code=3)
        self.assertIn('bridge', result.stderr)
        # The single Kitty invocation validates colors; no live reload occurs.
        self.assertEqual(len(self.calls('kitty')), before + 1)
        self.assertIn('background #182025', (self.cache/'generated/kitty.conf').read_text())
        status = json.loads(self.cli('status', '--json').stdout)
        self.assertIn('failed:', status['deployment']['kitty'])

    def test_fuzzel_static_include_is_not_success(self):
        self.apply()
        path = self.home/'.config/fuzzel/fuzzel.ini'
        path.write_text(path.read_text().replace('include=~/.local/share/mihao-theme/fuzzel.ini',
                                               'include=~/.config/fuzzel/colors.ini'))
        result = self.cli('reset', 'fuzzel', code=3)
        self.assertIn(str(path), result.stderr)
        self.assertIn('does not consume', result.stderr)

    def test_dunst_static_dropin_is_not_success(self):
        self.apply()
        path = self.home/'.config/dunst/dunstrc.d/99-theme.conf'
        path.unlink()
        path.write_text('[global]\nbackground="#000000"\n')
        before = len(self.calls('dunstctl'))
        self.cli('reset', 'dunst', code=3)
        self.assertEqual(len(self.calls('dunstctl')), before)

    def test_dunst_explicit_config_bypasses_dropins_and_is_reported(self):
        self.apply()
        result = self.cli('reset', 'dunst', code=3,
                          env=dict(self.env, MOCK_DUNST_COMMAND='dunst -conf "/some custom path/dunstrc"'))
        self.assertIn('explicit configuration', result.stderr)
        self.assertIn('drop-ins', result.stderr)
        self.assertEqual(len(self.calls('dunstctl')), 1)

    def test_fuzzel_native_validation_failure_restores_output(self):
        self.apply()
        path = self.cache/'generated/fuzzel.ini'
        before = path.read_bytes()
        self.cli('reset', 'fuzzel', code=3, env=dict(self.env, MOCK_FAIL='fuzzel'))
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.state()['applications']['fuzzel']['status'], 'failed')

    def test_kitty_uses_native_reload_even_with_inherited_socket(self):
        self.apply()
        self.cli('kitty', 'Tokyo Night', env=dict(self.env, KITTY_LISTEN_ON='unix:/tmp/kitty socket'))
        self.assertFalse([c for c in self.calls('kitten') if c[1] == '@'])
        self.assertIn('theming.kitty_runtime', self.calls('kitty')[-1][2])
        self.assertIn('SIGUSR1 delivered to PIDs 12345', self.state()['applications']['kitty']['status'])
        conf = (self.home/'.config/kitty/kitty.conf').read_text()
        self.assertNotIn('allow_remote_control', conf)

    def test_all_app_file_overrides_persist_and_reset_without_unrelated_changes(self):
        self.apply()
        originals = {p:p.read_bytes() for app in ('kitty','fuzzel','dunst')
                     for p in (self.home/'.config'/app).rglob('*') if p.is_file() and not p.is_symlink()}
        for app, text, filename in [
            ('fuzzel', '[colors]\nborder=abcdefaa\n', 'fuzzel.ini'),
            ('dunst', '[urgency_normal]\nframe_color="#abcdef"\n', 'dunst.conf'),
            ('hyprland', '{"general:col.inactive_border":"#abcdef"}', 'hyprland.json'),
            ('quickshell', '{"primary":"#abcdef"}', None),
        ]:
            path = self.home/f'custom {app} colors'
            path.write_text(text)
            self.cli(app, '--file', path, '--save')
            output = self.cache/'generated'/filename if filename else self.cache/'active.json'
            expected = output.read_bytes()
            self.cli(app, '--universal')
            self.assertNotEqual(output.read_bytes(), expected)
            self.assertIn(app, self.state()['temporary'])
            self.cli('reset', app)
            self.assertEqual(output.read_bytes(), expected)
            self.assertNotIn(app, self.state()['temporary'])
            self.cli(app, '--universal')
        self.cli('reset')
        self.assertFalse(self.state()['temporary'])
        self.apply()
        for p, text in originals.items():
            self.assertEqual(p.read_bytes(), text)
        self.assertTrue(all(c[1:] == ['reload'] for c in self.calls('dunstctl')))

    def test_hm_runtime_links_are_unique_and_out_of_store(self):
        config = (REPO/'home/modules/desktop.nix').read_text()
        for declaration in ('kitty/appearance.conf', 'fuzzel/colors.ini', 'dunst/dunstrc.d/99-theme.conf'):
            self.assertNotIn('"'+declaration+'"', config)
        self.assertNotIn('appFiles', config)
        self.assertEqual(config.count('home.file.".local/share/mihao-theme"'), 1)
        self.assertIn('mkOutOfStoreSymlink', config)
        self.assertNotIn('lib.mkForce', config)

    def test_dunst_separator_is_global_only_and_noncolor_rules_preserved(self):
        from theming.adapters import parse_ini
        self.apply()
        data = parse_ini((self.cache/'generated/dunst.conf').read_text())
        self.assertIn('separator_color', data['global'])
        for section in ('urgency_low', 'urgency_normal', 'urgency_critical'):
            self.assertNotIn('separator_color', data[section])
            self.assertEqual(set(data[section]), {'foreground', 'background', 'frame_color', 'highlight'})
        self.assertIn('set_stack_tag = volume', (self.home/'.config/dunst/dunstrc').read_text())

    def test_write_failure_is_reported_and_other_adapters_continue(self):
        from unittest.mock import patch
        from theming.engine import Engine
        from theming.model import atomic_write
        self.apply()
        old = (self.cache/'generated/dunst.conf').read_bytes()
        def writing(path, content):
            if path.name == 'dunst.conf':
                raise PermissionError('injected read-only destination')
            atomic_write(path, content)
        with patch.dict(os.environ, self.env, clear=True):
            engine = Engine()
            state = engine.state()
            plans = engine.prepare(self.default, self.saved, ['dunst', 'quickshell'])
            with patch('theming.engine.atomic_write', side_effect=writing), patch('theming.adapters.live', return_value='mock applied'):
                failures = engine.install(plans, state)
        self.assertIn('atomic write', failures[0])
        self.assertIn('injected read-only destination', failures[0])
        self.assertEqual((self.cache/'generated/dunst.conf').read_bytes(), old)
        self.assertEqual(state['applications']['quickshell']['status'], 'mock applied')
        self.assertTrue(state['applications']['dunst']['previous_files_preserved'])

    def test_restore_failure_does_not_claim_files_preserved(self):
        from unittest.mock import patch
        from theming.engine import Engine
        from theming.model import atomic_write, ThemeError
        self.apply()
        count = 0
        def writing(path, content):
            nonlocal count
            count += 1
            if count == 2:
                raise PermissionError('injected restore failure')
            atomic_write(path, content)
        with patch.dict(os.environ, self.env, clear=True):
            engine = Engine()
            state = engine.state()
            plans = engine.prepare(self.default, self.saved, ['dunst'])
            with patch('theming.engine.atomic_write', side_effect=writing), patch('theming.adapters.live', side_effect=ThemeError('reload failed')):
                failures = engine.install(plans, state)
        self.assertFalse(state['applications']['dunst']['previous_files_preserved'])
        self.assertIn('file restoration failed', failures[0])
        self.assertIn('injected restore failure', failures[0])

    def test_empty_default_preset_with_socket_uses_native_reload(self):
        self.apply()
        self.cli('kitty', 'Default', env=dict(self.env, KITTY_LISTEN_ON='unix:/tmp/kitty socket'))
        self.assertFalse(any(c[1] == '@' for c in self.calls('kitten')))
        self.assertIn('theming.kitty_runtime', self.calls('kitty')[-1][2])
        self.assertFalse((self.cache/'generated/kitty.conf').read_text().strip())

    def test_kitty_no_gui_is_staged_without_claiming_delivery(self):
        self.cli('apply', 'Princess Mononoke', env=dict(self.env, MOCK_KITTY_PIDS='[]'))
        status = self.state()['applications']['kitty']['status']
        self.assertIn('staged for next Kitty launch', status)
        self.assertNotIn('delivered', status)

    def test_kitty_effective_palette_failure_restores_previous_output(self):
        self.apply()
        output = self.cache/'generated/kitty.conf'
        previous = output.read_bytes()
        self.cli('kitty', 'Tokyo Night', code=3,
                 env=dict(self.env, MOCK_KITTY_PALETTE_MISMATCH='1'))
        self.assertEqual(output.read_bytes(), previous)
        self.assertEqual(self.state()['applications']['kitty']['status'], 'failed')

    def test_session_restore_failure_is_recorded_in_status(self):
        self.apply()
        self.cli('restore-session', code=3, env=dict(self.env, MOCK_HYPR_REPLY='error: injected Lua failure'))
        status = json.loads(self.cli('status', '--json').stdout)
        self.assertEqual(status['applications']['hyprland']['status'], 'failed')
        self.assertIn('injected Lua failure', status['applications']['hyprland']['error'])
        self.assertIn('hyprland', status['temporary'])
        self.assertEqual(len(self.calls('dunstctl')), 2)
        self.cli('restore-session')
        self.assertNotIn('error', self.state()['applications']['hyprland'])
        self.assertNotIn('hyprland', self.state()['temporary'])



if __name__ == '__main__':
    unittest.main()
