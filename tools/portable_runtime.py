"""Portable paths and deployment binding. Importing this module does no hardware IO."""
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

VERSION = '0.2.1-portable'
CANDIDATE_HASH = '8b3977b9d78bc9c8518f99f33fed8728b1ca00331802b2d990d4f431af2f70a3'
CANDIDATE_BYTES = 0x40000
POLICY_HASH = '47eb06f17c625c79479256c424b08b3b554851908c5c5ca85df9a6b43a0e6997'


def application_root():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).absolute().parent
    return Path(__file__).absolute().parents[1]


def is_reparse(path):
    return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def safe_path(path):
    p = Path(path).absolute()
    # Include all existing ancestors, not just paths below the output root.
    for current in [*reversed(p.parents), p]:
        if current.exists() or current.is_symlink():
            if current.is_symlink() or is_reparse(current):
                raise RuntimeError('路径含目录链接，拒绝运行：' + str(current))
    if p.resolve() != p:
        raise RuntimeError('路径不是规范绝对路径：' + str(p))
    return p


def atomic_json(path, data, exclusive=False):
    p = safe_path(path)
    if exclusive and p.exists():
        raise FileExistsError(str(p))
    temp = safe_path(p.with_suffix(p.suffix + '.tmp'))
    if temp.exists():
        raise RuntimeError('存在未完成的配置写入，请保留并检查：' + str(temp))
    with temp.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush(); os.fsync(f.fileno())
    if exclusive and p.exists():
        raise FileExistsError(str(p))
    temp.replace(p)


def bind_root(root):
    root = safe_path(root)
    atomic_json(root / 'deployment.json', {'version': VERSION, 'approved_root': str(root),
        'temporary_signed_driver_accepted': True,
        'bound_utc': datetime.now(timezone.utc).isoformat()}, exclusive=True)


def validate_binding(root):
    root = safe_path(root)
    config = safe_path(root / 'deployment.json')
    if not config.is_file():
        raise RuntimeError('当前文件夹未绑定，请完成首次启动确认。')
    data = json.loads(config.read_text(encoding='utf-8'))
    if data.get('approved_root') != str(root) or data.get('version') != VERSION:
        raise RuntimeError('绑定目录或发布版本不匹配。移动后请保留旧日志并重新审查部署。')
    if data.get('temporary_signed_driver_accepted') is not True:
        raise RuntimeError('没有确认临时签名驱动登记。')
    return root


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def system_powershell():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    get = kernel.GetSystemDirectoryW
    get.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
    get.restype = ctypes.c_uint
    buf = ctypes.create_unicode_buffer(32768)
    n = get(buf, len(buf))
    if not n or n >= len(buf):
        raise RuntimeError('无法确定Windows系统目录。')
    p = safe_path(Path(buf.value) / 'WindowsPowerShell/v1.0/powershell.exe')
    if not p.is_file():
        raise RuntimeError('缺少Windows自带PowerShell，拒绝使用未知替代程序。')
    return str(p)


def ps_script(script):
    return "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); $OutputEncoding = [Console]::OutputEncoding; " + script


def child_command(*args):
    if getattr(sys, 'frozen', False):
        return [sys.executable, *args]
    return [sys.executable, '-B', str(application_root() / 'portable_entry.py'), *args]


def child_environment():
    env = os.environ.copy()
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return env


def resource_root():
    if getattr(sys, 'frozen', False):
        return safe_path(Path(sys._MEIPASS))
    return safe_path(application_root())


def verify_policy_record():
    path = safe_path(resource_root() / 'assets/verified-policy.json')
    if not path.is_file():
        raise RuntimeError('缺少内置分析校验记录，拒绝控制。')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != POLICY_HASH:
        raise RuntimeError('内置分析校验记录完整性不匹配，拒绝控制。')
    record = json.loads(data)
    if record.get('candidate_sha256') != CANDIDATE_HASH or record.get('identity', {}).get('build') != 'C009A0':
        raise RuntimeError('内置分析记录身份不匹配。')
    return record
