"""Temporary, fixed OEM driver load/open/unload probe. No EC or IOCTL calls.

Installation authorization: user allowed installing/loading drivers on 2026-10-05.
Only a demand-start kernel-driver registration is created outside the project.
"""
import ctypes
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ROOT = Path(r'C:\Battery80-NLYA')
DRIVER = ROOT / 'reference/oem-downloads/NLYA-ControlCenter-3.0.0.29/app/ControlCenter64.sys'
DRIVER_HASH = '29eff643548103a94873608d88be2ea0659556aa3288c591538d5f9a198de6f9'
SERVICE = 'Battery80QuantaProbe'
DEVICE = 'CCDRV1'
PWSH = r'C:\Program Files\PowerShell\7\pwsh.exe'


def utc():
    return datetime.now(timezone.utc).isoformat()


def run_probe(api, save):
    result = {'started_utc': utc(), 'service': SERVICE, 'probe_succeeded': False,
              'cleanup_succeeded': False, 'created': False, 'started': False,
              'ioctl_calls': 0, 'ec_commands': 0, 'hardware_control_calls': 0,
              'events': [], 'errors': [], 'cleanup_errors': []}
    def event(name):
        result['events'].append({'utc': utc(), 'event': name})
        save(result)
    try:
        api.check_absent()
        event('preexisting_service_and_device_absent')
        api.create()
        result['created'] = True
        event('demand_start_kernel_driver_registered')
        api.start()
        result['started'] = True
        event('driver_running')
        result['probe'] = api.probe()
        result['probe_succeeded'] = bool(result['probe'].get('device_opened'))
        event('device_opened_and_closed_without_ioctl')
    except Exception as exc:
        result['errors'].append(str(exc))
        event('probe_stopped')
    finally:
        try:
            if result['created']:
                # Also query/stop after StartService failure in case it partially started.
                api.stop()
                event('driver_confirmed_stopped')
                api.delete()
                event('new_driver_registration_deleted')
        except Exception as exc:
            result['cleanup_errors'].append(str(exc))
        finally:
            api.close()
        if result['created'] and not result['cleanup_errors']:
            try:
                result['removed'] = api.verify_removed()
                result['cleanup_succeeded'] = all(result['removed'].values())
                if not result['cleanup_succeeded']:
                    result['cleanup_errors'].append('service/device removal not verified')
            except Exception as exc:
                result['cleanup_errors'].append(str(exc))
        result['finished_utc'] = utc()
        save(result)
    return result


class ServiceStatus(ctypes.Structure):
    _fields_ = [(n, W.DWORD) for n in ('service_type', 'state', 'controls',
                'win32_exit', 'service_exit', 'checkpoint', 'wait_hint')]


class NativeApi:
    def __init__(self):
        self.adv = ctypes.WinDLL('advapi32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.scm = None
        self.service = None
        def declare(lib, name, args, ret):
            f = getattr(lib, name)
            f.argtypes, f.restype = args, ret
            return f
        self.open_scm = declare(self.adv, 'OpenSCManagerW', [W.LPCWSTR, W.LPCWSTR, W.DWORD], W.HANDLE)
        self.open_service = declare(self.adv, 'OpenServiceW', [W.HANDLE, W.LPCWSTR, W.DWORD], W.HANDLE)
        self.create_service = declare(self.adv, 'CreateServiceW',
            [W.HANDLE, W.LPCWSTR, W.LPCWSTR, W.DWORD, W.DWORD, W.DWORD, W.DWORD,
             W.LPCWSTR, W.LPCWSTR, ctypes.POINTER(W.DWORD), W.LPCWSTR, W.LPCWSTR, W.LPCWSTR], W.HANDLE)
        self.start_service = declare(self.adv, 'StartServiceW', [W.HANDLE, W.DWORD, ctypes.c_void_p], W.BOOL)
        self.query_status = declare(self.adv, 'QueryServiceStatus', [W.HANDLE, ctypes.POINTER(ServiceStatus)], W.BOOL)
        self.control_service = declare(self.adv, 'ControlService', [W.HANDLE, W.DWORD, ctypes.POINTER(ServiceStatus)], W.BOOL)
        self.delete_service = declare(self.adv, 'DeleteService', [W.HANDLE], W.BOOL)
        self.close_service = declare(self.adv, 'CloseServiceHandle', [W.HANDLE], W.BOOL)
        self.dos_device = declare(self.kernel, 'QueryDosDeviceW', [W.LPCWSTR, W.LPWSTR, W.DWORD], W.DWORD)
        self.create_file = declare(self.kernel, 'CreateFileW',
            [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, W.HANDLE], W.HANDLE)
        self.close_handle = declare(self.kernel, 'CloseHandle', [W.HANDLE], W.BOOL)
        self.scm = self.open_scm(None, None, 3)  # CONNECT | CREATE_SERVICE
        if not self.scm:
            self.fail('OpenSCManager')

    @staticmethod
    def fail(action):
        code = ctypes.get_last_error()
        raise OSError(code, action + ': ' + ctypes.FormatError(code).strip())

    def device_target(self):
        b = ctypes.create_unicode_buffer(4096)
        if self.dos_device(DEVICE, b, len(b)):
            return b.value
        if ctypes.get_last_error() == 2:
            return None
        self.fail('QueryDosDevice')

    def check_absent(self):
        h = self.open_service(self.scm, SERVICE, 4)
        if h:
            self.close_service(h)
            raise RuntimeError('Existing probe service: refusing to modify it')
        if ctypes.get_last_error() != 1060:
            self.fail('OpenService preflight')
        if self.device_target() is not None:
            raise RuntimeError('CCDRV1 already exists: refusing to load another driver')

    def create(self):
        # QUERY_STATUS | START | STOP | DELETE; KERNEL_DRIVER; DEMAND_START; NORMAL.
        self.service = self.create_service(self.scm, SERVICE, 'Battery80 temporary Quanta bridge probe',
            0x10034, 1, 3, 1, str(DRIVER), None, None, None, None, None)
        if not self.service:
            self.fail('CreateService')

    def state(self):
        status = ServiceStatus()
        if not self.query_status(self.service, ctypes.byref(status)):
            self.fail('QueryServiceStatus')
        return status

    def wait_state(self, wanted):
        deadline = time.monotonic() + 15
        while True:
            s = self.state()
            if s.state == wanted:
                return s
            if time.monotonic() >= deadline:
                raise RuntimeError(f'Service state timeout: state={s.state}, win32={s.win32_exit}')
            if wanted == 4 and s.state == 1:
                raise RuntimeError(f'Driver stopped during load: win32={s.win32_exit}, specific={s.service_exit}')
            time.sleep(0.1)

    def start(self):
        if not self.start_service(self.service, 0, None):
            self.fail('StartService')
        self.wait_state(4)

    def probe(self):
        target = self.device_target()
        if target != r'\Device\CCDRV1':
            raise RuntimeError(f'Unexpected device mapping: {target!r}')
        handle = self.create_file(r'\\.\CCDRV1', 0xC0000000, 3, None, 3, 0, None)
        if handle in (None, ctypes.c_void_p(-1).value):
            self.fail('CreateFile CCDRV1')
        try:
            return {'device_target': target, 'device_opened': True, 'ioctl_calls': 0}
        finally:
            if not self.close_handle(handle):
                self.fail('CloseHandle CCDRV1')

    def stop(self):
        if self.state().state == 1:
            return
        status = ServiceStatus()
        if not self.control_service(self.service, 1, ctypes.byref(status)):
            if ctypes.get_last_error() != 1062:
                self.fail('ControlService STOP')
        self.wait_state(1)

    def delete(self):
        if not self.delete_service(self.service):
            self.fail('DeleteService')

    def close(self):
        for attr in ('service', 'scm'):
            h = getattr(self, attr)
            if h:
                self.close_service(h)
                setattr(self, attr, None)

    def verify_removed(self):
        scm = self.open_scm(None, None, 1)
        if not scm:
            self.fail('OpenSCManager cleanup check')
        try:
            deadline = time.monotonic() + 5
            while True:
                h = self.open_service(scm, SERVICE, 4)
                if not h and ctypes.get_last_error() == 1060:
                    break
                if h:
                    self.close_service(h)
                if time.monotonic() >= deadline:
                    return {'service_absent': False, 'device_absent': self.device_target() is None}
                time.sleep(0.1)
            return {'service_absent': True, 'device_absent': self.device_target() is None}
        finally:
            self.close_service(scm)


def preflight():
    if ROOT != EXPECTED_ROOT or DRIVER.resolve() != DRIVER:
        raise RuntimeError('Project/driver path mismatch')
    # Refuse junctions/symlinks anywhere in the driver path within the project.
    for p in [DRIVER, *[p for p in DRIVER.parents if p == ROOT or ROOT in p.parents]]:
        if p.is_symlink() or os.path.isjunction(p):
            raise RuntimeError('Reparse path refused: ' + str(p))
    actual = hashlib.sha256(DRIVER.read_bytes()).hexdigest()
    if actual != DRIVER_HASH:
        raise RuntimeError('OEM driver hash mismatch')
    script = r'''$ErrorActionPreference='Stop'; $p='C:\Battery80-NLYA\reference\oem-downloads\NLYA-ControlCenter-3.0.0.29\app\ControlCenter64.sys'; $s=Get-AuthenticodeSignature -LiteralPath $p; $b=Get-CimInstance Win32_BaseBoard; $f=Get-CimInstance Win32_BIOS; [ordered]@{SignatureStatus=[string]$s.Status;Signer=$s.SignerCertificate.Subject;Issuer=$s.SignerCertificate.Issuer;TimestampSigner=$s.TimeStamperCertificate.Subject;Board=$b.Product;Manufacturer=$b.Manufacturer;Bios=$f.SMBIOSBIOSVersion} | ConvertTo-Json -Compress'''
    process = subprocess.run([PWSH, '-NoProfile', '-NonInteractive', '-Command', script],
                             capture_output=True, text=True, encoding='utf-8', timeout=45)
    if process.returncode:
        raise RuntimeError('Signature/hardware preflight failed: ' + process.stderr.strip())
    data = json.loads(process.stdout)
    if (data['SignatureStatus'] != 'Valid' or 'CN=QUANTA COMPUTER INC.' not in data['Signer']
            or data['Board'] != 'NLYA' or data['Manufacturer'] != 'THUNDEROBOT' or data['Bios'] != 'TP181'):
        raise RuntimeError('Unverified signature or hardware identity: ' + json.dumps(data))
    return data


def main():
    if sys.argv[1:] != ['--capture']:
        raise SystemExit('Use --capture for the fixed temporary driver probe. No other actions supported.')
    sys.stdout.reconfigure(encoding='utf-8')
    folder = ROOT / 'evidence/ec/stage11'
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / ('driver-probe-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    info = {'scope': 'Load/open/close/unload fixed signed OEM driver; no IOCTL or EC commands',
            'driver_path': str(DRIVER), 'driver_sha256': DRIVER_HASH, 'saved_file': str(dest)}
    def save(result):
        temp = dest.with_suffix('.tmp')
        temp.write_text(json.dumps({**info, **result}, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(dest)
    try:
        info['preflight'] = preflight()
        admin = ctypes.WinDLL('shell32').IsUserAnAdmin()
        info['elevated'] = bool(admin)
        if not admin:
            raise RuntimeError('Administrator token required; no driver changes made')
        result = run_probe(NativeApi(), save)
        print(json.dumps({**info, **result}, ensure_ascii=False, indent=2))
        return 0 if result['probe_succeeded'] and result['cleanup_succeeded'] else 2
    except Exception as exc:
        result = {'finished_utc': utc(), 'errors': [str(exc)], 'created': False,
                  'ioctl_calls': 0, 'ec_commands': 0, 'hardware_control_calls': 0}
        save(result)
        print(json.dumps({**info, **result}, ensure_ascii=False, indent=2))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
