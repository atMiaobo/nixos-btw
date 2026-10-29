"""Independent color-only adapters. Rendering never changes the desktop."""
from __future__ import annotations
import configparser
import json
import os
from pathlib import Path
import re

from .model import ANSI, ThemeError, color, resolve_path, roles
from .palette import run
from . import integration

KITTY_KEYS = set('background foreground cursor cursor_text_color selection_background selection_foreground url_color active_border_color inactive_border_color bell_border_color visual_bell_color active_tab_foreground active_tab_background inactive_tab_foreground inactive_tab_background tab_bar_background tab_bar_margin_color mark1_foreground mark1_background mark2_foreground mark2_background mark3_foreground mark3_background wayland_titlebar_color macos_titlebar_color'.split())
KITTY_KEYS.update(f'color{i}' for i in range(256))
KITTY_KEYS.update('cursor_trail_color scrollbar_handle_color scrollbar_track_color window_title_bar_active_foreground window_title_bar_active_background window_title_bar_inactive_foreground window_title_bar_inactive_background transparent_background_colors'.split())
HYPR_KEYS = {'general:col.active_border', 'general:col.inactive_border'}
DUNST_KEYS = {'foreground', 'background', 'frame_color', 'separator_color', 'highlight'}
DUNST_SECTIONS = {'global', 'urgency_low', 'urgency_normal', 'urgency_critical'}
FUZZEL_KEYS = set('background text prompt placeholder input match selection selection-text selection-match counter border'.split())
FILES = dict(kitty='kitty.conf', quickshell='active.json', fuzzel='fuzzel.ini', dunst='dunst.conf', hyprland='hyprland.json')


def kitty_file(text: str, warnings: list, *, allow_empty=False) -> dict:
    values = {}
    ignored = set()
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(None, 1)
        key = parts[0]
        if key not in KITTY_KEYS:
            ignored.add(key)
            continue
        if len(parts) != 2:
            raise ThemeError(f'Kitty line {n}: missing color value')
        val = parts[1].strip()
        # Native RGB names and special values are resolved by Kitty's color parser.
        values[key] = val
    if ignored:
        warnings.append('Kitty ignored non-color/unsupported settings: ' + ', '.join(sorted(ignored)) + '. They require a separate config and reload/restart.')
    if not values and not allow_empty:
        raise ThemeError('Kitty theme contains no supported color settings')
    return values


def parse_ini(text):
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        raise ThemeError(f'Invalid application INI: {exc}') from exc
    if parser.defaults():
        raise ThemeError('Application color files cannot contain [DEFAULT]')
    return {s: dict(parser[s]) for s in parser.sections()}


def ini(data):
    return '\n'.join('[' + s + ']\n' + '\n'.join(f'{k}={v}' for k, v in values.items()) + '\n' for s, values in data.items())


def upgrade_dunst_output(text):
    """Remove the old generator's invalid urgency-level separator setting.

    This operates only on generated cache output, never the user's dunstrc.
    The valid global separator and all other values retain their semantics.
    """
    data = parse_ini(text)
    changed = False
    for section in ('urgency_low', 'urgency_normal', 'urgency_critical'):
        if 'separator_color' in data.get(section, {}):
            del data[section]['separator_color']
            changed = True
    return ini(data) if changed else text


def universal(app, theme):
    u, t = theme['ui'], theme['terminal']
    if app == 'kitty':
        v = dict(background=t['background'], foreground=t['foreground'], cursor=t['cursor'],
                 cursor_text_color=t['background'], selection_background=t['selection_bg'],
                 selection_foreground=t['selection_fg'], url_color=u['primary'],
                 active_border_color=u['primary'], inactive_border_color=u['border'],
                 bell_border_color=u['warning'], visual_bell_color='none',
                 wayland_titlebar_color='system', macos_titlebar_color='system',
                 active_tab_foreground=t['background'], active_tab_background=u['primary'],
                 inactive_tab_foreground=u['muted'], inactive_tab_background=u['surface'],
                 tab_bar_background=u['background'], tab_bar_margin_color='none')
        for n in range(1, 4):
            v[f'mark{n}_foreground'] = t['background']
            v[f'mark{n}_background'] = u[('primary', 'secondary', 'warning')[n-1]]
        v.update({f'color{i}': theme['ansi'][key] for i, key in enumerate(ANSI)})
        return v
    if app == 'quickshell':
        return dict(u)
    if app == 'fuzzel':
        mapped = dict(background='background', text='foreground', prompt='primary', placeholder='muted',
                      input='foreground', match='primary', selection='surface_alt', **{'selection-text': 'foreground',
                      'selection-match': 'primary', 'counter': 'muted', 'border': 'primary'})
        return {'colors': {k: u[v][1:] + ('ee' if k == 'background' else 'ff') for k, v in mapped.items()}}
    if app == 'dunst':
        values = dict(foreground=u['foreground'], background=u['surface'], frame_color=u['primary'],
                      separator_color=u['border'], highlight=u['secondary'])
        return {'global': values} | {s: dict({k: v for k, v in values.items() if k != 'separator_color'}, frame_color=u['error'] if s == 'urgency_critical' else u['border'] if s == 'urgency_low' else u['primary']) for s in ('urgency_low', 'urgency_normal', 'urgency_critical')}
    if app == 'hyprland':
        return {'general:col.active_border': u['primary'], 'general:col.inactive_border': u['border']}
    raise ThemeError(f'Unsupported adapter: {app}')


def render(app: str, theme: dict, theme_path: Path, override=None):
    spec = override if override is not None else theme.get('apps', {}).get(app, {})
    source = spec.get('source', 'universal')
    warnings = []
    values = universal(app, theme)
    if source in ('file', 'preset'):
        if source == 'preset':
            try:
                text = run(['kitten', 'themes', '--cache-age=-1', '--dump-theme', '--reload-in=none', '--', spec['name']])
            except ThemeError as exc:
                raise ThemeError(f'Kitty preset {spec["name"]!r} unavailable offline: {exc}') from exc
        else:
            path = resolve_path(spec['path'], theme_path.parent)
            try:
                text = path.read_text()
            except OSError as exc:
                raise ThemeError(f'{app}: cannot read {path}: {exc}') from exc
        if app == 'kitty':
            values = kitty_file(text, warnings, allow_empty=source == 'preset')
        elif app in ('quickshell', 'hyprland'):
            try:
                custom = json.loads(text)
                if not isinstance(custom, dict):
                    raise ValueError('expected a JSON object')
                if app == 'quickshell':
                    custom = custom.get('colors', custom)
                values.update(custom)
            except (ValueError, TypeError) as exc:
                raise ThemeError(f'{app}: invalid JSON color file: {exc}') from exc
        else:
            custom = parse_ini(text)
            for section, settings in custom.items():
                values.setdefault(section, {}).update(settings)
    elif source == 'partial':
        for key, value in spec['colors'].items():
            if app == 'fuzzel':
                if key not in FUZZEL_KEYS:
                    raise ThemeError(f'fuzzel: unsupported property {key!r}')
                values['colors'][key] = value[1:] + 'ff'
            elif app == 'dunst':
                if '.' not in key:
                    raise ThemeError('dunst partial keys must be "section.property"')
                section, prop = key.split('.', 1)
                values.setdefault(section, {})[prop] = value
            else:
                values[key] = value
    if app == 'hyprland' and 'active_border' in spec:
        gradient = spec['active_border']
        values['general:col.active_border'] = dict(
            colors=[theme['ui'].get(c, c) for c in gradient['colors']], angle=gradient.get('angle', 45))
    if app == 'kitty':
        for key, value in values.items():
            if key not in KITTY_KEYS:
                raise ThemeError(f'kitty: unsupported property {key!r}')
        text = '\n'.join(f'{k} {v}' for k, v in values.items()) + '\n'
        # Complete the color palette with this Kitty version's native defaults.
        # Otherwise an earlier current-theme.conf leaks unspecified colors into
        # universal/partial/file presets (including the empty native Default).
        # Read only color options with a serializable default. Empty defaults
        # (e.g. transparent_background_colors) are not valid config lines; any
        # conflicting inherited value is still caught by the effective verifier.
        # Fonts, opacity and bindings stay in kitty.conf.
        script = ('import json,sys; from kitty.config import parse_config; '
                  'from kitty.options.definition import definition; from kitty.conf.types import Option; '
                  'keys=set(json.loads(sys.argv[1])); '
                  'defaults={o.name:o.defval_as_string for o in definition.iter_all_options() '
                  'if isinstance(o,Option) and o.name in keys and o.defval_as_string}; '
                  'lines=[k+" "+v for k,v in defaults.items()] + sys.stdin.read().splitlines(); '
                  'errors=[]; parse_config(lines, accumulate_bad_lines=errors); '
                  'print(json.dumps(dict(errors=[str(e) for e in errors], defaults=defaults)))')
        try:
            result = json.loads(run(['kitty', '+runpy', script, json.dumps(sorted(KITTY_KEYS))], input=text))
            errors = result['errors']
            defaults = result['defaults']
            if not isinstance(errors, list) or not isinstance(defaults, dict) or set(defaults) - KITTY_KEYS:
                raise ValueError('invalid color defaults or errors')
        except (ValueError, KeyError, TypeError) as exc:
            raise ThemeError(f'Kitty validation returned invalid JSON: {exc}') from exc
        if errors:
            raise ThemeError('Invalid Kitty colors: ' + '; '.join(errors))
        values = dict(defaults, **values)
        text = '\n'.join(f'{k} {v}' for k, v in values.items()) + '\n'
    elif app == 'quickshell':
        for key, value in values.items():
            if key not in theme['ui']:
                raise ThemeError(f'quickshell: unsupported semantic color {key!r}')
            color(value, f'quickshell.{key}')
        text = json.dumps(dict(id=str(theme_path), name=theme['meta']['name'], variant=theme['meta']['mode'],
                               colors=roles(values)), indent=2) + '\n'
    elif app == 'hyprland':
        for key, value in values.items():
            if key not in HYPR_KEYS:
                raise ThemeError(f'hyprland: unsupported property {key!r}')
            hypr_color(value, key)
        text = json.dumps(values, indent=2) + '\n'
    else:
        for section, settings in values.items():
            if section not in ({'colors'} if app == 'fuzzel' else DUNST_SECTIONS):
                raise ThemeError(f'{app}: unsupported section {section!r}; only color sections are allowed')
            for key, value in settings.items():
                if key not in (FUZZEL_KEYS if app == 'fuzzel' else DUNST_KEYS):
                    raise ThemeError(f'{app}: unsupported color property {key!r}')
                if app == 'fuzzel':
                    if not re.fullmatch('[0-9a-fA-F]{8}', value):
                        raise ThemeError(f'fuzzel.{key}: expected RRGGBBAA')
                else:
                    if section != 'global' and key == 'separator_color':
                        raise ThemeError('dunst.separator_color is only supported in [global]')
                    value = value.strip('"')
                    color(value, f'dunst.{key}')
                    settings[key] = '"' + value + '"'
        text = ini(values)
    return text, values, warnings


def hypr_color(value, key):
    if isinstance(value, dict) and key == 'general:col.active_border':
        if set(value) != {'colors', 'angle'} or not isinstance(value['colors'], list) or len(value['colors']) != 2:
            raise ThemeError('hyprland: active border gradient requires two colors and an angle')
        for c in value['colors']:
            color(c, 'hyprland active border gradient')
        angle = value['angle']
        if isinstance(angle, bool) or not isinstance(angle, (int, float)) or not 0 <= angle <= 360:
            raise ThemeError('hyprland: gradient angle must be between 0 and 360')
    else:
        color(value, f'hyprland.{key}')


def lua_color(value):
    if isinstance(value, dict):
        return '{ colors = {' + ', '.join(lua_color(c) for c in value['colors']) + '}, angle = ' + str(value['angle']) + ' }'
    return json.dumps('rgb(' + value[1:] + ')')


def hypr_config(values):
    return ('hl.config({ general = { col = { active_border = ' + lua_color(values['general:col.active_border'])
            + ', inactive_border = ' + lua_color(values['general:col.inactive_border']) + ' } } })')


def verify_hypr(values):
    for key in ('general:col.active_border', 'general:col.inactive_border'):
        # Lua option names use dots (the schema retains old keys for compatibility).
        option = key.replace(':', '.')
        reply = run(['hyprctl', '-j', 'getoption', option])
        try:
            data = json.loads(reply)
        except ValueError as exc:
            raise ThemeError(f'getoption {option}: {reply.strip()}') from exc
        if not isinstance(data, dict) or not isinstance(data.get('gradient'), str):
            raise ThemeError(f'getoption {option}: expected gradient data, received {reply.strip()}')
        # 0.55's gradient serializer emits ARGB hex colors and a degree angle.
        actual = re.findall(r'(?:0x)?([0-9a-fA-F]{8})', data['gradient'])
        expected = values[key]
        colors = expected['colors'] if isinstance(expected, dict) else [expected]
        if [c.lower() for c in actual] != ['ff' + c[1:].lower() for c in colors]:
            raise ThemeError(f'getoption {option}: colors differ: {data["gradient"]}; expected {colors}')
        if isinstance(expected, dict):
            angle = re.search(r'([0-9.]+)deg', data['gradient'])
            if not angle or abs(float(angle[1]) - expected['angle']) > 1:
                raise ThemeError(f'getoption {option}: angle differs: {data["gradient"]}')


def live(app: str, output: Path, values: dict) -> str:
    main = integration.check(app, output)
    if app == 'kitty':
        # Verify the native effective config, then use Kitty's supported signal
        # reload. An inherited stale/unauthorized socket must not prevent it.
        script = ('import runpy,sys; sys.dont_write_bytecode=True; sys.path.insert(0, '
                  + repr(str(Path(__file__).resolve().parents[1]))
                  + '); runpy.run_module("theming.kitty_runtime", run_name="__main__")')
        try:
            result = json.loads(run(['kitty', '+runpy', script, main, str(output)]))
            pids = result['signaled']
            skipped = result['skipped']
            vanished = result['vanished']
            if not all(isinstance(group, list) and all(type(pid) is int for pid in group)
                       for group in (pids, skipped, vanished)):
                raise ValueError('invalid PID lists')
        except (ValueError, KeyError, TypeError) as exc:
            raise ThemeError(f'Kitty reload returned invalid delivery report: {exc}') from exc
        status = f'{main}: include and effective palette verified for new windows; '
        status += ('SIGUSR1 delivered to PIDs ' + ', '.join(map(str, pids))
                   + ' (application acknowledgment unavailable)' if pids else
                   'staged for next Kitty launch (no reloadable Kitty GUI visible)')
        if skipped or vanished:
            status += f'; skipped without native SIGUSR1 receiver: {skipped}; vanished: {vanished}'
        return status
    if app == 'fuzzel':
        run(['fuzzel', '--check-config', '--config', main])
        return f'{main}: include and syntax verified; staged for next launch'
    if app == 'dunst':
        pids = run(['pgrep', '--uid', str(os.getuid()), '--exact', 'dunst'], allowed_codes=(0, 1)).strip()
        if not pids:
            return f'{main}: include verified; staged for next Dunst launch (no daemon visible)'
        integration.check_dunst_processes(pids, Path(main))
        run(['dunstctl', 'reload'])
        return f'{main}: include verified; dunstctl reload requested'
    if app == 'hyprland':
        result = run(['hyprctl', 'eval', hypr_config(values)])
        if result.strip().lower() != 'ok':
            raise ThemeError(f'hyprctl eval hl.config: {result.strip() or "empty reply"}')
        verify_hypr(values)
        return 'Lua border colors updated; getoption verified'
    return 'reactive JSON updated'


def hypr_lua(values: dict) -> str:
    # The existing main Lua config accepts either a string or a gradient table.
    return 'return {\n' + '\n'.join(f'  {k} = {lua_color(values[v])},' for k, v in {
        'accent': 'general:col.active_border', 'border_inactive': 'general:col.inactive_border'}.items()) + '\n}\n'
