"""Actual Kitty config and native theme edits, entirely in a disconnected fixture."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from desktop_fixture import REPO, deploy_desktop, snapshot
import test_native
sys.path.insert(0, str(REPO/'scripts'))
from theming import adapters, integration
from theming.engine import Engine
from theming.model import ThemeError, dumps, read_toml
from theming.palette import run


@unittest.skipUnless(shutil.which('kitty'), 'Kitty unavailable')
class WallpaperKitty(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='wallpaper-kitty-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root/'home'
        self.home.mkdir()
        self.config = self.home/'.config'
        self.cache = self.home/'.cache/theme'
        self.checkout, _, _ = deploy_desktop(self.home, self.config, self.cache)
        env = {k:v for k,v in os.environ.items() if not k.startswith(
            ('XDG_', 'MIHAO_', 'KITTY_', 'DISPLAY', 'WAYLAND_', 'DBUS_', 'HYPRLAND_'))}
        env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(self.config),
                   XDG_CACHE_HOME=str(self.home/'.cache'), XDG_STATE_HOME=str(self.home/'.local/state'),
                   XDG_CONFIG_DIRS=str(self.root/'empty-system-config'), TMPDIR=str(self.root),
                   PYTHONDONTWRITEBYTECODE='1')
        self.environment = patch.dict(os.environ, env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.engine = Engine()
        self.main = self.config/'kitty/kitty.conf'
        self.output = self.engine.output('kitty')
        self.output.parent.mkdir(parents=True)
        self.entries = []
        for name, bg in (('A', '#253b27'), ('B', '#293957')):
            theme = read_toml(REPO/'scripts/theming/default.toml')
            theme['meta']['name'] = name
            theme['terminal']['background'] = bg
            path = self.root/f'{name}.toml'
            path.write_text(dumps(theme))
            image = self.root/f'{name}.png'
            image.write_bytes(b'wallpaper delivery mocked')
            self.entries.append(dict(name=name, path=str(image), theme=str(path), explicit=True))
        self.deliveries = []

    def effective(self):
        # This is Kitty's real discovery/parser for a new window, with no GUI.
        script = '''import json,sys
sys.path.insert(0,sys.argv[1])
from theming.kitty_runtime import verify_effective
from kitty.config import load_config
from kitty.cli import default_config_paths
verify_effective(sys.argv[2],sys.argv[3])
c=load_config(*default_config_paths(()))
print(json.dumps(dict(background=c.background.as_sharp,foreground=c.foreground.as_sharp,
                     color1=c.color1.as_sharp,font_size=c.font_size,opacity=c.background_opacity)))
'''
        return json.loads(run(['kitty', '+runpy', script, str(REPO/'scripts'), str(self.main), str(self.output)]))

    def stage(self, app, output, values):
        integration.check(app, output)
        appearance = self.effective()
        self.deliveries.append(appearance)
        self.assertEqual((appearance['font_size'], appearance['opacity']), (12, .85))
        return 'native palette verified; existing-window delivery simulated'

    def apply(self, entry):
        self.assertFalse(self.engine.apply(entry, only='kitty'))
        return self.effective()

    def native_edit(self, name):
        # Explicitly disable reload and networking. Never signal a desktop.
        run(['kitten', 'themes', '--cache-age=-1', '--reload-in=none', '--', name])
        text = self.main.read_text()
        self.assertEqual(text.count('include ~/.local/share/mihao-theme/kitty.conf'), 1)
        self.assertLess(text.index('# END_KITTY_THEME'), text.index('include ~/.local/share/mihao-theme/kitty.conf'))

    @unittest.skipUnless(shutil.which('kitten') and test_native.KITTY_CACHE.is_file(), 'offline native presets unavailable')
    def test_native_theme_then_A_B_A_and_same_wallpaper_for_all_override_sources(self):
        archive = self.home/'.cache/kitty/kitty-themes.zip'
        archive.parent.mkdir(parents=True)
        shutil.copyfile(test_native.KITTY_CACHE, archive)
        custom = self.root/'saved colors.conf'
        # A deliberately sparse file must clear colors from native themes.
        custom.write_text('background #765432\nfont_size 99\nmap ctrl+a quit\n')
        choices = ({'source':'universal'}, {'source':'preset','name':'Belafonte Day'},
                   {'source':'file','path':str(custom)})
        with patch.object(Engine, 'wallpaper'), patch.object(adapters, 'live', side_effect=self.stage):
            for spec in choices:
                with self.subTest(source=spec):
                    a, b = self.entries
                    self.apply(a)
                    self.assertFalse(self.engine.kitty(spec, save=True))
                    expected_a = self.output.read_text()
                    a_bytes = Path(a['theme']).read_bytes()
                    expected_effective_a = self.effective()
                    self.native_edit('Adapta Nokto Maia')
                    # Native edits cannot remove or bypass the final bridge.
                    self.assertEqual(self.effective(), expected_effective_a)
                    self.apply(a)
                    self.assertEqual(self.output.read_text(), expected_a)
                    self.assertEqual(Path(a['theme']).read_bytes(), a_bytes)
                    expected_b = self.apply(b)
                    self.assertEqual(expected_b['background'], '#293957')
                    b_bytes = Path(b['theme']).read_bytes()
                    self.native_edit('Belafonte Day')
                    self.apply(a)
                    self.assertEqual(self.output.read_text(), expected_a)
                    self.assertEqual(self.effective(), expected_effective_a)
                    # Simulate stale generated output too; reselection rewrites it.
                    self.output.write_text('background #abcdef\n')
                    self.apply(a)
                    self.assertEqual(self.output.read_text(), expected_a)
                    self.assertEqual(Path(a['theme']).read_bytes(), a_bytes)
                    self.assertEqual(Path(b['theme']).read_bytes(), b_bytes)
                    self.assertNotIn('kitty', self.engine.state()['temporary'])
        self.assertEqual(len(self.deliveries), 18)
        # Native commands may change only their fixture config/theme/backup.
        self.assertTrue((self.config/'kitty').is_symlink())
        self.assertTrue((self.home/'.local/share/mihao-theme').is_symlink())
        self.assertEqual((self.checkout/'dotfiles/kitty/Belafonte Day.conf').read_bytes(),
                         (REPO/'dotfiles/kitty/Belafonte Day.conf').read_bytes())

    def test_symlinked_bridge_passes_and_missing_include_is_a_real_failure(self):
        before = snapshot(self.checkout)
        with patch.object(Engine, 'wallpaper'), patch.object(adapters, 'live', side_effect=self.stage):
            self.apply(self.entries[0])
        self.assertEqual(snapshot(self.checkout), before)
        self.assertEqual(integration.check('kitty', self.output), str(self.main))
        self.assertIn(self.output.resolve(), integration.included_paths(self.main, 'kitty'))
        original = self.main.read_text()
        self.main.write_text(original.replace('include ~/.local/share/mihao-theme/kitty.conf', '# bridge missing'))
        with self.assertRaisesRegex(ThemeError, 'does not consume'):
            integration.check('kitty', self.output)
        self.main.write_text(original)
        self.assertEqual(self.effective()['background'], '#253b27')

    def test_sparse_and_default_palettes_clear_all_native_color_settings(self):
        # Cover versions without a cached theme archive using a native-format
        # current-theme.conf containing colors often absent from sparse themes.
        native = self.config/'kitty/current-theme.conf'
        native.write_text('background #ff0000\nforeground #00ff00\ncolor1 #0000ff\n'
                          'color200 #123456\ncursor_trail_color #aabbcc\n')
        with patch.object(Engine, 'wallpaper'), patch.object(adapters, 'live', side_effect=self.stage):
            self.apply(self.entries[0])
            custom = self.root/'sparse.conf'
            custom.write_text('background #765432\n')
            self.assertFalse(self.engine.kitty({'source':'file', 'path':str(custom)}, save=True))
            effective = self.effective()
            self.assertEqual(effective['background'], '#765432')
            self.assertEqual(effective['foreground'], '#dddddd')
            self.assertEqual(effective['color1'], '#cc0403')
        self.assertIn('color200 none\n', self.output.read_text())
        self.assertIn('cursor_trail_color none\n', self.output.read_text())
        self.assertTrue(all(len(line.split(None, 1)) == 2 for line in self.output.read_text().splitlines()))

    def test_two_wallpapers_keep_independent_saved_file_overrides(self):
        snapshots = {}
        with patch.object(Engine, 'wallpaper'), patch.object(adapters, 'live', side_effect=self.stage):
            for entry, bg in zip(self.entries, ('#654321', '#123456')):
                self.apply(entry)
                custom = self.root / (entry['name'] + '-colors.conf')
                custom.write_text(f'background {bg}\n')
                self.assertFalse(self.engine.kitty({'source':'file', 'path':str(custom)}, save=True))
                snapshots[entry['name']] = (Path(entry['theme']).read_bytes(), self.output.read_text(), bg)
            for entry in (self.entries[0], self.entries[1], self.entries[0], self.entries[0]):
                saved, output, bg = snapshots[entry['name']]
                self.assertEqual(self.apply(entry)['background'], bg)
                self.assertEqual(self.output.read_text(), output)
                self.assertEqual(Path(entry['theme']).read_bytes(), saved)
