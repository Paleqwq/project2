# -*- coding: utf-8 -*-
"""
情绪调节小工具 — 灵动美化版 (Fluid UI v4.0)
基于 fix/weather-suggestions 分支 (v3.7) 升级：
1. 动画引擎：平滑展开/收起、淡入淡出、呼吸光效
2. 悬停交互：卡片悬停发光、颜色渐变过渡
3. 现代视觉：渐变头部、柔和配色、层次分明
4. 流畅滚动：惯性滚动、平滑滚轮
5. 微交互：交错入场、状态切换动画、加载指示
6. 保留全部 v3.7 功能：多源定位、SSL兼容、WeatherTipsDB、离线建议
"""

import os
import sys
import ssl
import threading
import math
import time
import tkinter as tk
from tkinter import ttk
from datetime import datetime

import requests

# ----- 封包后证书路径处理（解决 PyInstaller 打包后 SSL 失败） -----
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except Exception:
    pass

# ============================================================
# 🎨 现代视觉主题 - 柔和渐变配色
# ============================================================
T = {
    "bg":           "#F0F4F8",
    "card":         "#FFFFFF",
    "card_hover":   "#FAFCFF",
    "nav_bg":       "#E8EDF5",
    "prim":         "#6366F1",
    "prim_dark":    "#4F46E5",
    "prim_light":   "#A5B4FC",
    "prim_l":       "#EEF2FF",
    "accent":       "#8B5CF6",
    "accent_light": "#C4B5FD",
    "success":      "#10B981",
    "warning":      "#F59E0B",
    "warn":         "#F43F5E",
    "text_h":       "#1E293B",
    "text_b":       "#475569",
    "text_s":       "#94A3B8",
    "border":       "#E2E8F0",
    "border_light": "#F1F5F9",
    "white":        "#FFFFFF",
    "shadow":       "#CBD5E1",
    "glow":         "#818CF8",
    "gradient_1":   "#6366F1",
    "gradient_2":   "#8B5CF6",
    "gradient_3":   "#A78BFA",
}

F = {
    "title":    ("Microsoft YaHei UI", 22, "bold"),
    "subtitle": ("Microsoft YaHei UI", 14),
    "head":     ("Microsoft YaHei UI", 13, "bold"),
    "body":     ("Microsoft YaHei UI", 11),
    "small":    ("Microsoft YaHei UI", 10),
    "tiny":     ("Microsoft YaHei UI", 9),
    "emoji_l":  ("Segoe UI Emoji", 42),
    "emoji_m":  ("Segoe UI Emoji", 24),
    "emoji_s":  ("Segoe UI Emoji", 16),
}


# ============================================================
# ✨ 动画引擎 - 流畅的缓动函数
# ============================================================
class AnimationEngine:
    @staticmethod
    def ease_out_cubic(t):
        return 1 - pow(1 - t, 3)

    @staticmethod
    def ease_out_back(t):
        c1 = 1.70158
        c3 = c1 + 1
        return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)

    @staticmethod
    def ease_in_out_quart(t):
        return 8 * t * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 4) / 2

    @staticmethod
    def ease_out_expo(t):
        return 1 if t == 1 else 1 - pow(2, -10 * t)

    @staticmethod
    def spring(t, damping=0.6, frequency=4.5):
        return 1 - math.exp(-damping * t * 10) * math.cos(frequency * t * math.pi)


class Animator:
    def __init__(self, root):
        self.root = root

    def animate(self, duration_ms, on_update, on_complete=None, easing=None):
        if easing is None:
            easing = AnimationEngine.ease_out_cubic
        start_time = time.time()
        duration_s = duration_ms / 1000.0

        def _step():
            if not self.root.winfo_exists():
                return
            elapsed = time.time() - start_time
            progress = min(elapsed / duration_s, 1.0)
            eased = easing(progress)
            try:
                on_update(eased)
            except tk.TclError:
                return
            if progress < 1.0:
                self.root.after(16, _step)
            elif on_complete:
                on_complete()

        self.root.after(16, _step)

    def pulse(self, widget, original_color, glow_color, duration=800):
        def _update(progress):
            t = progress * 2 if progress < 0.5 else 2 - progress * 2
            color = self._lerp_color(original_color, glow_color, t * 0.3)
            try:
                widget.configure(highlightbackground=color)
            except tk.TclError:
                pass
        self.animate(duration, _update, easing=AnimationEngine.ease_in_out_quart)

    @staticmethod
    def _lerp_color(c1, c2, t):
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"


# ============================================================
# 🌤️ 天气建议数据库（完整保留 v3.7）
# ============================================================
class WeatherTipsDB:
    _CATEGORY_MAP = {
        "sunny":  {0, 1},
        "cloudy": {2, 3},
        "fog":    {45, 48},
        "rain":   {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82},
        "snow":   {71, 73, 75, 77, 85, 86},
        "storm":  {95, 96, 99},
    }
    _TIPS = {
        "sunny": {"headline": "阳光充沛 · 把能量装进口袋", "items": [
            ("多巴胺漫步", "出门走 15 分钟，阳光直射皮肤可促进血清素与维生素 D 合成，是天然的情绪稳定剂。"),
            ("户外深呼吸", "找一处绿植区做 6 次腹式呼吸（吸 4 秒、呼 6 秒），降低皮质醇水平。"),
            ("补水提醒", "晴天容易脱水导致疲劳与烦躁，每隔 1 小时补充约 200ml 水。"),
        ]},
        "cloudy": {"headline": "多云时光 · 适合温和推进", "items": [
            ("番茄钟启动", "用 25 分钟专注 + 5 分钟休息推进一件事；柔和光线最适合深度工作。"),
            ("室内伸展", "肩颈环绕、靠墙站立 2 分钟，缓解久坐产生的低能量感。"),
            ("一杯温饮", "温水或淡茶，让身体在不刺眼的光线里慢慢『启动』。"),
        ]},
        "fog": {"headline": "雾气朦胧 · 放慢节奏更踏实", "items": [
            ("减速通勤", "雾天能见度低，预留多 10 分钟出行时间，降低焦躁感。"),
            ("书写式整理", "把脑中乱糟糟的事写到纸上，外化思绪，恢复清晰感。"),
            ("亮色光源", "打开暖白台灯或柑橘香薰，对抗雾天带来的低落。"),
        ]},
        "rain": {"headline": "雨天模式 · 把自己温柔包裹", "items": [
            ("白噪音陪伴", "雨声本身就是天然 ASMR，可放低音量作为背景，专注力会提升。"),
            ("一杯热饮仪式", "热可可、姜茶或牛奶。温热感会激活副交感神经，缓解紧绷。"),
            ("室内慢运动", "瑜伽或拉伸 10 分钟，代谢阴雨带来的钝痛与困倦。"),
        ]},
        "snow": {"headline": "雪日时刻 · 守住温度与节律", "items": [
            ("分层保暖", "重点护住颈部、脚踝。体温稳定，情绪更不易波动。"),
            ("热食满足感", "一碗热汤或燕麦粥，胃部温暖能直接降低焦虑感。"),
            ("窗边五分钟", "看雪 5 分钟，给视觉一个『慢镜头』，是最便宜的冥想。"),
        ]},
        "storm": {"headline": "雷雨天气 · 优先安全与安抚", "items": [
            ("远离窗户", "打雷时关好窗户、拔掉非必要电源，安全感是情绪稳定的前提。"),
            ("4-7-8 呼吸", "吸 4 秒、屏 7 秒、呼 8 秒，对抗雷声引发的惊吓反射。"),
            ("低刺激陪伴", "听轻音乐或有声书，避免强光、惊悚剧集叠加感官负担。"),
        ]},
        "default": {"headline": "舒适天气 · 顺势调节", "items": [
            ("十分钟轻活动", "散步、整理桌面或浇水，启动身体即启动情绪。"),
            ("一次主动联系", "给一位许久不见的朋友发条消息，建立微小连接。"),
            ("写下三件小确幸", "睡前回忆三件小好事，训练大脑捕捉积极信号。"),
        ]},
    }
    _TEMP_TIPS = {
        "hot":  ("高温降躁", "气温 ≥ 30°C，体感燥热易激惹。多喝凉水、避开正午外出，可显著降低烦躁感。"),
        "warm": ("温度宜人", "气温适合户外，安排一次 20 分钟的散步是最划算的情绪投资。"),
        "cool": ("微凉提神", "微凉天气最利于专注，安排今日最难的那件事在此时段。"),
        "cold": ("低温防御", "气温 ≤ 5°C，注意手脚保暖；身体一冷就更难调动正向情绪。"),
    }

    @classmethod
    def _category(cls, code):
        for name, codes in cls._CATEGORY_MAP.items():
            if code in codes:
                return name
        return "default"

    @classmethod
    def _temp_key(cls, temp):
        try:
            t = float(temp)
        except (TypeError, ValueError):
            return None
        if t >= 30: return "hot"
        if t >= 18: return "warm"
        if t >= 8:  return "cool"
        return "cold"

    @classmethod
    def get(cls, code, temp=None):
        cat = cls._category(code)
        base = cls._TIPS.get(cat, cls._TIPS["default"])
        items = list(base["items"])
        tk_ = cls._temp_key(temp)
        if tk_:
            items.append(cls._TEMP_TIPS[tk_])
        return {"headline": base["headline"], "items": items}

    @classmethod
    def offline(cls):
        return {"headline": "离线建议 · 网络未连接也能照顾自己", "items": [
            ("暂时不依赖网络", "把手机调成飞行模式 10 分钟，让神经系统从信息洪流中抽离。"),
            ("身体先动起来", "做 20 个深蹲或原地踏步 2 分钟，立即提升血氧与情绪基线。"),
            ("写一句感谢", "在纸上写下今天值得感谢的一件小事，训练积极注意力。"),
        ]}


# ============================================================
# ⚙️ 天气服务（完整保留 v3.7 多源定位）
# ============================================================
class WeatherService:
    W_MAP = {
        0: ("☀️","晴朗"), 1: ("🌤️","少云"), 2: ("⛅","多云"), 3: ("☁️","阴天"),
        45: ("🌫️","有雾"), 48: ("🌫️","雾凇"), 51: ("🌦️","细雨"), 53: ("🌦️","小雨"),
        55: ("🌧️","中雨"), 61: ("🌧️","小雨"), 63: ("🌧️","中雨"), 65: ("🌧️","大雨"),
        71: ("🌨️","小雪"), 73: ("🌨️","中雪"), 75: ("❄️","大雪"), 80: ("🌦️","阵雨"),
        81: ("🌧️","强阵雨"), 82: ("⛈️","暴雨"), 95: ("⛈️","雷雨"),
        96: ("⛈️","雷雨夹雹"), 99: ("⛈️","强雷暴"),
    }
    HEADERS = {"User-Agent": "MoodTool/4.0 (+https://example.local)"}

    @classmethod
    def _locate(cls):
        errors = []
        try:
            r = requests.get("http://ip-api.com/json/?fields=city,lat,lon,status,message",
                             timeout=6, headers=cls.HEADERS)
            j = r.json()
            if j.get("status") == "success":
                return {"city": j.get("city") or "未知地区", "lat": j["lat"], "lon": j["lon"]}
            errors.append(f"ip-api: {j.get('message')}")
        except Exception as e:
            errors.append(f"ip-api: {e}")
        try:
            r = requests.get("https://ipapi.co/json/", timeout=6, headers=cls.HEADERS)
            j = r.json()
            if j.get("latitude") is not None:
                return {"city": j.get("city") or "未知地区", "lat": j["latitude"], "lon": j["longitude"]}
            errors.append(f"ipapi.co: {j.get('reason')}")
        except Exception as e:
            errors.append(f"ipapi.co: {e}")
        try:
            r = requests.get("https://ipwho.is/", timeout=6, headers=cls.HEADERS)
            j = r.json()
            if j.get("success"):
                return {"city": j.get("city") or "未知地区", "lat": j["latitude"], "lon": j["longitude"]}
            errors.append(f"ipwho: {j.get('message')}")
        except Exception as e:
            errors.append(f"ipwho: {e}")
        raise RuntimeError("定位失败 -> " + " | ".join(errors))

    @classmethod
    def _weather(cls, lat, lon):
        params = {"latitude": lat, "longitude": lon, "current_weather": True, "timezone": "auto"}
        r = requests.get("https://api.open-meteo.com/v1/forecast",
                         params=params, timeout=8, headers=cls.HEADERS)
        r.raise_for_status()
        return r.json()

    @classmethod
    def fetch_all(cls, cb):
        def _run():
            try:
                loc = cls._locate()
                w = cls._weather(loc["lat"], loc["lon"])
                cw = w.get("current_weather") or {}
                code = int(cw.get("weathercode", 0))
                temp = cw.get("temperature")
                emoji, desc = cls.W_MAP.get(code, ("🌈", "舒适"))
                cb({"ok": True, "city": loc["city"], "emoji": emoji,
                    "desc": desc, "temp": temp, "code": code})
            except Exception as e:
                cb({"ok": False, "err": str(e)})
        threading.Thread(target=_run, daemon=True).start()


# ============================================================
# 🧱 高级 UI 组件
# ============================================================
class SmoothScrollContainer(tk.Frame):
    """带惯性的平滑滚动容器"""
    def __init__(self, parent, animator):
        super().__init__(parent, bg=T["bg"])
        self.animator = animator
        self.scroll_velocity = 0
        self.is_scrolling = False
        self._rendered = False
        self.canvas = tk.Canvas(self, bg=T["bg"], highlightthickness=0, bd=0)
        self.inner = tk.Frame(self.canvas, bg=T["bg"])
        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas_win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # 使用 bind 而非 bind_all，避免多实例时全局绑定互相覆盖
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.inner.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<MouseWheel>", self._on_mousewheel)

    def _bind_mousewheel_recursive(self, widget):
        """递归为所有子控件绑定滚轮事件"""
        try:
            widget.bind("<MouseWheel>", self._on_mousewheel)
            for child in widget.winfo_children():
                self._bind_mousewheel_recursive(child)
        except tk.TclError:
            pass

    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        # 每次 inner frame 变化时，重新绑定所有子控件的滚轮
        self._bind_mousewheel_recursive(self.inner)

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_win, width=event.width)

    def _on_mousewheel(self, event):
        # 仅在当前容器可见时处理滚轮
        if not self.winfo_ismapped():
            return
        self.scroll_velocity = -event.delta / 40.0
        if not self.is_scrolling:
            self.is_scrolling = True
            self._inertia_scroll()

    def _inertia_scroll(self):
        if abs(self.scroll_velocity) < 0.5:
            self.is_scrolling = False
            return
        self.canvas.yview_scroll(int(self.scroll_velocity), "units")
        self.scroll_velocity *= 0.85
        if self.winfo_exists():
            self.after(16, self._inertia_scroll)


class RoundedFrame(tk.Canvas):
    """圆角卡片容器 — 用 Canvas 绘制圆角矩形背景"""
    def __init__(self, parent, bg_color=None, radius=16, border_color=None,
                 border_width=2, **kwargs):
        bg_color = bg_color or T["card"]
        border_color = border_color or T["border_light"]
        super().__init__(parent, highlightthickness=0, bd=0,
                         bg=parent.cget("bg") if hasattr(parent, 'cget') else T["bg"], **kwargs)
        self.radius = radius
        self._bg_color = bg_color
        self._border_color = border_color
        self._border_width = border_width
        self._inner = tk.Frame(self, bg=bg_color)
        self._inner_win = None
        self.bind("<Configure>", self._redraw)

    @property
    def inner(self):
        return self._inner

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        """绘制圆角矩形"""
        points = [
            x1+r, y1, x1+r, y1, x2-r, y1, x2-r, y1,
            x2, y1, x2, y1+r, x2, y1+r, x2, y2-r,
            x2, y2-r, x2, y2, x2-r, y2, x2-r, y2,
            x1+r, y2, x1+r, y2, x1, y2, x1, y2-r,
            x1, y2-r, x1, y1+r, x1, y1+r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _redraw(self, event=None):
        self.delete("bg")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return
        bw = self._border_width
        # 绘制边框圆角矩形
        self._round_rect(bw//2, bw//2, w-bw//2, h-bw//2, self.radius,
                         fill=self._bg_color, outline=self._border_color,
                         width=bw, tags="bg")
        # 将 inner frame 放在 canvas 上
        if self._inner_win is None:
            self._inner_win = self.create_window(bw+4, bw+4, window=self._inner,
                                                  anchor="nw", tags="content")
        # 调整 inner frame 大小
        inner_w = max(w - 2*bw - 8, 1)
        inner_h = max(h - 2*bw - 8, 1)
        self.itemconfig(self._inner_win, width=inner_w)
        self.tag_raise("content")

    def set_border_color(self, color):
        self._border_color = color
        self._redraw()


class GlowCard(tk.Frame):
    """带悬停发光效果的圆角卡片（Canvas 圆角矩形背景）"""
    def __init__(self, parent, animator, glow_color=None, radius=14):
        parent_bg = T["bg"]
        try:
            parent_bg = parent.cget("bg")
        except Exception:
            pass
        super().__init__(parent, bg=parent_bg, bd=0, highlightthickness=0)
        self.animator = animator
        self.glow_color = glow_color or T["glow"]
        self.radius = radius
        self._current_border = T["border_light"]
        self._parent_bg = parent_bg

        # Canvas 作为圆角背景层
        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=parent_bg)
        self._canvas.pack(fill="both", expand=True)

        # 内部内容 frame
        self._inner = tk.Frame(self._canvas, bg=T["card"], bd=0)
        self._inner_win = self._canvas.create_window(6, 6, window=self._inner, anchor="nw")

        # 当内部内容大小变化时，更新 Canvas 大小
        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        self.bind("<Enter>", lambda e: self._animate_hover(True))
        self.bind("<Leave>", lambda e: self._animate_hover(False))
        self._canvas.bind("<Enter>", lambda e: self._animate_hover(True))
        self._canvas.bind("<Leave>", lambda e: self._animate_hover(False))
        self._inner.bind("<Enter>", lambda e: self._animate_hover(True))
        self._inner.bind("<Leave>", lambda e: self._animate_hover(False))

    def pack_content(self):
        """返回内部 frame 供外部添加内容"""
        return self._inner

    def _on_inner_configure(self, event):
        """内部内容改变时，调整 Canvas 最小高度"""
        req_w = self._inner.winfo_reqwidth()
        req_h = self._inner.winfo_reqheight()
        # Canvas 需要比 inner 大一圈（留出边框空间）
        self._canvas.configure(height=req_h + 12, width=req_w + 12)
        self._redraw()

    def _on_canvas_configure(self, event):
        """Canvas 大小变化时重绘圆角与调整 inner 宽度"""
        w = event.width
        if w > 12:
            self._canvas.itemconfig(self._inner_win, width=w - 12)
        self._redraw()

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1+r, y1, x1+r, y1, x2-r, y1, x2-r, y1,
            x2, y1, x2, y1+r, x2, y1+r, x2, y2-r,
            x2, y2-r, x2, y2, x2-r, y2, x2-r, y2,
            x1+r, y2, x1+r, y2, x1, y2, x1, y2-r,
            x1, y2-r, x1, y1+r, x1, y1+r, x1, y1,
        ]
        return self._canvas.create_polygon(points, smooth=True, **kwargs)

    def _redraw(self, event=None):
        self._canvas.delete("bg")
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w <= 1 or h <= 1:
            return
        self._round_rect(1, 1, w-1, h-1, self.radius,
                         fill=T["card"], outline=self._current_border,
                         width=2, tags="bg")
        self._canvas.tag_raise(self._inner_win)

    def _animate_hover(self, entering):
        start_color = self._current_border
        end = self.glow_color if entering else T["border_light"]
        def _update(progress):
            color = Animator._lerp_color(start_color, end, progress)
            self._current_border = color
            try: self._redraw()
            except tk.TclError: pass
        self.animator.animate(250, _update, easing=AnimationEngine.ease_out_expo)


class AnimatedExpandCard(tk.Frame):
    """带动画展开效果的情绪方案卡片（圆角版）"""
    def __init__(self, parent, item_data, animator, delay_index=0):
        super().__init__(parent, bg=T["bg"])
        self.data = item_data
        self.animator = animator
        self.expanded = False
        self.body = None
        self._animating = False

        # 使用简化的圆角卡片（Frame + 圆角边框模拟）
        self.card = tk.Frame(self, bg=T["card"], bd=0,
                             highlightthickness=2, highlightbackground=T["border_light"])
        self.card.pack(fill="x", pady=2)
        # 通过 configure relief + borderwidth 模拟圆角感
        self.card.configure(relief="flat")

        self.header = tk.Frame(self.card, bg=T["card"], padx=24, pady=20, cursor="hand2")
        self.header.pack(fill="x")

        icon_bg = tk.Frame(self.header, bg=T["prim_l"], width=52, height=52,
                           highlightthickness=0)
        icon_bg.pack(side="left", padx=(0, 18))
        icon_bg.pack_propagate(False)
        icon_lbl = tk.Label(icon_bg, text=item_data["icon"], font=F["emoji_m"], bg=T["prim_l"])
        icon_lbl.place(relx=0.5, rely=0.5, anchor="center")

        mid = tk.Frame(self.header, bg=T["card"])
        mid.pack(side="left", fill="x", expand=True)
        title_lbl = tk.Label(mid, text=item_data["title"], font=F["head"], fg=T["text_h"], bg=T["card"])
        title_lbl.pack(anchor="w")
        sub_lbl = tk.Label(mid, text=f"{len(item_data['methods'])} 个科学方案",
                           font=F["small"], fg=T["text_s"], bg=T["card"])
        sub_lbl.pack(anchor="w", pady=(2, 0))

        self.arrow = tk.Label(self.header, text="▸", font=("Microsoft YaHei UI", 14),
                             fg=T["prim"], bg=T["card"])
        self.arrow.pack(side="right", padx=(10, 0))

        for w in (self.header, icon_bg, icon_lbl, title_lbl, sub_lbl, self.arrow):
            w.bind("<Button-1>", lambda e: self._toggle())

        # 入场动画
        self.card.configure(highlightbackground=T["bg"])
        self.after(delay_index * 80, self._entrance)

    def _entrance(self):
        if not self.winfo_exists():
            return
        def _update(p):
            color = Animator._lerp_color(T["bg"], T["border_light"], p)
            try: self.card.configure(highlightbackground=color)
            except tk.TclError: pass
        self.animator.animate(400, _update)

    def _toggle(self):
        if self._animating: return
        if self.expanded: self._collapse()
        else: self._expand()

    def _expand(self):
        self._animating = True
        self.expanded = True
        self.arrow.config(text="▾")
        self.body = tk.Frame(self.card, bg=T["prim_l"], padx=24, pady=0)
        self.body.pack(fill="x")
        for i, (m_title, m_desc) in enumerate(self.data["methods"], 1):
            mf = tk.Frame(self.body, bg=T["card"], padx=18, pady=14,
                          highlightthickness=1, highlightbackground=T["border_light"])
            mf.pack(fill="x", pady=5, padx=4)
            num = tk.Frame(mf, bg=T["prim"], width=24, height=24)
            num.pack(side="left", padx=(0, 14))
            num.pack_propagate(False)
            tk.Label(num, text=str(i), font=F["tiny"], fg=T["white"],
                    bg=T["prim"]).place(relx=0.5, rely=0.5, anchor="center")
            tf = tk.Frame(mf, bg=T["card"])
            tf.pack(side="left", fill="x", expand=True)
            tk.Label(tf, text=m_title, font=F["head"], fg=T["prim"],
                    bg=T["card"], anchor="w").pack(fill="x")
            tk.Label(tf, text=m_desc, font=F["body"], fg=T["text_b"],
                    bg=T["card"], wraplength=580, justify="left", anchor="w").pack(fill="x", pady=(4,0))
            mf.bind("<Enter>", lambda e, f=mf: f.configure(highlightbackground=T["prim_light"]))
            mf.bind("<Leave>", lambda e, f=mf: f.configure(highlightbackground=T["border_light"]))
        tk.Frame(self.body, bg=T["prim_l"], height=12).pack(fill="x")
        self.animator.pulse(self.card, T["border_light"], T["prim_light"], duration=600)
        self._animating = False

    def _collapse(self):
        self._animating = True
        self.arrow.config(text="▸")
        if self.body: self.body.destroy(); self.body = None
        self.expanded = False
        self._animating = False


class GradientHeader(tk.Canvas):
    """渐变色头部"""
    def __init__(self, parent, height=130):
        super().__init__(parent, height=height, highlightthickness=0, bd=0)
        self.pack(fill="x")
        self.h = height
        self.bind("<Configure>", self._draw)

    def _draw(self, event=None):
        self.delete("gradient")
        w = self.winfo_width()
        if w <= 1: return
        steps = 80
        for i in range(steps):
            t = i / steps
            if t < 0.5:
                t2 = t * 2
                r = int(int(T["gradient_1"][1:3],16)*(1-t2) + int(T["gradient_2"][1:3],16)*t2)
                g = int(int(T["gradient_1"][3:5],16)*(1-t2) + int(T["gradient_2"][3:5],16)*t2)
                b = int(int(T["gradient_1"][5:7],16)*(1-t2) + int(T["gradient_2"][5:7],16)*t2)
            else:
                t2 = (t - 0.5) * 2
                r = int(int(T["gradient_2"][1:3],16)*(1-t2) + int(T["gradient_3"][1:3],16)*t2)
                g = int(int(T["gradient_2"][3:5],16)*(1-t2) + int(T["gradient_3"][3:5],16)*t2)
                b = int(int(T["gradient_2"][5:7],16)*(1-t2) + int(T["gradient_3"][5:7],16)*t2)
            color = f"#{r:02x}{g:02x}{b:02x}"
            x0, x1 = int(w*i/steps), int(w*(i+1)/steps)+1
            self.create_rectangle(x0, 0, x1, self.h, fill=color, outline=color, tags="gradient")
        hour = datetime.now().hour
        greeting = ("早安，开启舒心的一天 ☀️" if 5 <= hour < 12
                    else "午后好，恢复能量 🌤️" if 12 <= hour < 18
                    else "晚安，静享安宁 🌙")
        self.create_text(w//2, self.h//2-14, text=greeting, font=F["title"], fill="white", tags="gradient")
        self.create_text(w//2, self.h//2+20, text="✦ 基于心理学方案 · 陪你调节每一份情绪 ✦",
                        font=F["body"], fill="#E0E7FF", tags="gradient")


class AnimatedNavBar(tk.Frame):
    """带动画的圆角导航栏"""
    def __init__(self, parent, tabs, on_switch, animator):
        super().__init__(parent, bg=T["bg"], pady=14)
        self.animator = animator
        self.on_switch = on_switch
        self.current_idx = 0
        # 圆角药丸形容器
        self.pill = tk.Frame(self, bg=T["nav_bg"], padx=6, pady=6,
                             highlightthickness=1, highlightbackground=T["border_light"])
        self.pill.pack(anchor="center")
        self.btns = []
        for i, (icon, name) in enumerate(tabs):
            btn = tk.Label(self.pill, text=f"{icon}  {name}", font=F["body"],
                          padx=32, pady=10, cursor="hand2", bg=T["nav_bg"], fg=T["text_s"])
            btn.pack(side="left", padx=3)
            btn.bind("<Button-1>", lambda e, idx=i: self._switch_to(idx))
            btn.bind("<Enter>", lambda e, b=btn, idx=i: self._hover(b, idx, True))
            btn.bind("<Leave>", lambda e, b=btn, idx=i: self._hover(b, idx, False))
            self.btns.append(btn)
        self._activate(0, animate=False)

    def _switch_to(self, idx):
        if idx == self.current_idx: return
        self.current_idx = idx
        self._activate(idx)
        self.on_switch(idx)

    def _activate(self, idx, animate=True):
        for i, btn in enumerate(self.btns):
            if i == idx:
                if animate:
                    def _update(p, b=btn):
                        bg = Animator._lerp_color(T["nav_bg"], T["white"], p)
                        fg = Animator._lerp_color(T["text_s"], T["prim"], p)
                        try: b.config(bg=bg, fg=fg)
                        except tk.TclError: pass
                    self.animator.animate(200, _update, easing=AnimationEngine.ease_out_expo)
                else:
                    btn.config(bg=T["white"], fg=T["prim"])
            else:
                btn.config(bg=T["nav_bg"], fg=T["text_s"])

    def _hover(self, btn, idx, entering):
        if idx == self.current_idx: return
        btn.config(fg=T["text_b"] if entering else T["text_s"])


# ============================================================
# 🏠 主程序 - 灵动版
# ============================================================
class MoodApp:
    def __init__(self, root):
        self.root = root
        self.root.title("情绪调节小工具 v4.0 ✦ 灵动版")
        self.root.geometry("960x780")
        self.root.minsize(880, 680)
        self.root.configure(bg=T["bg"])
        self.animator = Animator(root)

        # 渲染占位
        self.suggest_container = None
        self.suggest_headline = None
        self.lbl_temp = None
        self.lbl_desc = None
        self.w_icon = None
        self.loading_dot = None

        self._init_header()
        self._init_content()
        self._init_nav()
        self._init_footer()
        self._refresh_weather()
        self._start_ambient()

    def _init_header(self):
        self.gradient_header = GradientHeader(self.root, height=130)

    def _init_content(self):
        self.main_container = tk.Frame(self.root, bg=T["bg"])
        self.main_container.pack(fill="both", expand=True)
        self.page_weather = SmoothScrollContainer(self.main_container, self.animator)
        self.page_quick = SmoothScrollContainer(self.main_container, self.animator)

    def _init_nav(self):
        tabs = [("🌤", "天气建议"), ("⚡", "快捷调节")]
        self.navbar = AnimatedNavBar(self.root, tabs, self._switch_page, self.animator)
        self.navbar.pack(fill="x")
        self._switch_page(0)

    def _init_footer(self):
        footer = tk.Frame(self.root, bg=T["border_light"], height=32,
                          highlightthickness=0)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self.status_dot = tk.Label(footer, text="●", font=F["tiny"], fg=T["success"], bg=T["border_light"])
        self.status_dot.pack(side="left", padx=(20, 6), pady=6)
        self.status_label = tk.Label(footer, text="系统就绪 · 等待数据同步",
                                    font=F["tiny"], fg=T["text_s"], bg=T["border_light"])
        self.status_label.pack(side="left", pady=6)
        tk.Label(footer, text=datetime.now().strftime("%Y-%m-%d %H:%M"),
                font=F["tiny"], fg=T["text_s"], bg=T["border_light"]).pack(side="right", padx=20, pady=6)

    def _switch_page(self, idx):
        if idx == 0:
            self.page_quick.pack_forget()
            self.page_weather.pack(fill="both", expand=True)
            self._render_weather()
        else:
            self.page_weather.pack_forget()
            self.page_quick.pack(fill="both", expand=True)
            self._render_quick()

    def _render_weather(self):
        c = self.page_weather.inner
        if self.page_weather._rendered:
            return
        self.page_weather._rendered = True

        weather_card = GlowCard(c, self.animator, glow_color=T["accent_light"])
        weather_card.pack(fill="x", padx=30, pady=(24, 16))
        wi = weather_card.pack_content()
        wi.configure(padx=36, pady=32)

        self.w_icon = tk.Label(wi, text="⌛", font=F["emoji_l"], bg=T["card"])
        self.w_icon.pack(side="left")

        info = tk.Frame(wi, bg=T["card"])
        info.pack(side="left", padx=30, fill="x", expand=True)
        self.lbl_temp = tk.Label(info, text="--°C", font=F["title"], fg=T["text_h"], bg=T["card"])
        self.lbl_temp.pack(anchor="w")
        self.lbl_desc = tk.Label(info, text="正在同步天气数据...", font=F["body"], fg=T["text_s"], bg=T["card"])
        self.lbl_desc.pack(anchor="w", pady=(4, 0))

        self.loading_dot = tk.Label(wi, text="◌", font=("Segoe UI", 16), fg=T["prim_light"], bg=T["card"])
        self.loading_dot.pack(side="right", padx=10)
        self._animate_loading()

        self.suggest_headline = tk.Label(c, text="💡 今日建议", font=F["head"], bg=T["bg"], fg=T["text_h"])
        self.suggest_headline.pack(anchor="w", padx=30, pady=(10, 8))

        self.suggest_container = tk.Frame(c, bg=T["bg"])
        self.suggest_container.pack(fill="x", padx=28)
        tk.Label(self.suggest_container, text="正在为您匹配最契合当前天气的情绪调节方案... ✨",
                font=F["body"], fg=T["text_s"], bg=T["bg"]).pack(anchor="w", padx=5)

    def _render_quick(self):
        c = self.page_quick.inner
        if self.page_quick._rendered:
            return
        self.page_quick._rendered = True

        hf = tk.Frame(c, bg=T["bg"], padx=30, pady=(20, 12))
        hf.pack(fill="x")
        tk.Label(hf, text="⚡", font=F["emoji_s"], bg=T["bg"]).pack(side="left")
        tk.Label(hf, text="  针对性情绪方案", font=F["head"], fg=T["text_h"], bg=T["bg"]).pack(side="left")
        tk.Label(hf, text=f"共 {len(QuickDB.ITEMS)} 种情绪", font=F["small"], fg=T["text_s"], bg=T["bg"]).pack(side="right")
        tk.Frame(c, bg=T["border"], height=1).pack(fill="x", padx=30, pady=(0, 8))
        for i, item in enumerate(QuickDB.ITEMS):
            AnimatedExpandCard(c, item, self.animator, delay_index=i).pack(fill="x", padx=28, pady=4)
        tk.Frame(c, bg=T["bg"], height=30).pack(fill="x")

    def _animate_loading(self):
        symbols = ["◐", "◓", "◑", "◒"]
        self._li = 0
        def _rot():
            if not self.root.winfo_exists(): return
            try:
                if self.loading_dot and self.loading_dot.winfo_exists():
                    self._li = (self._li + 1) % 4
                    self.loading_dot.config(text=symbols[self._li])
                    self.root.after(250, _rot)
            except tk.TclError: pass
        _rot()

    def _start_ambient(self):
        def _breathe():
            if not self.root.winfo_exists(): return
            t = (time.time() % 3) / 3
            alpha = 0.4 + 0.6 * (math.sin(t * math.pi * 2) + 1) / 2
            r = int(16 + 16 * alpha)
            g = int(185 + 70 * (1 - alpha))
            b = int(129 + 126 * (1 - alpha))
            try: self.status_dot.config(fg=f"#{min(r,255):02x}{min(g,255):02x}{min(b,255):02x}")
            except tk.TclError: return
            self.root.after(50, _breathe)
        self.root.after(1000, _breathe)

    def _refresh_weather(self):
        WeatherService.fetch_all(self._on_weather)

    def _on_weather(self, res):
        self.root.after(0, lambda: self._apply_weather(res))

    def _apply_weather(self, res):
        if not self.root.winfo_exists(): return
        if self.lbl_temp is None: self._render_weather()

        if res.get("ok"):
            temp = res.get("temp")
            try: temp_text = f"{float(temp):.1f}°C"
            except: temp_text = "--°C"
            self.w_icon.config(text=res["emoji"])
            self.lbl_temp.config(text=temp_text, fg=T["text_h"])
            self.lbl_desc.config(text=f"📍 {res['city']} · {res['desc']}", fg=T["text_s"])
            if self.loading_dot: self.loading_dot.config(text="✓", fg=T["success"])
            self.status_label.config(text=f"已同步 · {res['city']} {res['desc']} {temp_text}")
            tips = WeatherTipsDB.get(res["code"], temp)
            self._populate_suggestions(tips)
            # 圆角卡片不再使用 pulse（无 highlightbackground）
        else:
            self.lbl_temp.config(text="--°C", fg=T["warn"])
            self.lbl_desc.config(text="天气同步失败，已为您切换为离线建议", fg=T["warn"])
            self.w_icon.config(text="📵")
            if self.loading_dot: self.loading_dot.config(text="✗", fg=T["warn"])
            self.status_label.config(text="网络异常 · 已启用离线建议")
            self.status_dot.config(fg=T["warn"])
            self._populate_suggestions(WeatherTipsDB.offline())

    def _populate_suggestions(self, tips):
        if not self.suggest_container or not self.suggest_container.winfo_exists(): return
        for w in self.suggest_container.winfo_children(): w.destroy()
        if self.suggest_headline and self.suggest_headline.winfo_exists():
            self.suggest_headline.config(text=f"💡 {tips['headline']}")
        for i, (title, desc) in enumerate(tips["items"], 1):
            card = GlowCard(self.suggest_container, self.animator, glow_color=T["prim_light"])
            card.pack(fill="x", pady=5)
            inner = card.pack_content()
            inner.configure(padx=18, pady=14)
            num = tk.Frame(inner, bg=T["prim"], width=24, height=24)
            num.pack(side="left", padx=(0, 14))
            num.pack_propagate(False)
            tk.Label(num, text=str(i), font=F["tiny"], fg=T["white"],
                    bg=T["prim"]).place(relx=0.5, rely=0.5, anchor="center")
            tf = tk.Frame(inner, bg=T["card"])
            tf.pack(side="left", fill="x", expand=True)
            tk.Label(tf, text=title, font=F["head"], fg=T["prim"], bg=T["card"], anchor="w").pack(fill="x")
            tk.Label(tf, text=desc, font=F["body"], fg=T["text_b"], bg=T["card"],
                    wraplength=650, justify="left", anchor="w").pack(fill="x", pady=(4, 0))


# ============================================================
# 📦 快捷调节数据库
# ============================================================
class QuickDB:
    ITEMS = [
        {"icon": "😰", "title": "焦虑不安", "methods": [
            ("5-4-3-2-1 感官法", "寻找5种看到的、4种触碰到的、3种听到的、2种闻到的、1种尝到的。瞬间拉回当下。"),
            ("4-7-8 呼吸", "吸气4秒，屏息7秒，呼气8秒。重复4次，有效放松。"),
            ("担忧外化记录", "写下担心的事。标注『能控制』的，专注前者，暂时放下后者。"),
        ]},
        {"icon": "😤", "title": "愤怒烦躁", "methods": [
            ("10秒延迟法则", "想发火前默数10个数。给理智大脑（前额叶）留出接管时间。"),
            ("物理能量释放", "撕碎废纸、捏压力球或快走。代谢掉积压的攻击能量。"),
            ("冷水降温法", "用冷水洗脸或握住冰块。触发潜水反射，强制心跳减速。"),
        ]},
        {"icon": "😢", "title": "悲伤低落", "methods": [
            ("悲伤限定时间", "允许悲伤15分钟。闹钟响后去洗脸，做一件极小的事。"),
            ("微小行为激活", "即使没动力也强迫刷牙或整理椅子。行动先于动力。"),
            ("自然光照激活", "接受15分钟照射。阳光是天然抗抑郁剂。"),
        ]},
        {"icon": "🤯", "title": "压力过载", "methods": [
            ("原子化拆解", "把任务拆解到极小步骤。降低启动阻碍感。"),
            ("四象限法则", "区分紧急与重要。优先处理重要不紧急的事。"),
            ("15分钟剧烈运动", "开合跳或快走。代谢体内的压力激素。"),
        ]},
        {"icon": "😶", "title": "拖延无动力", "methods": [
            ("『只做5分钟』", "告诉自己只做5分钟。通常一旦开始，惯性会带你继续。"),
            ("环境气味唤醒", "换房间或闻柑橘香气。刺激唤醒意志力。"),
            ("即时奖励锚点", "设定小奖赏：写完这段话就吃块巧克力。"),
        ]},
        {"icon": "🌀", "title": "精神内耗", "methods": [
            ("寻找反证记录", "写下过去3件成功的小事。用证据对抗偏见。"),
            ("语言剥离法", '不要说『我很失败』，要说『我产生了一个 "我很失败" 的念头』。你不是你的想法。'),
            ("STOP 停顿技术", "Stop(停下) -> Take(呼吸) -> Observe(观察) -> Proceed(行动)。"),
        ]},
        {"icon": "😵\u200d💫", "title": "注意力涣散", "methods": [
            ("物理隔离分心源", "手机锁进抽屉。视线看不见干扰，专注力自动提升。"),
            ("单任务原则", "一次只处理一件事。任务切换会产生极高疲劳。"),
            ("白噪音屏障", "播放雨声背景音。过滤杂音，进入心流。"),
        ]},
        {"icon": "😨", "title": "社交焦虑", "methods": [
            ("注意力外移练习", "停止监控自己。强迫观察外部细节。将焦点投向外界。"),
            ("万能话题准备", "提前准备天气等话题。有预案会减轻恐慌。"),
            ("接纳紧张反应", "告诉自己紧张在提供能量。越承认越放松。"),
        ]},
        {"icon": "😴", "title": "失眠多梦", "methods": [
            ("肌肉渐进放松", "从脚趾开始用力收缩5秒再放松。一路向上。"),
            ("床铺功能纯化", "不在床上玩手机。建立床与睡眠的强关联。"),
            ("思维日志转存", "把待办写在纸上。告诉大脑：已经记好了，可以休息。"),
        ]},
    ]


# ============================================================
# 🚀 启动
# ============================================================
if __name__ == "__main__":
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TScrollbar", troughcolor=T["bg"], background=T["prim_light"],
                    bordercolor=T["bg"], arrowcolor=T["prim"])
    app = MoodApp(root)
    root.mainloop()
