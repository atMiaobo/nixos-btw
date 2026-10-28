"""Native Kitty config verification and SIGUSR1 delivery (run via +runpy).

No remote control permission is needed. Signal delivery is observable, but is
not an acknowledgment that a GUI has finished applying the new configuration.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import sys

from .model import ThemeError


def verify_effective(main: str, output: str, *, config_paths=(), overrides=()):
    from kitty.cli import default_config_paths, parse_override
    from kitty.config import load_config
    from .adapters import KITTY_KEYS

    errors = []
    expected = load_config(output, accumulate_bad_lines=errors)
    # Use native discovery too: KITTY_CONFIG_DIRECTORY and system configs can
    # make a new Kitty read something other than XDG_CONFIG_HOME/kitty.
    effective = load_config(*default_config_paths(config_paths),
                            overrides=map(parse_override, overrides or ()),
                            accumulate_bad_lines=errors)
    if errors:
        raise ThemeError('Kitty effective configuration: ' + '; '.join(map(str, errors)))
    different = sorted(key for key in KITTY_KEYS if hasattr(expected, key)
                       and getattr(expected, key) != getattr(effective, key))
    if different:
        raise ThemeError(f'Kitty effective palette differs from {output}: ' + ', '.join(different)
                         + f'; check later color settings/includes, command-line overrides '
                         + f'and native config discovery ({main})')


def signal_instances(proc: Path = Path('/proc'), *, output: str | None = None) -> dict:
    from kitty.child import cmdline_of_pid
    from kitty.utils import get_all_processes, is_kitty_gui_cmdline

    result = dict(signaled=[], skipped=[], vanished=[])
    for pid in get_all_processes():
        directory = proc / str(pid)
        try:
            if directory.stat().st_uid != os.getuid():
                continue
            command = cmdline_of_pid(pid)
            if not command:
                continue
            # Nix wrappers may expose the wrapped executable as argv[0].
            if Path(command[0]).name not in ('kitty', '.kitty-wrapped', 'kitty-wrapped'):
                continue
            if not is_kitty_gui_cmdline('kitty', *command[1:]):
                continue
            # Linux Kitty receives blocked signals through signalfd; older
            # versions can use a traditional handler. A process with neither
            # receiver would be terminated by SIGUSR1.
            status = directory.joinpath('status').read_text().splitlines()
            masks = {line.split()[0]: int(line.split()[1], 16) for line in status
                     if line.startswith(('SigCgt:', 'SigBlk:'))}
            if not (masks.get('SigCgt:', 0) | masks.get('SigBlk:', 0)) & (1 << (signal.SIGUSR1 - 1)):
                result['skipped'].append(pid)
                continue
            if output is not None:
                from kitty.cli import parse_args
                from kitty.cli_stub import CLIOptions
                options, _ = parse_args(list(command[1:]), result_class=CLIOptions)
                try:
                    verify_effective(f'PID {pid}', output, config_paths=options.config,
                                     overrides=options.override)
                except ThemeError as exc:
                    raise ThemeError(f'Kitty PID {pid}: {exc}') from exc
            os.kill(pid, signal.SIGUSR1)
            result['signaled'].append(pid)
        except (FileNotFoundError, ProcessLookupError):
            result['vanished'].append(pid)
        except (OSError, ValueError) as exc:
            raise ThemeError(f'Kitty reload inspection/delivery failed for PID {pid}: {exc}') from exc
    return result


def main():
    try:
        verify_effective(sys.argv[1], sys.argv[2])
        print(json.dumps(signal_instances(output=sys.argv[2])))
    except ThemeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
