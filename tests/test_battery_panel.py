"""Panel policy tests use a simulated EC; no driver or WMI access."""
import copy
import pathlib
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from test_nlya_policy_trial import Ec, Clock, telemetry
try:
    import battery_panel_core as core
except ModuleNotFoundError:
    core = None


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(core, 'Panel backend is missing')
        self.ec, self.clock, self.state = Ec(), Clock(), {}
        self.ec.memory.update({0x0340: 9, 0x03a4: 1})
        self.p = core.PanelProtocol(self.ec.read, self.ec.write, self.clock.now, self.clock.sleep)
    def save(self):
        self.ec.events.append(copy.deepcopy(self.state))
    def operate(self, action, t=None, allow=False):
        return core.operate(self.p, action, lambda: t or telemetry(), self.state,
                            self.save, allow_high_soc=allow, sleep=self.clock.sleep)
    def test_status_reads_actual_policy_and_adapter_without_control(self):
        s = self.operate('status')
        self.assertFalse(s['enabled'])
        self.assertTrue(s['ec_adapter_present'])
        self.assertEqual(self.ec.control_commands(), [])
    def test_high_soc_requires_explicit_acknowledgement(self):
        with self.assertRaisesRegex(RuntimeError, 'active discharge'):
            self.operate('enable')
        self.assertEqual(self.ec.control_commands(), [])
    def test_enable_readback_and_close_leave_native_policy_enabled(self):
        s = self.operate('enable', allow=True)
        self.assertTrue(s['enabled'])
        self.assertEqual(s['target'], 80)
        self.assertFalse(self.state['recovery_required'])
        self.assertTrue(self.state['keep_after_close'])
        self.assertEqual(self.ec.control_commands(), [0x73])
    def test_enable_at_low_soc_without_discharge_ack(self):
        self.ec.memory[0x0396] = 76
        t = telemetry(); t['soc'] = 76
        self.assertTrue(self.operate('enable', t)['enabled'])
    def test_readback_mismatch_triggers_one_cancel_no_enable_retry(self):
        self.ec.ignore_set = True
        with self.assertRaisesRegex(RuntimeError, 'readback'):
            self.operate('enable', allow=True)
        self.assertEqual(self.ec.control_commands(), [0x73, 0x74])
        self.assertFalse(self.state['recovery_required'])
    def test_failed_cancel_blocks_repeated_writes(self):
        self.ec.ignore_set = True; self.ec.fail_cancel = True
        with self.assertRaises(RuntimeError): self.operate('enable', allow=True)
        before = len(self.ec.writes)
        with self.assertRaises(RuntimeError): self.operate('disable')
        with self.assertRaises(RuntimeError): self.operate('status')
        self.assertEqual(len(self.ec.writes), before)
        self.assertEqual(self.ec.control_commands(), [0x73, 0x74])
        self.assertTrue(self.state['recovery_required'])
    def test_foreign_target_not_overwritten(self):
        self.ec.memory[0x0475] = 0xbc
        with self.assertRaises(RuntimeError): self.operate('enable', allow=True)
        with self.assertRaises(RuntimeError): self.operate('disable')
        self.assertEqual(self.ec.control_commands(), [])
    def test_cancel_verifies_default_policy_three_times(self):
        self.ec.memory.update({0x0475: 0xd0, 0x0476: 0x20, 0x03a6: 2})
        s = self.operate('disable')
        self.assertFalse(s['enabled'])
        self.assertFalse(self.state['recovery_required'])
        self.assertEqual(self.ec.control_commands(), [0x74])
    def test_already_enabled_does_not_repeat_setter(self):
        self.ec.memory[0x0475] = 0xd0
        self.assertTrue(self.operate('enable', allow=True)['enabled'])
        self.assertEqual(self.ec.control_commands(), [])
    def test_windows_source_false_does_not_mean_ec_adapter_absent(self):
        t = telemetry(); t['power_online'] = False
        self.assertTrue(self.operate('status', t)['ec_adapter_present'])
        with self.assertRaises(RuntimeError): self.operate('enable', t, True)
        self.assertEqual(self.ec.control_commands(), [])
    def test_ec_adapter_absent_blocks_enable(self):
        self.ec.memory[0x0340] = 1
        with self.assertRaises(RuntimeError): self.operate('enable', allow=True)
        self.assertEqual(self.ec.control_commands(), [])
    def test_invalid_telemetry_blocks_enable_but_not_recovery(self):
        t = telemetry(); t['charge_rate_mw'] = 0xffffffff
        with self.assertRaises(RuntimeError): self.operate('enable', t, True)
        self.assertEqual(self.ec.control_commands(), [])
        self.ec.memory[0x0475] = 0xd0
        self.assertFalse(self.operate('disable', t)['enabled'])
    def test_revision_mismatch_no_control(self):
        self.ec.memory[0x2002] = 3
        with self.assertRaises(RuntimeError): self.operate('enable', allow=True)
        self.assertEqual(self.ec.control_commands(), [])
    def test_unknown_address_is_refused(self):
        with self.assertRaises(RuntimeError): self.p.reader().read_known(0x0477)
        self.assertEqual(self.ec.writes, [])
    def test_partial_control_transport_is_not_blindly_cancelled(self):
        self.ec.fail_set_payload = True
        with self.assertRaises(OSError):
            self.operate('enable', allow=True)
        self.assertEqual(self.ec.control_commands(), [0x73])
        self.assertTrue(self.state['recovery_required'])
        self.assertFalse(self.state['transport_safe'])
        before = len(self.ec.writes)
        with self.assertRaises(RuntimeError): self.operate('status')
        self.assertEqual(len(self.ec.writes), before)
    def test_partial_status_query_latches_fault_before_next_refresh(self):
        original = self.ec.write
        def fail(port, byte):
            if port == 0x68: raise OSError('partial query')
            original(port, byte)
        self.p = core.PanelProtocol(self.ec.read, fail, self.clock.now, self.clock.sleep)
        with self.assertRaises(OSError): self.operate('status')
        self.assertTrue(self.state.get('transport_fault'))
        fresh = core.PanelProtocol(self.ec.read, self.ec.write, self.clock.now, self.clock.sleep)
        before = len(self.ec.writes)
        with self.assertRaises(RuntimeError):
            core.operate(fresh, 'status', telemetry, self.state, self.save)
        self.assertEqual(len(self.ec.writes), before)


class JournalTests(unittest.TestCase):
    def test_transient_replace_denial_retries_file_only(self):
        import battery_panel as panel
        panel.checked_folder()  # Fresh checkout: project-local output directory only.
        path = panel.OUT / 'test-atomic-save.json'
        original = pathlib.Path.replace
        attempts = []
        def replace(p, target):
            attempts.append(1)
            if len(attempts) < 3:
                raise PermissionError(13, 'temporary replacement lock')
            return original(p, target)
        try:
            with patch.object(pathlib.Path, 'replace', replace), patch.object(panel.time, 'sleep'):
                panel.save_json(path, {'test': True})
            self.assertEqual(len(attempts), 3)
            self.assertTrue(panel.load_json(path)['test'])
        finally:
            path.unlink(missing_ok=True)
            path.with_suffix('.tmp').unlink(missing_ok=True)
    def test_supervisor_success_requires_closed_ui_valid_read_and_zero_exit(self):
        import battery_panel as panel
        good = {'ui_closed_utc': 'test', 'last_read_valid': True, 'refresh_count': 1}
        self.assertTrue(panel.normal_exit_verified(good, 0))
        for changed, code in [({}, 0), (good, 2), ({**good, 'transport_fault': True}, 0),
                              ({**good, 'recovery_required': True}, 0),
                              ({**good, 'last_read_valid': False}, 0)]:
            self.assertFalse(panel.normal_exit_verified(changed, code))
    def test_lifecycle_log_failure_does_not_skip_service_delete(self):
        from test_inpout_status_probe import FakeApi
        from inpout_status_probe import run_probe
        api = FakeApi()
        def save(data):
            if any(x['event'] == 'driver_confirmed_stopped' for x in data['events']):
                raise PermissionError('cleanup journal locked')
        result = run_probe(api, save)
        self.assertIn('delete', api.calls)
        self.assertTrue(result['cleanup_succeeded'])
        self.assertTrue(result['errors'])

if __name__ == '__main__': unittest.main()
