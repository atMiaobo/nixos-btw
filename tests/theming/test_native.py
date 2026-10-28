"""Non-activating native checks; every writable path is under a temporary HOME."""
import json
from copy import deepcopy
import os
from pathlib import Path
import shutil
import struct
import subprocess
import threading
import time
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from theming.adapters import KITTY_KEYS, kitty_file, render
from theming.model import ThemeError, dumps, read_toml
from theming.palette import generate, run, webp_frame

KITTY_CACHE = Path(os.environ.get('XDG_CACHE_HOME', Path.home()/'.cache'))/'kitty/kitty-themes.zip'


def png(path):
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind+data))
    pixels = b''.join(b'\0' + bytes([45+y*3, 80+y*2, 140+y])*32 for y in range(32))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B',32,32,8,2,0,0,0)) + chunk(b'IDAT',zlib.compress(pixels)) + chunk(b'IEND',b''))


@unittest.skipUnless(shutil.which('kitty') and shutil.which('matugen'), 'native Kitty/Matugen unavailable')
class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='theme-native-test-')
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, dict(HOME=self.tmp.name, XDG_CONFIG_HOME=self.tmp.name+'/config', XDG_CACHE_HOME=self.tmp.name+'/cache', XDG_STATE_HOME=self.tmp.name+'/state', TMPDIR=self.tmp.name))
        self.env.start()
        self.image = self.root/'color sample.png'
        png(self.image)
        self.default = read_toml(Path(__file__).resolve().parents[2]/'scripts/theming/default.toml')

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_real_matugen_noninteractive_generation(self):
        data = generate(self.image,'Native sample')
        self.assertTrue(data['ui']['primary'].startswith('#'))
        for app in ('kitty','quickshell','fuzzel','dunst','hyprland'):
            self.assertTrue(render(app,data,self.root/'theme.toml')[0])
        self.assertEqual({p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file()}, {'color sample.png'})

    def test_native_kitty_rejects_invalid_named_color(self):
        conf = self.root/'bad.conf'
        conf.write_text('background wrongcolor\n')
        with self.assertRaises(ThemeError):
            render('kitty',self.default,self.root/'theme.toml',{'source':'file','path':str(conf)})

    @unittest.skipUnless(KITTY_CACHE.is_file(), 'no local Kitty theme archive')
    def test_real_offline_preset_dump_without_config_mutation(self):
        cache = self.root/'cache/kitty'
        cache.mkdir(parents=True)
        shutil.copyfile(KITTY_CACHE,cache/'kitty-themes.zip')
        text,_,_=render('kitty',self.default,self.root/'theme.toml',{'source':'preset','name':'Tokyo Night'})
        self.assertIn('background #1a1b26',text)
        self.assertFalse((self.root/'config/kitty/kitty.conf').exists())
        self.assertFalse((self.root/'config/kitty/current-theme.conf').exists())

    @unittest.skipUnless(KITTY_CACHE.is_file(), 'no local Kitty theme archive')
    def test_cached_native_preset_color_syntax(self):
        # Check the entire archive with one native parser process. No GUI/reload.
        themes = {}
        with zipfile.ZipFile(KITTY_CACHE) as archive:
            for name in archive.namelist():
                if '/themes/' in name and name.endswith('.conf'):
                    values=kitty_file(archive.read(name).decode(),[],allow_empty=True)
                    themes[name]='\n'.join(f'{k} {v}' for k,v in values.items())
        script = ('import json,sys; from kitty.config import parse_config; errors={}; '
                  'themes=json.load(sys.stdin); '
                  '\nfor name,text in themes.items():\n e=[]; parse_config(text.splitlines(),accumulate_bad_lines=e); '
                  '\n if e: errors[name]=[str(x) for x in e]\n'
                  'print(json.dumps(errors))')
        errors=json.loads(run(['kitty','+runpy',script],input=json.dumps(themes)))
        self.assertGreater(len(themes) - len(errors),390)
        # The local upstream archive has several #RRGGBBAA values rejected by
        # this installed Kitty version. They must be reported, never replaced.
        self.assertTrue(all('Invalid color' in ' '.join(e) for e in errors.values()))

    def test_native_kitty_effective_include_preserves_preferences(self):
        repo = Path(__file__).resolve().parents[2]
        directory = self.root/'config/kitty'
        directory.mkdir(parents=True)
        shutil.copyfile(repo/'dotfiles/kitty/kitty.conf', directory/'kitty.conf')
        runtime = self.root/'cache/theme/generated/kitty.conf'
        runtime.parent.mkdir(parents=True)
        runtime.write_text(render('kitty', self.default, self.root/'theme.toml')[0])
        link = self.root/'HM store link'
        link.symlink_to(runtime)
        bridge = self.root/'.local/share/mihao-theme'
        bridge.parent.mkdir(parents=True)
        bridge.symlink_to(runtime.parent)
        script = ('import json,sys; from kitty.config import load_config; '
                  'errors=[]; c=load_config(sys.argv[1],accumulate_bad_lines=errors); '
                  'print(json.dumps(dict(background=c.background.as_sharp,foreground=c.foreground.as_sharp, '
                  'font_size=c.font_size,opacity=c.background_opacity,errors=[str(e) for e in errors])))')
        result = json.loads(run(['kitty', '+runpy', script, str(directory/'kitty.conf')]))
        self.assertFalse(result['errors'])
        self.assertEqual(result['background'], self.default['terminal']['background'])
        self.assertEqual(result['foreground'], self.default['terminal']['foreground'])
        self.assertEqual(result['font_size'], 12)
        self.assertEqual(result['opacity'], .85)

    def test_distinct_kitty_themes_change_native_effective_palette(self):
        directory = self.root/'config/kitty'
        directory.mkdir(parents=True)
        main = directory/'kitty.conf'
        repo = Path(__file__).resolve().parents[2]
        shutil.copyfile(repo/'dotfiles/kitty/kitty.conf', main)
        runtime = self.root/'cache/theme/generated/kitty.conf'
        runtime.parent.mkdir(parents=True)
        bridge = self.root/'.local/share/mihao-theme'
        bridge.parent.mkdir(parents=True)
        bridge.symlink_to(runtime.parent)
        script = '''import json,sys
sys.path.insert(0, sys.argv[1])
from theming.kitty_runtime import verify_effective
from kitty.config import load_config
verify_effective(sys.argv[2], sys.argv[3])
c=load_config(sys.argv[2])
print(json.dumps(dict(background=c.background.as_sharp, foreground=c.foreground.as_sharp,
                     color1=c.color1.as_sharp, font_size=c.font_size, opacity=c.background_opacity)))
'''
        appearances = []
        for bg, fg, red in (('#152535', '#e0e1e2', '#ff4567'),
                            ('#fff3da', '#182838', '#a01020'),
                            ('#352040', '#f1e2d3', '#f08090')):
            data = deepcopy(self.default)
            data['terminal'].update(background=bg, foreground=fg)
            data['ansi']['red'] = red
            runtime.write_text(render('kitty', data, self.root/'theme.toml')[0])
            result = json.loads(run(['kitty', '+runpy', script, str(repo/'scripts'), str(main), str(runtime)]))
            self.assertEqual((result['background'], result['foreground'], result['color1']), (bg, fg, red))
            self.assertEqual((result['font_size'], result['opacity']), (12, .85))
            appearances.append(result)
        self.assertEqual(len({x['background'] for x in appearances}), 3)
        # The previous include-only check accepted a later override. The native
        # verifier must reject it before sending any runtime signal.
        main.write_text(main.read_text() + '\nbackground #000000\n')
        with self.assertRaisesRegex(ThemeError, 'effective palette differs.*background'):
            run(['kitty', '+runpy', script, str(repo/'scripts'), str(main), str(runtime)])

        main.write_text(main.read_text().removesuffix('\nbackground #000000\n'))
        script = script.replace('verify_effective(sys.argv[2], sys.argv[3])',
            'verify_effective(sys.argv[2], sys.argv[3], overrides=["background=black"])')
        with self.assertRaisesRegex(ThemeError, 'command-line overrides'):
            run(['kitty', '+runpy', script, str(repo/'scripts'), str(main), str(runtime)])

    def test_actual_kitty_adapter_helper_with_all_runtime_delivery_mocked(self):
        from theming import adapters
        repo = Path(__file__).resolve().parents[2]
        directory = self.root/'config/kitty'
        directory.mkdir(parents=True)
        shutil.copyfile(repo/'dotfiles/kitty/kitty.conf', directory/'kitty.conf')
        output = self.root/'cache/theme/generated/kitty.conf'
        output.parent.mkdir(parents=True)
        bridge = self.root/'.local/share/mihao-theme'
        bridge.parent.mkdir(parents=True)
        bridge.symlink_to(output.parent)
        text, values, _ = render('kitty', self.default, self.root/'theme.toml')
        output.write_text(text)

        gui = False

        def native_without_signals(command, **kwargs):
            self.assertEqual(command[:2], ['kitty', '+runpy'])
            # Run the exact adapter entrypoint and native config validation,
            # with no visible processes and a guard against any real signal.
            prelude = ('import os,signal; from unittest.mock import patch; '
                'signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGUSR1}); '
                f'patch("kitty.utils.get_all_processes", return_value={"[os.getpid()]" if gui else "[]"}).start(); '
                'patch("kitty.child.cmdline_of_pid", return_value=["kitty", "-o", "font_size=23"]).start(); '
                'patch("os.kill").start(); ')
            return run(command[:2] + [prelude + command[2]] + command[3:], **kwargs)

        with patch.object(adapters, 'run', side_effect=native_without_signals):
            status = adapters.live('kitty', output, values)
        self.assertIn('effective palette verified', status)
        self.assertIn('staged for next Kitty launch', status)
        # Run the same entrypoint with an actual blocked native signal mask in
        # this disposable child; os.kill is still entirely mocked.
        gui = True
        with patch.object(adapters, 'run', side_effect=native_without_signals):
            status = adapters.live('kitty', output, values)
        self.assertIn('SIGUSR1 delivered to PIDs', status)

    def test_kitty_native_discovery_detects_alternate_config_directory(self):
        repo = Path(__file__).resolve().parents[2]
        runtime = self.root/'colors.conf'
        runtime.write_text(render('kitty', self.default, self.root/'theme.toml')[0])
        alternate = self.root/'alternate'
        alternate.mkdir()
        (alternate/'kitty.conf').write_text('background #abcdef\n')
        script = ('import sys; sys.path.insert(0,sys.argv[1]); '
                  'from theming.kitty_runtime import verify_effective; verify_effective(sys.argv[2],sys.argv[3])')
        with patch.dict(os.environ, KITTY_CONFIG_DIRECTORY=str(alternate)):
            with self.assertRaisesRegex(ThemeError, 'effective palette differs'):
                run(['kitty', '+runpy', script, str(repo/'scripts'), 'default/kitty.conf', str(runtime)])

    @unittest.skipUnless(shutil.which('fuzzel'), 'Fuzzel unavailable')
    def test_native_fuzzel_effective_include_and_rgba_syntax(self):
        repo = Path(__file__).resolve().parents[2]
        directory = self.root/'config/fuzzel'
        directory.mkdir(parents=True)
        main = directory/'fuzzel.ini'
        # Native tilde expansion uses HOME, independent of XDG_CONFIG_HOME.
        fixture_dir = self.root/'.local/share/mihao-theme'
        fixture_dir.mkdir(parents=True)
        runtime = self.root/'colors with spaces.ini'
        runtime.write_text(render('fuzzel', self.default, self.root/'theme.toml')[0])
        (fixture_dir/'fuzzel.ini').symlink_to(runtime)
        shutil.copyfile(repo/'dotfiles/fuzzel/fuzzel.ini', main)
        self.assertEqual(run(['fuzzel', '--check-config', '--config', str(main)]), '')
        runtime.write_text('[colors]\nbackground=not-a-color\n')
        with self.assertRaises(ThemeError):
            run(['fuzzel', '--check-config', '--config', str(main)])

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg unavailable')
    def test_animated_webp_first_frame_native_decode(self):
        static = self.root/'static.webp'
        run(['ffmpeg','-v','error','-i',str(self.image),'-frames:v','1',str(static)])
        raw = static.read_bytes()
        cursor=12
        payload=b''
        while cursor+8 <= len(raw):
            size=int.from_bytes(raw[cursor+4:cursor+8],'little')
            if raw[cursor:cursor+4] in (b'ALPH',b'VP8 ',b'VP8L'):
                payload+=raw[cursor:cursor+8+size+(size%2)]
            cursor+=8+size+(size%2)
        frame=bytes(6)+(31).to_bytes(3,'little')*2+bytes(4)+payload
        content=b'ANMF'+len(frame).to_bytes(4,'little')+frame
        animated=self.root/'animated.webp'
        animated.write_bytes(b'RIFF'+(len(content)+4).to_bytes(4,'little')+b'WEBP'+content)
        data=generate(animated,'Animated sample')
        self.assertTrue(data['ui']['primary'].startswith('#'))

    @unittest.skipUnless(shutil.which('qs'), 'Quickshell unavailable')
    def test_theme_store_atomic_watch_without_desktop(self):
        root = self.root
        (root/'run').mkdir(mode=0o700)
        source = Path(__file__).resolve().parents[2]/'dotfiles/quickshell/shared/ThemeStore.qml'
        shutil.copyfile(source,root/'ThemeStore.qml')
        active=root/'cache/theme/active.json'
        active.parent.mkdir(parents=True)
        def write(value):
            temporary=active.with_suffix('.tmp')
            temporary.write_text(json.dumps({'colors': {'primary':value,'accent':value}}))
            temporary.replace(active)
        write('#123456')
        (root/'shell.qml').write_text('''import Quickshell
import QtQuick
Scope {
  ThemeStore { id: store }
  property int ticks: 0
  Timer {
    interval: 250; running: true; repeat: true
    onTriggered: {
      console.log("THEME_PRIMARY", store.primary)
      ticks += 1
      if (ticks >= 14) Qt.quit()
    }
  }
}
''')
        env=dict(os.environ,XDG_RUNTIME_DIR=str(root/'run'),MIHAO_THEME_CACHE=str(root/'cache/theme'),QT_QPA_PLATFORM='offscreen',QML_DISABLE_DISK_CACHE='1')
        for key in ('DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS'):
            env.pop(key,None)
        def updates():
            time.sleep(.8); write('#abcdef')
            time.sleep(.8); active.write_text('{invalid')
            time.sleep(.8); write('#fedcba')
        thread=threading.Thread(target=updates)
        thread.start()
        try:
            result=subprocess.run(['qs','--no-color','-p',str(root/'shell.qml')],env=env,capture_output=True,text=True,timeout=10)
        finally:
            thread.join()
        output=result.stdout+result.stderr
        self.assertEqual(result.returncode,0,output)
        for value in ('#123456','#abcdef','#fedcba'):
            self.assertIn('THEME_PRIMARY '+value,output)
        self.assertIn('Failed to read active theme',output)
        self.assertNotIn('THEME_PRIMARY #c6a0f6',output)



if __name__ == '__main__':
    unittest.main()
