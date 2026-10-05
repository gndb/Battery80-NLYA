"""Entry routing tests: forbidden hardware actions are never called."""
import pathlib
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
import portable_entry as entry

class EntryTests(unittest.TestCase):
    def test_default_only_opens_setup(self):
        with patch.object(entry, 'setup_window', return_value=0) as setup, patch.object(entry, 'run_panel', side_effect=AssertionError):
            self.assertEqual(entry.dispatch([]), 0)
            setup.assert_called_once_with(False)
    def test_preview_routes_without_live_gate(self):
        with patch.object(entry, 'run_panel', return_value=0) as panel, patch.object(entry, 'validate_binding', side_effect=AssertionError):
            self.assertEqual(entry.dispatch(['--preview-smoke']), 0)
            panel.assert_called_once_with(['--preview-smoke'])
    def test_run_requires_binding_before_panel(self):
        with patch.object(entry, 'validate_binding', side_effect=RuntimeError('unbound')), patch.object(entry, 'run_panel', side_effect=AssertionError):
            with self.assertRaisesRegex(RuntimeError, 'unbound'): entry.dispatch(['--run'])
    def test_run_requires_record_before_panel(self):
        with patch.object(entry, 'validate_binding'), patch.object(entry, 'verify_policy_record', side_effect=RuntimeError('proof')), patch.object(entry, 'run_panel', side_effect=AssertionError):
            with self.assertRaisesRegex(RuntimeError, 'proof'): entry.dispatch(['--run'])
    def test_unknown_flags_rejected(self):
        with self.assertRaisesRegex(RuntimeError, '参数'): entry.dispatch(['--capture'])
    def test_child_session_arguments_still_restricted(self):
        with patch.object(entry, 'run_panel', return_value=2) as panel:
            self.assertEqual(entry.dispatch(['--ui', '../bad']), 2)
            panel.assert_called_once_with(['--ui', '../bad'])
