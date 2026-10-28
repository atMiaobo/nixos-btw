"""Read-only checks that generated colors are reachable from application configs."""
from __future__ import annotations
import glob
import os
from pathlib import Path
import re

from .model import ThemeError
from .palette import run


def config_home():
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))


def included_paths(main: Path, app: str, seen=None, stack=None) -> set[Path]:
    """Follow native plain-file includes without executing config directives."""
    seen = set() if seen is None else seen
    stack = set() if stack is None else stack
    try:
        resolved = main.resolve(strict=True)
    except FileNotFoundError:
        return seen
    except (OSError, RuntimeError) as exc:
        raise ThemeError(f'include check: cannot resolve {main}: {exc}') from exc
    if resolved in stack:
        raise ThemeError(f'include check: recursive {app} include at {main}')
    if resolved in seen:
        return seen
    if not main.is_file():
        return seen
    seen.add(resolved)
    stack.add(resolved)
    for line in main.read_text().splitlines():
        line = line.strip()
        match = re.match(r'include\s+(.+)$' if app == 'kitty' else r'include\s*=\s*(.+)$', line)
        if not match:
            continue
        value = os.path.expanduser(match[1].strip())
        if app == 'kitty':
            value = os.path.expandvars(value)
        path = Path(value)
        if not path.is_absolute():
            if app == 'fuzzel':
                raise ThemeError(f'include check: Fuzzel requires an absolute or ~/ include: {value}')
            path = main.parent / path
        for name in glob.glob(str(path)):
            included_paths(Path(name), app, seen, stack)
    stack.remove(resolved)
    return seen


def check(app: str, output: Path) -> str:
    try:
        return _check(app, output)
    except (OSError, RuntimeError) as exc:
        raise ThemeError(f'include check: cannot resolve {app} configuration: {exc}') from exc


def _check(app: str, output: Path) -> str:
    root = config_home()
    if app in ('kitty', 'fuzzel'):
        main = root / app / ('kitty.conf' if app == 'kitty' else 'fuzzel.ini')
        paths = included_paths(main, app)
    elif app == 'dunst':
        main = root / 'dunst/dunstrc'
        paths = {p.resolve(strict=True) for p in (main.parent / 'dunstrc.d').glob('*.conf')
                 if p.is_file() or p.is_symlink()}
        if not main.is_file():
            paths.clear()
    else:
        return ''
    if output.resolve() not in paths:
        reference = (root / 'dunst/dunstrc.d/99-theme.conf' if app == 'dunst'
                     else Path.home() / '.local/share/mihao-theme' / output.name)
        raise ThemeError(f'include check: {main} does not consume {output}; '
                         f'{reference} resolves to {reference.resolve()}. '
                         'Restore the directory-owned app config and the separate '
                         '~/.local/share/mihao-theme bridge; do not install files inside directory links.')
    if not os.access(output, os.R_OK):
        raise ThemeError(f'include check: unreadable runtime colors: {output}')
    return str(main)


def check_dunst_processes(pids: str, main: Path):
    # A daemon started with -conf skips normal discovery and all drop-ins.
    # Query only the known Dunst processes, never the session's other commands.
    commands = run(['ps', '-p', ','.join(pids.split()), '-o', 'args='])
    if not commands.strip():
        raise ThemeError('Dunst process disappeared during configuration inspection; retry theme reset dunst')
    for command in commands.splitlines():
        args = command.split()
        if any(arg in ('-conf', '-config', '--config') or arg.startswith(('-conf=', '-config=', '--config=')) for arg in args[1:]):
            raise ThemeError(f'running Dunst uses an explicit configuration ({command}); '
                             f'default drop-ins beside {main} are bypassed. '
                             'Launch Dunst without -conf, or integrate the generated appearance in its custom config list.')
