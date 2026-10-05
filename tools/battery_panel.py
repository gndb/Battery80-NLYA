"""NLYA/TP181 native charge panel. Supervisor owns the temporary signed driver.

Closing a verified panel leaves the native policy unchanged, as requested.
No installer, flash, arbitrary port/address/threshold, startup, or UEFI writes.
"""
import ctypes
from ctypes import wintypes as W
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox
import uuid

from inpout_status_probe import NativeApi, ROOT, run_probe, utc
from nlya_policy_trial import TrialApi, telemetry, check_preflight, guard_restore
from battery_panel_core import PanelProtocol, operate
from battery_panel_dpi import enable_native_dpi, initialize_window, pixels
from portable_runtime import child_command, child_environment
from battery_panel_widgets import Card, Button, BatteryGauge, BG, CARD, FG, MUTED, GOLD, AMBER, LINE, BADGE, NEUTRAL

OUT = ROOT / 'evidence/panel'


def checked_folder():
    for p in (ROOT, ROOT / 'evidence', OUT):
        if p.is_symlink() or os.path.isjunction(p):
            raise RuntimeError('Panel evidence reparse path refused')
    OUT.mkdir(exist_ok=True)


def save_json(path, data):
    if path.parent != OUT or path.is_symlink() or os.path.isjunction(path):
        raise RuntimeError('Panel output outside fixed directory')
    temp = path.with_suffix('.tmp')
    if temp.is_symlink() or os.path.isjunction(temp):
        raise RuntimeError('Panel temporary reparse path refused')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    for attempt in range(20):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt == 19: raise
            time.sleep(.01)  # File replacement only; never retry a hardware call.


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


class PanelApi(TrialApi):
    def __init__(self, journal):
        super().__init__(journal, True)
        self.active_protocol = None
    @contextmanager
    def session(self, recovery=False):
        with super().session(recovery=recovery) as base:
            self.active_protocol = PanelProtocol(base.read, base.write)
            try:
                yield self.active_protocol
            finally:
                self.active_protocol = None


class Backend:
    def __init__(self, session_path):
        self.path = session_path
        self.state = {'started_utc': utc(), 'keep_after_close': True,
                      'recovery_required': False, 'owned_active': False,
                      'hardware_control_calls': 0, 'refresh_count': 0,
                      'ioctl_calls': 0, 'ec_commands': 0, 'transport_fault': False,
                      'last_read_valid': False}
        self.save()
    def save(self):
        save_json(self.path, self.state)
    def job(self, action, allow=False):
        if self.state.get('transport_fault') or self.state.get('recovery_required'):
            raise RuntimeError('传输或上次操作尚未解决；读取和控制均已锁定，请查看日志。')
        self.state['last_read_valid'] = False
        op_path = OUT / ('operation-' + uuid.uuid4().hex + '.json')
        api = None
        operation = {'action': action, 'started_utc': utc(), 'session_file': self.path.name}
        def journal():
            if api:
                if api.active_protocol:
                    safe = api.active_protocol.transport_safe
                    if self.state.get('transport_safe') != safe:
                        self.state['transport_safe'] = safe
                        self.save()
        try:
            api = PanelApi(journal)
            with api.session() as protocol:
                result = operate(protocol, action, telemetry, self.state, self.save,
                                 allow_high_soc=allow)
                if action == 'status' and result['telemetry_error'] and self.state['owned_active']:
                    # A previously completed setting is reversible. Never retry
                    # an uncertain control or incomplete PMC2 transaction.
                    result = operate(protocol, 'disable', telemetry, self.state, self.save)
                    result['monitoring_error'] = '遥测失效；本面板开启的维护已取消。'
                self.state['refresh_count'] += 1
                self.state['last_read_valid'] = bool(result.get('telemetry'))
                return result
        except Exception as exc:
            operation['error'] = str(exc)
            self.state['last_error'] = str(exc)
            raise
        finally:
            if api:
                self.state['hardware_control_calls'] += api.policy_writes
                self.state['ioctl_calls'] += api.ioctl_calls
                self.state['ec_commands'] += api.ec_commands
                journal()
                api.close()
                operation.update(port_trace=api.trace, ioctl_calls=api.ioctl_calls,
                                 hardware_control_calls=api.policy_writes,
                                 finished_utc=utc())
                save_json(op_path, operation)
            self.state['last_operation_file'] = op_path.name
            self.save()


class Panel:
    def __init__(self, backend, preview=False, auto_close=False):
        self.backend, self.preview = backend, preview
        enable_native_dpi()
        self.root = tk.Tk()
        self.root.title('雷神 R16 · 电池维护')
        initialize_window(self.root)
        self.root.configure(bg=BG)
        self.root.option_add('*Font', ('Microsoft YaHei UI', 10))
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='BatteryEC')
        self.mail = queue.Queue()
        self.busy, self.closing, self.last = False, False, None
        self.exit_error = None
        self.history = []
        self.status_text = tk.StringVar(value='等待本机 EC 回读…')
        self.values = {k: tk.StringVar(value='—') for k in ('soc', 'power', 'capacity', 'supply', 'native', 'detail', 'raw', 'time', 'flow', 'supply_brief', 'badge', 'summary', 'chart_note')}
        self.build()
        self.root.after(100, self.poll)
        if preview:
            self.render(preview_snapshot())
            self.status_text.set('界面预览 · 模拟数据 · 控制按钮禁用')
        else:
            self.request('status')
            self.root.after(15000, self.refresh_timer)
        if auto_close:
            self.root.after(1500, self.close)

    def label(self, parent, text=None, variable=None, size=10, color=FG, bold=False):
        label = tk.Label(parent, text=text, textvariable=variable, bg=parent['bg'], fg=color,
                         font=('Microsoft YaHei UI', size, 'bold' if bold else 'normal'),
                         anchor='w', justify='left')
        label.bind('<Configure>', lambda e: label.configure(wraplength=max(e.width, 1)))
        return label

    def build(self):
        dp = lambda value: pixels(self.root, value)
        footer = tk.Frame(self.root, bg=BG, padx=dp(24), pady=dp(12))
        footer.pack(side='bottom', fill='x')
        self.label(footer, variable=self.status_text, size=9).pack(fill='x')
        self.label(footer, variable=self.values['time'], size=9, color=MUTED).pack(fill='x', pady=dp((3, 0)))
        viewport = tk.Frame(self.root, bg=BG)
        viewport.pack(fill='both', expand=True)
        self.scroll = tk.Canvas(viewport, bg=BG, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(viewport, orient='vertical', command=self.scroll.yview)
        scrollbar.pack(side='right', fill='y')
        self.scroll.pack(side='left', fill='both', expand=True)
        self.scroll.configure(yscrollcommand=scrollbar.set)
        self.body = tk.Frame(self.scroll, bg=BG, padx=dp(24), pady=dp(16))
        body_id = self.scroll.create_window(0, 0, window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda e: self.scroll.configure(scrollregion=self.scroll.bbox('all')))
        self.scroll.bind('<Configure>', lambda e: self.scroll.itemconfigure(body_id, width=e.width))
        self.root.bind('<MouseWheel>', lambda e: self.scroll.yview_scroll(-int(e.delta/120), 'units'))
        head = tk.Frame(self.body, bg=BG)
        head.pack(fill='x', pady=dp((0, 12)))
        heading = tk.Frame(head, bg=BG)
        heading.pack(side='left', fill='x', expand=True)
        self.label(heading, '电池维护', size=23, color=GOLD, bold=True).pack(anchor='w')
        self.label(heading, '雷神 R16  ·  让电量保持在适合插电使用的范围', size=9, color=MUTED).pack(fill='x', pady=dp((5, 0)))
        self.refresh = Button(head, '刷新状态', lambda: self.request('status'))
        self.refresh.pack(side='right', padx=dp((18, 0)))
        tk.Frame(self.body, bg=LINE, height=dp(1)).pack(fill='x', pady=dp((0, 14)))
        top = tk.Frame(self.body, bg=BG)
        top.pack(fill='x')
        top.columnconfigure(0, weight=2, uniform='hero')
        top.columnconfigure(1, weight=3, uniform='hero')
        battery = Card(top, padding=14)
        battery.grid(row=0, column=0, sticky='nsew', padx=dp((0, 14)))
        self.label(battery.content, '电池概览', size=12, color=GOLD, bold=True).pack(fill='x')
        self.gauge = BatteryGauge(battery.content)
        self.gauge.pack(fill='both', expand=True)
        self.flow_label = self.label(battery.content, variable=self.values['flow'], size=10, color=GOLD, bold=True)
        self.flow_label.pack(fill='x')
        self.label(battery.content, '环上刻度标记 80% 维护目标', size=9, color=MUTED).pack(fill='x', pady=dp((4, 0)))
        control = Card(top, padding=14)
        control.grid(row=0, column=1, sticky='nsew')
        c = control.content
        title = tk.Frame(c, bg=CARD)
        title.pack(fill='x')
        self.label(title, '电量维护', size=13, color=GOLD, bold=True).pack(side='left')
        self.badge = tk.Label(title, textvariable=self.values['badge'], bg=NEUTRAL,
                              fg=MUTED, font=('Microsoft YaHei UI', 9, 'bold'), padx=dp(12), pady=dp(5))
        self.badge.pack(side='right')
        self.label(c, '80%', size=28, color=GOLD, bold=True).pack(anchor='w', pady=dp((6, 0)))
        self.native_label = self.label(c, variable=self.values['native'], size=11, bold=True)
        self.native_label.pack(fill='x', pady=dp((2, 0)))
        self.label(c, variable=self.values['summary'], size=9, color=MUTED).pack(fill='x', pady=dp((6, 10)))
        row = tk.Frame(c, bg=CARD)
        row.pack(fill='x', pady=dp((0, 10)))
        self.enable = Button(row, '开启 80% 维护', self.enable_clicked, primary=True, state='disabled')
        self.enable.pack(side='left')
        self.disable = Button(row, '取消维护', lambda: self.request('disable'), state='disabled')
        self.disable.pack(side='left', padx=dp((10, 0)))
        self.label(c, '关闭窗口后继续保持；取消维护可恢复正常充电。', size=9, color=MUTED).pack(fill='x')
        self.label(c, '低于目标允许充电，高于目标可能主动放电。', size=9, color=AMBER).pack(fill='x', pady=dp((5, 0)))
        metrics = tk.Frame(self.body, bg=BG)
        metrics.pack(fill='x', pady=dp(14))
        for col, (key, title, subtitle) in enumerate([
            ('power', '电池净功率', '正值充电 / 负值放电'),
            ('capacity', '剩余容量', '当前可用电量'),
            ('supply_brief', '供电状态', 'Windows 交流供电信号')]):
            metrics.columnconfigure(col, weight=1, uniform='metrics')
            metric = Card(metrics, padding=12)
            metric.grid(row=0, column=col, sticky='nsew', padx=dp((0, 12 if col < 2 else 0)))
            self.label(metric.content, title, size=9, color=MUTED).pack(fill='x')
            self.label(metric.content, variable=self.values[key], size=18, color=GOLD, bold=True).pack(fill='x', pady=dp(3))
            self.label(metric.content, subtitle, size=8, color=MUTED).pack(fill='x')
        chart = Card(self.body, padding=12)
        chart.pack(fill='x')
        chart_head = tk.Frame(chart.content, bg=CARD)
        chart_head.pack(fill='x')
        self.label(chart_head, '电池功率趋势', size=11, color=GOLD, bold=True).pack(side='left')
        self.label(chart_head, variable=self.values['chart_note'], size=8, color=MUTED).pack(side='right')
        self.canvas = tk.Canvas(chart.content, bg=CARD, highlightthickness=0, height=dp(72))
        self.canvas.pack(fill='x', pady=dp((6, 0)))
        self.canvas.bind('<Configure>', lambda e: self.draw_chart())
        self.details_toggle = Button(self.body, '诊断详情  ▾', self.toggle_details)
        self.details_toggle.pack(anchor='w', pady=dp((6, 0)))
        self.details = Card(self.body, padding=18)
        self.details_open = False
        for key in ('detail', 'supply', 'raw'):
            self.label(self.details.content, variable=self.values[key], size=9, color=MUTED).pack(fill='x', pady=dp((0, 6)))
        self.label(self.details.content, 'EC 原厂策略执行；日志保存在 evidence/panel。完整充电、睡眠及重启保持仍需分别验收。', size=9, color=MUTED).pack(fill='x')
        self.values['badge'].set('等待回读')
        self.values['native'].set('正在确认维护状态')
        self.values['summary'].set('状态来自本机回读，打开面板不会自动开启维护。')
        self.values['chart_note'].set('最近 60 次采样  /  15 秒刷新')

    def toggle_details(self):
        dp = lambda value: pixels(self.root, value)
        self.details_open = not self.details_open
        if self.details_open:
            self.details.pack(fill='x', pady=dp((10, 0)))
        else:
            self.details.pack_forget()
        self.details_toggle.configure(text='诊断详情  ▴' if self.details_open else '诊断详情  ▾')

    def unknown_visuals(self):
        self.gauge.set(None)
        self.values['badge'].set('状态未知')
        self.badge.configure(bg=BADGE, fg=AMBER)
        self.native_label.configure(fg=AMBER)
        self.flow_label.configure(fg=MUTED)
        self.values['chart_note'].set('历史采样  /  当前更新失败')
        self.values['summary'].set('状态读取失败，控制已暂停；旧读数不作为当前状态。')
        for key in ('flow', 'supply_brief', 'supply', 'raw', 'time'):
            self.values[key].set('—')

    def controls(self, valid=True):
        if self.preview or self.busy or not valid or not self.last or self.backend.state.get('recovery_required'):
            self.enable.configure(state='disabled'); self.disable.configure(state='disabled')
        else:
            known = self.last['policy']['0475'] in (0x3c, 0xd0)
            healthy = self.last['telemetry'] and self.last['telemetry']['power_online'] and self.last['ec_adapter_present'] and self.last['ec_battery_present']
            self.enable.configure(state='normal' if known and healthy and not self.last['enabled'] else 'disabled')
            self.disable.configure(state='normal' if known and self.last['enabled'] else 'disabled')
        self.refresh.configure(state='disabled' if self.busy or self.preview else 'normal')
    def enable_clicked(self):
        if not self.last: return
        soc = max(self.last['policy']['0396'], self.last['telemetry']['soc'])
        if soc > 80 and not messagebox.askyesno('开启原厂电量维护',
            f'当前电量约 {soc}%。\n\n原厂策略可能使电池在插电时主动放电，降向 80%；关闭窗口后仍继续执行。\n\n是否开启并保持这项策略？', parent=self.root):
            return
        self.request('enable', allow=soc > 80)
    def request(self, action, allow=False):
        if self.preview or self.busy or self.closing: return
        self.busy = True
        self.status_text.set({'status': '正在读取 EC 与电池状态…', 'enable': '正在设置并回读验证…', 'disable': '正在取消并回读验证…'}[action])
        self.controls()
        def work():
            try: self.mail.put(('ok', action, self.backend.job(action, allow)))
            except Exception as e: self.mail.put(('error', action, str(e)))
        self.pool.submit(work)
    def poll(self):
        try:
            kind, action, value = self.mail.get_nowait()
            self.busy = False
            if kind == 'ok':
                self.render(value)
                self.status_text.set(value.get('monitoring_error') or {'status': '状态已回读 · 每 15 秒自动刷新', 'enable': '80% 原厂维护已开启 · 参数连续三次回读通过', 'disable': '维护已取消 · 默认参数与 Learn 清除连续三次回读通过'}[action])
                self.controls()
            else:
                self.last = None
                self.unknown_visuals()
                self.values['native'].set('状态未知 · 控制已暂停')
                self.values['detail'].set('上次显示值已过期，请刷新；失败的写入不会重复发送。')
                for key in ('soc', 'power', 'capacity'): self.values[key].set('—')
                self.status_text.set('读取 / 操作失败：' + value)
                self.controls(False)
                if action != 'status': messagebox.showerror('操作未完成', value + '\n\n请查看 evidence/panel 中的记录；不要连续重复控制。', parent=self.root)
        except queue.Empty: pass
        if self.closing and not self.busy:
            try:
                self.backend.state['ui_closed_utc'] = utc()
                self.backend.save()
            except Exception as exc:
                self.exit_error = str(exc)
                self.backend.state.pop('ui_closed_utc', None)
            finally:
                self.pool.shutdown(wait=False)
                self.root.destroy()
            return
        self.root.after(100, self.poll)
    def refresh_timer(self):
        if not self.closing:
            self.request('status')
            self.root.after(15000, self.refresh_timer)
    def close(self):
        self.closing = True
        self.status_text.set('正在结束监测；已经验证的 EC 维护状态将保留…')
        self.controls(False)
    def render(self, s):
        self.last = s
        t, p = s['telemetry'], s['policy']
        if t:
            power = (t['charge_rate_mw'] - t['discharge_rate_mw']) / 1000
            self.values['soc'].set(str(t['soc']) + '%')
            self.values['power'].set(f'{power:+.2f} W' if power else '0.00 W')
            self.values['capacity'].set(f"{t['remaining_capacity_mwh'] / 1000:.2f} Wh")
            charging = '充电中' if t['charging'] else '放电中' if t['discharging'] else '未充电 / 未放电'
            windows = '有' if t['power_online'] else '无'
            self.history.append(power); self.history = self.history[-60:]
        else:
            for key in ('soc', 'power', 'capacity'): self.values[key].set('—')
            charging, windows = '电池遥测不可用', '未知'
        self.values['native'].set(f"EC 回读：维护已开启 · 目标 {s['target']}%" if s['enabled'] else 'EC 回读：维护已关闭 · 使用原厂正常充电')
        branch = {0x10: '低于目标 / 允许充电', 0x20: '高于目标 / 放电分支', 0x40: '等于目标 / 零电流分支', 0x80: '门控条件未满足', 0: '维护未执行'}.get(s['branch'], '未识别分支')
        self.values['detail'].set(f"当前：{charging}    ·    固件：{branch}    ·    EC 电量 {p['0396']}%")
        self.values['supply'].set(f"EC 适配器检测：{'有' if s['ec_adapter_present'] else '无'}    |    Windows 交流供电信号：{windows}（原厂放电时可能变化）")
        self.values['raw'].set(f"IT5570 rev07 · C009A0    |    EC 参数 0475={p['0475']:02X} / 0476={p['0476']:02X}    |    Learn 请求：{'是' if s['learn_requested'] else '否'}")
        self.values['time'].set('最近更新  ' + datetime.fromisoformat(s['utc']).astimezone().strftime('%H:%M:%S') + '    ·    每 15 秒刷新')
        self.values['supply_brief'].set('插电供电' if t and t['power_online'] else '交流信号无' if t else '状态未知')
        flow = '充电中' if t and t['charging'] else '放电中' if t and t['discharging'] else '未充电 / 未放电' if t else '遥测不可用'
        color = AMBER if t and t['discharging'] else GOLD
        self.values['flow'].set(flow)
        self.flow_label.configure(fg=color)
        self.values['chart_note'].set('最近 60 次采样  /  15 秒刷新')
        self.gauge.set(t['soc'] if t else None, color)
        self.values['badge'].set('已开启' if s['enabled'] else '已关闭')
        self.badge.configure(bg=BADGE if s['enabled'] else NEUTRAL, fg=GOLD if s['enabled'] else MUTED)
        self.native_label.configure(fg=GOLD if s['enabled'] else FG)
        if not t:
            summary = '电池遥测不可用，请查看诊断详情。'
        elif s['enabled'] and t['discharging']:
            summary = '电池正在放电；高于目标时原厂策略可能主动降向 80%。'
        elif s['enabled'] and t['charging']:
            summary = '电池正在充电，原厂维护目标为 80%。'
        elif s['enabled']:
            summary = '当前未充电、未放电；维护已开启。'
        else:
            summary = '维护已关闭，使用原厂正常充电策略。'
        self.values['summary'].set(summary)
        self.draw_chart()
    def draw_chart(self):
        dp = lambda value: pixels(self.root, value)
        c = self.canvas
        c.delete('all')
        w, h = max(c.winfo_width(), 1), max(c.winfo_height(), 1)
        y, margin = h / 2, dp(44)
        c.create_line(margin, y, w - dp(10), y, fill=LINE, dash=(4, 4))
        c.create_text(dp(20), y, text='0 W', fill=MUTED, font=('Segoe UI', 9))
        if len(self.history) < 2:
            c.create_text(w/2, y-dp(22), text='等待下一次采样…', fill=MUTED, font=('Microsoft YaHei UI', 10))
            return
        scale = max(5, max(abs(x) for x in self.history) * 1.2)
        points = []
        for i, value in enumerate(self.history):
            points.extend((margin + (w-margin-dp(12)) * i / (len(self.history)-1), y - value/scale*(h/2-dp(14))))
        c.create_line(*points, fill=GOLD, width=dp(2))
        if h >= dp(80):
            c.create_text(dp(20), dp(12), text=f'+{scale:.0f}', fill=MUTED, font=('Segoe UI', 9))
            c.create_text(dp(20), h-dp(12), text=f'-{scale:.0f}', fill=MUTED, font=('Segoe UI', 9))


def preview_snapshot():
    return {'utc': utc(), 'enabled': False, 'target': 60, 'ec_adapter_present': True,
            'ec_battery_present': True, 'learn_requested': False, 'branch': 0,
            'policy': {'0475': 60, '0476': 0, '0396': 99},
            'telemetry': {'soc': 99, 'charge_rate_mw': 0, 'discharge_rate_mw': 0,
                          'remaining_capacity_mwh': 62929, 'charging': False,
                          'discharging': False, 'power_online': True}}


def normal_exit_verified(state, code):
    return bool(code == 0 and state.get('ui_closed_utc') and state.get('last_read_valid')
                and state.get('refresh_count', 0) > 0 and not state.get('recovery_required')
                and not state.get('transport_fault'))


class Supervisor(NativeApi):
    def __init__(self, path, save, capture=False):
        super().__init__()
        self.path, self.save, self.capture = path, save, capture
    def probe(self):
        if self.capture:
            b = Backend(self.path)
            s = b.job('status')
            self.ioctl_calls = b.state['ioctl_calls']
            return {'device_opened': True, 'status_valid': True, 'snapshot': s,
                    'hardware_control_calls': b.state['hardware_control_calls']}
        child = subprocess.Popen(child_command('--ui', self.path.name), cwd=ROOT, env=child_environment(), creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.save({'ui_pid': child.pid, 'ui_session_file': self.path.name})
            child.wait()
        except BaseException:
            if child.poll() is None: child.terminate()
            child.wait(timeout=5)
            raise
        finally:
            s = load_json(self.path)
            if s.get('transport_safe') is False:
                s['transport_fault'] = True
                save_json(self.path, s)
            if s.get('recovery_required'):
                # Never issue a new command into an incompletely journaled
                # multi-byte transaction, or repeat an attempted cancellation.
                if s.get('transport_fault') or not s.get('transport_safe') or s.get('cancel_attempted'):
                    self.save({'guard_error': 'Uncertain transport/cancel; automatic repeat refused', 'recovery_required': True})
                else:
                    api = PanelApi(lambda: None)
                    try:
                        with api.session(recovery=True) as p:
                            def record(update):
                                s.update(update)
                                if update.get('guard_cancel_attempted'): s['cancel_attempted'] = True
                                save_json(self.path, s)
                            r = guard_restore(p, s, record)
                            if r['verified']: s['recovery_required'] = False
                            s['hardware_control_calls'] += api.policy_writes
                            save_json(self.path, s)
                    finally: api.close()
            self.save({'child_state': s, 'hardware_control_calls': s.get('hardware_control_calls', 0), 'ui_exit_code': child.returncode})
            self.ioctl_calls = s.get('ioctl_calls', 0)
        valid = normal_exit_verified(s, child.returncode)
        return {'device_opened': s.get('refresh_count', 0) > 0, 'status_valid': valid,
                'ui_exit_code': child.returncode, 'native_policy_kept_after_close': True}


def singleton():
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateMutexW.argtypes, k.CreateMutexW.restype = [ctypes.c_void_p, W.BOOL, W.LPCWSTR], W.HANDLE
    h = k.CreateMutexW(None, False, 'Global\\Battery80NLYAPanelSupervisor')
    if not h or ctypes.get_last_error() == 183:
        if h: k.CloseHandle.argtypes = [W.HANDLE]; k.CloseHandle(h)
        raise RuntimeError('面板或诊断已在运行，请使用已打开的窗口。')
    return k, h


def main():
    checked_folder()
    cache = OUT / 'runtime-temp'
    if cache.is_symlink() or os.path.isjunction(cache):
        raise RuntimeError('Runtime cache reparse path refused')
    cache.mkdir(exist_ok=True)
    os.environ.update(TEMP=str(cache), TMP=str(cache),
                      PSModuleAnalysisCachePath=str(OUT / 'powershell-modulecache'))
    args = sys.argv[1:]
    if args == ['--preview'] or args == ['--preview-smoke']:
        b = Backend(OUT / 'preview-session.json')
        Panel(b, preview=True, auto_close=args == ['--preview-smoke']).root.mainloop()
        return 0
    if len(args) == 2 and args[0] == '--ui':
        name = args[1]
        if Path(name).name != name or not name.startswith('session-') or not name.endswith('.json'):
            raise RuntimeError('Invalid fixed panel session name')
        check_preflight()
        b = Backend(OUT / name)
        try:
            gui = Panel(b)
            gui.root.mainloop()
        except BaseException as exc:
            b.state['ui_error'] = str(exc); b.save(); raise
        return 2 if gui.exit_error else 0
    if args not in ([], ['--capture']):
        raise RuntimeError('Only panel launch or --capture diagnostic is available')
    k, mutex = singleton()
    data, api = {'keep_after_close': True, 'firmware_writes': 0, 'uefi_nvram_writes': 0}, None
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
    path, owner_path = OUT / ('session-' + stamp + '.json'), OUT / ('driver-' + stamp + '.json')
    def save(update=None):
        if update: data.update(update)
        save_json(owner_path, data)
    try:
        for previous in OUT.glob('session-*.json'):
            prior = load_json(previous)
            if prior.get('transport_fault') or prior.get('recovery_required') or prior.get('transport_safe') is False:
                raise RuntimeError('此前有未解决的传输/控制记录，拒绝新查询：' + str(previous))
        data['preflight'] = check_preflight()
        save()
        api = Supervisor(path, save, capture=args == ['--capture'])
        result = run_probe(api, save)
        # run_probe's original read-only counter is not used as a control claim.
        data['hardware_control_calls'] = load_json(path).get('hardware_control_calls', 0)
        save()
        if args == ['--capture'] and sys.stdout:
            sys.stdout.reconfigure(encoding='utf-8')
            print(json.dumps({'owner_file': str(owner_path), **data}, ensure_ascii=False, indent=2))
        elif not result['probe_succeeded'] or not result['cleanup_succeeded']:
            messagebox.showerror('面板退出检查', '状态或驱动清理尚未验证。\n请查看：' + str(owner_path))
        return 0 if result['probe_succeeded'] and result['cleanup_succeeded'] and not result['errors'] else 2
    except Exception as exc:
        save({'startup_error': str(exc)})
        if args == ['--capture'] and sys.stdout: print(str(exc))
        else: messagebox.showerror('面板无法启动', str(exc) + '\n\n记录：' + str(owner_path))
        return 2
    finally:
        k.CloseHandle.argtypes = [W.HANDLE]
        k.CloseHandle(mutex)


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as error:
        messagebox.showerror('电池维护面板', str(error))
        raise SystemExit(2)
