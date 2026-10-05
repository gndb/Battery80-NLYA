"""Tk appearance primitives only; no battery, driver or platform control."""
import math
import tkinter as tk
from battery_panel_dpi import pixels

BG = '#090a0c'
CARD = '#17181b'
FG = '#f2eee7'
MUTED = '#aaa69e'
GOLD = '#e5b55c'
AMBER = '#ffa454'
LINE = '#403828'
BADGE = '#302718'
NEUTRAL = '#242426'


def rounded(canvas, x1, y1, x2, y2, radius=20, **options):
    r = min(radius, (x2-x1)/2, (y2-y1)/2)
    return canvas.create_polygon(
        x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
        x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
        x1, y2, x1, y2-r, x1, y1+r, x1, y1,
        smooth=True, splinesteps=24, **options)


class Card(tk.Frame):
    def __init__(self, parent, color=CARD, padding=20):
        super().__init__(parent, bg=parent['bg'])
        self.surface = tk.Canvas(self, bg=parent['bg'], highlightthickness=0, bd=0)
        self.surface.place(x=0, y=0, relwidth=1, relheight=1)
        self.content = tk.Frame(self, bg=color)
        self.content.pack(fill='both', expand=True, padx=pixels(self, padding), pady=pixels(self, padding))
        self.surface.bind('<Configure>', lambda e: self.paint(color))

    def paint(self, color):
        self.surface.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        if w > 2 and h > 2:
            cut = min(pixels(self, 12), w/4, h/4)
            self.surface.create_polygon(
                1, 1, w-1-cut, 1, w-1, 1+cut, w-1, h-1,
                1+cut, h-1, 1, h-1-cut, fill=color, outline=LINE,
                width=pixels(self, 1))
            self.surface.create_line(pixels(self, 16), 1, min(w-cut, pixels(self, 82)), 1,
                                     fill=GOLD, width=pixels(self, 2))


class Button(tk.Button):
    """Keep native keyboard, focus and disabled behavior with gold styling."""
    def __init__(self, parent, text, command, primary=False, **kwargs):
        self.base = GOLD if primary else NEUTRAL
        self.hover = '#f2ca7f' if primary else '#393125'
        super().__init__(parent, text=text, command=command, bg=self.base,
                         fg=BG if primary else FG, activebackground=self.hover,
                         activeforeground=BG if primary else FG,
                         disabledforeground='#746443' if primary else '#817d76', relief='flat', bd=0,
                         highlightthickness=pixels(parent, 1), highlightbackground=GOLD if primary else LINE,
                         highlightcolor=GOLD, padx=pixels(parent, 18), pady=pixels(parent, 8), cursor='hand2',
                         font=('Microsoft YaHei UI', 10, 'bold'), **kwargs)
        self.bind('<Enter>', lambda e: self.configure(bg=self.hover) if self['state'] == 'normal' else None)
        self.bind('<Leave>', lambda e: self.configure(bg=self.base))


class BatteryGauge(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, bg=parent['bg'], height=pixels(parent, 170),
                         highlightthickness=0, bd=0)
        self.soc, self.color = None, GOLD
        self.bind('<Configure>', lambda e: self.paint())

    def set(self, soc, color=GOLD):
        self.soc, self.color = soc, color
        self.paint()

    def paint(self):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20 or h < 20:
            return
        dp = lambda value: pixels(self, value)
        radius = min(dp(86), (w-dp(40))/2, (h-dp(30))/2)
        cx, cy = w/2, h/2
        box = (cx-radius, cy-radius, cx+radius, cy+radius)
        rim = dp(10)
        self.create_oval(cx-radius-rim, cy-radius-rim, cx+radius+rim, cy+radius+rim,
                         outline=LINE, width=dp(1))
        self.create_oval(*box, outline=LINE, width=dp(12))
        if self.soc is not None and self.soc > 0:
            self.create_arc(*box, start=90, extent=-min(self.soc, 100)*3.6,
                            style='arc', outline=self.color, width=dp(12))
        angle = math.radians(90 - 80*3.6)
        px, py = cx+radius*math.cos(angle), cy-radius*math.sin(angle)
        self.create_oval(px-dp(5), py-dp(5), px+dp(5), py+dp(5), fill=FG, outline=BG, width=dp(2))
        self.create_text(cx, cy-dp(8), text='—' if self.soc is None else f'{self.soc}%',
                         font=('Segoe UI', 36, 'bold'), fill=FG)
        self.create_text(cx, cy+dp(35), text='当前电量', font=('Microsoft YaHei UI', 10), fill=MUTED)
