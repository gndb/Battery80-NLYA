"""One fixed 20-second native-80 experiment, followed by cancellation.

THUNDEROBOT NLYA / TP181 / IT5570 rev07 / C009A0 only. No firmware writes,
arbitrary address inputs, persistent setup, or general-purpose EC setter.
The parent owns the temporary driver; the child controls the experiment.
"""
import ctypes
from ctypes import wintypes as W
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from inpout_status_probe import ROOT, PWSH, DRIVER_HASH, preflight, run_probe, utc
from nlya_pmc2_query import Pmc2Query, QueryApi, POLICY
from portable_runtime import verify_policy_record, ps_script

CANDIDATE_HASH = '8b3977b9d78bc9c8518f99f33fed8728b1ca00331802b2d990d4f431af2f70a3'
OUT = ROOT / 'evidence/ec/stage13'


class TrialProtocol:
    def __init__(self, read, write, now=time.monotonic, sleep=time.sleep):
        self.read, self.write, self.now, self.sleep = read, write, now, sleep
        self.queries = 0
        self.set_attempted = False
        self.cancel_attempted = False

    def reader(self):
        def send(port, value):
            if port == 0x6c:
                if self.queries >= 256:
                    raise RuntimeError('Fixed experiment query budget exhausted')
                self.queries += 1
            self.write(port, value)
        return Pmc2Query(self.read, send, self.now, self.sleep)

    def identity(self):
        result = self.reader().snapshot()
        if result['chip_revision'] != 7:
            raise RuntimeError('EC revision mismatch; no control')
        return result

    def policy(self):
        q = self.reader()
        return {f'{a:04X}': q.read_known(a) for a in POLICY}

    def enable_80(self):
        if self.set_attempted:
            raise RuntimeError('Setter cannot be retried')
        q = self.reader()
        deadline = self.now() + 1
        q.wait(False, deadline)
        self.set_attempted = True
        self.write(0x6c, 0x73)
        q.wait(False, deadline)
        self.write(0x68, 0x50)
        q.wait(False, deadline)

    def cancel(self):
        if self.cancel_attempted:
            raise RuntimeError('Cancellation cannot be retried')
        q = self.reader()
        deadline = self.now() + 1
        q.wait(False, deadline)
        self.cancel_attempted = True
        self.write(0x6c, 0x74)
        q.wait(False, deadline)


def validate_telemetry(t, ac_required=True):
    for key in ('soc', 'charge_rate_mw', 'discharge_rate_mw',
                'remaining_capacity_mwh', 'voltage_mv'):
        v = t.get(key)
        if isinstance(v, bool) or not isinstance(v, int) or v < 0 or v >= 0x7fffffff:
            raise RuntimeError('Invalid battery telemetry: ' + key)
    if not 0 <= t['soc'] <= 100 or t['voltage_mv'] == 0 or t['remaining_capacity_mwh'] == 0:
        raise RuntimeError('Invalid battery SOC/voltage/capacity')
    for key in ('power_online', 'charging', 'discharging'):
        if not isinstance(t.get(key), bool):
            raise RuntimeError('Invalid battery boolean: ' + key)
    if ac_required and not t['power_online']:
        raise RuntimeError('Adapter absent; experiment stopped')


def restored(p):
    return p['0475'] == 0x3c and not p['0476'] & 0xf0 and not p['03A6'] & 2


def roundtrip(protocol, get_telemetry, record, now=time.monotonic, sleep=time.sleep):
    state = {'started_utc': utc(), 'policy_set_attempted': False, 'cancel_attempted': False,
             'recovery_required': False, 'set_readback_verified': False,
             'restore_readback_verified': False, 'samples': [], 'errors': []}
    enabled_at = None
    def save(**update):
        state.update(update)
        record(state)
    def sample(phase):
        p = protocol.policy()
        t = get_telemetry()
        entry = {'utc': utc(), 'phase': phase, 'policy': p, 'telemetry': t}
        state['samples'].append(entry)
        record(state)
        validate_telemetry(t, ac_required=phase == 'enabled')
        if abs(p['0396'] - t['soc']) > 2:
            raise RuntimeError('EC and Windows SOC disagree')
        return p
    try:
        identity = protocol.identity()
        baseline = identity['groups'][-1]
        if not all(restored(p) and not p['03A6'] & 0x80 for p in identity['groups']):
            raise RuntimeError('Baseline is not default-disabled without Learn request')
        t = get_telemetry()
        validate_telemetry(t)
        if abs(baseline['0396'] - t['soc']) > 2:
            raise RuntimeError('Baseline SOC disagreement')
        # Durable intent comes before the first possibly effective control byte.
        save(baseline_identity=identity, baseline_policy=baseline, baseline_telemetry=t,
             recovery_required=True, policy_set_attempted=True)
        enabled_at = now()
        protocol.enable_80()
        deadline = enabled_at + 20
        while now() < deadline:
            p = sample('enabled')
            if p['0475'] != 0xd0:
                raise RuntimeError('80% setting readback mismatch; no setter retry')
            save(set_readback_verified=True)
            sleep(min(2, max(0, deadline - now())))
    except Exception as exc:
        state['errors'].append(str(exc))
    finally:
        if state['recovery_required']:
            try:
                # Mark an attempt before transport, including ambiguous failures.
                save(cancel_attempted=True, enabled_duration_seconds=now() - enabled_at
                     if enabled_at is not None else 0)
                protocol.cancel()
                confirmations = 0
                for _ in range(6):
                    p = sample('restored')
                    confirmations = confirmations + 1 if restored(p) else 0
                    if confirmations == 3:
                        save(restore_readback_verified=True, recovery_required=False)
                        break
                    sleep(2)
                if state['recovery_required']:
                    raise RuntimeError('Cancellation readback not verified')
            except Exception as exc:
                state['errors'].append('Restore: ' + str(exc))
        save(finished_utc=utc())
    return state


def guard_restore(protocol, child, record):
    """Independent confirmation; one cancel only if the child never attempted it."""
    result = {'verified': False, 'cancel_sent': False, 'errors': []}
    try:
        identity = protocol.identity()
        groups = identity['groups']
        if all(restored(p) for p in groups):
            result['verified'] = True
        elif (child.get('recovery_required') and not child.get('cancel_attempted')
              and child.get('baseline_policy', {}).get('0475') == 60
              and all(p['0475'] in (0x3c, 0xd0) for p in groups)):
            result['cancel_sent'] = True
            record({'guard_cancel_attempted': True})
            protocol.cancel()
            samples = [protocol.policy() for _ in range(3)]
            result['verified'] = all(restored(p) for p in samples)
            result['readback'] = samples
        else:
            raise RuntimeError('Guard cannot safely repeat cancel or overwrite another policy')
        if not result['verified']:
            raise RuntimeError('Guard restore readback failed')
    except Exception as exc:
        result['errors'].append(str(exc))
    record({'guard_restore': result})
    return result


def telemetry():
    script = r'''$ErrorActionPreference='Stop'; $b=@(Get-CimInstance Win32_Battery); $s=@(Get-CimInstance -Namespace root\wmi -ClassName BatteryStatus | Where-Object Active); if($b.Count -ne 1 -or $s.Count -ne 1){throw 'One active battery required'}; [ordered]@{soc=$b[0].EstimatedChargeRemaining;power_online=$s[0].PowerOnline;charging=$s[0].Charging;discharging=$s[0].Discharging;charge_rate_mw=$s[0].ChargeRate;discharge_rate_mw=$s[0].DischargeRate;remaining_capacity_mwh=$s[0].RemainingCapacity;voltage_mv=$s[0].Voltage} | ConvertTo-Json -Compress'''
    r = subprocess.run([PWSH, '-NoProfile', '-NonInteractive', '-Command', ps_script(script)],
                       capture_output=True, text=True, encoding='utf-8', timeout=4, creationflags=subprocess.CREATE_NO_WINDOW)
    if r.returncode:
        raise RuntimeError('Telemetry query failed: ' + r.stderr.strip())
    return json.loads(r.stdout)


def atomic_save(path, data):
    if path.parent.resolve() != OUT.resolve() or path.is_symlink():
        raise RuntimeError('Journal outside experiment directory')
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)


class TrialApi(QueryApi):
    def __init__(self, journal, setters_allowed):
        super().__init__(journal)
        self.setters_allowed = setters_allowed
        self.policy_writes = 0
        self.controls = []

    def io(self, handle, port, value=None):
        if port not in (0x68, 0x6c):
            raise RuntimeError('Non-PMC2 port refused')
        if value is not None and port == 0x6c:
            allowed = (0x92, 0x73, 0x74) if self.setters_allowed else (0x92, 0x74)
            if value not in allowed:
                raise RuntimeError('Command outside fixed trial')
            if value != 0x92:
                if value in self.controls or len(self.controls) >= 2:
                    raise RuntimeError('Control command cannot be repeated')
                self.controls.append(value)
                self.policy_writes += 1
        if value is None or port != 0x6c or value == 0x92:
            return super().io(handle, port, value)
        # Same inspected byte-write IOCTL as QueryApi, for 73/74 only.
        ioctl = self.kernel.DeviceIoControl
        ioctl.argtypes = [W.HANDLE, W.DWORD, ctypes.c_void_p, W.DWORD, ctypes.c_void_p,
                          W.DWORD, ctypes.POINTER(W.DWORD), ctypes.c_void_p]
        ioctl.restype = W.BOOL
        request = ctypes.create_string_buffer(16)
        request[0], request[1], request[2] = port, 0, value
        reply = ctypes.create_string_buffer(16)
        returned = W.DWORD()
        self.ioctl_calls += 1
        self.ec_commands += 1
        self.port_writes += 1
        entry = {'utc': utc(), 'port': hex(port), 'direction': 'write',
                 'value_sent': value, 'completed': False}
        self.trace.append(entry)
        self.journal()
        if not ioctl(handle, 0x9c402008, request, 16, reply, 16, ctypes.byref(returned), None):
            self.fail('Fixed control port IOCTL')
        if returned.value != 10:
            raise RuntimeError('Unexpected control IOCTL reply size')
        entry.update(completed=True, returned_bytes=returned.value)
        self.journal()

    @contextmanager
    def session(self, recovery=False):
        mutexes, handle = [], None
        create = self.kernel.CreateMutexW
        create.argtypes, create.restype = [ctypes.c_void_p, W.BOOL, W.LPCWSTR], W.HANDLE
        wait = self.kernel.WaitForSingleObject
        wait.argtypes, wait.restype = [W.HANDLE, W.DWORD], W.DWORD
        release = self.kernel.ReleaseMutex
        release.argtypes, release.restype = [W.HANDLE], W.BOOL
        try:
            for name in ('Global\\Access_EC', 'Global\\Access_ISABUS.HTP.Method',
                         'Global\\Battery80NLYAPMC2'):
                m = create(None, False, name)
                if not m:
                    self.fail('CreateMutex')
                status = wait(m, 1000)
                if status not in (0, 0x80):
                    self.close_handle(m)
                    raise RuntimeError('EC mutex unavailable')
                mutexes.append(m)
                if status == 0x80 and not recovery:
                    raise RuntimeError('Abandoned mutex; initial trial refused')
            if self.device_target() != r'\Device\inpoutx64':
                raise RuntimeError('Unexpected InpOut mapping')
            handle = self.create_file(r'\\.\inpoutx64', 0xc0000000, 3, None, 3, 0, None)
            if handle in (None, ctypes.c_void_p(-1).value):
                handle = None
                self.fail('Open fixed driver')
            yield TrialProtocol(lambda p: self.io(handle, p), lambda p, v: self.io(handle, p, v))
        finally:
            if handle:
                self.close_handle(handle)
            for m in reversed(mutexes):
                release(m)
                self.close_handle(m)


def check_preflight():
    verify_policy_record()  # Offline provenance integrity, not a running-image hash
    info = preflight()
    if not ctypes.WinDLL('shell32').IsUserAnAdmin():
        raise RuntimeError('Administrator token required')
    return info


def worker(path):
    state, api = {}, None
    def save(update=None):
        if update:
            state.update(update)
        if api:
            state.update(port_trace=api.trace, ioctl_calls=api.ioctl_calls,
                         ec_commands=api.ec_commands, policy_write_attempts=api.policy_writes)
        atomic_save(path, state)
    try:
        state['preflight'] = check_preflight()
        api = TrialApi(save, True)
        with api.session() as protocol:
            result = roundtrip(protocol, telemetry, save)
        save(result)
        return 0 if result['set_readback_verified'] and result['restore_readback_verified'] and not result['errors'] else 2
    except Exception as exc:
        save({'worker_error': str(exc), 'worker_finished_utc': utc()})
        return 2
    finally:
        if api:
            api.close()


class GuardApi(TrialApi):
    def __init__(self, journal, worker_path):
        super().__init__(journal, False)
        self.worker_path = worker_path

    def probe(self):
        child = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()),
                                 '--worker', self.worker_path.name], cwd=ROOT)
        interrupted = None
        try:
            child.wait(timeout=70)
        except BaseException as exc:
            interrupted = str(exc)
            child.terminate()
            child.wait(timeout=5)
        state = json.loads(self.worker_path.read_text(encoding='utf-8')) if self.worker_path.exists() else {}
        with self.session(recovery=True) as protocol:
            guard = guard_restore(protocol, state, lambda update: self.journal(update))
        return {'device_opened': True, 'status_valid': guard['verified'],
                'worker_exit_code': child.returncode, 'worker': state,
                'guard': guard, 'supervisor_interruption': interrupted}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    OUT.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        name = sys.argv[2]
        if Path(name).name != name or not name.startswith('trial-worker-') or not name.endswith('.json'):
            raise SystemExit('Fixed child journal name required')
        return worker(OUT / name)
    if sys.argv[1:] != ['--roundtrip']:
        raise SystemExit('Only --roundtrip is available: fixed80, 20 seconds, automatic cancel')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
    dest = OUT / ('trial-' + stamp + '.json')
    worker_path = OUT / ('trial-worker-' + stamp + '.json')
    info = {'scope': 'Fixed 20-second native80 experiment and cancellation',
            'saved_file': str(dest), 'worker_file': str(worker_path),
            'driver_sha256': DRIVER_HASH, 'candidate_sha256': CANDIDATE_HASH,
            'firmware_writes': 0, 'uefi_nvram_writes': 0, 'running_image_hash_verified': False}
    latest, api = {}, None
    def save(update=None):
        if update:
            latest.update(update)
        data = {**info, **latest}
        if api:
            data.update(guard_port_trace=api.trace, guard_ioctl_calls=api.ioctl_calls,
                        guard_control_attempts=api.policy_writes)
        if worker_path.exists():
            child = json.loads(worker_path.read_text(encoding='utf-8'))
            data['worker'] = child
            data['hardware_control_calls'] = child.get('policy_write_attempts', 0) + (api.policy_writes if api else 0)
        atomic_save(dest, data)
        return data
    try:
        info['preflight'] = check_preflight()
        api = GuardApi(save, worker_path)
        result = run_probe(api, save)
        data = save(result)
        p = result.get('probe', {})
        print(json.dumps({'saved_file': str(dest), 'probe_succeeded': result['probe_succeeded'],
                          'cleanup_succeeded': result['cleanup_succeeded'],
                          'worker_exit_code': p.get('worker_exit_code'),
                          'worker_errors': data.get('worker', {}).get('errors'),
                          'guard': p.get('guard'), 'errors': result['errors']}, indent=2))
        return 0 if result['probe_succeeded'] and result['cleanup_succeeded'] and p.get('worker_exit_code') == 0 else 2
    except Exception as exc:
        save({'errors': [str(exc)], 'finished_utc': utc()})
        print(json.dumps({'saved_file': str(dest), 'error': str(exc)}, indent=2))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
