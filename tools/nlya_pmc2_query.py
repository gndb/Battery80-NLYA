"""Fixed NLYA/TP181 PMC2 metadata query. No charge setters or flash operations.

0x92 is confirmed in the saved candidate: high/low address, one MOVX response.
Only three documented read-only chip registers, six build bytes and five traced RAM fields are
allowed. This does not prove that the running firmware equals the saved image.
"""
import ctypes
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import json
import sys
import time

from inpout_status_probe import NativeApi, ROOT, DRIVER, DRIVER_HASH, preflight, run_probe, utc

CHIP = (0x2000, 0x2001, 0x2002)
BUILD = tuple(range(0x03FA, 0x0400))
POLICY = (0x0475, 0x0476, 0x0442, 0x03A6, 0x0396)


class Pmc2Query:
    def __init__(self, read, write, now=time.monotonic, sleep=time.sleep):
        self.read, self.write, self.now, self.sleep = read, write, now, sleep
        self.queries = 0

    def wait(self, response, deadline):
        while True:
            status = self.read(0x6C)
            if status == 0xFF:
                raise RuntimeError('PMC2 status 0xFF; abort')
            if status & 1 and not response:
                raise RuntimeError('Unknown residual PMC2 output; not consumed')
            if not status & 2 and bool(status & 1) == response:
                return
            if self.now() >= deadline:
                raise RuntimeError('PMC2 handshake timeout; no retry')
            self.sleep(0.002)

    def read_known(self, address):
        if address not in CHIP + BUILD + POLICY:
            raise RuntimeError('Address outside fixed read allowlist')
        if self.queries >= 25:
            raise RuntimeError('Fixed query budget exhausted')
        deadline = self.now() + 1.0
        self.wait(False, deadline)
        self.queries += 1
        self.write(0x6C, 0x92)
        self.wait(False, deadline)
        self.write(0x68, address >> 8)
        self.wait(False, deadline)
        self.write(0x68, address & 255)
        self.wait(True, deadline)
        value = self.read(0x68)
        self.wait(False, deadline)
        return value

    def snapshot(self):
        chip = [self.read_known(a) for a in CHIP]
        identity = chip[0] * 256 + chip[1]
        if identity != 0x5570:
            raise RuntimeError('Unexpected EC chip: ' + hex(identity) + '; policy queries skipped')
        builds = [bytes(self.read_known(a) for a in BUILD) for _ in range(2)]
        if builds != [b'C009A0', b'C009A0']:
            raise RuntimeError('Unexpected or inconsistent runtime build: ' + repr(builds) + '; policy queries skipped')
        groups = [{f'{a:04X}': self.read_known(a) for a in POLICY} for _ in range(2)]
        return {'chip_id': hex(identity), 'chip_revision': chip[2], 'groups': groups,
                'runtime_build_identifier': builds[0].decode('ascii'),
                'runtime_build_identifier_matched': True, 'running_image_hash_verified': False,
                'policy_target_stable': groups[0]['0475'] == groups[1]['0475'],
                'candidate_policy_interpretation': {
                    'enabled': bool(groups[-1]['0475'] & 128),
                    'target': groups[-1]['0475'] & 127,
                    'branch_high_nibble': hex(groups[-1]['0476'] & 0xF0),
                    'learn_request_bit': bool(groups[-1]['03A6'] & 2),
                    'soc': groups[-1]['0396']},
                'firmware_identity_verified': False, 'charge_policy_writes': 0}


class QueryApi(NativeApi):
    def __init__(self, journal):
        super().__init__()
        self.journal = journal
        self.trace = []
        self.ec_commands = 0
        self.port_writes = 0

    def io(self, handle, port, value=None):
        if (value is None and port not in (0x68, 0x6C)) or (value is not None and port not in (0x68, 0x6C)):
            raise RuntimeError('Port outside fixed PMC2 transport')
        if value is not None and port == 0x6C and value != 0x92:
            raise RuntimeError('Only the confirmed query command is allowed')
        ioctl = self.kernel.DeviceIoControl
        ioctl.argtypes = [W.HANDLE, W.DWORD, ctypes.c_void_p, W.DWORD, ctypes.c_void_p,
                          W.DWORD, ctypes.POINTER(W.DWORD), ctypes.c_void_p]
        ioctl.restype = W.BOOL
        request = ctypes.create_string_buffer(16)
        request[0], request[1] = port, 0
        reply = ctypes.create_string_buffer(16)
        returned = W.DWORD()
        code = 0x9C402004 if value is None else 0x9C402008
        if value is not None:
            request[2] = value
            self.port_writes += 1
            if port == 0x6C:
                self.ec_commands += 1
        self.ioctl_calls += 1
        entry = {'utc': utc(), 'port': hex(port), 'direction': 'read' if value is None else 'write',
                 'value_sent': value, 'completed': False}
        self.trace.append(entry)
        self.journal()
        if not ioctl(handle, code, request, 16, reply, 16, ctypes.byref(returned), None):
            self.fail('Fixed PMC2 port IOCTL')
        # The official byte-write branch reports 10 bytes; provide a 16-byte
        # initialized buffer, avoiding the driver's bad small-buffer behavior.
        expected = 1 if value is None else 10
        if returned.value != expected:
            raise RuntimeError('Unexpected byte IOCTL length: ' + str(returned.value))
        entry.update(completed=True, returned_bytes=returned.value)
        if value is None:
            entry['value_read'] = reply.raw[0]
        self.journal()
        return reply.raw[0] if value is None else None

    def probe(self):
        mutexes = []
        handle = None
        create_mutex = self.kernel.CreateMutexW
        create_mutex.argtypes, create_mutex.restype = [ctypes.c_void_p, W.BOOL, W.LPCWSTR], W.HANDLE
        wait = self.kernel.WaitForSingleObject
        wait.argtypes, wait.restype = [W.HANDLE, W.DWORD], W.DWORD
        release = self.kernel.ReleaseMutex
        release.argtypes, release.restype = [W.HANDLE], W.BOOL
        try:
            for name in ('Global\\Access_EC', 'Global\\Access_ISABUS.HTP.Method', 'Global\\Battery80NLYAPMC2'):
                m = create_mutex(None, False, name)
                if not m:
                    self.fail('CreateMutex')
                state = wait(m, 1000)
                if state not in (0, 0x80):
                    self.close_handle(m)
                    raise RuntimeError('EC mutex unavailable; no query')
                mutexes.append(m)
                if state == 0x80:
                    raise RuntimeError('Abandoned EC mutex; state uncertain, no query')
            if self.device_target() != r'\Device\inpoutx64':
                raise RuntimeError('Unexpected InpOut device mapping')
            handle = self.create_file(r'\\.\inpoutx64', 0xC0000000, 3, None, 3, 0, None)
            if handle in (None, ctypes.c_void_p(-1).value):
                handle = None
                self.fail('Open fixed InpOut device')
            snapshot = Pmc2Query(lambda p: self.io(handle, p), lambda p, v: self.io(handle, p, v)).snapshot()
            return {'device_opened': True, 'status_valid': True, **snapshot}
        finally:
            if handle:
                self.close_handle(handle)
            for m in reversed(mutexes):
                release(m)
                self.close_handle(m)


def main():
    if sys.argv[1:] != ['--capture']:
        raise SystemExit('Fixed metadata query only: --capture')
    sys.stdout.reconfigure(encoding='utf-8')
    folder = ROOT / 'evidence/ec/stage11'
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / ('pmc2-query-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    info = {'scope': 'Fixed 0x92 readback queries only, temporary signed InpOut driver',
            'driver_sha256': DRIVER_HASH, 'saved_file': str(dest), 'hardware_control_calls': 0,
            'charge_policy_writes': 0, 'firmware_writes': 0, 'firmware_identity_verified': False,
            'collector_version': 2, 'maximum_query_count': 25}
    api = None
    latest = {}
    def save(result=None):
        if result is not None:
            latest.update(result)
        data = {**info, **latest}
        if api is not None:
            data.update(ioctl_calls=api.ioctl_calls, ec_commands=api.ec_commands,
                        port_writes=api.port_writes, port_trace=api.trace)
        temp = dest.with_suffix('.tmp')
        temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
        temp.replace(dest)
        return data
    try:
        candidate = ROOT / 'evidence/ec/NLYA-EC-candidate.bin'
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != '8b3977b9d78bc9c8518f99f33fed8728b1ca00331802b2d990d4f431af2f70a3':
            raise RuntimeError('Candidate hash mismatch; no query')
        info['preflight'] = preflight()
        info['elevated'] = bool(ctypes.WinDLL('shell32').IsUserAnAdmin())
        if not info['elevated']:
            raise RuntimeError('Administrator token required; no changes made')
        api = QueryApi(save)
        result = run_probe(api, save)
        data = save(result)
        print(json.dumps(data, indent=2))
        return 0 if result['probe_succeeded'] and result['cleanup_succeeded'] else 2
    except Exception as exc:
        data = save({'errors': [str(exc)], 'finished_utc': utc()})
        print(json.dumps(data, indent=2))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
