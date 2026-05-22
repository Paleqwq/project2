# -*- coding: utf-8 -*-
"""
情绪调节小工具 — 灵动美化版 (Fluid UI v4.2 - Anti-Aliased Smooth)
基于 fix/weather-suggestions 分支 (v3.7) 升级：
1. 动画引擎：平滑展开/收起、淡入淡出、呼吸光效
2. 悬停交互：卡片悬停发光、颜色渐变过渡
3. 现代视觉：渐变头部、柔和配色、层次分明
4. 流畅滚动：惯性滚动、平滑滚轮 + 可拖拽滑块
5. 微交互：交错入场、状态切换动画、加载指示
6. 心情转盘：5 选 1 等概率随机决策（喝茶 / 站起 / 刷手机 / 运动 / 零食）
7. 保留全部 v3.7 功能：多源定位、SSL兼容、WeatherTipsDB、离线建议

v4.1 流畅度专项优化（让画面过渡更顺滑、帧率更高）：
 - Animator: perf_counter 时间驱动 + 漂移补偿调度，目标 ~120Hz；同进度跳帧抑制
 - MoodWheel: 一次性 build canvas item，旋转期改用 itemconfig/coords 增量更新
   （单帧 50+ 次 delete/create → 15 次属性改写，转盘真正"丝滑"）
 - 滚动：yview_moveto 亚像素分数滚动 + 速度累加 + 0.92 衰减，告别整行跳变
 - 呼吸光：50ms (20fps) → 16ms (~60fps)，颜色 lerp 平滑无台阶

v4.2 抗锯齿专项优化（让画面更光滑，告别像素台阶）：
 - MoodWheel：tk 的原生 create_arc 不支持抗锯齿，扇形边沿很糙；
   改用 PIL 在 3x 超采样画面上绘制 pieslice，再 LANCZOS 下采样到显示尺寸，
   边缘平滑度肉眼可见地提升一个档次。旋转使用 BICUBIC 重采样。
 - 圆角卡片：splinesteps 12 → 36，圆角曲线更柔和，不再"折角"。
 - 兜底：PIL 不可用时自动回退到原 tk 扇形渲染，不会崩。
"""

import os
import sys
import ssl
import threading
import math
import random
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

# ----- 抗锯齿渲染依赖（Pillow）：可选依赖，未安装时优雅降级到 tk 原生绘制 -----
# 思路：tk Canvas 的 create_arc / create_oval 不做抗锯齿，曲面边缘很糙。
# 使用 PIL 在 3x 超采样画布上画好图形，再用 LANCZOS 滤波下采样到显示尺寸，
# 借助滤波器的"加权平均"让边缘像素呈现亚像素级渐变，肉眼看上去就"光滑"了。
try:
    from PIL import Image, ImageDraw, ImageTk  # noqa: F401
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

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
    """高帧率动画引擎 - 基于 perf_counter 的真实时间驱动 + 漂移补偿调度

    关键设计（让画面更顺滑的核心）：
    1. 使用 time.perf_counter()，不受系统墙上时钟跳动影响，比 time.time() 更精准；
    2. 进度严格按"真实流逝时间 / 总时长"计算，不依赖帧数，因此即便某一帧
       因 GC/重绘耗时拖慢，下一帧会自动追上去，动画总时长稳定；
    3. 漂移补偿：下一帧 delay = max(1, 目标间隔 - 本帧实际工作耗时)，
       让平均帧率始终贴近目标，而不是越跑越慢；
    4. 默认目标 ~120Hz (8ms 间隔)。Tk 的事件循环最高约 60-100fps，
       8ms 调度让"准备好就尽快画"，配合补偿后实际帧率显著高于固定 16ms；
    5. 跳帧抑制：同一进度值不会重复触发 on_update，省下 widget 重绘。
    """

    FRAME_INTERVAL_MS = 8  # 目标帧间隔 (~125Hz)，给系统留余量后实际逼近 60-90fps

    def __init__(self, root):
        self.root = root

    def animate(self, duration_ms, on_update, on_complete=None, easing=None):
        if easing is None:
            easing = AnimationEngine.ease_out_cubic
        start_time = time.perf_counter()
        duration_s = max(duration_ms / 1000.0, 1e-6)
        last_progress = [-1.0]

        def _step():
            if not self.root.winfo_exists():
                return
            frame_start = time.perf_counter()
            elapsed = frame_start - start_time
            progress = min(elapsed / duration_s, 1.0)
            # 跳帧抑制：进度未变（高刷下偶尔出现）就不重画，省 CPU
            if progress != last_progress[0]:
                eased = easing(progress)
                try:
                    on_update(eased)
                except tk.TclError:
                    return
                last_progress[0] = progress

            if progress < 1.0:
                # 漂移补偿：本帧花了多久、就从下一帧的间隔里扣多久
                work_ms = (time.perf_counter() - frame_start) * 1000.0
                next_delay = max(1, int(self.FRAME_INTERVAL_MS - work_ms))
                self.root.after(next_delay, _step)
            elif on_complete:
                on_complete()

        # 立即（下一个 idle）起步，避免开头那 16ms 的迟滞感
        self.root.after(1, _step)

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
    """带惯性的平滑滚动容器 + 可拖拽滚动条（方便鼠标精确定位）

    平滑度优化（v4.1）：
    - 改用 yview_moveto 做亚像素级分数滚动，告别 yview_scroll(int,"units")
      的整行跳变。低速滚动时不再"卡格子"。
    - 速度累加而非覆盖：连续滚轮事件能叠加冲量，符合直觉。
    - 衰减系数从 0.85 调到 0.92，惯性帧数更多，停下更自然。
    - 帧间隔 16ms → 8ms，惯性更新更频繁，配合分数滚动看起来更顺滑。
    """
    SCROLL_FRAME_MS = 8       # 惯性帧间隔（~120Hz 目标）
    SCROLL_DECAY = 0.92       # 速度衰减；越接近 1，惯性拖尾越长
    SCROLL_STOP_EPS = 0.05    # 速度小于此值时停止
    SCROLL_PIXELS_PER_UNIT = 22  # 1 速度单位约等于多少像素，调节体感
    SCROLL_VELOCITY_CAP = 18.0   # 防止用户疯狂滚导致冲量爆炸

    def __init__(self, parent, animator):
        super().__init__(parent, bg=T["bg"])
        self.animator = animator
        self.scroll_velocity = 0
        self.is_scrolling = False
        self._rendered = False
        self._syncing = False
        self.canvas = tk.Canvas(self, bg=T["bg"], highlightthickness=0, bd=0)
        # 可拖拽滚动条 —— 用户可以直接抓取滑块精确定位到任意位置
        self.scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self._on_scrollbar,
            style="Mood.Vertical.TScrollbar",
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.inner = tk.Frame(self.canvas, bg=T["bg"])
        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas_win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        # 先放滚动条，再让 canvas 占据剩余空间，避免被压缩成 0 宽
        self.scrollbar.pack(side="right", fill="y", padx=(2, 6), pady=4)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # 冗余：把 <Configure> 也绑在外层 Frame 与 <Map> 上。
        # PyInstaller 封包后 canvas 自身的 <Configure> 不一定及时触发，
        # 外层 Frame 的 <Configure> 与首次 <Map> 是更可靠的尺寸信号。
        self.bind("<Configure>", self._on_self_configure)
        self.bind("<Map>", self._on_self_configure)
        # 使用 bind 而非 bind_all，避免多实例时全局绑定互相覆盖
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.inner.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<MouseWheel>", self._on_mousewheel)

    def sync_inner_width(self, fallback_widths=()):
        """显式同步 inner frame 宽度到 canvas 宽度，并刷新 scrollregion。
        封包后 <Configure> 链路不可靠时由外部主动调用。"""
        if self._syncing:
            return
        self._syncing = True
        try:
            candidates = [
                self.canvas.winfo_width(),
                self.winfo_width(),
                *fallback_widths,
            ]
            w = next((c for c in candidates if isinstance(c, int) and c > 1), 0)
            if w > 1:
                try:
                    cur = self.canvas.itemcget(self.canvas_win, "width")
                    cur_w = int(float(cur)) if cur else 0
                except (tk.TclError, ValueError):
                    cur_w = 0
                if cur_w != w:
                    self.canvas.itemconfig(self.canvas_win, width=w)
            try:
                bbox = self.canvas.bbox("all")
                if bbox:
                    self.canvas.configure(scrollregion=bbox)
            except tk.TclError:
                pass
        except tk.TclError:
            pass
        finally:
            self._syncing = False

    def _on_self_configure(self, event=None):
        # 外层 Frame 尺寸变化（含首次 Map）时，主动把宽度同步给 canvas window
        self.sync_inner_width()

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
        # 累加冲量（而不是覆盖）：连续滚轮事件能叠加，手感更顺
        delta = -event.delta / 40.0
        self.scroll_velocity = max(
            -self.SCROLL_VELOCITY_CAP,
            min(self.SCROLL_VELOCITY_CAP, self.scroll_velocity + delta),
        )
        if not self.is_scrolling:
            self.is_scrolling = True
            self._inertia_scroll()

    def _on_scrollbar(self, *args):
        # 用户主动拖拽 / 点击滑块时，立即终止惯性滚动，避免抖动
        self.scroll_velocity = 0
        self.is_scrolling = False
        self.canvas.yview(*args)

    def _inertia_scroll(self):
        if abs(self.scroll_velocity) < self.SCROLL_STOP_EPS:
            self.is_scrolling = False
            return
        try:
            bbox = self.canvas.bbox("all")
            canvas_h = self.canvas.winfo_height()
            if bbox and canvas_h > 0:
                total_h = bbox[3] - bbox[1]
                if total_h > canvas_h:
                    # 分数滚动：把"速度*像素/像素总高"加到 yview top，
                    # 实现亚像素级平滑滚动（yview_scroll units 会强制取整）
                    top, _ = self.canvas.yview()
                    delta_frac = (self.scroll_velocity * self.SCROLL_PIXELS_PER_UNIT) / total_h
                    new_top = top + delta_frac
                    max_top = max(0.0, 1.0 - canvas_h / total_h)
                    new_top = max(0.0, min(new_top, max_top))
                    self.canvas.yview_moveto(new_top)
                    # 撞到顶/底就立刻把速度归零，避免无谓空转
                    if new_top <= 0.0 or new_top >= max_top:
                        self.scroll_velocity = 0
        except tk.TclError:
            self.is_scrolling = False
            return
        self.scroll_velocity *= self.SCROLL_DECAY
        if self.winfo_exists():
            self.after(self.SCROLL_FRAME_MS, self._inertia_scroll)


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
        """绘制圆角矩形

        smooth=True 时 tk 用 B-spline 插值；splinesteps 默认 12，分段太少
        会让圆角看起来"有折角"。提到 36 之后曲线明显变柔和，对性能几乎无影响
        （只在 <Configure> 时重绘一次）。
        """
        points = [
            x1+r, y1, x1+r, y1, x2-r, y1, x2-r, y1,
            x2, y1, x2, y1+r, x2, y1+r, x2, y2-r,
            x2, y2-r, x2, y2, x2-r, y2, x2-r, y2,
            x1+r, y2, x1+r, y2, x1, y2, x1, y2-r,
            x1, y2-r, x1, y1+r, x1, y1+r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, splinesteps=36, **kwargs)

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
    """带悬停发光效果的卡片（柔和厚边框模拟圆角视觉）

    关键修复（解决"鼠标移到卡片上底下的光不流畅"）：
    1. Enter/Leave 动画都从 *当前实际颜色* 起步，不再硬编码起点，
       这样快速进出鼠标时不会出现颜色"跳变"。
    2. 通过 token 让旧动画静默失效，避免多个动画同时写
       highlightbackground 互相抢占，产生闪烁。
    3. 把 Enter/Leave 也绑到所有子控件上：tk 的 <Leave> 会在鼠标
       从父卡片移到内部 Label/Frame 的瞬间触发，原实现因此会
       不停 leave→enter→leave 循环，看起来就是"光晕在抖"。
       现在统一用「鼠标是否真的还在卡片矩形内」作为权威判断。
    """
    def __init__(self, parent, animator, glow_color=None, radius=14):
        # 使用厚边框 + 浅色边框模拟柔和圆角的视觉效果
        super().__init__(parent, bg=T["card"], bd=0,
                         highlightthickness=2, highlightbackground=T["border_light"])
        self.animator = animator
        self.glow_color = glow_color or T["glow"]
        self.radius = radius  # 保留参数兼容旧调用，不再使用
        self._base_color = T["border_light"]
        self._current_color = self._base_color
        self._is_hovered = False
        self._anim_token = 0
        self._bound_widgets = set()
        self._leave_pending = False
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        # 首次显示后把 Enter/Leave 也绑到所有后代控件
        self.bind("<Map>", lambda e: self._bind_descendants())

    def pack_content(self):
        """返回自身作为内容容器（兼容旧 API）"""
        return self

    def _bind_descendants(self):
        try:
            self._bind_recursive(self)
        except tk.TclError:
            pass
        # 子树可能在 Map 之后才完全建好（如 _populate_suggestions 里再追加内容），
        # 短延迟后再扫一次，确保新加入的子控件也被覆盖到。
        self.after(120, self._bind_recursive_safe)

    def _bind_recursive_safe(self):
        try:
            self._bind_recursive(self)
        except tk.TclError:
            pass

    def _bind_recursive(self, w):
        for child in w.winfo_children():
            if child not in self._bound_widgets:
                try:
                    child.bind("<Enter>", self._on_enter, add="+")
                    child.bind("<Leave>", self._on_leave, add="+")
                    self._bound_widgets.add(child)
                except tk.TclError:
                    continue
            self._bind_recursive(child)

    def _mouse_inside(self):
        try:
            x, y = self.winfo_pointerxy()
            wx, wy = self.winfo_rootx(), self.winfo_rooty()
            ww, wh = self.winfo_width(), self.winfo_height()
            return wx <= x < wx + ww and wy <= y < wy + wh
        except tk.TclError:
            return False

    def _on_enter(self, _event=None):
        if self._is_hovered:
            return
        self._is_hovered = True
        self._animate_to(self.glow_color)

    def _on_leave(self, _event=None):
        # 子→父 / 父→子 切换时也会触发 <Leave>，所以延迟一帧再判断
        # 鼠标是否真的离开卡片矩形，避免误退出造成抖动。
        if self._leave_pending:
            return
        self._leave_pending = True
        self.after(30, self._maybe_leave)

    def _maybe_leave(self):
        self._leave_pending = False
        if not self.winfo_exists():
            return
        if self._mouse_inside():
            return
        if not self._is_hovered:
            return
        self._is_hovered = False
        self._animate_to(self._base_color)

    def _animate_to(self, target):
        # 失效之前还在跑的动画 —— 它们的 _update 会在 token 不匹配时直接返回
        self._anim_token += 1
        token = self._anim_token
        start = self._current_color

        def _update(p):
            if token != self._anim_token:
                return
            color = Animator._lerp_color(start, target, p)
            self._current_color = color
            try:
                self.configure(highlightbackground=color)
            except tk.TclError:
                pass
        # 320ms + ease_out_cubic：足够让鼠标快速划过时也能保持平滑感
        self.animator.animate(320, _update, easing=AnimationEngine.ease_out_cubic)

    def pulse_glow(self, accent_color=None, duration=900):
        """一次性高亮脉冲，与 hover 系统协同（不会再被 hover 动画抢占）。"""
        accent = accent_color or self.glow_color
        self._anim_token += 1
        token = self._anim_token
        start = self._current_color
        peak = accent

        def _update(p):
            if token != self._anim_token or not self.winfo_exists():
                return
            # 0→0.5 上升、0.5→1 回落；如果中途用户开始悬停，就由 _animate_to 接管
            t = p * 2 if p < 0.5 else 2 - p * 2
            color = Animator._lerp_color(start, peak, t)
            self._current_color = color
            try:
                self.configure(highlightbackground=color)
            except tk.TclError:
                pass

        def _done():
            if token == self._anim_token and not self._is_hovered:
                self._current_color = self._base_color
                try:
                    self.configure(highlightbackground=self._base_color)
                except tk.TclError:
                    pass
        self.animator.animate(duration, _update, on_complete=_done,
                              easing=AnimationEngine.ease_in_out_quart)


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


class MoodWheel(tk.Frame):
    """🎡 心情转盘 - 五个等概率选项的随机决策转盘

    设计要点：
    - 五等分扇形（每片 72°），五种主题色对应五个选项；
    - 顶部三角指针固定不动，扇形整体绕中心旋转；
    - 旋转用 ease_out_cubic 缓动 + 至少 5 圈整圈，模拟物理减速；
    - 每个选项概率严格等于 1/5（random.randint 决定目标扇区，不是
      凭最终角度反推，避免浮点误差导致的概率偏差）；
    - 落定后弹出 WheelResultDialog 给出具体说明。
    """

    # 排版说明：数字与紧随其后的中文单位之间使用 NBSP (\u00A0) 而非普通空格。
    # tkinter 的 Label wraplength 是按"空白处可断行"的英文式规则换行，普通空格
    # 会让 "5" 与 "分钟" 被拆到两行（出现「…10\n分钟」这种尴尬断行）。
    # NBSP 在 Tk 中被视为不可断行字符，能让 "数字+单位" 永远黏在同一行，
    # 同时保留作者原本想要的视觉空隙。
    OPTIONS = [
        ("🍵", "喝一杯茶",
         "泡一杯热茶，给自己\u00A05\u00A0分钟无目的地慢慢喝。温热感会激活副交感神经，"
         "让心跳变慢、肩膀松下来，是性价比极高的小型暂停。"),
        ("🪑", "站起来休息一会",
         "起身走\u00A02\u00A0分钟，远眺窗外或做几个简单拉伸。每小时离开座位一次，"
         "眼睛、脊柱和情绪都会明显变好。"),
        ("📱", "刷\u00A010\u00A0分钟手机",
         "给自己一个明确的\u00A010\u00A0分钟窗口，刷完就放下。比『偷偷刷』更有掌控感，"
         "也不用背负罪恶感，是合法的小奖励。"),
        ("🏃", "去运动一下",
         "做\u00A03\u00A0组\u00A010\u00A0个深蹲，或下楼快走\u00A010\u00A0分钟。"
         "运动是最划算的情绪药，5\u00A0分钟内就能把心率和心情同时拉起来。"),
        ("🍪", "吃点小零食",
         "拿一份你喜欢的零食，专心吃完它。把注意力交给一件具体的小事，"
         "可以暂时切断焦虑回路，给大脑一个『现在很好』的信号。"),
    ]

    SECTOR_COLORS = [
        "#FCA5A5",  # 茶 - 暖红
        "#FCD34D",  # 椅 - 黄
        "#86EFAC",  # 手机 - 绿
        "#93C5FD",  # 运动 - 蓝
        "#C4B5FD",  # 零食 - 紫
    ]

    def __init__(self, parent, animator):
        super().__init__(parent, bg=T["bg"])
        self.animator = animator
        self.angle = 0.0       # 当前旋转角度（度）
        self.spinning = False
        self.canvas_size = 360

        # 抗锯齿渲染状态：PIL 不可用时自动降级到 tk 原生绘制
        self._use_pil = _HAS_PIL
        self._wheel_base_pil = None     # base 图：超采样后下采样到显示尺寸（含 AA 边缘）
        self._wheel_photo = None        # 当前帧的 ImageTk.PhotoImage —— 必须持引用，
                                        # GC 后 tk 内部的 image 也会被销毁。
        self._wheel_image_id = None     # canvas image item id（旋转时 itemconfig 替换）

        # 旋转期间复用的 canvas item ID（avoid 每帧 delete+create 全部重建）
        self._arc_ids = []
        self._icon_ids = []
        self._title_ids = []
        self._cx = self._cy = self._r = 0

        # ---- 标题区 ----
        head = tk.Frame(self, bg=T["bg"])
        head.pack(fill="x", padx=30, pady=(20, 12))
        tk.Label(head, text="🎡", font=F["emoji_s"], bg=T["bg"]).pack(side="left")
        tk.Label(head, text="  转一下，让随机替你做决定", font=F["head"],
                 fg=T["text_h"], bg=T["bg"]).pack(side="left")
        tk.Label(head, text=f"共 {len(self.OPTIONS)} 个选项 · 等概率",
                 font=F["small"], fg=T["text_s"], bg=T["bg"]).pack(side="right")
        tk.Frame(self, bg=T["border"], height=1).pack(fill="x", padx=30, pady=(0, 16))

        tk.Label(self, text="不知道现在该做什么？让转盘替你决定。",
                 font=F["body"], fg=T["text_b"], bg=T["bg"]).pack(pady=(0, 12))

        # ---- 转盘画布 ----
        self.canvas = tk.Canvas(
            self, width=self.canvas_size, height=self.canvas_size + 24,
            bg=T["bg"], highlightthickness=0, bd=0,
        )
        self.canvas.pack(pady=(4, 6))
        self._build_wheel()  # 一次性建好所有 canvas item，后续旋转只改属性

        # ---- 结果提示行 ----
        self.result_label = tk.Label(
            self, text="点击下方按钮，让转盘开始旋转 ✨",
            font=F["body"], fg=T["text_s"], bg=T["bg"],
        )
        self.result_label.pack(pady=(8, 8))

        # ---- 旋转按钮 ----
        self.btn = tk.Label(
            self, text="🎲   开始旋转   🎲", font=F["head"],
            bg=T["prim"], fg=T["white"], padx=44, pady=14,
            cursor="hand2",
        )
        self.btn.pack(pady=(8, 24))
        self.btn.bind("<Button-1>", lambda e: self.spin())
        self.btn.bind("<Enter>", lambda e: self._btn_hover(True))
        self.btn.bind("<Leave>", lambda e: self._btn_hover(False))

    def _btn_hover(self, entering):
        if self.spinning:
            return
        self.btn.config(bg=T["prim_dark"] if entering else T["prim"])

    def _build_wheel(self):
        """构建转盘：根据 PIL 可用性分派到抗锯齿路径或 tk 原生路径。

        共同步骤：
        - 清空 canvas
        - 记录中心坐标 (cx, cy) 和半径 r（其它方法都基于这个）
        - 画扇形（PIL: 一张 AA 图；tk: 5 个 create_arc）
        - 画文字标签（5 组 icon + title 的 canvas text）
        - 画静态叠加层（中心圆盘、🎯 字符、顶部三角指针）
        """
        self.canvas.delete("all")
        self._arc_ids = []
        self._icon_ids = []
        self._title_ids = []
        self._wheel_image_id = None

        size = self.canvas_size
        cx, cy = size // 2, size // 2 + 12   # 给顶部指针留 12px
        r = size // 2 - 18
        self._cx, self._cy, self._r = cx, cy, r

        # 扇形渲染分派
        if self._use_pil:
            try:
                self._build_wheel_aa()
            except Exception as e:
                # PIL 异常时透明降级，保证转盘永远能用
                sys.stderr.write(f"[mood_tool] PIL wheel render failed, falling back: {e!r}\n")
                self._use_pil = False
                self.canvas.delete("all")
                self._arc_ids = []
                self._icon_ids = []
                self._title_ids = []
                self._wheel_image_id = None
                self._build_wheel_legacy()
        else:
            self._build_wheel_legacy()

        # 静态叠加：中心圆盘 + 🎯 + 顶部指针（不随旋转变）
        self._draw_static_overlay()

    def _build_wheel_aa(self):
        """PIL 抗锯齿路径：用一张超采样下采样的 RGBA 图代替 5 个 create_arc。

        优点：边缘像素被 LANCZOS 滤波器加权平均出亚像素级渐变，
        视觉效果由"硬阶梯锯齿"变成"丝绒般光滑"。
        旋转时只需 Image.rotate + 重新 PhotoImage + itemconfig，单帧 ~5ms。
        """
        cx, cy, r = self._cx, self._cy, self._r
        diameter = 2 * r

        # 一次性构建 base 图（未旋转）。后续每帧仅旋转、不再重画扇形。
        self._wheel_base_pil = self._render_wheel_pil_base(diameter)

        # 初始角度可能为 0（首次构建）也可能不是 0（重建时保留当前角度）
        if self.angle:
            display_img = self._wheel_base_pil.rotate(
                self.angle, resample=Image.BICUBIC, expand=False,
            )
        else:
            display_img = self._wheel_base_pil

        photo = ImageTk.PhotoImage(display_img)
        self._wheel_image_id = self.canvas.create_image(cx, cy, image=photo)
        # 关键：必须把 photo 挂到 self 上。tkinter 不会增加 Python 引用计数，
        # 一旦 PhotoImage 对象被 GC，其底层的 tk 图也随之销毁，canvas 上就空了。
        self._wheel_photo = photo

        # 文字标签依然用 canvas text（freetype 已天然抗锯齿，无须 PIL）。
        # 旋转时只需 update coords，不必重建 widget。
        n = len(self.OPTIONS)
        sector_angle = 360 / n
        text_r = r * 0.66
        for i, (icon, title, _) in enumerate(self.OPTIONS):
            start = self.angle + i * sector_angle
            mid = math.radians(start + sector_angle / 2)
            tx = cx + text_r * math.cos(mid)
            ty = cy - text_r * math.sin(mid)
            icon_id = self.canvas.create_text(
                tx, ty - 14, text=icon, font=("Segoe UI Emoji", 22),
            )
            title_id = self.canvas.create_text(
                tx, ty + 14, text=title, font=F["small"], fill=T["text_h"],
            )
            self._icon_ids.append(icon_id)
            self._title_ids.append(title_id)

    @classmethod
    def _render_wheel_pil_base(cls, diameter):
        """生成 wheel 的抗锯齿 base 图（未旋转，转盘正面朝向 0°）。

        关键算法：
        1. 在 3x 超采样画布（大 9 倍像素）上画 pieslice —— 大画布上锯齿就是
           子像素级的细锯齿；
        2. 用 LANCZOS（窗口 sinc）滤波下采样回 1x —— 滤波器把多个超采样像素
           加权平均成一个目标像素，边缘自然出现亚像素级渐变。
        3. PIL 的 pieslice 角度约定与 tk arc 相反（PIL CW，tk CCW）；
           画完后 vertical flip 一下就对齐了，比改 angle 算式更直观。

        坐标约定：base 图里 self.angle = 0 时，sector 0（茶）的起始边在 3 点钟方向，
        与 tk arc start=0 的位置一致；后续 Image.rotate(angle, ...) 也是 CCW，
        正好对应 tk arc 的 start += angle 行为。
        """
        SS = 3                                       # 超采样倍数
        big = diameter * SS
        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        n = len(cls.OPTIONS)
        sector_angle = 360.0 / n
        bbox = (0, 0, big - 1, big - 1)
        outline_w = max(1, 3 * SS)
        white = (255, 255, 255, 255)

        for i in range(n):
            start = i * sector_angle
            end = start + sector_angle
            color_hex = cls.SECTOR_COLORS[i % len(cls.SECTOR_COLORS)]
            rgb = tuple(int(color_hex[j:j+2], 16) for j in (1, 3, 5))
            draw.pieslice(
                bbox, start, end,
                fill=rgb + (255,), outline=white, width=outline_w,
            )

        # PIL 的 CW 翻成 tk arc 的 CCW
        img = img.transpose(Image.FLIP_TOP_BOTTOM)

        # LANCZOS 下采样：超采样 + 高质量重采样 = 抗锯齿
        return img.resize((diameter, diameter), Image.LANCZOS)

    def _build_wheel_legacy(self):
        """tk 原生扇形渲染（PIL 不可用时的兜底，视觉上有锯齿）。"""
        cx, cy, r = self._cx, self._cy, self._r
        n = len(self.OPTIONS)
        sector_angle = 360 / n

        for i, (icon, title, _) in enumerate(self.OPTIONS):
            start = self.angle + i * sector_angle
            color = self.SECTOR_COLORS[i % len(self.SECTOR_COLORS)]
            arc_id = self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=start, extent=sector_angle,
                fill=color, outline=T["white"], width=3, style="pieslice",
            )
            self._arc_ids.append(arc_id)

            mid = math.radians(start + sector_angle / 2)
            tx = cx + (r * 0.66) * math.cos(mid)
            ty = cy - (r * 0.66) * math.sin(mid)
            icon_id = self.canvas.create_text(tx, ty - 14, text=icon,
                                              font=("Segoe UI Emoji", 22))
            title_id = self.canvas.create_text(tx, ty + 14, text=title,
                                               font=F["small"], fill=T["text_h"])
            self._icon_ids.append(icon_id)
            self._title_ids.append(title_id)

    def _draw_static_overlay(self):
        """中心圆盘 + 🎯 + 顶部三角指针：不随旋转变，画在 wheel 之上。"""
        cx, cy = self._cx, self._cy
        cr = 28
        self.canvas.create_oval(cx - cr, cy - cr, cx + cr, cy + cr,
                                fill=T["white"], outline=T["prim"], width=3)
        self.canvas.create_text(cx, cy, text="🎯",
                                font=("Segoe UI Emoji", 22))
        # 顶部指针（静态）
        self.canvas.create_polygon(
            cx - 16, 4, cx + 16, 4, cx, 36,
            fill=T["prim_dark"], outline=T["white"], width=2,
        )

    def _update_wheel_rotation(self):
        """高频热路径：仅更新随旋转变化的属性。

        AA 路径单帧成本估算：
          Image.rotate (BICUBIC, 324x324) ≈ 3-5 ms
          ImageTk.PhotoImage 构造        ≈ 1-2 ms
          itemconfig + 5*coords          ≈ <1 ms
          合计 ~5-8 ms，60fps (16ms 预算) 安全。
        Legacy 路径单帧仅 5 次 itemconfig + 10 次 coords ≈ <1 ms。
        """
        if (self._use_pil
                and self._wheel_base_pil is not None
                and self._wheel_image_id is not None):
            self._update_wheel_rotation_aa()
        else:
            self._update_wheel_rotation_legacy()

    def _update_wheel_rotation_aa(self):
        cx, cy, r = self._cx, self._cy, self._r
        n = len(self.OPTIONS)
        sector_angle = 360 / n
        text_r = r * 0.66
        try:
            # BICUBIC 比 BILINEAR 更顺滑，比 LANCZOS 更快，旋转动画里最优解
            rotated = self._wheel_base_pil.rotate(
                self.angle, resample=Image.BICUBIC, expand=False,
            )
            new_photo = ImageTk.PhotoImage(rotated)
            # 顺序很重要：先 itemconfig 让 tk 接管新 image，再覆盖 self._wheel_photo，
            # 旧 photo 此时才进入 GC 候选，tk 已经不在用它了
            self.canvas.itemconfig(self._wheel_image_id, image=new_photo)
            self._wheel_photo = new_photo

            for i in range(n):
                start = self.angle + i * sector_angle
                mid = math.radians(start + sector_angle / 2)
                tx = cx + text_r * math.cos(mid)
                ty = cy - text_r * math.sin(mid)
                self.canvas.coords(self._icon_ids[i], tx, ty - 14)
                self.canvas.coords(self._title_ids[i], tx, ty + 14)
        except tk.TclError:
            # 控件被销毁时静默退出
            pass
        except Exception as e:
            # PIL 偶发异常 → 这一帧跳过，下一帧继续。不要让动画整体崩。
            sys.stderr.write(f"[mood_tool] AA wheel rotate frame skipped: {e!r}\n")

    def _update_wheel_rotation_legacy(self):
        if not self._arc_ids:
            self._build_wheel()
            return
        n = len(self.OPTIONS)
        sector_angle = 360 / n
        cx, cy, r = self._cx, self._cy, self._r
        text_r = r * 0.66
        try:
            for i in range(n):
                start = self.angle + i * sector_angle
                self.canvas.itemconfig(self._arc_ids[i], start=start)
                mid = math.radians(start + sector_angle / 2)
                tx = cx + text_r * math.cos(mid)
                ty = cy - text_r * math.sin(mid)
                self.canvas.coords(self._icon_ids[i], tx, ty - 14)
                self.canvas.coords(self._title_ids[i], tx, ty + 14)
        except tk.TclError:
            # 控件被销毁时静默退出
            pass

    # 兼容旧调用点（如果以后有人想完整重建）
    def _draw_wheel(self):
        self._build_wheel()

    def spin(self):
        if self.spinning:
            return
        self.spinning = True
        self.btn.config(bg=T["text_s"], text="🌀   旋转中...")
        self.result_label.config(text="🌀  转盘正在为你挑选...", fg=T["prim"])

        n = len(self.OPTIONS)
        sector_angle = 360 / n

        # 关键：先用 randint 等概率选目标扇区，再据此计算落点角度。
        # 这样保证概率严格 1/5，不会因浮点最终角度落在边界上偏倚。
        target_idx = random.randint(0, n - 1)

        # tk Canvas 的 arc 角度：0° 在 3 点钟方向，逆时针为正。
        # 顶部指针位于 90°；要让扇区 i 的中心落在 90°：
        #   self.angle + i*sector_angle + sector_angle/2 ≡ 90  (mod 360)
        target_base = (90 - target_idx * sector_angle - sector_angle / 2) % 360

        # 至少 5 圈整圈 + 落到目标，确保视觉上有「真的转过」的感觉。
        extra_rotations = 5
        current = self.angle % 360
        delta = (target_base - current) % 360 + extra_rotations * 360

        start_angle = self.angle
        end_angle = self.angle + delta

        def _update(p):
            self.angle = start_angle + (end_angle - start_angle) * p
            self._update_wheel_rotation()

        def _done():
            self.angle = end_angle
            self._update_wheel_rotation()
            self.spinning = False
            self.btn.config(bg=T["prim"], text="🎲   再转一次   🎲")
            self._show_result(target_idx)

        # 3 秒 + ease_out_cubic：开头快、末尾慢慢停下，物理感更强
        self.animator.animate(3000, _update, on_complete=_done,
                              easing=AnimationEngine.ease_out_cubic)

    def _show_result(self, idx):
        icon, title, desc = self.OPTIONS[idx]
        self.result_label.config(
            text=f"✨ 转盘选中：{icon}  {title}", fg=T["prim_dark"],
        )
        WheelResultDialog(self.winfo_toplevel(), icon, title, desc)


class WheelResultDialog(tk.Toplevel):
    """🎉 心情转盘结果弹窗 - 展示选中项 + 详细做法。

    布局尺寸说明（修复『边框遮挡文字』）：
    - 弹窗整体放大到 600 x 500，给长描述留足竖向空间；
    - 描述卡片 `desc_frame.pack(padx=OUTER)` + `desc_frame(padx=INNER)`，
      `wraplength` 必须 ≤ 可用宽度，否则换行后每行右端会被内边框/内 padding
      盖住，看起来就像「文字被边框吃了」。
        可用宽度 = 600 - 2*OUTER - 2*INNER - 2*highlightthickness
    """

    # 几何参数集中放，调整尺寸只改一处
    DIALOG_W = 600
    DIALOG_H = 500
    OUTER_PAD = 36   # desc 卡片与窗口边缘的距离
    INNER_PAD = 22   # desc 卡片内部 padding

    def __init__(self, parent, icon, title, desc):
        super().__init__(parent)
        self.title("✨ 转盘结果")
        self.configure(bg=T["card"])
        self.resizable(False, False)
        # 模态：阻塞在父窗口上，避免连续乱点旋转
        self.transient(parent)
        try:
            self.grab_set()
        except tk.TclError:
            pass

        w, h = self.DIALOG_W, self.DIALOG_H
        # 计算 wraplength：留 4px 安全余量给字体 metrics 的舍入误差，
        # 避免最后一个汉字偶发性贴边
        wraplength = w - 2 * self.OUTER_PAD - 2 * self.INNER_PAD - 2 - 4

        self.geometry(f"{w}x{h}")
        # 居中到父窗口
        try:
            self.update_idletasks()
            px = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
            py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
            self.geometry(f"{w}x{h}+{max(px, 0)}+{max(py, 0)}")
        except tk.TclError:
            pass

        # 顶部装饰条（稍加厚一点，更显眼）
        tk.Frame(self, bg=T["prim"], height=8).pack(fill="x")

        # 图标 + 标题
        tk.Label(self, text=icon, font=("Segoe UI Emoji", 60),
                 bg=T["card"]).pack(pady=(28, 6))
        tk.Label(self, text=title, font=F["title"],
                 fg=T["text_h"], bg=T["card"]).pack()
        tk.Label(self, text="✨  转盘为你选定", font=F["small"],
                 fg=T["text_s"], bg=T["card"]).pack(pady=(6, 18))

        # 描述卡片：使用 subtitle 字号让长描述更清楚易读
        desc_frame = tk.Frame(
            self, bg=T["prim_l"],
            padx=self.INNER_PAD, pady=self.INNER_PAD,
            highlightthickness=1, highlightbackground=T["prim_light"],
        )
        desc_frame.pack(fill="x", padx=self.OUTER_PAD)
        tk.Label(
            desc_frame, text=desc, font=F["subtitle"], fg=T["text_b"],
            bg=T["prim_l"], wraplength=wraplength, justify="left",
        ).pack(anchor="w", fill="x")

        # 关闭按钮
        btn = tk.Label(self, text="知道了，去做这件事", font=F["head"],
                       bg=T["prim"], fg=T["white"], padx=36, pady=12,
                       cursor="hand2")
        btn.pack(pady=(24, 26))
        btn.bind("<Button-1>", lambda e: self.destroy())
        btn.bind("<Enter>", lambda e: btn.config(bg=T["prim_dark"]))
        btn.bind("<Leave>", lambda e: btn.config(bg=T["prim"]))

        # Esc 关闭，并主动获取焦点
        self.bind("<Escape>", lambda e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.focus_force()


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
        self.root.title("情绪调节小工具 v4.2 ✦ 灵动版 · Smooth-AA")
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
        # 预渲染：把两个页面的内容在 init 阶段就构建好。
        # 即便 PyInstaller 封包后 Canvas <Configure> 事件链不可靠，
        # 内容的 widget 也已经存在；切换页面后只需要把宽度对齐到 canvas 即可。
        # 这一步对解决"封包后点击快捷调节看不到心情卡片"非常关键。
        # 用 try/except 兜底：万一渲染过程里某个 widget 选项不被当前 Tcl 构建
        # 接受（比如老 Tk 不认 Frame pady tuple），不要把整个 app 拖崩，
        # 切换页面时还有惰性渲染兜底。
        try:
            self._render_weather()
        except Exception as e:
            sys.stderr.write(f"[mood_tool] eager render weather failed: {e!r}\n")
        try:
            self._render_quick()
        except Exception as e:
            sys.stderr.write(f"[mood_tool] eager render quick failed: {e!r}\n")
        try:
            self._render_wheel()
        except Exception as e:
            sys.stderr.write(f"[mood_tool] eager render wheel failed: {e!r}\n")
        self._refresh_weather()
        self._start_ambient()

    def _init_header(self):
        self.gradient_header = GradientHeader(self.root, height=130)

    def _init_content(self):
        self.main_container = tk.Frame(self.root, bg=T["bg"])
        self.main_container.pack(fill="both", expand=True)
        self.page_weather = SmoothScrollContainer(self.main_container, self.animator)
        self.page_quick = SmoothScrollContainer(self.main_container, self.animator)
        self.page_wheel = SmoothScrollContainer(self.main_container, self.animator)

    def _init_nav(self):
        tabs = [("🌤", "天气建议"), ("⚡", "快捷调节"), ("🎡", "心情转盘")]
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
        # 三页用列表统一管理，避免 if/else 分支随页面增加而膨胀
        pages = [
            (self.page_weather, self._render_weather),
            (self.page_quick,   self._render_quick),
            (self.page_wheel,   self._render_wheel),
        ]
        # 先把其它页面收起，再把当前页 pack 到主容器里
        for i, (p, _) in enumerate(pages):
            if i != idx:
                p.pack_forget()
        target, render_fn = pages[idx]
        target.pack(fill="both", expand=True)
        # 关键修复（封包后点击快捷调节空白）：
        # 1) 用 update() 而非 update_idletasks()，确保 <Configure> 事件被派发
        #    而不仅仅是 idle 任务被处理。这是切换页面时 canvas 拿到真实宽度的前提。
        # 2) 渲染（首次切换时才会真正建 widget；预渲染过则是 no-op）。
        # 3) 立即同步一次宽度 + 多次延迟兜底刷新，应对封包后的尺寸事件抖动。
        try:
            self.root.update()
        except tk.TclError:
            pass
        render_fn()
        self._refresh_scroll(target)
        self.root.after(0, lambda: self._refresh_scroll(target))
        self.root.after(50, lambda: self._refresh_scroll(target))
        self.root.after(150, lambda: self._refresh_scroll(target))

    def _refresh_scroll(self, container):
        """强制刷新滚动容器的 inner 宽度和 scrollregion，
        修复封包后 <Configure> 事件链不可靠导致内容不显示的问题。
        多重宽度回退，避免 canvas.winfo_width() 还是 1 时静默不刷新。"""
        if not container.winfo_exists():
            return
        try:
            container.update_idletasks()
        except tk.TclError:
            return
        fallbacks = []
        if hasattr(self, "main_container") and self.main_container.winfo_exists():
            fallbacks.append(self.main_container.winfo_width())
        if self.root.winfo_exists():
            fallbacks.append(self.root.winfo_width())
        container.sync_inner_width(tuple(fallbacks))

    def _render_weather(self):
        c = self.page_weather.inner
        if self.page_weather._rendered:
            return

        weather_card = GlowCard(c, self.animator, glow_color=T["accent_light"])
        weather_card.pack(fill="x", padx=30, pady=(24, 16))
        # 保存引用，让 _apply_weather 的脉冲走 GlowCard 协同通道，
        # 避免直接写 highlightbackground 与 hover 动画相互抢占
        self.weather_card = weather_card
        wi = tk.Frame(weather_card, bg=T["card"], padx=36, pady=32)
        wi.pack(fill="x")

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
        # 仅在全部 widget 创建成功后再标记已渲染，
        # 避免中途异常把页面卡在"_rendered=True 但内容残缺"的状态。
        self.page_weather._rendered = True

    def _render_quick(self):
        c = self.page_quick.inner
        if self.page_quick._rendered:
            return

        # 注意：tk.Frame 的 widget 选项 padx/pady 在部分 Tcl/Tk 构建里
        # 不接受 tuple（"bad screen distance" 错），所以非对称 padding
        # 一律挪到 .pack() 上（pack/grid 的 padx/pady 是支持 tuple 的）。
        hf = tk.Frame(c, bg=T["bg"])
        hf.pack(fill="x", padx=30, pady=(20, 12))
        tk.Label(hf, text="⚡", font=F["emoji_s"], bg=T["bg"]).pack(side="left")
        tk.Label(hf, text="  针对性情绪方案", font=F["head"], fg=T["text_h"], bg=T["bg"]).pack(side="left")
        tk.Label(hf, text=f"共 {len(QuickDB.ITEMS)} 种情绪", font=F["small"], fg=T["text_s"], bg=T["bg"]).pack(side="right")
        tk.Frame(c, bg=T["border"], height=1).pack(fill="x", padx=30, pady=(0, 8))
        for i, item in enumerate(QuickDB.ITEMS):
            AnimatedExpandCard(c, item, self.animator, delay_index=i).pack(fill="x", padx=28, pady=4)
        tk.Frame(c, bg=T["bg"], height=30).pack(fill="x")
        # 同上：成功后才标记已渲染
        self.page_quick._rendered = True

    def _render_wheel(self):
        c = self.page_wheel.inner
        if self.page_wheel._rendered:
            return
        # 心情转盘：把整个 MoodWheel 居中放进滚动容器
        wheel = MoodWheel(c, self.animator)
        wheel.pack(anchor="center", pady=(4, 0))
        tk.Frame(c, bg=T["bg"], height=30).pack(fill="x")
        # 同上：成功后才标记已渲染
        self.page_wheel._rendered = True

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
        """状态点的呼吸光晕：从 50ms (~20fps) 提到 16ms (~60fps)，
        颜色插值改用线性 RGB lerp，过渡更顺，肉眼几乎看不到色阶台阶。"""
        # 起止颜色：成功绿 → 紫调主色，呼吸感更柔
        c_a = T["success"]   # #10B981
        c_b = T["prim_light"]  # #A5B4FC
        ra, ga, ba = int(c_a[1:3], 16), int(c_a[3:5], 16), int(c_a[5:7], 16)
        rb, gb, bb = int(c_b[1:3], 16), int(c_b[3:5], 16), int(c_b[5:7], 16)
        period_s = 3.2  # 一个完整呼吸的时长

        def _breathe():
            if not self.root.winfo_exists():
                return
            # 用 perf_counter 算相位，画面停顿后也能"接着呼吸"，无突跳
            t = (time.perf_counter() % period_s) / period_s
            # 0..1..0 平滑曲线
            alpha = (math.sin(t * math.pi * 2 - math.pi / 2) + 1) / 2
            r = int(ra + (rb - ra) * alpha)
            g = int(ga + (gb - ga) * alpha)
            b = int(ba + (bb - ba) * alpha)
            try:
                self.status_dot.config(fg=f"#{r:02x}{g:02x}{b:02x}")
            except tk.TclError:
                return
            self.root.after(16, _breathe)

        self.root.after(800, _breathe)

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
            self._refresh_scroll(self.page_weather)
            # 走 GlowCard 自身的脉冲通道，与 hover 动画协同（不会互相抢色）
            try:
                if hasattr(self, "weather_card") and self.weather_card.winfo_exists():
                    self.weather_card.pulse_glow(T["accent_light"], duration=1000)
            except Exception:
                pass
        else:
            self.lbl_temp.config(text="--°C", fg=T["warn"])
            self.lbl_desc.config(text="天气同步失败，已为您切换为离线建议", fg=T["warn"])
            self.w_icon.config(text="📵")
            if self.loading_dot: self.loading_dot.config(text="✗", fg=T["warn"])
            self.status_label.config(text="网络异常 · 已启用离线建议")
            self.status_dot.config(fg=T["warn"])
            self._populate_suggestions(WeatherTipsDB.offline())
            self._refresh_scroll(self.page_weather)

    def _populate_suggestions(self, tips):
        if not self.suggest_container or not self.suggest_container.winfo_exists(): return
        for w in self.suggest_container.winfo_children(): w.destroy()
        if self.suggest_headline and self.suggest_headline.winfo_exists():
            self.suggest_headline.config(text=f"💡 {tips['headline']}")
        for i, (title, desc) in enumerate(tips["items"], 1):
            card = GlowCard(self.suggest_container, self.animator, glow_color=T["prim_light"])
            card.pack(fill="x", pady=5)
            inner = tk.Frame(card, bg=T["card"], padx=18, pady=14)
            inner.pack(fill="x")
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
    # 自定义滚动条样式：主题配色 + 悬停/拖动反馈，方便用户精确定位
    style.configure(
        "Mood.Vertical.TScrollbar",
        troughcolor=T["nav_bg"],
        background=T["prim_light"],
        bordercolor=T["nav_bg"],
        arrowcolor=T["prim"],
        gripcount=0,
        relief="flat",
        borderwidth=0,
    )
    style.map(
        "Mood.Vertical.TScrollbar",
        background=[("active", T["prim"]), ("pressed", T["prim_dark"])],
        arrowcolor=[("active", T["prim_dark"])],
    )
    # 兼容旧引用
    style.configure("TScrollbar", troughcolor=T["bg"], background=T["prim_light"],
                    bordercolor=T["bg"], arrowcolor=T["prim"])
    app = MoodApp(root)
    root.mainloop()
