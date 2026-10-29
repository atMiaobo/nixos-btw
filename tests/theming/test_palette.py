"""Generation-only surface defaults; saved palettes and light roles are authoritative."""
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
from theming.adapters import render
from theming.engine import Engine
from theming.model import dumps, read_toml
from theming.palette import contrast, generate, oklab, rgb


# Measured from Matugen 4's default tonal-spot scheme, without templates/hooks.
SAMPLES = (
    ('#258a45', '#101510', '#1c211c', '#262b26', '#9bd4a0'),
    ('#306ec0', '#111318', '#1d2024', '#282a2f', '#a9c7ff'),
    ('#d47832', '#19120d', '#261e19', '#312823', '#ffb787'),
)


def matugen_colors(sample, mode):
    source, bg, surface, high, primary = sample
    return dict(source_color=source, background=bg, surface_container=surface,
                surface_container_high=high, primary=primary, secondary=primary,
                on_surface='#e1e4e0', on_surface_variant='#c1c9be', outline='#899384', error='#ffb4ab')


class PaletteGeneration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='palette-regression-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root / 'image.png'
        self.image.write_bytes(b'isolated mocked extraction')

    def generated(self, colors, mode='dark'):
        # Cover the current and legacy Matugen JSON nesting independently.
        data = {'colors': {mode: colors}} if mode == 'dark' else {
            'colors': {k: {mode: {'color': v}} for k, v in colors.items()}}
        with patch('theming.palette.run', return_value=json.dumps(data)):
            return generate(self.image, 'sample', mode)

    def assert_surfaces(self, theme, source):
        ui = theme['ui']
        _, a, b = oklab(source)
        for role in ('background', 'surface', 'surface_alt'):
            lightness, x, y = oklab(ui[role])
            self.assertGreaterEqual(lightness, .298)
            self.assertLessEqual(math.hypot(x, y), .052)
            # Same perceptual hue, allowing only sRGB rounding error.
            cosine = (a*x + b*y) / (math.hypot(a, b) * math.hypot(x, y))
            self.assertGreater(cosine, .99)
            for text in ('foreground', 'muted'):
                self.assertGreaterEqual(contrast(ui[text], ui[role]), 4.5)
            for accent in ('primary', 'secondary', 'success', 'warning', 'error'):
                self.assertGreaterEqual(contrast(ui[accent], ui[role]), 3)
        self.assertLess(oklab(ui['background'])[0], oklab(ui['surface'])[0])
        self.assertLess(oklab(ui['surface'])[0], oklab(ui['surface_alt'])[0])

    def test_contrasting_sources_make_distinct_readable_surfaces(self):
        themes = [self.generated(matugen_colors(s, 'dark')) for s in SAMPLES]
        for theme, sample in zip(themes, SAMPLES):
            self.assert_surfaces(theme, sample[0])
            self.assertGreater(contrast(theme['ui']['background'], '#000000'), 1.35)
        for role in ('background', 'surface', 'surface_alt'):
            for i, first in enumerate(themes):
                for second in themes[i+1:]:
                    distance = math.dist(rgb(first['ui'][role]), rgb(second['ui'][role])) * 255
                    self.assertGreater(distance, 25)

    def test_neutral_source_does_not_invent_saturation(self):
        colors = matugen_colors(SAMPLES[0], 'dark')
        colors['source_color'] = '#808080'
        theme = self.generated(colors)
        for role in ('background', 'surface', 'surface_alt'):
            self.assertLess(max(rgb(theme['ui'][role])) - min(rgb(theme['ui'][role])), .005)

    def test_generated_surfaces_reach_canonical_and_dashboard_alias_roles_unchanged(self):
        for sample in SAMPLES:
            theme = self.generated(matugen_colors(sample, 'dark'))
            text, _, _ = render('quickshell', theme, self.root/'theme.toml')
            colors = json.loads(text)['colors']
            for role, value in theme['ui'].items():
                self.assertEqual(colors[role], value)
            for alias, role in (('background_deep','background'), ('background_alt','surface'),
                                ('hover','surface'), ('surface_high','surface_alt'),
                                ('foreground_alt','foreground')):
                self.assertEqual(colors[alias], theme['ui'][role])

    def test_light_matugen_roles_are_exactly_preserved(self):
        colors = dict(source_color='#d47832', background='#fff8f5', surface_container='#fcebe2',
                      surface_container_high='#f6e5dc', on_surface='#221a15',
                      on_surface_variant='#52443c', primary='#8b4f24', secondary='#775744',
                      outline='#85746b', error='#ba1a1a')
        theme = self.generated(colors, 'light')
        mapping = dict(background='background', surface='surface_container', surface_alt='surface_container_high',
                       foreground='on_surface', muted='on_surface_variant', primary='primary', secondary='secondary',
                       border='outline', error='error')
        for role, key in mapping.items():
            self.assertEqual(theme['ui'][role], colors[key])
        for role in ('background', 'surface', 'surface_alt'):
            self.assertGreaterEqual(contrast(theme['ui']['foreground'], theme['ui'][role]), 4.5)

    def test_saved_light_dark_and_custom_quickshell_colors_are_never_transformed(self):
        for mode in ('light', 'dark'):
            data = read_toml(REPO / 'scripts/theming/default.toml')
            data['meta']['mode'] = mode
            data['ui'].update(background='#fff3db', surface='#f3e3c4', surface_alt='#e8d5ac')
            override = self.root / 'custom.json'
            override.write_text(json.dumps({'background':'#123456', 'surface':'#234567'}))
            data['apps'] = {'quickshell': {'source':'file', 'path':str(override)}}
            path = self.root / f'{mode}.toml'
            path.write_text(dumps(data))
            before = path.read_bytes()
            entry = dict(theme=str(path), path=str(self.image), name=mode, explicit=True)
            with patch.dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.root)), \
                 patch('theming.engine.generate', side_effect=AssertionError('saved theme regenerated')):
                loaded = Engine().load(entry)
                self.assertEqual(loaded, data)
                text, _, _ = render('quickshell', loaded, path)
            colors = json.loads(text)['colors']
            self.assertEqual(colors['background'], '#123456')
            self.assertEqual(colors['surface'], '#234567')
            self.assertEqual(colors['hover'], '#234567')
            self.assertEqual(path.read_bytes(), before)

    @unittest.skipUnless(shutil.which('matugen'), 'Matugen unavailable')
    def test_real_wallpaper_extraction_for_green_blue_warm_and_neutral(self):
        def chunk(kind, data):
            return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind+data))
        env = dict(HOME=str(self.root), XDG_CONFIG_HOME=str(self.root/'config'),
                   XDG_CACHE_HOME=str(self.root/'cache'), XDG_STATE_HOME=str(self.root/'state'), TMPDIR=str(self.root))
        with patch.dict(os.environ, env):
            for source in ('#258a45', '#306ec0', '#d47832', '#808080'):
                pixels = b''.join(b'\0' + bytes(round(v*255) for v in rgb(source))*32 for _ in range(32))
                self.image.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B',32,32,8,2,0,0,0))
                                       + chunk(b'IDAT',zlib.compress(pixels)) + chunk(b'IEND',b''))
                theme = generate(self.image, source)
                if source != '#808080':
                    self.assert_surfaces(theme, source)
                else:
                    _, a, b = oklab(theme['ui']['background'])
                    self.assertLess(math.hypot(a, b), .01)
