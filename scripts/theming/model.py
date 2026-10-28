"""Canonical schema, legacy import, atomic IO and deterministic associations."""
from __future__ import annotations

from datetime import date, datetime, time
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib


class ThemeError(Exception):
    pass


UI = 'background surface surface_alt foreground muted primary secondary border success warning error'.split()
TERMINAL = 'background foreground cursor selection_bg selection_fg'.split()
ANSI = 'black red green yellow blue magenta cyan white'.split()
ANSI += ['bright_' + c for c in ANSI[:]]
APPS = ('kitty', 'quickshell', 'fuzzel', 'dunst', 'hyprland')
HEX = re.compile(r'#[0-9a-fA-F]{6}\Z')


def atomic_write(path: Path, content: str, *, overwrite=True) -> None:
    if path.resolve().is_relative_to('/nix/store'):
        raise ThemeError(f'Refusing to write an immutable Nix store path: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(name, path)
        else:
            os.link(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_toml(path: Path) -> dict:
    try:
        with path.open('rb') as stream:
            return tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ThemeError(f'{path}: {exc}') from exc


def dumps(data: dict) -> str:
    """Small deterministic TOML writer; no executable/interpolated theme values."""
    lines = ['# Universal theme schema 1. See THEMING.md.', '']

    def key(value):
        return value if re.fullmatch(r'[A-Za-z0-9_-]+', value) else json.dumps(value, ensure_ascii=False)

    def value(v):
        if isinstance(v, str):
            return json.dumps(v, ensure_ascii=False)
        if isinstance(v, bool):
            return str(v).lower()
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, (date, datetime, time)):
            return v.isoformat()
        if isinstance(v, list):
            return '[' + ', '.join(value(item) for item in v) + ']'
        if isinstance(v, dict):
            return '{' + ', '.join(f'{key(k)} = {value(item)}' for k, item in v.items()) + '}'
        raise ThemeError(f'Unsupported TOML value: {v!r}')

    def table(obj, keys):
        if keys:
            lines.append('[' + '.'.join(key(k) for k in keys) + ']')
        for k, v in obj.items():
            if not isinstance(v, dict):
                lines.append(f'{key(k)} = {value(v)}')
        lines.append('')
        for k, v in obj.items():
            if isinstance(v, dict):
                table(v, keys + [k])
    table(data, [])
    return '\n'.join(lines)


def color(value, label):
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise ThemeError(f'{label}: expected #RRGGBB, got {value!r}')
    return value.lower()


def validate(data: dict, path: Path) -> dict:
    meta = data.get('meta', {})
    if not isinstance(meta, dict) or not isinstance(meta.get('name'), str) or not meta['name'].strip():
        raise ThemeError(f'{path}: [meta].name must be a nonempty string')
    if meta.get('mode') not in ('dark', 'light') or meta.get('schema', 1) != 1:
        raise ThemeError(f'{path}: meta.mode must be dark/light and meta.schema must be 1')
    for section, required in (('ui', UI), ('terminal', TERMINAL), ('ansi', ANSI)):
        values = data.get(section)
        if not isinstance(values, dict):
            raise ThemeError(f'{path}: missing [{section}]')
        for key in required:
            color(values.get(key), f'{path}: {section}.{key}')
        for key, val in values.items():
            color(val, f'{path}: {section}.{key}')
    apps = data.get('apps', {})
    if not isinstance(apps, dict):
        raise ThemeError(f'{path}: apps must be a table')
    for app, spec in apps.items():
        if app not in APPS:
            raise ThemeError(f'{path}: unsupported application {app!r}')
        if not isinstance(spec, dict):
            raise ThemeError(f'{path}: apps.{app} must be a table')
        source = spec.get('source', 'universal')
        if source not in ('universal', 'preset', 'file', 'partial'):
            raise ThemeError(f'{path}: apps.{app}: unsupported source {source!r}')
        if source == 'preset' and app != 'kitty':
            raise ThemeError(f'{path}: apps.{app}: preset source is only supported by Kitty')
        for key in ('name',) if source == 'preset' else ('path',) if source == 'file' else ():
            if not isinstance(spec.get(key), str) or not spec[key].strip():
                raise ThemeError(f'{path}: apps.{app}.{key} is required for {source}')
        if source == 'file' and not resolve_path(spec['path'], path.parent).is_file():
            raise ThemeError(f'{path}: apps.{app}: file not found: {spec["path"]}')
        if app == 'hyprland' and 'active_border' in spec:
            gradient = spec['active_border']
            if not isinstance(gradient, dict) or set(gradient) - {'colors', 'angle'}:
                raise ThemeError(f'{path}: apps.hyprland.active_border: expected colors and angle')
            colors = gradient.get('colors')
            if not isinstance(colors, list) or len(colors) != 2:
                raise ThemeError(f'{path}: active_border.colors must contain two UI roles or #RRGGBB colors')
            for item in colors:
                if not isinstance(item, str) or item not in UI:
                    color(item, f'{path}: active_border.colors')
            angle = gradient.get('angle', 45)
            if isinstance(angle, bool) or not isinstance(angle, (int, float)) or not 0 <= angle <= 360:
                raise ThemeError(f'{path}: active_border.angle must be between 0 and 360 degrees')
        if source == 'partial':
            overrides = spec.get('colors')
            if not isinstance(overrides, dict) or not overrides:
                raise ThemeError(f'{path}: apps.{app}.colors must be a nonempty table')
            for key, val in overrides.items():
                color(val, f'apps.{app}.colors.{key}')
    return data


def resolve_path(value: str, base: Path) -> Path:
    p = Path(value).expanduser()
    return (p if p.is_absolute() else base / p).resolve()


def association(path: Path, generated: Path) -> Path:
    return generated / (hashlib.sha256(os.fsencode(path.resolve())).hexdigest() + '.toml')


def registry(path: Path, generated: Path) -> list[dict]:
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise ThemeError(f'Cannot read wallpaper registry {path}: {exc}') from exc
    rows = []
    for n, raw in enumerate(lines, 1):
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        parts = [p.strip() for p in raw.split('|')]
        if len(parts) not in (2, 3) or not all(parts[:2]):
            raise ThemeError(f'{path}:{n}: expected Name|WallpaperPath[|ThemeConfigPath]')
        wallpaper = resolve_path(parts[1], path.parent)
        explicit = len(parts) == 3 and bool(parts[2])
        theme = resolve_path(parts[2], path.parent) if explicit else association(wallpaper, generated)
        rows.append(dict(name=parts[0], path=str(wallpaper), theme=str(theme), explicit=explicit))
    return rows


def roles(ui: dict) -> dict:
    """Keep the original Quickshell semantic API while exposing canonical names."""
    return dict(ui, background_alt=ui['surface'], background_deep=ui['background'],
                surface_high=ui['surface_alt'], foreground_alt=ui['foreground'],
                disabled=ui['muted'], accent=ui['primary'], accent_alt=ui['secondary'],
                on_accent=ui['background'], selection=ui['surface_alt'],
                selection_text=ui['foreground'], hover=ui['surface'], pressed=ui['surface_alt'],
                focus=ui['primary'], border_inactive=ui['border'], shadow=ui['background'],
                critical=ui['error'], info=ui['secondary'], link=ui['primary'],
                link_visited=ui['secondary'], match=ui['primary'], highlight=ui['warning'])


def legacy(data: dict) -> dict:
    """Read the existing [theme]/[palette]/[roles] preset without rewriting it."""
    from .palette import terminal_palette
    try:
        if not all(isinstance(data.get(section), dict) for section in ('palette', 'roles', 'theme')):
            raise ThemeError('Legacy preset requires [theme], [palette] and [roles] tables')
        p = data['palette']
        r = {k: p.get(v, v) for k, v in data['roles'].items()}
        ui = {key: r[{'primary': 'accent', 'secondary': 'accent_alt'}.get(key, key)] for key in UI}
        for key, value in ui.items():
            color(value, f'legacy roles.{key}')
        mode = data['theme'].get('variant', 'dark')
        if mode not in ('dark', 'light'):
            raise ThemeError('Legacy theme variant must be dark/light')
        terminal, ansi = terminal_palette(ui, mode)
        return dict(meta=dict(name=data['theme']['name'], mode=mode, schema=1),
                    ui=ui, terminal=terminal, ansi=ansi)
    except (KeyError, TypeError) as exc:
        raise ThemeError(f'Invalid legacy preset: {exc}') from exc
