#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from evidence_host_command_templates import template_qemu_json, template_reviewed_host_data


class evidence_host_command_tests(unittest.TestCase):
    def test_qemu_temp_is_templated_but_guest_temp_is_preserved(self):
        host = '/tm' + 'p/host-run/disk.img'
        guest = '/tm' + 'p/guest-file'
        data = json.dumps({'qemu_command': ['/usr/bin/qemu-system-x86_64', 'file=' + host],
                           'guest_output': guest}).encode()
        result, variables, skipped = template_qemu_json(data)
        obj = json.loads(result)
        self.assertTrue(obj['qemu_command'][1].startswith('file=${XOS_HOST_TEMP_'))
        self.assertEqual(obj['guest_output'], guest)
        self.assertEqual(len(variables), 1)
        self.assertEqual(skipped, [])

    def test_same_temp_root_outside_qemu_preserves_guest_value(self):
        root = '/tm' + 'p/shared'
        data = json.dumps({'qemu_command': ['/usr/bin/qemu-system-x86_64', root + '/disk'],
                           'guest_output': root + '/fixture'}).encode()
        result, variables, skipped = template_qemu_json(data)
        self.assertTrue(json.loads(result)['qemu_command'][1].startswith('${XOS_HOST_TEMP_'))
        self.assertEqual(json.loads(result)['guest_output'], root + '/fixture')
        self.assertEqual(len(variables), 1)
        self.assertEqual(skipped, [])

    def test_identical_value_outside_qemu_is_left_for_review(self):
        value = '/tm' + 'p/shared/disk'
        data = json.dumps({'qemu_command': ['/usr/bin/qemu-system-x86_64', value],
                           'guest_output': value}).encode()
        result, variables, skipped = template_qemu_json(data)
        self.assertEqual(result, data)
        self.assertEqual(variables, {})
        self.assertEqual(len(skipped), 1)

    def test_guest_command_and_plain_text_are_not_rewritten(self):
        guest = '/tm' + 'p/guest-file'
        data = json.dumps({'command': ['/bin/dash', guest]}).encode()
        self.assertEqual(template_qemu_json(data)[0], data)
        self.assertEqual(template_qemu_json(guest.encode())[0], guest.encode())

    def test_host_command_list_and_relative_qemu_are_templated(self):
        executable = '../runtime/qemu-prefix/opt/qemu/bin/qemu-system-x86_64'
        data = json.dumps({'command': [executable, '-drive', 'file=' + '/tm' + 'p/run/disk']}).encode()
        result, variables, _ = template_qemu_json(data)
        obj = json.loads(result)
        self.assertEqual(obj['command'][0], '${XOS_QEMU}')
        self.assertIn('XOS_QEMU', variables)
        self.assertTrue(obj['command'][2].startswith('file=${XOS_HOST_TEMP_'))

    def test_host_reference_command_does_not_change_test_input(self):
        root = '/tm' + 'p/host-run'
        data = json.dumps({'host_reference': [{'command': root + '/probe arg', 'input': root + '/fixture'}]}).encode()
        result, _, _ = template_qemu_json(data)
        obj = json.loads(result)
        self.assertTrue(obj['host_reference'][0]['command'].startswith('${XOS_HOST_TEMP_'))
        self.assertEqual(obj['host_reference'][0]['input'], root + '/fixture')

    def test_only_reviewed_host_log_gets_temp_template(self):
        value = b'/tm' + b'p/build-root/source.c'
        reviewed = 'docs/reports/modern_apps_20261029/build/python-build.log.gz'
        changed, variables = template_reviewed_host_data(value, reviewed)
        self.assertTrue(changed.startswith(b'${XOS_BUILD_TEMP_'))
        self.assertEqual(len(variables), 1)
        self.assertEqual(template_reviewed_host_data(value, 'guest/serial.log')[0], value)
        mac_temp = b'/private/var/fol' + b'ders/ab/session/file'
        self.assertTrue(template_reviewed_host_data(mac_temp, reviewed)[0].startswith(b'${XOS_BUILD_TEMP_'))

    def test_reviewed_host_error_does_not_change_guest_value(self):
        root = '/tm' + 'p/shared'
        error = 'Command work_disk_host ' + root + '/disk failed'
        data = json.dumps({'error': error, 'guest': root + '/fixture'}).encode()
        name = 'docs/reports/qt_e17_qualified_20261029/attempts/save-cases-1/report.json'
        changed, _ = template_reviewed_host_data(data, name)
        result = json.loads(changed)
        self.assertIn('${XOS_BUILD_TEMP_', result['error'])
        self.assertEqual(result['guest'], root + '/fixture')

    def test_reviewed_archive_argument_is_templated(self):
        value = '../runtime/xos-1024-images.tar.gz'
        data = json.dumps({'runs': [{'command': ['python3', value]}]}).encode()
        name = 'docs/reports/dash_c3_20261026/regression_summary.json'
        changed, _ = template_reviewed_host_data(data, name)
        self.assertEqual(json.loads(changed)['runs'][0]['command'][1], '${XOS_INPUT_ARCHIVE}')

    def test_reviewed_host_environment_is_scoped_to_exact_evidence(self):
        value = b'/work' + b'space/example/build /opt/codex/run' + b'times/version/bin/python'
        name = 'docs/reports/fb0_20261029/system_manifest.json.gz'
        changed, variables = template_reviewed_host_data(value, name)
        self.assertIn(b'${XOS_WORKSPACE_', changed)
        self.assertIn(b'${XOS_RUNTIME_', changed)
        self.assertEqual(len(variables), 2)
        self.assertEqual(template_reviewed_host_data(value, 'guest/serial.log')[0], value)

    def test_reviewed_document_template_preserves_markdown_delimiters(self):
        value = b'`' + b'/tm' + b'p/example` and ' + b'/tm' + b'p/other/file'
        name = 'docs/work_log/0063_input_edit_design.md'
        changed, _ = template_reviewed_host_data(value, name)
        self.assertIn(b'}` and ${XOS_DOC_TEMP_', changed)
        self.assertEqual(template_reviewed_host_data(value, 'docs/unreviewed.md')[0], value)


if __name__ == '__main__':
    unittest.main()
