"""Selection, transactions, persistent definitions and explicit runtime changes."""
from __future__ import annotations
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from . import adapters
from .model import APPS, ThemeError, association, atomic_write, dumps, legacy, read_toml, registry, resolve_path, validate
from .palette import generate, run


class Engine:
    def __init__(self):
        home = Path.home()
        self.config = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config'))
        self.cache = Path(os.environ.get('MIHAO_THEME_CACHE', Path(os.environ.get('XDG_CACHE_HOME', home / '.cache')) / 'theme'))
        self.state_dir = Path(os.environ.get('MIHAO_THEME_STATE', Path(os.environ.get('XDG_STATE_HOME', home / '.local/state')) / 'mihao/theme'))
        self.registry_path = Path(os.environ.get('MIHAO_THEME_REGISTRY', self.config / 'themes/wallpapers'))
        self.generated = Path(os.environ.get('MIHAO_THEME_GENERATED_DIR', self.config / 'themes/generated'))
        self.state_path = self.state_dir / 'state.json'

    @contextmanager
    def locked(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with (self.state_dir / 'lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def entries(self):
        return registry(self.registry_path, self.generated)

    def find(self, selector, theme=None, name=None):
        entries = self.entries() if self.registry_path.exists() else []
        matches = [r for r in entries if r['name'] == selector or r['path'] == str(Path(selector).expanduser().resolve())]
        if name is not None:
            matches = [r for r in matches if r['name'] == name and r['path'] == str(Path(selector).expanduser().resolve())]
            if not matches:
                raise ThemeError(f'Wallpaper registry entry changed or missing: {name!r} | {selector}')
        if len(matches) > 1:
            raise ThemeError(f'Ambiguous wallpaper {selector!r}; select its unique absolute path')
        if matches:
            entry = matches[0].copy()
        else:
            path = Path(selector).expanduser().resolve()
            if not path.is_file():
                raise ThemeError(f'Unknown wallpaper or missing file: {selector}')
            entry = dict(name=path.stem, path=str(path), theme=str(association(path, self.generated)), explicit=False)
        if theme is not None:
            entry.update(theme=str(resolve_path(theme, self.registry_path.parent)), explicit=True)
        return entry

    def state(self, required=True):
        if not self.state_path.exists():
            if required:
                raise ThemeError('No active theme. Select a wallpaper with: theme apply NAME')
            return {}
        try:
            state = json.loads(self.state_path.read_text())
            if not isinstance(state, dict) or state.get('schema', 1) != 1:
                raise ValueError('expected state schema 1')
            selection = state.get('selection')
            if not isinstance(selection, dict) or not all(isinstance(selection.get(k), str) for k in ('name', 'path', 'theme')) or not selection['theme'] or not isinstance(selection.get('explicit'), bool):
                raise ValueError('invalid or missing selection')
            for key in ('applications', 'temporary', 'runtime'):
                if key in state and not isinstance(state[key], dict):
                    raise ValueError(f'{key} must be an object')
            if not all(app in APPS and isinstance(text, str) for app, text in state.get('runtime', {}).items()):
                raise ValueError('invalid application runtime snapshots')
            return state
        except (OSError, ValueError) as exc:
            raise ThemeError(f'Invalid active state {self.state_path}: {exc}') from exc

    def save_state(self, state):
        state['schema'] = 1
        atomic_write(self.state_path, json.dumps(state, indent=2) + '\n')

    def load(self, entry):
        path = Path(entry['theme'])
        if path.exists():
            if not path.is_file():
                raise ThemeError(f'Theme path is not a regular file: {path}')
            data = read_toml(path)
            if 'meta' not in data and 'roles' in data:
                data = legacy(data)
            return validate(data, path)
        if entry['explicit']:
            raise ThemeError(f'Explicit theme file not found: {path}; refusing automatic substitution')
        data = generate(Path(entry['path']), entry['name'])
        try:
            atomic_write(path, dumps(data), overwrite=False)
        except FileExistsError:
            # A manual editor may have created a theme while extraction ran.
            return self.load(entry)
        return data

    def output(self, app):
        return self.cache / ('active.json' if app == 'quickshell' else 'generated/' + adapters.FILES[app])

    def prepare(self, theme, path, apps):
        return {app: adapters.render(app, theme, path) for app in apps}

    def install(self, plans, state, temporary=False):
        failures = []
        state.setdefault('applications', {})
        state.setdefault('temporary', {})
        state.setdefault('runtime', {})
        for app, (text, values, warnings) in plans.items():
            output = self.output(app)
            auxiliary = self.cache / 'generated/hyprland.lua'
            snapshots = {}
            written = []
            operation = 'snapshot previous generated files'
            try:
                for path in ([output, auxiliary] if app == 'hyprland' else [output]):
                    snapshots[path] = path.read_text() if path.is_file() else None
                operation = 'atomic write'
                atomic_write(output, text)
                written.append(output)
                if app == 'hyprland':
                    atomic_write(auxiliary, adapters.hypr_lua(values))
                    written.append(auxiliary)
                operation = 'verify effective configuration / apply runtime colors'
                result = adapters.live(app, output, values)
            except (ThemeError, OSError) as exc:
                rollback_errors = []
                for path in reversed(written):
                    try:
                        if snapshots[path] is None:
                            path.unlink(missing_ok=True)
                        else:
                            atomic_write(path, snapshots[path])
                    except (ThemeError, OSError) as rollback:
                        rollback_errors.append(f'{path}: {rollback}')
                preserved = not rollback_errors
                preservation = 'previous generated files preserved' if preserved else 'file restoration failed: ' + '; '.join(rollback_errors)
                message = f'{operation}: {output}: {exc}; {preservation}; live appearance unconfirmed'
                failures.append(f'{app}: {message}')
                state['applications'][app] = dict(status='failed', operation=operation, path=str(output),
                                                   error=message, previous_files_preserved=preserved)
                # Live changes can be partially delivered before failure. Report it,
                # retain the previous valid files, and permit explicit retry/reset.
                state['temporary'][app] = {'unknown': 'adapter failed; live appearance may differ'}
                continue
            state['applications'][app] = dict(status=result, warnings=warnings,
                                               sha256=hashlib.sha256(text.encode()).hexdigest())
            state['runtime'][app] = text
            if not temporary:
                state['temporary'].pop(app, None)
            for warning in warnings:
                print(f'warning: {warning}', file=sys.stderr)
        return failures

    def wallpaper(self, path):
        if not Path(path).is_file():
            raise ThemeError(f'Wallpaper not found: {path}')
        # The existing awww path supports still images and animated WebP directly.
        try:
            run(['awww', 'query'])
        except ThemeError:
            log = self.cache / 'awww-daemon.log'
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open('a') as stream:
                try:
                    subprocess.Popen(['awww-daemon'], stdout=stream, stderr=stream, start_new_session=True)
                except OSError as exc:
                    raise ThemeError(f'Cannot start awww-daemon: {exc}') from exc
            for _ in range(30):
                time.sleep(.1)
                try:
                    run(['awww', 'query'])
                    break
                except ThemeError:
                    continue
            else:
                raise ThemeError(f'awww-daemon did not become ready; see {log}')
        run(['awww', 'img', path])

    def apply(self, entry, wallpaper=True, only=None):
        theme = self.load(entry)
        apps = [only] if only else APPS
        plans = self.prepare(theme, Path(entry['theme']), apps)
        state = self.state(False)
        previous = state.get('selection')
        if wallpaper:
            self.wallpaper(entry['path'])
            atomic_write(self.cache.parent / 'mihao/current-wallpaper', entry['path'] + '\n')
        state['selection'] = entry
        if previous != entry:
            state['temporary'] = {}
        failures = self.install(plans, state)
        self.save_state(state)
        return failures

    def reset(self, app=None):
        return self.apply(self.state()['selection'], wallpaper=False, only=app)

    def kitty(self, spec, save=False):
        return self.app('kitty', spec, save)

    def app(self, app, spec, save=False):
        state = self.state(False)
        if not state:
            # Compatibility with the old wallpaper script's selection marker.
            marker = self.cache.parent / 'mihao/current-wallpaper'
            if not marker.is_file():
                raise ThemeError(f'No active wallpaper. Run theme apply NAME before changing {app}.')
            state = dict(selection=self.find(marker.read_text().strip()))
        entry = state['selection']
        theme = self.load(entry)
        path = Path(entry['theme'])
        updated = deepcopy(theme)
        updated.setdefault('apps', {})[app] = spec
        validate(updated, path)
        plans = self.prepare(updated, path, [app])
        # --save writes only after successful rendering. Backups retain comments.
        if save:
            self.backup(path)
            atomic_write(path, dumps(updated))
        failures = self.install(plans, state, temporary=not save)
        if not failures and not save:
            state['temporary'][app] = spec
        self.save_state(state)
        return failures

    def backup(self, path):
        backup = path.with_name(path.name + f'.bak.{time.time_ns()}')
        atomic_write(backup, path.read_text())
        return backup

    def regenerate(self, selector=None):
        entry = self.find(selector) if selector else self.state()['selection']
        path = Path(entry['theme'])
        old = self.load(entry) if path.exists() else None
        data = generate(Path(entry['path']), entry['name'], old['meta']['mode'] if old else 'dark')
        if old:
            data['meta'] = old['meta']
            if 'apps' in old:
                data['apps'] = old['apps']
        validate(data, path)
        # Resolve every override before replacing a customized palette.
        self.prepare(data, path, APPS)
        backup = self.backup(path) if path.exists() else None
        atomic_write(path, dumps(data))
        return path, backup

    def init(self):
        """Explicit initialization; recover last runtime outputs after cache loss."""
        state = self.state(False)
        if state:
            for app, text in state.get('runtime', {}).items():
                if app in APPS and not self.output(app).exists():
                    atomic_write(self.output(app), text)
        else:
            default = Path(__file__).with_name('default.toml')
            data = validate(read_toml(default), default)
            for app, (text, values, _) in self.prepare(data, default, APPS).items():
                if not self.output(app).exists():
                    atomic_write(self.output(app), text)
        hypr = self.output('hyprland')
        auxiliary = self.cache / 'generated/hyprland.lua'
        if hypr.exists() and not auxiliary.exists():
            atomic_write(auxiliary, adapters.hypr_lua(json.loads(hypr.read_text())))
        dunst = self.output('dunst')
        if dunst.is_file():
            previous = dunst.read_text()
            upgraded = adapters.upgrade_dunst_output(previous)
            if upgraded != previous:
                atomic_write(dunst, upgraded)
                print(f'Upgraded generated Dunst urgency colors: {dunst}', file=sys.stderr)

    def restore_session(self):
        self.init()
        state = self.state(False)
        if state and state['selection']['path']:
            self.wallpaper(state['selection']['path'])
        failures = []
        if state:
            # Restore the runtime snapshots, including temporary choices, once
            # at login. This also covers a cache cleared between sessions.
            for app in ('hyprland', 'dunst'):
                output = self.output(app)
                if output.exists():
                    try:
                        values = json.loads(output.read_text()) if app == 'hyprland' else {}
                        result = adapters.live(app, output, values)
                        previous = state.setdefault('applications', {}).get(app, {})
                        state['applications'][app] = dict(status=result, **{
                            k: previous[k] for k in ('warnings', 'sha256') if k in previous})
                        if 'unknown' in state.get('temporary', {}).get(app, {}):
                            state['temporary'].pop(app, None)
                    except (ThemeError, OSError, ValueError) as exc:
                        message = f'session runtime restore: {output}: {exc}; previous generated files preserved; live appearance unconfirmed'
                        failures.append(f'{app}: {message}')
                        state.setdefault('applications', {})[app] = dict(status='failed', error=message,
                            operation='session runtime restore', path=str(output), previous_files_preserved=True)
                        state.setdefault('temporary', {})[app] = {'unknown': 'adapter failed; live appearance may differ'}
            self.save_state(state)
        return failures
