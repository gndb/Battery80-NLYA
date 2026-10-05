"""Protocol safety tests with an EC simulator; no hardware access."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from nlya_pmc2_query import Pmc2Query


class Ec:
    def __init__(self, memory=None, status=0):
        self.memory = memory or {}
        self.status = status
        self.payload = []
        self.writes = []
        self.data_reads = 0
        self.reply = 0

    def read(self, port):
        if port == 0x6C:
            return self.status
        self.data_reads += 1
        self.status = 0
        return self.reply

    def write(self, port, value):
        self.writes.append((port, value))
        if port == 0x6C:
            self.payload = []
        else:
            self.payload.append(value)
            if len(self.payload) == 2:
                address = self.payload[0] * 256 + value
                self.reply = self.memory.get(address, 0)
                self.status = 1


class ProtocolTests(unittest.TestCase):
    @staticmethod
    def build_memory():
        return {0x03FA + i: b for i, b in enumerate(b'C009A0')}

    def test_reads_chip_then_two_policy_groups_using_only_92(self):
        ec = Ec({0x2000: 0x55, 0x2001: 0x70, 0x2002: 2,
                 0x0475: 60, 0x0396: 97, **self.build_memory()})
        result = Pmc2Query(ec.read, ec.write).snapshot()
        self.assertEqual(result['chip_id'], '0x5570')
        self.assertEqual(ec.data_reads, 25)
        self.assertTrue(result['runtime_build_identifier_matched'])
        self.assertTrue(result['policy_target_stable'])
        self.assertEqual(ec.writes[:3], [(0x6C, 0x92), (0x68, 0x20), (0x68, 0)])
        self.assertEqual([v for p, v in ec.writes if p == 0x6C], [0x92] * 25)

    def test_wrong_build_stops_before_policy_query(self):
        ec = Ec({0x2000: 0x55, 0x2001: 0x70})
        with self.assertRaisesRegex(RuntimeError, 'build'):
            Pmc2Query(ec.read, ec.write).snapshot()
        self.assertEqual(ec.data_reads, 15)

    def test_unknown_output_aborts_without_consuming_or_writing(self):
        ec = Ec(status=1)
        with self.assertRaisesRegex(RuntimeError, 'residual'):
            Pmc2Query(ec.read, ec.write).snapshot()
        self.assertEqual(ec.writes, [])
        self.assertEqual(ec.data_reads, 0)

    def test_ff_port_aborts_without_writes(self):
        ec = Ec(status=255)
        with self.assertRaisesRegex(RuntimeError, '0xFF'):
            Pmc2Query(ec.read, ec.write).snapshot()
        self.assertEqual(ec.writes, [])

    def test_wrong_chip_stops_before_policy_addresses(self):
        ec = Ec({0x2000: 0x55, 0x2001: 0x71})
        with self.assertRaisesRegex(RuntimeError, 'chip'):
            Pmc2Query(ec.read, ec.write).snapshot()
        self.assertEqual(ec.data_reads, 3)

    def test_unknown_address_rejected_before_io(self):
        ec = Ec()
        with self.assertRaisesRegex(RuntimeError, 'allowlist'):
            Pmc2Query(ec.read, ec.write).read_known(0x1234)
        self.assertEqual(ec.writes, [])

    def test_busy_port_times_out_without_writes(self):
        ec = Ec(status=2)
        tick = iter([0, 0, 2])
        with self.assertRaisesRegex(RuntimeError, 'timeout'):
            Pmc2Query(ec.read, ec.write, now=lambda: next(tick), sleep=lambda _: None).snapshot()
        self.assertEqual(ec.writes, [])


if __name__ == '__main__':
    unittest.main()
