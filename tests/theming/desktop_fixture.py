"""Disposable directory-owned desktop, with two-hop Home Manager style links."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from functools import lru_cache

REPO = Path(__file__).resolve().parents[2]
APPS = ('quickshell', 'hypr', 'dunst', 'kitty', 'fuzzel', 'matugen', 'rofi')


@lru_cache(maxsize=1)
def cached_nix_libraries():
    nixpkgs = hm = None
    for p in Path('/nix/store').glob('*-source'):
        if nixpkgs is None and (p / 'nixos/lib/eval-config.nix').is_file():
            nixpkgs = p / 'lib'
        if hm is None and (p / 'modules/lib/dag.nix').is_file():
            hm = p / 'modules/lib'
        if nixpkgs and hm:
            return nixpkgs, hm


def evaluate_desktop(home, config, cache, state, module=None):
    """Evaluate the actual module, substituting only HM's dependency interface.

    Use cached Nixpkgs/HM libraries when present, otherwise a small dependency
    interface. This is declaration evaluation, not a full module-system
    evaluation or derivation build. No daemon, network or store writes.
    """
    path = module or REPO / 'home/modules/desktop.nix'
    expression = r'''let
      lib = {
        genAttrs = names: f: builtins.listToAttrs
          (map (name: { inherit name; value = f name; }) names);
        escapeShellArg = s: "'" + builtins.replaceStrings ["'"] ["'\\''"] s + "'";
        hm.dag.entryBetween = before: after: data: { inherit before after data; };
      };
      config = {
        home.homeDirectory = HOME_PATH;
        xdg = { configHome = CONFIG_PATH; cacheHome = CACHE_PATH; stateHome = STATE_PATH; };
        lib.file.mkOutOfStoreSymlink = path: path;
      };
    in import MODULE_PATH { inherit config lib;
      pkgs = { python3 = PYTHON_PATH; kitty = KITTY_PATH; };
    }
    '''
    libraries = cached_nix_libraries()
    if libraries:
        start = expression.index('      lib = {')
        end = expression.index('      config = {')
        expression = (expression[:start] + '      baseLib = import ' + json.dumps(str(libraries[0])) + ';\n'
                      + '      lib = baseLib // { hm = import ' + json.dumps(str(libraries[1]))
                      + ' { inherit lib; }; };\n' + expression[end:])
    for key, value in dict(HOME_PATH=home, CONFIG_PATH=config, CACHE_PATH=cache,
                           STATE_PATH=state, MODULE_PATH=path,
                           PYTHON_PATH=Path(shutil.which('python3')).resolve().parents[1],
                           KITTY_PATH=Path(shutil.which('kitty')).resolve().parents[1]).items():
        expression = expression.replace(key, json.dumps(str(value)))
    # import accepts an absolute string path too.
    env = dict(os.environ, XDG_CACHE_HOME=str(Path(home).parent / 'nix-cache'))
    result = subprocess.run(['nix', 'eval', '--store', 'dummy://', '--offline',
                             '--impure', '--json', '--expr', expression],
                            env=env, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def targets(module, home, config):
    result = {Path(config) / k: v for k, v in module['xdg']['configFile'].items()}
    result.update({Path(home) / k: v for k, v in module['home']['file'].items()})
    return result


def validate_targets(files):
    paths = sorted(files, key=lambda p: len(p.parts))
    for i, path in enumerate(paths):
        for parent in paths[:i]:
            if path.is_relative_to(parent):
                raise ValueError(f'overlapping ownership: {parent} and {path}')
        if files[path].get('force') or files[path].get('recursive'):
            raise ValueError(f'force/recursive ownership is forbidden: {path}')


def git_paths(directory, revision=None):
    """List index paths, or baseline paths from a revision, never disk extras."""
    command = (['ls-files', '-z'] if revision is None else
               ['ls-tree', '-r', '-z', '--name-only', revision])
    output = subprocess.check_output(['git', '-C', str(REPO), *command, '--', directory])
    return tuple(Path(os.fsdecode(p)) for p in output.split(b'\0') if p)


def deploy_desktop(home, config, cache, module=None):
    checkout = home / 'nixos'
    # Select tracked paths from the index, but exercise the current repair's
    # bytes and symlinks. Untracked/ignored local backups are not fixture inputs.
    for rel in git_paths('dotfiles'):
        source, destination = REPO / rel, checkout / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            destination.symlink_to(os.readlink(source))
        else:
            shutil.copy2(source, destination)
    # Manual initialization can run explicitly from this reviewed checkout.
    shutil.copytree(REPO / 'scripts', checkout / 'scripts', symlinks=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.backup'))
    if module is None:
        files = {config / app: {'source': str(checkout / 'dotfiles' / app)} for app in APPS}
        files[home / '.local/share/mihao-theme'] = {'source': str(cache / 'generated')}
    else:
        files = targets(module, home, config)
    validate_targets(files)
    generation = home.parent / 'generation/home-files'
    intermediates = home.parent / 'out-of-store'
    intermediates.mkdir()
    for i, (target, entry) in enumerate(files.items()):
        source = intermediates / str(i)
        source.symlink_to(entry['source'], target_is_directory=True)
        store = generation / target.relative_to(home)
        store.parent.mkdir(parents=True, exist_ok=True)
        store.symlink_to(source, target_is_directory=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(store, target_is_directory=True)
    return checkout, generation, files


def snapshot(root):
    return {str(p.relative_to(root)): ('link', os.readlink(p)) if p.is_symlink()
            else ('file', p.read_bytes()) for p in root.rglob('*')
            if p.is_symlink() or p.is_file()}
