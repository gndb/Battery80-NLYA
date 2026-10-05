"""Portable deployment tests: files/synthetic bytes only, never hardware."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'tools'))
import portable_runtime as rt


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=BASE, prefix='fixture-')
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def test_binding_absent_refuses(self):
        with self.assertRaisesRegex(RuntimeError, '未绑定'):
            rt.validate_binding(self.root)
    def test_explicit_binding_validates_same_root(self):
        rt.bind_root(self.root)
        self.assertEqual(rt.validate_binding(self.root), self.root)
    def test_moved_binding_refused(self):
        rt.bind_root(self.root)
        data = json.loads((self.root / 'deployment.json').read_text(encoding='utf-8'))
        data['approved_root'] = str(self.root / 'other')
        (self.root / 'deployment.json').write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, '目录'):
            rt.validate_binding(self.root)
    def test_binding_overwrite_refused(self):
        rt.bind_root(self.root)
        with self.assertRaises(FileExistsError): rt.bind_root(self.root)
    def test_reparse_ancestor_rejected(self):
        with patch.object(rt, 'is_reparse', side_effect=lambda p: p == self.root.parent):
            with self.assertRaisesRegex(RuntimeError, '链接'):
                rt.safe_path(self.root)
    def test_policy_record_valid_and_not_running_firmware_attestation(self):
        data = rt.verify_policy_record()
        self.assertEqual(data['identity']['build'], 'C009A0')
        self.assertFalse(data['evidence']['running_full_image_hash_verified'])
    def test_missing_policy_record_refuses(self):
        with patch.object(rt, 'resource_root', return_value=self.root):
            with self.assertRaises(RuntimeError): rt.verify_policy_record()
    def test_changed_policy_record_refuses(self):
        (self.root/'assets').mkdir(); (self.root/'assets/verified-policy.json').write_text('{}',encoding='utf-8')
        with patch.object(rt, 'resource_root', return_value=self.root):
            with self.assertRaises(RuntimeError): rt.verify_policy_record()
    def test_policy_record_reparse_refused(self):
        path=rt.resource_root()/'assets/verified-policy.json'
        with patch.object(rt, 'is_reparse', side_effect=lambda p:p==path):
            with self.assertRaises(RuntimeError): rt.verify_policy_record()
    def test_ps_quote_blocks_apostrophe_injection(self):
        self.assertEqual(rt.ps_quote("a'; Write-Host BAD; '"), "'a''; Write-Host BAD; '''")
    def test_frozen_child_has_no_script_or_interpreter_flags(self):
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', 'BatteryPanel.exe'):
            self.assertEqual(rt.child_command('--ui', 'session-a.json'), ['BatteryPanel.exe', '--ui', 'session-a.json'])
    def test_unfrozen_child_uses_fixed_script(self):
        with patch.object(sys, 'frozen', False, create=True):
            cmd=rt.child_command('--ui', 'session-a.json')
        self.assertIn('-B', cmd); self.assertTrue(cmd[2].endswith('portable_entry.py'))
    def test_child_environment_is_independent_and_parent_unchanged(self):
        with patch.dict(rt.os.environ, {'PORTABLE_TEST': 'yes'}, clear=True):
            env=rt.child_environment()
            self.assertEqual(env['PYINSTALLER_RESET_ENVIRONMENT'], '1')
            self.assertNotIn('PYINSTALLER_RESET_ENVIRONMENT', rt.os.environ)
    def test_binding_validation_no_symlink_follow(self):
        rt.bind_root(self.root)
        with patch.object(rt, 'is_reparse', side_effect=lambda p: p == self.root/'deployment.json'):
            with self.assertRaises(RuntimeError): rt.validate_binding(self.root)


if __name__ == '__main__': unittest.main()
