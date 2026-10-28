"""Recovery integration: original config bytes, ownership and native parsers.

All subprocesses use a disposable HOME, disconnected display and D-Bus settings.
The HM link/cleanup helpers, when cached locally, run only against that fixture.
No complete generation activation or live reload is executed.
"""
import configparser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from desktop_fixture import (APPS, REPO, deploy_desktop, evaluate_desktop,
                             git_paths, snapshot, targets, validate_targets)

sys.path.insert(0, str(REPO / 'scripts'))
from theming import adapters, integration
from theming.engine import Engine
from theming.model import ThemeError, read_toml, dumps


def baseline(rel):
    return subprocess.check_output(['git', '-C', str(REPO), 'show', 'HEAD:' + rel])


def backups(files):
    return {name: value for name, value in files.items() if name.endswith('.backup')}


def app_ini(text, main=False):
    p = configparser.ConfigParser(interpolation=None)
    p.read_string(('[main]\n' if main else '') + text)
    return {s: dict(p[s]) for s in p.sections()}


def cached_hm_helper(suffix, marker):
    for p in Path('/nix/store').glob('*-' + suffix):
        if p.is_file() and marker in p.read_text(errors='replace'):
            return p


class DesktopFixture(unittest.TestCase):
    def test_preexisting_untracked_backups_do_not_enter_fixture(self):
        with tempfile.TemporaryDirectory(prefix='desktop fixture ') as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            subprocess.run(['git', 'init', '--quiet', str(source)], check=True)
            (source / '.gitignore').write_text('*.backup\n')
            tracked = {
                'dotfiles/kitty/kitty.conf': b'font_size 12\n',
                'dotfiles/kitty/Adapta Nokto Maia.conf': b'background #123456\n',
                'dotfiles/fuzzel/fuzzel.ini': b'[main]\nfont=test\n',
                'dotfiles/dunst/dunstrc': b'[global]\nfont=test\n',
                # A tracked backup is a legitimate input and must survive.
                'dotfiles/kitty/tracked.conf.backup': b'tracked original\n',
            }
            for rel, data in tracked.items():
                path = source / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            (source / 'dotfiles/kitty/current-theme.conf').symlink_to('Adapta Nokto Maia.conf')
            subprocess.run(['git', '-C', str(source), 'add', '--force', '--',
                            '.gitignore', 'dotfiles'], check=True)
            # Fixture inputs must retain working-tree edits, not index bytes.
            (source / 'dotfiles/kitty/kitty.conf').write_bytes(b'font_size 13\n')
            (source / 'scripts').mkdir()
            (source / 'scripts/theme.py').write_text('# current implementation\n')
            with patch('desktop_fixture.REPO', source):
                def deploy(name):
                    home = root / name / 'home'
                    home.mkdir(parents=True)
                    checkout, _, _ = deploy_desktop(home, home / '.config', home / '.cache/theme')
                    return snapshot(checkout)

                clean = deploy('clean')
                extras = ('dotfiles/kitty/kitty.conf.backup',
                          'dotfiles/kitty/Adapta Nokto Maia.conf.backup',
                          'dotfiles/kitty/Belafonte Day.conf.backup',
                          'dotfiles/fuzzel/fuzzel.ini.backup',
                          'dotfiles/dunst/dunstrc.backup',
                          'scripts/theme.py.backup')
                for rel in extras:
                    (source / rel).write_bytes(b'preexisting unrelated backup\n')
                self.assertEqual(subprocess.check_output(
                    ['git', '-C', str(source), 'ls-files', '--', *extras]), b'')
                before = snapshot(source)
                self.assertEqual(deploy('with-backups'), clean)
                self.assertEqual(snapshot(source), before)
                self.assertEqual(clean['dotfiles/kitty/kitty.conf'], ('file', b'font_size 13\n'))
                self.assertEqual(clean['dotfiles/kitty/current-theme.conf'],
                                 ('link', 'Adapta Nokto Maia.conf'))
                self.assertEqual(backups(clean), {
                    'dotfiles/kitty/tracked.conf.backup': ('file', b'tracked original\n')})


class SourcePreservation(unittest.TestCase):
    def test_hyprland_entire_main_configs_are_original(self):
        for name in ('hyprland.lua', 'hyprland.conf'):
            rel = 'dotfiles/hypr/' + name
            self.assertEqual((REPO / rel).read_bytes(), baseline(rel))
        lua = (REPO / 'dotfiles/hypr/hyprland.lua').read_text()
        for text in ('hl.bind(mod .. " + Return", hl.dsp.exec_cmd("kitty"))',
                     'hl.bind(mod .. " + e", hl.dsp.exec_cmd("kitty -e yazi"))',
                     'scale = 1.6', '2560x1600@240', '2560x1440@144'):
            self.assertIn(text, lua)

    def test_only_color_include_changes_in_main_kitty_and_fuzzel(self):
        for app, name, old, new in (
            ('kitty', 'kitty.conf', 'include current-theme.conf',
             'include ~/.local/share/mihao-theme/kitty.conf'),
            ('fuzzel', 'fuzzel.ini', 'include=~/.config/fuzzel/colors.ini',
             'include=~/.local/share/mihao-theme/fuzzel.ini'),
        ):
            rel = f'dotfiles/{app}/{name}'
            original = baseline(rel).decode()
            actual = (REPO / rel).read_text()
            self.assertEqual(actual, original.replace(old, new))
            self.assertEqual(actual.count(new), 1)

    def test_dunst_main_rules_and_unrelated_app_files_are_original(self):
        for row in subprocess.check_output(['git', '-C', str(REPO), 'ls-tree', '-r', 'HEAD',
                                           'dotfiles/kitty', 'dotfiles/fuzzel', 'dotfiles/dunst']).decode().splitlines():
            _, rel = row.split('\t')
            if rel in ('dotfiles/kitty/kitty.conf', 'dotfiles/fuzzel/fuzzel.ini',
                       'dotfiles/dunst/dunstrc.d/99-theme.conf'):
                continue
            self.assertFalse((REPO / rel).is_symlink(), rel)
            self.assertEqual((REPO / rel).read_bytes(), baseline(rel), rel)
        dunst = app_ini((REPO / 'dotfiles/dunst/dunstrc').read_text())
        self.assertEqual(dunst['volume']['set_stack_tag'], 'volume')
        self.assertEqual(dunst['brightness']['set_transient'], 'true')
        self.assertEqual(dunst['global']['font'], '0xProto Nerd Font 11')

    def test_hypr_runtime_changes_only_border_colors(self):
        data = read_toml(REPO / 'scripts/theming/default.toml')
        _, values, _ = adapters.render('hyprland', data, REPO / 'scripts/theming/default.toml')
        self.assertEqual(set(values), {'general:col.active_border', 'general:col.inactive_border'})
        self.assertNotIn('shadow', adapters.hypr_config(values))
        self.assertNotIn('shadow', adapters.hypr_lua(values))


@unittest.skipUnless(shutil.which('nix') and shutil.which('kitty'), 'Nix/Kitty unavailable')
class InstalledDesktop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="desktop recovery ' ")
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.config = self.home / 'config with spaces'
        self.cache = self.home / 'cache with spaces'
        self.state = self.home / 'state with spaces'
        self.module = evaluate_desktop(self.home, self.config, self.cache, self.state)
        self.checkout, self.generation, self.files = deploy_desktop(
            self.home, self.config, self.cache / 'theme', self.module)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(('XDG_', 'MIHAO_', 'KITTY_', 'DBUS_', 'HYPRLAND_', 'QT_', 'QS_'))
                    and k not in ('DISPLAY', 'WAYLAND_DISPLAY', 'HOME_MANAGER_BACKUP_EXT',
                                  'HOME_MANAGER_BACKUP_COMMAND', 'HOME_MANAGER_BACKUP_OVERWRITE')}
        self.env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(self.config),
                        XDG_CACHE_HOME=str(self.cache), XDG_STATE_HOME=str(self.state),
                        XDG_CONFIG_DIRS=str(self.root / 'empty-system-config'),
                        XDG_RUNTIME_DIR=str(self.root), TMPDIR=str(self.root),
                        DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(self.root / 'absent-bus'),
                        PYTHONDONTWRITEBYTECODE='1')
        self.before = snapshot(self.checkout)

    def tearDown(self):
        self.tmp.cleanup()

    def command(self, args, **kwargs):
        return subprocess.run(args, env=self.env, capture_output=True, text=True,
                              timeout=15, **kwargs)

    def init(self):
        # Explicitly choose this reviewed copy; never resolve ~/.local/bin/theme
        # or the original HOME/nixos script while reviewing an isolated tree.
        r = self.command([sys.executable, str(self.checkout / 'scripts/bin/theme'), 'init'])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def assert_checkout_preserved(self, before):
        actual = snapshot(self.checkout)
        self.assertEqual(backups(actual), backups(before))
        self.assertEqual(actual, before)

    def test_evaluation_from_isolated_module_has_no_initialization_hook(self):
        isolated = self.root / 'isolated repair worktree/home/modules/desktop.nix'
        isolated.parent.mkdir(parents=True)
        shutil.copyfile(REPO / 'home/modules/desktop.nix', isolated)
        module = evaluate_desktop(self.home, self.config, self.cache, self.state, isolated)
        self.assertEqual(module, self.module)
        self.assertEqual(module['home'].get('activation', {}), {})
        self.assertFalse(self.cache.exists())
        self.assertFalse(self.state.exists())
        self.assertEqual(snapshot(self.checkout), self.before)

    def test_explicit_worktree_init_is_idempotent_and_preserves_configs(self):
        repair = self.root / 'isolated repair worktree'
        shutil.copytree(self.checkout / 'scripts', repair / 'scripts')
        # A sentinel makes accidental use of the old hardcoded script fail.
        (self.checkout / 'scripts/bin/theme').write_text('raise RuntimeError("wrong checkout")\n')
        before = snapshot(self.checkout)
        command = [sys.executable, str(repair / 'scripts/bin/theme'), 'init']
        for iteration in range(2):
            r = self.command(command)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(snapshot(self.checkout), before)
            generated = snapshot(self.cache)
            if iteration == 0:
                first = generated
                mtimes = {p: p.stat().st_mtime_ns for p in self.cache.rglob('*') if p.is_file()}
            else:
                self.assertEqual(generated, first)
                self.assertEqual({p: p.stat().st_mtime_ns for p in mtimes}, mtimes)
        self.assertFalse((self.state / 'mihao/theme/state.json').exists())
        for app in ('kitty', 'fuzzel', 'dunst'):
            with patch.dict(os.environ, self.env, clear=True):
                engine = Engine()
                self.assertTrue(integration.check(app, engine.output(app)))
                if app == 'dunst':
                    self.assertEqual((self.config / 'dunst/dunstrc.d/99-theme.conf').resolve(strict=True),
                                     engine.output(app))
        for p in self.files:
            p.resolve(strict=True)
        for p in self.checkout.rglob('*'):
            if p.is_symlink():
                p.resolve(strict=True)

    def test_evaluated_targets_match_original_directory_ownership(self):
        self.assertEqual(set(self.module['xdg']['configFile']), set(APPS))
        for app in APPS:
            self.assertEqual(self.module['xdg']['configFile'][app],
                             {'source': str(self.checkout / 'dotfiles' / app)})
            self.assertTrue((self.config / app).is_symlink())
            self.assertEqual((self.config / app).resolve(), self.checkout / 'dotfiles' / app)
        self.assertEqual(set(self.module['home']['file']), {'.local/share/mihao-theme'})
        validate_targets(self.files)
        self.assertEqual(snapshot(self.checkout), self.before)

    def test_missing_generated_files_fail_checks_without_rewriting_configs(self):
        # Cover both a fresh deployment and cache loss after manual init.
        for initialized in (False, True):
            with self.subTest(initialized=initialized):
                if initialized:
                    self.init()
                    shutil.rmtree(self.cache / 'theme/generated')
                with patch.dict(os.environ, self.env, clear=True):
                    engine = Engine()
                    for app in ('kitty', 'fuzzel', 'dunst'):
                        with self.assertRaises(ThemeError):
                            integration.check(app, engine.output(app))
                self.assertEqual(snapshot(self.checkout), self.before)

    @unittest.skipUnless(shutil.which('fuzzel') and shutil.which('dunst'),
                         'Fuzzel/Dunst unavailable')
    def test_native_missing_colors_refuse_fuzzel_and_keep_kitty_dunst_preferences(self):
        r = self.command(['fuzzel', '--check-config', '--config',
                          str(self.config / 'fuzzel/fuzzel.ini')])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('failed to open', r.stderr)
        self.assertIn('No such file or directory', r.stderr)
        r = self.command(['kitty', '+runpy',
                          'import sys; from kitty.config import load_config; '
                          'c=load_config(sys.argv[1]); assert c.font_size == 12; '
                          'assert c.background_opacity == .85; '
                          'assert c.font_family == "JetBrainsMono Nerd Font"',
                          str(self.config / 'kitty/kitty.conf')])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('Could not find included config file', r.stderr)
        r = self.command(['dunst', '--verbosity', 'debug'])
        output = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Couldn't initialize X11 output", output)
        self.assertIn('Cannot open', output)
        self.assertIn('Trying to set font to 0xProto Nerd Font 11', output)
        for rule in ('volume', 'brightness'):
            self.assertIn(f"Creating new rule '{rule}'", output)
        self.assertEqual(snapshot(self.checkout), self.before)

    def test_ownership_guard_rejects_nested_files_force_and_recursion(self):
        bad = dict(self.files)
        bad[self.config / 'fuzzel/fuzzel.ini'] = {'source': '/unused'}
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            validate_targets(bad)
        for key in ('force', 'recursive'):
            bad = dict(self.files)
            bad[self.config / 'fuzzel'] = {'source': '/unused', key: True}
            with self.assertRaisesRegex(ValueError, 'forbidden'):
                validate_targets(bad)

    def test_manual_init_and_repeated_install_do_not_replace_original_configs(self):
        self.init()
        self.assert_checkout_preserved(self.before)
        self.assert_repeated_install_preserves_checkout(self.before)
        for p in self.files:
            self.assertTrue(p.is_symlink())
            p.resolve(strict=True)
        with patch.dict(os.environ, self.env, clear=True):
            engine = Engine()
            for app in ('kitty', 'fuzzel', 'dunst'):
                self.assertTrue(integration.check(app, engine.output(app)))
        for p in self.checkout.rglob('*'):
            if p.is_symlink():
                p.resolve(strict=True)

    def assert_repeated_install_preserves_checkout(self, before):
        helper = cached_hm_helper('link', 'targetPath="$HOME/$relativePath"')
        cleanup = cached_hm_helper('cleanup', 'homeFilePattern=')
        if not helper or not cleanup:
            self.skipTest('cached Home Manager link/cleanup helpers unavailable')
        sources = [str(self.generation / p.relative_to(self.home)) for p in self.files]
        for _ in range(2):
            r = self.command(['bash', str(cleanup), str(self.generation),
                              *[str(p.relative_to(self.home)) for p in self.files]])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = self.command(['bash', str(helper), str(self.generation), *sources])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assert_checkout_preserved(before)

    def test_negative_control_file_migration_can_create_source_symlink_loop(self):
        helper = cached_hm_helper('link', 'targetPath="$HOME/$relativePath"')
        if not helper:
            self.skipTest('cached Home Manager link helper unavailable')
        # Existing symlink configs are legal under a directory-owned desktop.
        main = self.checkout / 'dotfiles/fuzzel/fuzzel.ini'
        original = main.read_bytes()
        main.rename(main.with_name('custom.ini'))
        main.symlink_to('custom.ini')
        broken = self.root / 'broken-generation/home-files'
        source = broken / self.config.relative_to(self.home) / 'fuzzel/fuzzel.ini'
        source.parent.mkdir(parents=True)
        source.symlink_to(main)
        r = self.command(['bash', str(helper), str(broken), str(source)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with self.assertRaises((OSError, RuntimeError)):
            main.resolve(strict=True)
        self.assertEqual(main.with_name('custom.ini').read_bytes(), original)

    def assert_kitty_preferences_match_baseline(self):
        base = self.root / 'baseline-kitty'
        base.mkdir()
        for rel in git_paths('dotfiles/kitty', revision='HEAD'):
            destination = base / rel.relative_to('dotfiles/kitty')
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(baseline(rel.as_posix()))
        script = '''import json,sys
from kitty.config import load_config
errors=[]
a=load_config(sys.argv[1],accumulate_bad_lines=errors)
b=load_config(sys.argv[2],accumulate_bad_lines=errors)
ignore=set(json.loads(sys.argv[3])) | {'config_paths','all_config_paths'}
differences={k:[repr(v),repr(getattr(b,k))] for k,v in a._asdict().items()
             if k not in ignore and v != getattr(b,k)}
print(json.dumps({'differences':differences,'errors':[str(e) for e in errors],
                  'background':b.background.as_sharp, 'foreground':b.foreground.as_sharp}))
'''
        r = self.command(['kitty', '+runpy', script, str(base / 'kitty.conf'),
                          str(self.config / 'kitty/kitty.conf'), json.dumps(sorted(adapters.KITTY_KEYS))])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = json.loads(r.stdout)
        self.assertFalse(data['errors'])
        self.assertEqual(data['differences'], {})
        default = read_toml(REPO / 'scripts/theming/default.toml')
        self.assertEqual(data['background'], default['terminal']['background'])
        self.assertEqual(data['foreground'], default['terminal']['foreground'])

    def test_native_kitty_effective_all_noncolor_preferences_equal_baseline(self):
        self.init()
        self.assert_kitty_preferences_match_baseline()
        self.assertEqual(snapshot(self.checkout), self.before)

    def test_init_preserves_preexisting_backups_and_creates_none(self):
        for rel in ('kitty/kitty.conf.backup', 'kitty/Adapta Nokto Maia.conf.backup',
                    'kitty/Belafonte Day.conf.backup', 'fuzzel/fuzzel.ini.backup',
                    'dunst/dunstrc.backup'):
            with (self.checkout / 'dotfiles' / rel).open('xb') as backup:
                backup.write(b'original backup: ' + rel.encode())
        # Preserve backup link identity as well as regular backup contents.
        (self.checkout / 'dotfiles/kitty/current-theme.conf.backup').symlink_to(
            'Adapta Nokto Maia.conf')
        # These files predate the tested operations, unlike unexpected new ones.
        before = snapshot(self.checkout)
        self.assertTrue(backups(before))
        for _ in range(2):
            self.init()
            self.assert_checkout_preserved(before)
        self.assert_kitty_preferences_match_baseline()
        self.assert_checkout_preserved(before)
        self.assert_repeated_install_preserves_checkout(before)

    @unittest.skipUnless(shutil.which('fuzzel'), 'Fuzzel unavailable')
    def test_native_fuzzel_consumes_colors_and_preserves_entire_layout(self):
        self.init()
        main = self.config / 'fuzzel/fuzzel.ini'
        original = app_ini(baseline('dotfiles/fuzzel/fuzzel.ini').decode(), main=True)
        actual = app_ini(main.read_text(), main=True)
        original['main'].pop('include')
        actual['main'].pop('include')
        self.assertEqual(actual, original)
        r = self.command(['fuzzel', '--check-config', '--config', str(main)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # Prove the native parser really consumes the runtime include.
        output = self.cache / 'theme/generated/fuzzel.ini'
        output.write_text('[colors]\nborder=not-a-color\n')
        r = self.command(['fuzzel', '--check-config', '--config', str(main)])
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(snapshot(self.checkout), self.before)

    @unittest.skipUnless(shutil.which('dunst'), 'Dunst unavailable')
    def test_native_dunst_discovers_dropin_and_preserves_rules(self):
        self.init()
        r = self.command(['dunst', '--verbosity', 'debug'])
        output = r.stdout + r.stderr
        # Dunst has no check-config mode. It parses before trying the explicitly
        # disconnected display. A backend failure is expected, not a daemon test.
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('Couldn\'t initialize X11 output', output)
        self.assertIn("Reading config file '" + str(self.config / 'dunst/dunstrc') + "'", output)
        self.assertIn("Reading config file '" + str(self.config / 'dunst/dunstrc.d/99-theme.conf') + "'", output)
        colors = app_ini((self.cache / 'theme/generated/dunst.conf').read_text())
        for section, settings in colors.items():
            for key, value in settings.items():
                if key == 'separator_color':
                    self.assertIn(f'[{section}] Trying to set {key} to {value.strip(chr(34))}', output)
                else:
                    self.assertIn(f"Adding rule '{key} = {value.strip(chr(34))}' to special section {section}", output)
        for rule in ('volume', 'brightness'):
            self.assertIn(f"Creating new rule '{rule}'", output)
            self.assertIn(f"Adding rule 'set_stack_tag = {rule}' to section {rule}", output)
            self.assertIn(f"Adding rule 'timeout = 1' to section {rule}", output)
        self.assertIn('Trying to set font to 0xProto Nerd Font 11', output)
        self.assertIn('Trying to set width to (220, 360)', output)
        self.assertNotIn('Unknown', output)
        self.assertNotIn('Invalid', output)
        self.assertEqual(snapshot(self.checkout), self.before)

    @unittest.skipUnless(Path('/run/current-system/sw/bin/Hyprland').is_file(),
                         'unwrapped Hyprland verifier unavailable')
    def test_native_hyprland_lua_verifier_with_fallback_and_runtime_gradient(self):
        self.init()
        main = self.config / 'hypr/hyprland.lua'
        default = read_toml(REPO / 'scripts/theming/default.toml')
        for mode in ('solid', 'gradient', 'fallback'):
            with self.subTest(mode=mode):
                auxiliary = self.cache / 'theme/generated/hyprland.lua'
                if mode == 'gradient':
                    _, values, _ = adapters.render('hyprland', default, self.root / 'theme.toml',
                        {'source': 'universal', 'active_border': {'colors': ['primary', 'secondary'], 'angle': 45}})
                    auxiliary.write_text(adapters.hypr_lua(values))
                elif mode == 'fallback':
                    auxiliary.unlink()
                r = self.command(['/run/current-system/sw/bin/Hyprland', '--verify-config',
                                  '--config', str(main)])
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn('config ok', r.stdout)
        self.assertEqual(snapshot(self.checkout), self.before)

    def test_include_checker_reports_recursive_includes_and_symlink_loops(self):
        self.init()
        with patch.dict(os.environ, self.env, clear=True):
            main = self.config / 'fuzzel/fuzzel.ini'
            main.write_text('include=' + str(main) + '\n')
            with self.assertRaisesRegex(ThemeError, 'recursive'):
                integration.included_paths(main, 'fuzzel')
            main.unlink()
            main.symlink_to(main)
            with self.assertRaisesRegex(ThemeError, 'cannot resolve'):
                integration.included_paths(main, 'fuzzel')

    def test_reselection_restores_saved_overrides_in_consumed_configs(self):
        self.init()
        definition = self.root / 'wallpaper.toml'
        definition.write_text(dumps(read_toml(REPO / 'scripts/theming/default.toml')))
        image = self.root / 'wallpaper.png'
        image.write_bytes(b'wallpaper is mocked, no decoder or live wallpaper action')
        entry = dict(name='Recovery test', path=str(image), theme=str(definition), explicit=True)
        saved = self.root / 'saved kitty colors.conf'
        saved.write_text('background #123456\nfont_size 90\n')
        temporary = self.root / 'temporary kitty colors.conf'
        temporary.write_text('background #abcdef\n')

        def effective_background():
            r = self.command(['kitty', '+runpy',
                'import sys; from kitty.config import load_config; '
                'c=load_config(sys.argv[1]); assert c.font_size == 12; '
                'assert c.background_opacity == .85; print(c.background.as_sharp)',
                str(self.config / 'kitty/kitty.conf')])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            return r.stdout.strip()

        def stage(app, output, values):
            # Exercise installation and native consumption; runtime delivery is
            # explicitly simulated to avoid all signals, IPC and wallpaper work.
            integration.check(app, output)
            if app == 'fuzzel':
                r = self.command(['fuzzel', '--check-config', '--config',
                                  str(self.config / 'fuzzel/fuzzel.ini')])
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            return 'fixture: native includes checked; runtime delivery simulated'

        with patch.dict(os.environ, self.env, clear=True), \
             patch.object(adapters, 'live', side_effect=stage), \
             patch.object(Engine, 'wallpaper') as wallpaper:
            engine = Engine()
            self.assertFalse(engine.apply(entry))
            self.assertFalse(engine.app('kitty', {'source': 'file', 'path': str(saved)}, save=True))
            self.assertEqual(effective_background(), '#123456')
            self.assertFalse(engine.app('kitty', {'source': 'file', 'path': str(temporary)}))
            self.assertEqual(effective_background(), '#abcdef')
            self.assertFalse(engine.app('fuzzel', {'source': 'partial', 'colors': {'border': '#123456'}}))
            self.assertFalse(engine.app('dunst', {'source': 'partial', 'colors': {'global.frame_color': '#123456'}}))
            self.assertEqual(set(engine.state()['temporary']), {'kitty', 'fuzzel', 'dunst'})
            self.assertFalse(engine.apply(entry))
            self.assertEqual(effective_background(), '#123456')
            self.assertEqual(engine.state()['temporary'], {})
            self.assertEqual(read_toml(definition)['apps']['kitty']['path'], str(saved))
            self.assertNotIn('123456', engine.output('fuzzel').read_text())
            self.assertNotIn('123456', engine.output('dunst').read_text())
            self.assertEqual(wallpaper.call_count, 2)
        self.assertEqual(snapshot(self.checkout), self.before)


if __name__ == '__main__':
    unittest.main()
