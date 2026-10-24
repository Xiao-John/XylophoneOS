# SPDX-License-Identifier: Apache-2.0
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from seed_diagnostics import diagnose, guest_command


class DiagnosticCases(unittest.TestCase):
    def test_driver_routing(self):
        self.assertEqual(guest_command('/usr/bin/gcc -c /src/a.c', ('/usr/bin/gcc',)),
                         'exec-driver /usr/bin/gcc -c /src/a.c')
        self.assertEqual(guest_command('/out/app'), 'exec-file /out/app')
        self.assertEqual(guest_command('exec-file /bin/as'), 'exec-file /bin/as')

    def test_load_failure_without_wait(self):
        result = diagnose(b'exec-file /bin/missing\nexec-file: error=-1\nsup> ')
        self.assertEqual(result['stage'], 'loader')
        self.assertIsNone(result['exit_code'])

    def test_fault_is_not_exit(self):
        result = diagnose('[wait] pid=9 kind=faulted code=14\nsup> ')
        self.assertEqual(result['stage'], 'runtime_faulted')

    def test_nonzero_error(self):
        result = diagnose('x.c:1: error: syntax\n[wait] pid=10 kind=exited code=1\nsup> ')
        self.assertEqual((result['stage'], result['exit_code']), ('compile', 1))

    def test_actual_paths_only(self):
        result = diagnose('Configured with: /Users/builder/gcc/configure\n'
                          '#include <...> search starts here:\n /sysroot/include\n'
                          'End of search list.\n /usr/libexec/gcc/cc1 /src/a.c\n'
                          '[wait] pid=9 kind=exited code=0\n')
        self.assertEqual(result['stage'], 'completed')
        self.assertEqual(result['include_search_paths'], ['/sysroot/include'])
        self.assertFalse(result['host_path_leaks'])
        self.assertEqual(len(result['child_commands']), 1)

    def test_host_search_leak(self):
        result = diagnose('#include <...> search starts here:\n /opt/homebrew/include\nEnd of search list.\n')
        self.assertTrue(result['host_path_leaks'])

    def test_basename_assembler_trace(self):
        result = diagnose(' as -o /out/a.o /tmp/cc.s\n[wait] pid=9 kind=exited code=0')
        self.assertEqual(result['child_commands'], ['as -o /out/a.o /tmp/cc.s'])

    def test_link_and_authority(self):
        self.assertEqual(diagnose('undefined reference to x')['stage'], 'link')
        self.assertEqual(diagnose('collect2: posix_spawn: Operation not permitted')['stage'],
                         'subprocess_authority_or_access')

    def test_echo_not_evidence(self):
        result = diagnose('exec-driver /bin/gcc /Users/echoed\n[wait] pid=9 kind=exited code=0')
        self.assertFalse(result['host_path_leaks'])
        self.assertFalse(result['child_commands'])


if __name__ == '__main__':
    unittest.main()
