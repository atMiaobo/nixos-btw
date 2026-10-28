"""Matugen extraction without templates/hooks, plus readable terminal defaults."""
from __future__ import annotations
import colorsys
import json
from pathlib import Path
import subprocess
import tempfile

from .model import ANSI, ThemeError, color, validate


def run(command: list[str], *, allowed_codes=(0,), **kwargs) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=45, **kwargs)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ThemeError(f'{command[0]}: {exc}') from exc
    if result.returncode not in allowed_codes:
        raise ThemeError(f'{command[0]} exited {result.returncode}: {result.stderr.strip() or result.stdout.strip()}')
    return result.stdout


def rgb(value):
    return tuple(int(value[i:i+2], 16) / 255 for i in (1, 3, 5))


def hexcolor(values):
    return '#' + ''.join(f'{round(max(0, min(1, c)) * 255):02x}' for c in values)


def luminance(c):
    return sum(v * w for v, w in zip((x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in rgb(c)), (.2126, .7152, .0722)))


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + .05) / (lo + .05)


def readable(c, bg, minimum=4.5):
    target = '#ffffff' if luminance(bg) < .35 else '#000000'
    for i in range(101):
        t = i / 100
        candidate = hexcolor(tuple(x * (1-t) + y*t for x, y in zip(rgb(c), rgb(target))))
        if contrast(candidate, bg) >= minimum:
            return candidate
    return target


def terminal_palette(ui, mode='dark'):
    bg = ui['background']
    fg = readable(ui['foreground'], bg)
    terminal = dict(background=bg, foreground=fg, cursor=readable(ui['primary'], bg),
                    selection_bg=ui['surface_alt'], selection_fg=readable(fg, ui['surface_alt']))
    # Semantic terminal hues stay recognizable; the wallpaper subtly sets saturation.
    _, saturation, _ = colorsys.rgb_to_hsv(*rgb(ui['primary']))
    sat = .38 + min(saturation, .7) * .25
    hues = dict(red=.0, green=.34, yellow=.13, blue=.61, magenta=.80, cyan=.50)
    ansi = dict(black=ui['surface'], white=fg, bright_black=readable(ui['muted'], bg, 3), bright_white=fg)
    for name, hue in hues.items():
        ansi[name] = readable(hexcolor(colorsys.hls_to_rgb(hue, .72 if mode == 'dark' else .32, sat)), bg)
        ansi['bright_' + name] = readable(hexcolor(colorsys.hls_to_rgb(hue, .82 if mode == 'dark' else .24, sat)), bg)
    return terminal, {key: ansi[key] for key in ANSI}


def webp_frame(wallpaper: Path, target: Path) -> Path:
    """Extract an ANMF bitstream without requiring ffmpeg's animated WebP decoder.

    A cropped first animation frame is sufficient for palette sampling. awww
    always receives the original animation. Static WebP is used directly.
    """
    with wallpaper.open('rb') as stream:
        header = stream.read(12)
        if len(header) != 12 or header[:4] != b'RIFF' or header[8:] != b'WEBP':
            raise ThemeError(f'Invalid WebP header: {wallpaper}')
        limit = int.from_bytes(header[4:8], 'little') + 8
        if limit > wallpaper.stat().st_size:
            raise ThemeError(f'Truncated WebP: {wallpaper}')
        while stream.tell() + 8 <= limit:
            chunk = stream.read(8)
            length = int.from_bytes(chunk[4:], 'little')
            if stream.tell() + length > limit:
                raise ThemeError(f'Truncated WebP chunk: {wallpaper}')
            if chunk[:4] == b'ANMF':
                frame = stream.read(length)
                if len(frame) < 24:
                    raise ThemeError(f'Invalid WebP animation frame: {wallpaper}')
                # Extended static WebP header preserves alpha and frame dimensions.
                width = frame[6:9]
                height = frame[9:12]
                payload = frame[16:]
                if payload[:4] == b'ALPH':
                    payload = b'VP8X' + (10).to_bytes(4, 'little') + bytes([16, 0, 0, 0]) + width + height + payload
                target.write_bytes(b'RIFF' + (len(payload) + 4).to_bytes(4, 'little') + b'WEBP' + payload)
                return target
            stream.seek(length + (length % 2), 1)
    return wallpaper


def generate(wallpaper: Path, name: str, mode='dark') -> dict:
    if not wallpaper.is_file():
        raise ThemeError(f'Wallpaper not found: {wallpaper}')
    with tempfile.TemporaryDirectory(prefix='mihao-palette-') as tmp:
        root = Path(tmp)
        config = root / 'matugen.toml'
        config.write_text('[config]\n[templates]\n')
        image = wallpaper
        # awww still receives the original animated image, never this extraction.
        if wallpaper.suffix.lower() == '.webp':
            image = webp_frame(wallpaper, root / 'preview.webp')
        elif wallpaper.suffix.lower() in ('.gif', '.mp4', '.mkv', '.webm', '.mov'):
            image = root / 'preview.png'
            run(['ffmpeg', '-v', 'error', '-i', str(wallpaper), '-frames:v', '1', '-y', str(image)])
        output = run(['matugen', '--config', str(config), '--dry-run', '--json', 'hex', '--mode', mode, '--source-color-index', '0', 'image', str(image)])
        try:
            raw = json.loads(output)
            colors = raw['colors']
            # Matugen 4's default JSON has {colors: {dark: {role: hex}}}.
            if mode in colors:
                colors = colors[mode]
            def get(key):
                v = colors[key]
                if isinstance(v, dict):
                    v = v.get(mode, v.get('default', v))
                    if isinstance(v, dict):
                        v = v.get('hex', v.get('color'))
                return color(v, f'matugen.{key}')
            ui = dict(background=get('background'), surface=get('surface_container'),
                      surface_alt=get('surface_container_high'), foreground=get('on_surface'),
                      muted=get('on_surface_variant'), primary=get('primary'), secondary=get('secondary'),
                      border=get('outline'), error=get('error'), success='#a6da95' if mode == 'dark' else '#27632a',
                      warning='#eed49f' if mode == 'dark' else '#795900')
        except (KeyError, TypeError, ValueError) as exc:
            raise ThemeError(f'Unsupported Matugen JSON: {exc}') from exc
    terminal, ansi = terminal_palette(ui, mode)
    return validate(dict(meta=dict(name=name, mode=mode, schema=1), ui=ui, terminal=terminal, ansi=ansi), wallpaper)
