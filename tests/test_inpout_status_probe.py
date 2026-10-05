"""Fixed status probe lifecycle; fake services only, never real hardware."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from inpout_status_probe import run_probe
from test_quanta_bridge_probe import FakeApi


class StatusApi(FakeApi):
    ioctl_calls = 0

    def probe(self):
        self.calls.append('probe')
        self.ioctl_calls = 1
        if self.fail == 'ioctl':
            raise RuntimeError('status ioctl failed')
        return {'device_opened': True, 'ioctl_calls': 1,
                'status_valid': self.fail != 'invalid_status'}


class StatusLifecycleTests(unittest.TestCase):
    def test_success_reads_status_then_unloads(self):
        api = StatusApi()
        result = run_probe(api, lambda r: None)
        self.assertTrue(result['probe_succeeded'])
        self.assertEqual(result['ioctl_calls'], 1)
        self.assertTrue(result['cleanup_succeeded'])
        self.assertEqual(result['ec_commands'], 0)

    def test_failed_ioctl_records_attempt_and_unloads(self):
        api = StatusApi(fail='ioctl')
        result = run_probe(api, lambda r: None)
        self.assertEqual(result['ioctl_calls'], 1)
        self.assertFalse(result['probe_succeeded'])
        self.assertTrue(result['cleanup_succeeded'])

    def test_ff_is_not_successful_ec_detection(self):
        api = StatusApi(fail='invalid_status')
        result = run_probe(api, lambda r: None)
        self.assertFalse(result['probe_succeeded'])
        self.assertTrue(result['cleanup_succeeded'])

    def test_rejected_load_never_issues_ioctl(self):
        api = StatusApi(fail='start')
        result = run_probe(api, lambda r: None)
        self.assertEqual(result['ioctl_calls'], 0)
        self.assertNotIn('probe', api.calls)
        self.assertTrue(result['cleanup_succeeded'])


if __name__ == '__main__':
    unittest.main()
