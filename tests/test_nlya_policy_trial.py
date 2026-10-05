"""Fixed short round-trip against a simulated EC; never loads a driver."""
import copy
import importlib
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
try:
    trial = importlib.import_module('nlya_policy_trial')
except ModuleNotFoundError:
    trial = None


class Clock:
    def __init__(self):
        self.value = 0
    def now(self):
        return self.value
    def sleep(self, seconds):
        self.value += seconds


class Ec:
    def __init__(self):
        self.memory = {0x2000: 0x55, 0x2001: 0x70, 0x2002: 7,
                       0x0475: 0x3c, 0x0476: 0, 0x0442: 13,
                       0x03a6: 0, 0x0396: 100,
                       **{0x03fa + i: b for i, b in enumerate(b'C009A0')}}
        self.status = 0
        self.command = None
        self.payload = []
        self.writes = []
        self.fail_set_payload = False
        self.fail_cancel = False
        self.ignore_set = False
        self.events = []

    def read(self, port):
        if port == 0x6c:
            return self.status
        self.status = 0
        return self.reply

    def write(self, port, byte):
        self.writes.append((port, byte))
        if port == 0x6c:
            self.command, self.payload = byte, []
            if byte == 0x73:
                if not any(x.get('recovery_required') for x in self.events):
                    raise AssertionError('Missing durable recovery intent before setter')
            if byte == 0x74:
                if self.fail_cancel:
                    raise OSError('cancel transport failed')
                self.memory.update({0x0475: 0x3c, 0x0476: 0, 0x03a6: 0, 0x0442: 13})
            return
        self.payload.append(byte)
        if self.command == 0x92 and len(self.payload) == 2:
            self.reply = self.memory.get(self.payload[0] * 256 + byte, 0)
            self.status = 1
        if self.command == 0x73:
            if self.fail_set_payload:
                raise OSError('set payload failed')
            if not self.ignore_set:
                self.memory.update({0x0475: 0xd0, 0x0476: 0x20, 0x03a6: 2, 0x0442: 7})

    def control_commands(self):
        return [v for p, v in self.writes if p == 0x6c and v != 0x92]


def telemetry():
    return {'soc': 100, 'power_online': True, 'charging': False,
            'discharging': False, 'charge_rate_mw': 0, 'discharge_rate_mw': 0,
            'remaining_capacity_mwh': 63050, 'voltage_mv': 17058}


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(trial, 'Fixed policy round-trip implementation is missing')
        self.ec = Ec()
        self.clock = Clock()
        self.protocol = trial.TrialProtocol(self.ec.read, self.ec.write,
                                           self.clock.now, self.clock.sleep)
    def record(self, update):
        self.ec.events.append(copy.deepcopy(update))
    def run_trial(self, get_telemetry=telemetry):
        return trial.roundtrip(self.protocol, get_telemetry, self.record,
                               self.clock.now, self.clock.sleep)

    def test_fixed_80_payload_and_one_cancel_restore_original_disabled_state(self):
        result = self.run_trial()
        self.assertEqual(self.ec.control_commands(), [0x73, 0x74])
        i = self.ec.writes.index((0x6c, 0x73))
        self.assertEqual(self.ec.writes[i + 1], (0x68, 0x50))
        self.assertEqual(self.ec.memory[0x0475], 0x3c)
        self.assertTrue(result['restore_readback_verified'])
        self.assertFalse(result['recovery_required'])
        self.assertGreaterEqual(result['enabled_duration_seconds'], 20)
        self.assertLessEqual(result['enabled_duration_seconds'], 20.01)

    def test_existing_enabled_policy_is_preserved(self):
        self.ec.memory[0x0475] = 0xd0
        self.assertTrue(self.run_trial()['errors'])
        self.assertEqual(self.ec.control_commands(), [])

    def test_unrestorable_disabled_target_is_preserved(self):
        self.ec.memory[0x0475] = 61
        self.assertTrue(self.run_trial()['errors'])
        self.assertEqual(self.ec.control_commands(), [])

    def test_chip_revision_mismatch_prevents_setter(self):
        self.ec.memory[0x2002] = 2
        self.assertTrue(self.run_trial()['errors'])
        self.assertEqual(self.ec.control_commands(), [])

    def test_build_mismatch_prevents_setter(self):
        self.ec.memory[0x03fa] = ord('X')
        self.assertTrue(self.run_trial()['errors'])
        self.assertEqual(self.ec.control_commands(), [])

    def test_bad_baseline_telemetry_prevents_setter(self):
        t = telemetry(); t['charge_rate_mw'] = 0xffffffff
        self.assertTrue(self.run_trial(lambda: t)['errors'])
        self.assertEqual(self.ec.control_commands(), [])

    def test_existing_learn_request_prevents_setter(self):
        self.ec.memory[0x03a6] = 0x80
        self.assertTrue(self.run_trial()['errors'])
        self.assertEqual(self.ec.control_commands(), [])

    def test_adapter_removed_after_enable_cancels_early(self):
        count = 0
        def read():
            nonlocal count
            count += 1
            t = telemetry(); t['power_online'] = count < 3
            return t
        result = self.run_trial(read)
        self.assertTrue(result['errors'])
        self.assertLess(result['enabled_duration_seconds'], 20)
        self.assertEqual(self.ec.control_commands(), [0x73, 0x74])
        self.assertTrue(result['restore_readback_verified'])

    def test_failed_set_readback_cancels_without_retrying_set(self):
        self.ec.ignore_set = True
        result = self.run_trial()
        self.assertTrue(result['errors'])
        self.assertEqual(self.ec.control_commands(), [0x73, 0x74])
        self.assertTrue(result['restore_readback_verified'])

    def test_partial_set_transport_failure_still_attempts_cancel(self):
        self.ec.fail_set_payload = True
        result = self.run_trial()
        self.assertEqual(self.ec.control_commands(), [0x73, 0x74])
        self.assertTrue(result['errors'])
        self.assertTrue(result['restore_readback_verified'])

    def test_failed_cancel_is_not_repeated_and_requires_recovery(self):
        self.ec.fail_cancel = True
        result = self.run_trial()
        self.assertEqual(self.ec.control_commands(), [0x73, 0x74])
        self.assertTrue(result['recovery_required'])
        self.assertFalse(result['restore_readback_verified'])

    def test_process_exit_guard_recovers_owned_policy_once(self):
        self.ec.memory.update({0x0475: 0xd0, 0x0476: 0x20, 0x03a6: 2})
        result = trial.guard_restore(self.protocol, {'baseline_policy': {'0475': 60},
                    'recovery_required': True, 'cancel_attempted': False}, self.record)
        self.assertTrue(result['verified'])
        self.assertEqual(self.ec.control_commands(), [0x74])

    def test_guard_does_not_repeat_previously_failed_cancel(self):
        self.ec.memory[0x0475] = 0xd0
        result = trial.guard_restore(self.protocol, {'baseline_policy': {'0475': 60},
                    'recovery_required': True, 'cancel_attempted': True}, self.record)
        self.assertFalse(result['verified'])
        self.assertEqual(self.ec.control_commands(), [])

    def test_unknown_residual_output_prevents_any_control_command(self):
        self.ec.status = 1
        self.assertTrue(self.run_trial()['errors'])
        self.assertEqual(self.ec.control_commands(), [])


if __name__ == '__main__':
    unittest.main()
