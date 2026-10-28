"""Public CLI; all UI callers enter through the same engine."""
import argparse
import json
from pathlib import Path
import sys

from .engine import Engine
from . import integration
from .model import APPS, ThemeError


def parser():
    root = argparse.ArgumentParser(prog='theme', description='Apply saved wallpaper themes; Kitty changes are temporary unless --save.')
    commands = root.add_subparsers(dest='command', required=True)
    commands.add_parser('help', help='show command help')
    p = commands.add_parser('list', help='list registry and resolved theme paths')
    p.add_argument('--json', action='store_true')
    p = commands.add_parser('status', help='show selection, overrides, adapter results and known deviations')
    p.add_argument('--json', action='store_true')
    p = commands.add_parser('apply', help='apply wallpaper and every saved app theme, including on reselection')
    p.add_argument('wallpaper')
    p.add_argument('legacy_theme', nargs='?', help=argparse.SUPPRESS)
    p.add_argument('--name', help='registry identity when selecting by wallpaper path')
    p.add_argument('--theme', help='authoritative TOML path, relative to registry directory')
    p = commands.add_parser('kitty', help='change only Kitty colors')
    p.add_argument('name', nargs='?', help='native Kitty preset name')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--file', type=Path)
    group.add_argument('--universal', action='store_true')
    p.add_argument('--save', action='store_true', help='also save override in active wallpaper TOML')
    for app in ('hyprland', 'fuzzel', 'dunst', 'quickshell'):
        p = commands.add_parser(app, help=f'change only {app} colors')
        group = p.add_mutually_exclusive_group(required=True)
        group.add_argument('--file', type=Path)
        group.add_argument('--universal', action='store_true')
        if app == 'hyprland':
            group.add_argument('--gradient', type=float, metavar='ANGLE',
                               help='universal primary/secondary active border gradient in degrees')
        p.add_argument('--save', action='store_true')
    p = commands.add_parser('reset', help='restore saved theme without changing wallpaper')
    p.add_argument('app', nargs='?', choices=APPS)
    p = commands.add_parser('regenerate', help='back up and regenerate palette; retain app overrides; do not apply')
    p.add_argument('wallpaper', nargs='?')
    commands.add_parser('init', help='initialize missing runtime files without changing running apps')
    commands.add_parser('restore-session', help='restore selected wallpaper at session startup')
    return root


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = parser()
    # Preserve `theme /path/image [preset]`; names use `theme apply NAME`.
    known = {'help', 'list', 'status', 'apply', 'kitty', 'reset', 'regenerate', 'init', 'restore-session', 'hyprland', 'fuzzel', 'dunst', 'quickshell'}
    if argv and argv[0] not in known and not argv[0].startswith('-'):
        argv.insert(0, 'apply')
    args = root.parse_args(argv)
    engine = Engine()
    try:
        if args.command == 'help':
            root.print_help()
            return 0
        if args.command == 'list':
            rows = engine.entries()
            if args.json:
                print(json.dumps(rows))
            else:
                for row in rows:
                    print(f'{row["name"]}|{row["path"]}|{row["theme"]}' + ('' if Path(row['theme']).exists() else ' [not generated]'))
            return 0
        if args.command == 'status':
            state = engine.state(False)
            if not state:
                print('{}' if args.json else 'No active theme.')
                return 0
            data = engine.load(state['selection']) if Path(state['selection']['theme']).exists() else None
            deployment = {}
            for app in ('kitty', 'fuzzel', 'dunst'):
                try:
                    deployment[app] = integration.check(app, engine.output(app))
                except (ThemeError, OSError) as exc:
                    deployment[app] = 'failed: ' + str(exc)
            status = dict(state, deployment=deployment, saved_overrides=data.get('apps', {}) if data else {},
                          note='Only engine changes are tracked. External edits are not continuously monitored.')
            if args.json:
                print(json.dumps(status, indent=2))
            else:
                entry = state['selection']
                print(f'Wallpaper: {entry["name"]}\nPath: {entry["path"]}\nTheme: {entry["theme"]}')
                print('Saved overrides: ' + json.dumps(status['saved_overrides']))
                print('Known temporary deviations: ' + json.dumps(state.get('temporary', {})))
                for app, result in state.get('applications', {}).items():
                    print(f'{app}: {result.get("error", result["status"])}')
                for app, result in deployment.items():
                    print(f'{app} deployment: {result}')
                print(status['note'])
            return 0
        with engine.locked():
            failures = []
            if args.command == 'apply':
                override = args.theme or args.legacy_theme
                if args.legacy_theme and not args.theme and not override.endswith('.toml') and not Path(override).is_file():
                    # Old theme-apply IDs and picker's historical third argument.
                    override = str(engine.config / 'themes/presets' / (override + '.toml'))
                failures = engine.apply(engine.find(args.wallpaper, override, args.name))
            elif args.command == 'kitty':
                if sum((bool(args.name), args.file is not None, args.universal)) != 1:
                    root.error('kitty requires exactly one preset name, --file, or --universal')
                spec = dict(source='preset', name=args.name) if args.name else dict(source='file', path=str(args.file.expanduser().resolve())) if args.file else dict(source='universal')
                failures = engine.kitty(spec, args.save)
            elif args.command in ('hyprland', 'fuzzel', 'dunst', 'quickshell'):
                spec = dict(source='file', path=str(args.file.expanduser().resolve())) if args.file else dict(source='universal')
                if args.command == 'hyprland' and args.gradient is not None:
                    spec['active_border'] = dict(colors=['primary', 'secondary'], angle=args.gradient)
                failures = engine.app(args.command, spec, args.save)
            elif args.command == 'reset':
                failures = engine.reset(args.app)
            elif args.command == 'regenerate':
                path, backup = engine.regenerate(args.wallpaper)
                print(f'Regenerated: {path}' + (f'\nBackup: {backup}' if backup else '') + '\nUse theme reset to apply.')
            elif args.command == 'init':
                engine.init()
            elif args.command == 'restore-session':
                failures = engine.restore_session()
            for failure in failures:
                print('theme: ' + failure, file=sys.stderr)
            if failures:
                print('theme: partial failure; see theme status for errors, file preservation and live-application results.', file=sys.stderr)
                return 3
        return 0
    except (ThemeError, OSError) as exc:
        print(f'theme: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
