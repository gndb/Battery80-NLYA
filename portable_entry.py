"""Portable GUI entry. Default launch never touches a driver or battery."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).absolute().parent / 'tools'))
from portable_runtime import (VERSION, application_root, safe_path, bind_root,
    validate_binding, verify_policy_record, child_command, child_environment,
    atomic_json)


def prepare_folders():
    root = safe_path(application_root())
    for relative in ('evidence', 'evidence/panel', 'evidence/packaging', 'evidence/panel/runtime-temp'):
        safe_path(root / relative).mkdir(exist_ok=True)
    os.environ.update(TEMP=str(root / 'evidence/panel/runtime-temp'),
        TMP=str(root / 'evidence/panel/runtime-temp'),
        PSModuleAnalysisCachePath=str(root / 'evidence/panel/powershell-modulecache'))
    return root


def run_panel(args):
    import battery_panel
    old = sys.argv
    try:
        sys.argv = [old[0], *args]
        return battery_panel.main()
    finally:
        sys.argv = old


def elevate_run():
    command = child_command('--run')
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    shell.ShellExecuteW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
        ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int]
    shell.ShellExecuteW.restype = ctypes.c_void_p
    result = shell.ShellExecuteW(None, 'runas', command[0],
        subprocess.list2cmdline(command[1:]), str(application_root()), 1)
    if not result or result <= 32:
        raise RuntimeError('管理员启动被取消或失败；没有启动硬件控制。')
    return 0


def setup_window(smoke=False):
    import tkinter as tk
    from tkinter import ttk, messagebox
    from battery_panel_dpi import enable_native_dpi, initialize_window, pixels
    root_path = prepare_folders()
    verify_policy_record()
    enable_native_dpi()
    root = tk.Tk()
    root.title('Battery80 · 便携运行版')
    initialize_window(root)
    dp = lambda n: pixels(root, n)
    work = root._dpi_info['work_area']
    w, h = min(dp(700), work[2]-work[0]-dp(40)), min(dp(560), work[3]-work[1]-dp(64))
    root.minsize(min(dp(560), w), min(dp(460), h))
    root.geometry(f'{w}x{h}')
    root.configure(bg='#f3f6fb')
    box = tk.Frame(root, bg='#ffffff', padx=dp(28), pady=dp(24))
    box.pack(fill='both', expand=True, padx=dp(18), pady=dp(18))
    wrap = max(dp(400), w-dp(110))
    def label(text, size=10, color='#526175'):
        tk.Label(box, text=text, bg='#ffffff', fg=color, justify='left',
            anchor='w', wraplength=wrap, font=('Microsoft YaHei UI', size)).pack(fill='x', pady=dp(6))
    label('原厂 80% 电池维护', 21, '#152539')
    label('仅支持 THUNDEROBOT NLYA / TP181 / IT5570 rev07 / C009A0。')
    label('首次免导入 ROM；内置的是分析校验记录，不含 BIOS 或 EC 固件。')
    label('高于 80% 时原厂策略可能主动放电。成功开启后关闭面板继续保持策略；取消维护需重新打开面板。', 10, '#986118')
    label('真实面板需要管理员权限，临时登记签名驱动，退出时清理。不会自动开启维护、安装开机启动项或刷写固件。')
    label('部署目录：' + str(root_path), 9)
    accepted = tk.BooleanVar(value=False)
    bound = False
    try:
        validate_binding(root_path)
        bound = True
    except Exception as exc:
        if (root_path / 'deployment.json').exists():
            label(str(exc), 9, '#ad263c')
    confirm = ttk.Checkbutton(box, text='我确认本目录部署并允许临时签名驱动登记', variable=accepted)
    confirm.pack(anchor='w', pady=dp(10))
    row = tk.Frame(box, bg='#ffffff')
    row.pack(fill='x', pady=dp(12))
    def start():
        try:
            if not bound:
                if not accepted.get(): raise RuntimeError('请先确认部署和临时驱动使用。')
                bind_root(root_path)
            validate_binding(root_path)
            verify_policy_record()
            elevate_run()
            root.destroy()
        except Exception as exc:
            messagebox.showerror('启动检查', str(exc), parent=root)
    start_button = ttk.Button(row, text='打开真实面板', command=start,
        state='normal' if bound else 'disabled')
    start_button.pack(side='right', padx=dp(4))
    def consent_changed(*_):
        start_button.configure(state='normal' if bound or accepted.get() else 'disabled')
    accepted.trace_add('write', consent_changed)
    def demo():
        subprocess.Popen(child_command('--preview'), cwd=root_path,
            env=child_environment(), creationflags=subprocess.CREATE_NO_WINDOW)
    ttk.Button(row, text='查看模拟演示', command=demo).pack(side='left')
    if smoke:
        root.update_idletasks()
        atomic_json(root_path / 'evidence/packaging/setup-smoke.json',
            {'frozen': bool(getattr(sys, 'frozen', False)), 'dpi': root._dpi_info,
             'start_state': str(start_button['state']), 'bound': bound,
             'hardware_calls': 0, 'driver_loads': 0})
        root.after(1200, root.destroy)
    root.mainloop()
    return 0


def self_test(child=False):
    root = prepare_folders()
    verify_policy_record()
    import inpout_status_probe as driver
    import nlya_policy_trial as policy
    def forbidden(*a, **kw): raise AssertionError('Hardware forbidden in packaging self-test')
    driver.NativeApi.__init__ = forbidden
    policy.telemetry = forbidden
    actual_hash = hashlib.sha256(safe_path(root / 'drivers/inpoutx64.sys').read_bytes()).hexdigest()
    if actual_hash != driver.DRIVER_HASH: raise RuntimeError('Driver file hash mismatch')
    try:
        validate_binding(root)
        binding = 'valid'
    except RuntimeError:
        binding = 'unbound_or_rejected'
    result = {'version': VERSION, 'frozen': bool(getattr(sys, 'frozen', False)),
        'exe': sys.executable, 'root': str(root), 'driver_hash_valid': True,
        'policy_record_valid': True, 'binding': binding, 'hardware_calls': 0,
        'child': child}
    if not child:
        completed = subprocess.run(child_command('--self-test-child'), cwd=root,
            env=child_environment(), timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        if completed.returncode: raise RuntimeError('Independent frozen child failed')
        c = json.loads((root / 'evidence/packaging/child.json').read_text(encoding='utf-8'))
        if c['root'] != str(root) or c['frozen'] != result['frozen'] or not c['child']:
            raise RuntimeError('Child root/dispatch mismatch')
        result['independent_child_passed'] = True
    atomic_json(root / ('evidence/packaging/child.json' if child else 'evidence/packaging/self-test.json'), result)
    return 0


def dispatch(args):
    if not args: return setup_window(False)
    if args == ['--setup-smoke']: return setup_window(True)
    if args == ['--self-test']: return self_test()
    if args == ['--self-test-child']: return self_test(True)
    if args in (['--preview'], ['--preview-smoke']): return run_panel(args)
    if len(args) == 2 and args[0] == '--ui': return run_panel(args)
    if args == ['--run']:
        validate_binding(application_root())
        verify_policy_record()
        if not ctypes.windll.shell32.IsUserAnAdmin(): return elevate_run()
        return run_panel([])
    raise RuntimeError('不支持此启动参数。')


if __name__ == '__main__':
    try:
        prepare_folders()
        raise SystemExit(dispatch(sys.argv[1:]))
    except Exception as exc:
        # Smoke automation gets an exit code and local diagnostic, never a blocking dialog.
        if any(x.endswith('smoke') or x.startswith('--self-test') for x in sys.argv[1:]):
            atomic_json(application_root() / 'evidence/packaging/error.json', {'error': str(exc)})
        else:
            from tkinter import messagebox
            messagebox.showerror('Battery80 启动失败', str(exc))
        raise SystemExit(2)
