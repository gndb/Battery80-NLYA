"""Lifecycle tests use a fake service API and never access hardware."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from quanta_bridge_probe import run_probe


class FakeApi:
    def __init__(self, fail=None, occupied=False):
        self.fail = fail
        self.occupied = occupied
        self.calls = []

    def check_absent(self):
        self.calls.append('check_absent')
        if self.occupied:
            raise RuntimeError('existing service or device')

    def create(self):
        self.calls.append('create')
        if self.fail == 'create':
            raise RuntimeError('create failed')

    def start(self):
        self.calls.append('start')
        if self.fail == 'start':
            raise RuntimeError('start blocked')

    def probe(self):
        self.calls.append('probe')
        if self.fail == 'probe':
            raise RuntimeError('open failed')
        return {'device_opened': True}

    def stop(self):
        self.calls.append('stop')
        if self.fail == 'stop':
            raise RuntimeError('stop failed')

    def delete(self):
        self.calls.append('delete')

    def close(self):
        self.calls.append('close')

    def verify_removed(self):
        self.calls.append('verify_removed')
        return {'service_absent': True, 'device_absent': True}


class LifecycleTests(unittest.TestCase):
    def test_success_closes_probe_then_unloads_and_deletes(self):
        api = FakeApi()
        result = run_probe(api, lambda r: None)
        self.assertTrue(result['probe_succeeded'])
        self.assertTrue(result['cleanup_succeeded'])
        self.assertEqual(api.calls, ['check_absent', 'create', 'start', 'probe',
                                     'stop', 'delete', 'close', 'verify_removed'])

    def test_blocked_start_removes_only_new_service(self):
        api = FakeApi(fail='start')
        result = run_probe(api, lambda r: None)
        self.assertFalse(result['probe_succeeded'])
        self.assertNotIn('probe', api.calls)
        self.assertIn('stop', api.calls)
        self.assertIn('delete', api.calls)

    def test_existing_service_is_not_modified(self):
        api = FakeApi(occupied=True)
        run_probe(api, lambda r: None)
        self.assertEqual(api.calls, ['check_absent', 'close'])

    def test_create_failure_does_not_delete_someone_elses_service(self):
        api = FakeApi(fail='create')
        run_probe(api, lambda r: None)
        self.assertEqual(api.calls, ['check_absent', 'create', 'close'])

    def test_failed_device_open_still_unloads_driver(self):
        api = FakeApi(fail='probe')
        result = run_probe(api, lambda r: None)
        self.assertFalse(result['probe_succeeded'])
        self.assertTrue(result['cleanup_succeeded'])
        self.assertLess(api.calls.index('stop'), api.calls.index('delete'))

    def test_failed_stop_keeps_service_for_explicit_recovery(self):
        api = FakeApi(fail='stop')
        result = run_probe(api, lambda r: None)
        self.assertTrue(result['probe_succeeded'])
        self.assertFalse(result['cleanup_succeeded'])
        self.assertNotIn('delete', api.calls)
        self.assertIn('close', api.calls)


if __name__ == '__main__':
    unittest.main()
