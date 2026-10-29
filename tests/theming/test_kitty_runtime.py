"""Kitty signal targeting with a disposable /proc and all signals mocked."""
import os
from pathlib import Path
import signal
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from theming.kitty_runtime import signal_instances
from theming.model import ThemeError


class KittySignals(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='kitty-proc-')
        self.addCleanup(self.tmp.cleanup)
        self.proc = Path(self.tmp.name)
        self.commands = {}
        self.child = SimpleNamespace(cmdline_of_pid=lambda pid: self.commands[pid])
        self.utils = SimpleNamespace(get_all_processes=lambda: sorted(self.commands),
            is_kitty_gui_cmdline=Mock(side_effect=lambda name, *args:
                not args or not args[0].startswith(('+', '@'))))
        self.modules = patch.dict(sys.modules, {'kitty.child': self.child, 'kitty.utils': self.utils})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def process(self, pid, *command, handler=True, blocked=False):
        self.commands[pid] = command
        directory = self.proc / str(pid)
        directory.mkdir()
        mask = 1 << (signal.SIGUSR1 - 1) if handler else 0
        blocked_mask = 1 << (signal.SIGUSR1 - 1) if blocked else 0
        (directory / 'status').write_text(f'SigCgt:\t{mask:016x}\nSigBlk:\t{blocked_mask:016x}\n')

    def test_native_and_nix_wrapped_guis_only(self):
        self.process(100, 'kitty')
        self.process(101, '/nix/store/pkg/bin/.kitty-wrapped', '-e', 'yazi')
        self.process(102, '/nix/store/pkg/bin/kitty-wrapped', '--single-instance')
        self.process(103, 'kitty', '+runpy', 'helper')
        self.process(104, 'kitty', '@', 'ls')
        self.process(105, 'kitten', 'themes')
        self.process(106, 'kitty', handler=False)
        self.process(107, 'another-kitty-program')
        with patch('theming.kitty_runtime.os.kill') as kill:
            result = signal_instances(self.proc)
        self.assertEqual(result, dict(signaled=[100, 101, 102], skipped=[106], vanished=[]))
        self.assertEqual(kill.call_args_list, [((pid, signal.SIGUSR1),) for pid in (100, 101, 102)])
        self.utils.is_kitty_gui_cmdline.assert_any_call('kitty', '-e', 'yazi')

    def test_other_users_never_signaled(self):
        self.process(100, 'kitty')
        with patch('theming.kitty_runtime.os.getuid', return_value=os.getuid() + 1), \
             patch('theming.kitty_runtime.os.kill') as kill:
            self.assertEqual(signal_instances(self.proc)['signaled'], [])
        kill.assert_not_called()

    def test_linux_signalfd_receiver_with_no_traditional_handler(self):
        self.process(100, 'kitty', handler=False, blocked=True)
        with patch('theming.kitty_runtime.os.kill') as kill:
            self.assertEqual(signal_instances(self.proc)['signaled'], [100])
        kill.assert_called_once_with(100, signal.SIGUSR1)

    def test_disappearing_process_does_not_prevent_other_reload(self):
        self.process(100, 'kitty')
        self.process(101, 'kitty')
        with patch('theming.kitty_runtime.os.kill', side_effect=[ProcessLookupError(), None]):
            self.assertEqual(signal_instances(self.proc),
                             dict(signaled=[101], skipped=[], vanished=[100]))

    def test_permission_failure_is_not_reported_as_delivery(self):
        self.process(100, 'kitty')
        with patch('theming.kitty_runtime.os.kill', side_effect=PermissionError('denied')):
            with self.assertRaisesRegex(ThemeError, 'delivery failed for PID 100'):
                signal_instances(self.proc)

    def test_each_process_configuration_is_verified_before_reload(self):
        self.process(100, 'kitty', '--config', '/fixture/kitty.conf', '-o', 'font_size=23')
        options = SimpleNamespace(config=['/fixture/kitty.conf'], override=['font_size=23'])
        modules = {'kitty.cli': SimpleNamespace(parse_args=Mock(return_value=(options, []))),
                   'kitty.cli_stub': SimpleNamespace(CLIOptions=object)}
        events = []
        with patch.dict(sys.modules, modules), \
             patch('theming.kitty_runtime.verify_effective', side_effect=lambda *a, **kw: events.append(('verify', a, kw))), \
             patch('theming.kitty_runtime.os.kill', side_effect=lambda *a: events.append(('signal', a))):
            result = signal_instances(self.proc, output='/fixture/generated/kitty.conf')
        self.assertEqual(result['signaled'], [100])
        self.assertEqual(events, [
            ('verify', ('PID 100', '/fixture/generated/kitty.conf'),
             dict(config_paths=options.config, overrides=options.override)),
            ('signal', (100, signal.SIGUSR1))])

    def test_existing_process_palette_conflict_prevents_signal_and_success(self):
        self.process(100, 'kitty', '-o', 'background=red')
        options = SimpleNamespace(config=[], override=['background=red'])
        modules = {'kitty.cli': SimpleNamespace(parse_args=Mock(return_value=(options, []))),
                   'kitty.cli_stub': SimpleNamespace(CLIOptions=object)}
        with patch.dict(sys.modules, modules), \
             patch('theming.kitty_runtime.verify_effective', side_effect=ThemeError('effective palette differs')), \
             patch('theming.kitty_runtime.os.kill') as kill:
            with self.assertRaisesRegex(ThemeError, 'Kitty PID 100.*effective palette differs'):
                signal_instances(self.proc, output='/fixture/generated/kitty.conf')
        kill.assert_not_called()


if __name__ == '__main__':
    unittest.main()
