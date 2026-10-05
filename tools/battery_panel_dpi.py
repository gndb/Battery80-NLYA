"""Process-local Windows DPI setup. No system settings or hardware control."""
import ctypes as c
import sys


def enable_native_dpi():
    if sys.platform != 'win32':
        return
    user = c.WinDLL('user32', use_last_error=True)
    user.SetProcessDpiAwarenessContext.argtypes = [c.c_void_p]
    user.SetProcessDpiAwarenessContext.restype = c.c_int
    user.GetThreadDpiAwarenessContext.restype = c.c_void_p
    user.GetAwarenessFromDpiAwarenessContext.argtypes = [c.c_void_p]
    user.GetAwarenessFromDpiAwarenessContext.restype = c.c_int
    user.SetThreadDpiAwarenessContext.argtypes = [c.c_void_p]
    user.SetThreadDpiAwarenessContext.restype = c.c_void_p
    # pythonw is the process which draws the UI; the launcher manifest does
    # not establish pythonw's awareness. Set this before constructing Tk.
    user.SetProcessDpiAwarenessContext(c.c_void_p(-4))
    awareness = user.GetAwarenessFromDpiAwarenessContext(user.GetThreadDpiAwarenessContext())
    if awareness != 2:
        # A host may have fixed its process awareness already. Our UI thread
        # can still opt in before creating any of our windows.
        user.SetThreadDpiAwarenessContext(c.c_void_p(-4))
        awareness = user.GetAwarenessFromDpiAwarenessContext(user.GetThreadDpiAwarenessContext())
    if awareness != 2:
        raise RuntimeError('无法启用本进程的高清 DPI 绘制；未修改系统显示设置。')


def pixels(widget, value):
    scale = getattr(widget.winfo_toplevel(), '_ui_scale', 1.0)
    if isinstance(value, (tuple, list)):
        return tuple(round(x*scale) for x in value)
    return round(value*scale)


def initialize_window(root):
    dpi = 96
    work = (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
    root.withdraw()
    root.update_idletasks()
    if sys.platform == 'win32':
        user = c.WinDLL('user32', use_last_error=True)
        user.GetParent.argtypes, user.GetParent.restype = [c.c_void_p], c.c_void_p
        window = user.GetParent(root.winfo_id()) or root.winfo_id()
        user.GetDpiForWindow.argtypes, user.GetDpiForWindow.restype = [c.c_void_p], c.c_uint
        dpi = user.GetDpiForWindow(window) or 96
        user.MonitorFromWindow.argtypes, user.MonitorFromWindow.restype = [c.c_void_p, c.c_uint], c.c_void_p
        class Rect(c.Structure):
            _fields_ = [('left', c.c_long), ('top', c.c_long), ('right', c.c_long), ('bottom', c.c_long)]
        class Monitor(c.Structure):
            _fields_ = [('size', c.c_uint), ('monitor', Rect), ('work', Rect), ('flags', c.c_uint)]
        user.GetMonitorInfoW.argtypes = [c.c_void_p, c.POINTER(Monitor)]
        user.GetMonitorInfoW.restype = c.c_int
        info = Monitor()
        info.size = c.sizeof(info)
        if user.GetMonitorInfoW(user.MonitorFromWindow(window, 2), c.byref(info)):
            work = (info.work.left, info.work.top, info.work.right, info.work.bottom)
    root._ui_scale = dpi/96
    root.tk.call('tk', 'scaling', dpi/72)
    dp = lambda value: pixels(root, value)
    available_w = max(1, work[2]-work[0]-dp(40))
    available_h = max(1, work[3]-work[1]-dp(64))
    width, height = min(dp(940), available_w), min(dp(780), available_h)
    root.minsize(min(dp(820), available_w), min(dp(640), available_h))
    x = work[0]+(work[2]-work[0]-width)//2
    y = work[1]+dp(16)
    root.geometry(f'{width}x{height}+{x}+{y}')
    root._dpi_info = {'window_dpi': dpi, 'scale': root._ui_scale,
                      'work_area': list(work), 'startup_client_size': [width, height]}
    # Fonts are subsequently created at the native DPI, not stretched from
    # a 96-DPI bitmap. Pixel dimensions and canvas strokes use the same scale.
    root.deiconify()
