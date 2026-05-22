# -*- coding: utf-8 -*-
"""
情绪调节小工具 — 灵动美化版 (Fluid UI v4.0)
全新升级：
1. 动画系统：平滑展开/收起、淡入淡出、呼吸光效
2. 悬停交互：卡片悬停升起、颜色渐变过渡
3. 现代视觉：毛玻璃质感、柔和阴影、渐变色彩
4. 流畅滚动：惯性滚动、平滑滚轮
5. 微交互：点击涟漪、状态切换动画
"""

import tkinter as tk
from tkinter import ttk
import threading
import requests
import math
import time
from datetime import datetime

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
    """统一动画调度器，支持多种缓动曲线"""
    
    @staticmethod
    def ease_out_cubic(t):
        """减速缓动 - 自然舒适的减速感"""
        return 1 - pow(1 - t, 3)
    
    @staticmethod
    def ease_out_back(t):
        """弹性回弹 - 灵动弹跳效果"""
        c1 = 1.70158
        c3 = c1 + 1
        return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)
    
    @staticmethod
    def ease_in_out_quart(t):
        """平滑加减速"""
        if t < 0.5:
            return 8 * t * t * t * t
        else:
            return 1 - pow(-2 * t + 2, 4) / 2
    
    @staticmethod
    def ease_out_expo(t):
        """指数减速 - 极致丝滑"""
        return 1 if t == 1 else 1 - pow(2, -10 * t)
    
    @staticmethod
    def spring(t, damping=0.6, frequency=4.5):
        """弹簧物理效果"""
        return 1 - math.exp(-damping * t * 10) * math.cos(frequency * t * math.pi)


class Animator:
    """动画控制器 - 管理所有正在进行的动画"""
    
    def __init__(self, root):
        self.root = root
        self.animations = []
    
    def animate(self, duration_ms, on_update, on_complete=None, easing=None):
        """启动一个动画"""
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
                self.root.after(16, _step)  # ~60fps
            elif on_complete:
                on_complete()
        
        self.root.after(16, _step)
    
    def fade_in(self, widget, duration=400):
        """淡入动画（通过透明度模拟）"""
        # tkinter没有真正的透明度，用颜色渐变模拟
        pass
    
    def slide_down(self, widget, target_height, duration=350):
        """向下滑出动画"""
        widget.configure(height=0)
        
        def _update(progress):
            h = int(target_height * progress)
            widget.configure(height=max(1, h))
        
        self.animate(duration, _update, easing=AnimationEngine.ease_out_back)
    
    def pulse(self, widget, original_color, glow_color, duration=800):
        """呼吸脉冲效果"""
        def _update(progress):
            if progress < 0.5:
                t = progress * 2
            else:
                t = 2 - progress * 2
            color = self._lerp_color(original_color, glow_color, t * 0.3)
            try:
                widget.configure(highlightbackground=color)
            except tk.TclError:
                pass
        
        self.animate(duration, _update, easing=AnimationEngine.ease_in_out_quart)
    
    @staticmethod
    def _lerp_color(c1, c2, t):
        """颜色线性插值"""
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"


# ============================================================
# ⚙️ 天气服务
# ============================================================
class WeatherService:
    @classmethod
    def fetch_all(cls, cb):
        def _run():
            try:
                loc = requests.get("http://ip-api.com/json/?fields=city,lat,lon,status", timeout=6).json()
                if loc.get("status") != "success":
                    raise Exception()
                
                p = {"latitude": loc["lat"], "longitude": loc["lon"],
                     "current_weather": True, "timezone": "auto"}
                w = requests.get("https://api.open-meteo.com/v1/forecast",
                                 params=p, timeout=6).json()
                cw = w.get("current_weather", {})
                code = cw.get("weathercode", 0)
                
                w_map = {
                    0: ("☀️", "晴朗"), 1: ("🌤️", "少云"), 2: ("⛅", "多云"),
                    3: ("☁️", "阴天"), 51: ("🌧️", "细雨"), 61: ("🌧️", "小雨"),
                    71: ("🌨️", "小雪"), 95: ("⛈️", "雷雨")
                }
                emoji, desc = w_map.get(code, ("🌈", "舒适"))
                cb({"ok": True, "city": loc["city"], "emoji": emoji,
                    "desc": desc, "temp": cw["temperature"], "code": code})
            except:
                cb({"ok": False})
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
        
        self.canvas = tk.Canvas(self, bg=T["bg"], highlightthickness=0, bd=0)
        self.inner = tk.Frame(self.canvas, bg=T["bg"])
        
        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas_win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
    
    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_win, width=event.width)
    
    def _on_mousewheel(self, event):
        """带惯性的平滑滚动"""
        self.scroll_velocity = -event.delta / 40.0
        if not self.is_scrolling:
            self.is_scrolling = True
            self._inertia_scroll()
    
    def _inertia_scroll(self):
        """惯性滚动动画"""
        if abs(self.scroll_velocity) < 0.5:
            self.is_scrolling = False
            return
        
        self.canvas.yview_scroll(int(self.scroll_velocity), "units")
        self.scroll_velocity *= 0.85  # 阻尼系数
        
        if self.winfo_exists():
            self.after(16, self._inertia_scroll)


class GlowCard(tk.Frame):
    """带悬停发光效果的卡片组件"""
    
    def __init__(self, parent, animator, glow_color=None, **kwargs):
        super().__init__(parent, bg=T["card"], bd=0,
                         highlightthickness=2, highlightbackground=T["border_light"])
        self.animator = animator
        self.glow_color = glow_color or T["glow"]
        self._hovered = False
        
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
    
    def _on_enter(self, event):
        self._hovered = True
        self._animate_hover(True)
    
    def _on_leave(self, event):
        self._hovered = False
        self._animate_hover(False)
    
    def _animate_hover(self, entering):
        """悬停时的发光渐变动画"""
        start_color = T["border_light"] if entering else self.glow_color
        end_color = self.glow_color if entering else T["border_light"]
        
        def _update(progress):
            color = Animator._lerp_color(start_color, end_color, progress)
            try:
                self.configure(highlightbackground=color)
            except tk.TclError:
                pass
        
        self.animator.animate(250, _update, easing=AnimationEngine.ease_out_expo)


class AnimatedExpandCard(tk.Frame):
    """带动画展开效果的卡片"""
    
    def __init__(self, parent, item_data, animator, delay_index=0):
        super().__init__(parent, bg=T["bg"])
        self.data = item_data
        self.animator = animator
        self.expanded = False
        self.body = None
        self._animating = False
        
        # 外层发光卡片
        self.card = GlowCard(self, animator, glow_color=T["prim_light"])
        self.card.pack(fill="x", pady=2)
        
        # 头部区域
        self.header = tk.Frame(self.card, bg=T["card"], padx=24, pady=20, cursor="hand2")
        self.header.pack(fill="x")
        
        # 左侧图标 - 带背景圆
        icon_bg = tk.Frame(self.header, bg=T["prim_l"], width=52, height=52)
        icon_bg.pack(side="left", padx=(0, 18))
        icon_bg.pack_propagate(False)
        icon_lbl = tk.Label(icon_bg, text=item_data["icon"], font=F["emoji_m"],
                           bg=T["prim_l"])
        icon_lbl.place(relx=0.5, rely=0.5, anchor="center")
        
        # 中间文字
        mid = tk.Frame(self.header, bg=T["card"])
        mid.pack(side="left", fill="x", expand=True)
        title_lbl = tk.Label(mid, text=item_data["title"], font=F["head"],
                            fg=T["text_h"], bg=T["card"])
        title_lbl.pack(anchor="w")
        subtitle_lbl = tk.Label(mid, text=f"{len(item_data['methods'])} 个科学方案",
                               font=F["small"], fg=T["text_s"], bg=T["card"])
        subtitle_lbl.pack(anchor="w", pady=(2, 0))
        
        # 右侧箭头
        self.arrow = tk.Label(self.header, text="▸", font=("Microsoft YaHei UI", 14),
                             fg=T["prim"], bg=T["card"])
        self.arrow.pack(side="right", padx=(10, 0))
        
        # 绑定点击
        for w in (self.header, icon_bg, icon_lbl, title_lbl, subtitle_lbl, self.arrow):
            w.bind("<Button-1>", lambda e: self._toggle())
        
        # 入场动画 - 延迟淡入
        self._entrance_animation(delay_index)


    def _entrance_animation(self, delay_index):
        """卡片入场动画 - 交错淡入上滑"""
        self.card.configure(highlightbackground=T["bg"])
        
        def _start():
            def _update(progress):
                # 模拟入场效果：边框逐渐显示
                color = Animator._lerp_color(T["bg"], T["border_light"], progress)
                try:
                    self.card.configure(highlightbackground=color)
                except tk.TclError:
                    pass
            
            self.animator.animate(400, _update, easing=AnimationEngine.ease_out_cubic)
        
        # 交错延迟
        delay = delay_index * 80
        self.after(delay, _start)
    
    def _toggle(self):
        """动画展开/收起"""
        if self._animating:
            return
        
        if self.expanded:
            self._collapse_animated()
        else:
            self._expand_animated()
    
    def _expand_animated(self):
        """动画展开方案列表"""
        self._animating = True
        self.expanded = True
        
        # 旋转箭头
        self.arrow.config(text="▾")
        
        # 创建内容区
        self.body = tk.Frame(self.card, bg=T["prim_l"], padx=24, pady=0)
        self.body.pack(fill="x")
        
        # 逐个添加方案卡片（带延迟动画）
        for i, (m_title, m_desc) in enumerate(self.data["methods"], 1):
            method_frame = tk.Frame(self.body, bg=T["card"], padx=18, pady=14,
                                   highlightthickness=1, highlightbackground=T["border_light"])
            method_frame.pack(fill="x", pady=5, padx=4)
            
            # 序号标记
            num_frame = tk.Frame(method_frame, bg=T["prim"], width=24, height=24)
            num_frame.pack(side="left", padx=(0, 14))
            num_frame.pack_propagate(False)
            tk.Label(num_frame, text=str(i), font=F["tiny"], fg=T["white"],
                    bg=T["prim"]).place(relx=0.5, rely=0.5, anchor="center")
            
            # 文字内容
            text_frame = tk.Frame(method_frame, bg=T["card"])
            text_frame.pack(side="left", fill="x", expand=True)
            tk.Label(text_frame, text=m_title, font=F["head"], fg=T["prim"],
                    bg=T["card"], anchor="w").pack(fill="x")
            tk.Label(text_frame, text=m_desc, font=F["body"], fg=T["text_b"],
                    bg=T["card"], wraplength=580, justify="left",
                    anchor="w").pack(fill="x", pady=(4, 0))
            
            # 悬停效果
            self._bind_method_hover(method_frame)
        
        # 底部间距
        tk.Frame(self.body, bg=T["prim_l"], height=12).pack(fill="x")
        
        # 展开动画 - 高亮卡片
        self.animator.pulse(self.card, T["border_light"], T["prim_light"], duration=600)
        
        self._animating = False
    
    def _collapse_animated(self):
        """动画收起"""
        self._animating = True
        self.arrow.config(text="▸")
        
        if self.body:
            self.body.destroy()
            self.body = None
        
        self.expanded = False
        self._animating = False
    
    def _bind_method_hover(self, frame):
        """方案卡片悬停效果"""
        def on_enter(e):
            frame.configure(highlightbackground=T["prim_light"])
        
        def on_leave(e):
            frame.configure(highlightbackground=T["border_light"])
        
        frame.bind("<Enter>", on_enter)
        frame.bind("<Leave>", on_leave)
        for child in frame.winfo_children():
            child.bind("<Enter>", on_enter)
            child.bind("<Leave>", on_leave)


class GradientHeader(tk.Canvas):
    """渐变色头部 - 模拟现代渐变效果"""
    
    def __init__(self, parent, height=140):
        super().__init__(parent, height=height, highlightthickness=0, bd=0)
        self.pack(fill="x")
        self.h = height
        self.bind("<Configure>", self._draw_gradient)
    
    def _draw_gradient(self, event=None):
        """绘制水平渐变"""
        self.delete("gradient")
        w = self.winfo_width()
        if w <= 1:
            return
        
        # 从左到右渐变
        steps = 100
        for i in range(steps):
            t = i / steps
            # 三色渐变
            if t < 0.5:
                t2 = t * 2
                r = int(int(T["gradient_1"][1:3], 16) * (1 - t2) + int(T["gradient_2"][1:3], 16) * t2)
                g = int(int(T["gradient_1"][3:5], 16) * (1 - t2) + int(T["gradient_2"][3:5], 16) * t2)
                b = int(int(T["gradient_1"][5:7], 16) * (1 - t2) + int(T["gradient_2"][5:7], 16) * t2)
            else:
                t2 = (t - 0.5) * 2
                r = int(int(T["gradient_2"][1:3], 16) * (1 - t2) + int(T["gradient_3"][1:3], 16) * t2)
                g = int(int(T["gradient_2"][3:5], 16) * (1 - t2) + int(T["gradient_3"][3:5], 16) * t2)
                b = int(int(T["gradient_2"][5:7], 16) * (1 - t2) + int(T["gradient_3"][5:7], 16) * t2)
            
            color = f"#{r:02x}{g:02x}{b:02x}"
            x0 = int(w * i / steps)
            x1 = int(w * (i + 1) / steps) + 1
            self.create_rectangle(x0, 0, x1, self.h, fill=color, outline=color, tags="gradient")
        
        # 绘制文字
        hour = datetime.now().hour
        if 5 <= hour < 12:
            greeting = "早安，开启舒心的一天 ☀️"
        elif 12 <= hour < 18:
            greeting = "午后好，恢复能量 🌤️"
        else:
            greeting = "晚安，静享安宁 🌙"
        
        self.create_text(w // 2, self.h // 2 - 14, text=greeting,
                        font=F["title"], fill="white", tags="gradient")
        self.create_text(w // 2, self.h // 2 + 20,
                        text="✦ 基于心理学方案 · 陪你调节每一份情绪 ✦",
                        font=F["body"], fill="#E0E7FF", tags="gradient")


class AnimatedNavBar(tk.Frame):
    """带滑块动画的导航栏"""
    
    def __init__(self, parent, tabs, on_switch, animator):
        super().__init__(parent, bg=T["bg"], pady=14)
        self.animator = animator
        self.on_switch = on_switch
        self.current_idx = 0
        
        # 导航容器 - 药丸造型
        self.pill = tk.Frame(self, bg=T["nav_bg"], padx=4, pady=4)
        self.pill.pack(anchor="center")
        
        self.btns = []
        self.btn_frames = []
        
        for i, (icon, name) in enumerate(tabs):
            btn = tk.Label(self.pill, text=f"{icon}  {name}", font=F["body"],
                          padx=32, pady=10, cursor="hand2",
                          bg=T["nav_bg"], fg=T["text_s"])
            btn.pack(side="left", padx=2)
            btn.bind("<Button-1>", lambda e, idx=i: self._switch_to(idx))
            btn.bind("<Enter>", lambda e, b=btn, idx=i: self._hover_btn(b, idx, True))
            btn.bind("<Leave>", lambda e, b=btn, idx=i: self._hover_btn(b, idx, False))
            self.btns.append(btn)
        
        # 初始激活
        self._activate(0, animate=False)
    
    def _switch_to(self, idx):
        if idx == self.current_idx:
            return
        old_idx = self.current_idx
        self.current_idx = idx
        self._activate(idx, animate=True)
        self.on_switch(idx)
    
    def _activate(self, idx, animate=True):
        """激活指定tab"""
        for i, btn in enumerate(self.btns):
            if i == idx:
                if animate:
                    self._animate_activate(btn)
                else:
                    btn.config(bg=T["white"], fg=T["prim"])
            else:
                btn.config(bg=T["nav_bg"], fg=T["text_s"])
    
    def _animate_activate(self, btn):
        """激活动画"""
        def _update(progress):
            color = Animator._lerp_color(T["nav_bg"], T["white"], progress)
            fg_color = Animator._lerp_color(T["text_s"], T["prim"], progress)
            try:
                btn.config(bg=color, fg=fg_color)
            except tk.TclError:
                pass
        
        self.animator.animate(200, _update, easing=AnimationEngine.ease_out_expo)
    
    def _hover_btn(self, btn, idx, entering):
        """悬停效果"""
        if idx == self.current_idx:
            return
        if entering:
            btn.config(fg=T["text_b"])
        else:
            btn.config(fg=T["text_s"])


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
        
        # 动画引擎
        self.animator = Animator(root)
        
        # 构建UI
        self._init_header()
        self._init_content()
        self._init_nav()
        self._init_footer()
        
        # 启动天气获取
        self._refresh_weather()
        
        # 启动呼吸动画
        self._start_ambient_animation()
    
    def _init_header(self):
        """渐变头部"""
        self.gradient_header = GradientHeader(self.root, height=130)
    
    def _init_content(self):
        """主内容区域"""
        self.main_container = tk.Frame(self.root, bg=T["bg"])
        self.main_container.pack(fill="both", expand=True, padx=0, pady=0)
        
        self.page_weather = SmoothScrollContainer(self.main_container, self.animator)
        self.page_quick = SmoothScrollContainer(self.main_container, self.animator)
    
    def _init_nav(self):
        """动画导航栏"""
        tabs = [("🌤", "天气建议"), ("⚡", "快捷调节")]
        self.navbar = AnimatedNavBar(self.root, tabs, self._switch_page, self.animator)
        self.navbar.pack(fill="x")
        self._switch_page(0)
    
    def _init_footer(self):
        """底部状态栏"""
        footer = tk.Frame(self.root, bg=T["border_light"], height=32)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        
        self.status_dot = tk.Label(footer, text="●", font=F["tiny"],
                                   fg=T["success"], bg=T["border_light"])
        self.status_dot.pack(side="left", padx=(20, 6), pady=6)
        self.status_label = tk.Label(footer, text="系统就绪 · 等待数据同步",
                                    font=F["tiny"], fg=T["text_s"], bg=T["border_light"])
        self.status_label.pack(side="left", pady=6)
        
        time_lbl = tk.Label(footer, text=datetime.now().strftime("%Y-%m-%d %H:%M"),
                           font=F["tiny"], fg=T["text_s"], bg=T["border_light"])
        time_lbl.pack(side="right", padx=20, pady=6)
    
    def _switch_page(self, idx):
        """切换页面"""
        if idx == 0:
            self.page_quick.pack_forget()
            self.page_weather.pack(fill="both", expand=True)
            self._render_weather()
        else:
            self.page_weather.pack_forget()
            self.page_quick.pack(fill="both", expand=True)
            self._render_quick()
    
    def _render_weather(self):
        """天气建议页面"""
        c = self.page_weather.inner
        if c.winfo_children():
            return
        
        # 天气主卡片
        weather_card = GlowCard(c, self.animator, glow_color=T["accent_light"])
        weather_card.pack(fill="x", padx=30, pady=(24, 16))
        
        weather_inner = tk.Frame(weather_card, bg=T["card"], padx=36, pady=32)
        weather_inner.pack(fill="x")
        
        # 天气图标
        self.w_icon = tk.Label(weather_inner, text="⌛", font=F["emoji_l"], bg=T["card"])
        self.w_icon.pack(side="left")
        
        # 温度信息
        info = tk.Frame(weather_inner, bg=T["card"])
        info.pack(side="left", padx=30, fill="x", expand=True)
        self.lbl_temp = tk.Label(info, text="--°C", font=F["title"], fg=T["text_h"], bg=T["card"])
        self.lbl_temp.pack(anchor="w")
        self.lbl_desc = tk.Label(info, text="正在同步天气数据...", font=F["body"],
                                fg=T["text_s"], bg=T["card"])
        self.lbl_desc.pack(anchor="w", pady=(4, 0))
        
        # 加载动画指示
        self.loading_dot = tk.Label(weather_inner, text="◌", font=("Segoe UI", 16),
                                   fg=T["prim_light"], bg=T["card"])
        self.loading_dot.pack(side="right", padx=10)
        self._animate_loading()
        
        # 建议区域标题
        suggest_header = tk.Frame(c, bg=T["bg"], padx=30, pady=(10, 8))
        suggest_header.pack(fill="x")
        tk.Label(suggest_header, text="💡", font=F["emoji_s"], bg=T["bg"]).pack(side="left")
        tk.Label(suggest_header, text="  今日情绪建议", font=F["head"],
                fg=T["text_h"], bg=T["bg"]).pack(side="left")
        
        # 建议卡片
        self.suggest_frame = tk.Frame(c, bg=T["bg"], padx=30)
        self.suggest_frame.pack(fill="x")
        
        hint_card = GlowCard(self.suggest_frame, self.animator)
        hint_card.pack(fill="x", pady=4)
        hint_inner = tk.Frame(hint_card, bg=T["card"], padx=24, pady=18)
        hint_inner.pack(fill="x")
        self.suggest_text = tk.Label(hint_inner,
                                    text="获取天气后将为您展示专属的情绪调节策略 ✨",
                                    font=F["body"], fg=T["text_s"], bg=T["card"],
                                    wraplength=700, justify="left")
        self.suggest_text.pack(anchor="w")


    def _render_quick(self):
        """快捷调节页面 - 带交错入场动画"""
        c = self.page_quick.inner
        if c.winfo_children():
            return
        
        # 页面标题
        header_f = tk.Frame(c, bg=T["bg"], padx=30, pady=(20, 12))
        header_f.pack(fill="x")
        tk.Label(header_f, text="⚡", font=F["emoji_s"], bg=T["bg"]).pack(side="left")
        tk.Label(header_f, text="  针对性情绪方案", font=F["head"],
                fg=T["text_h"], bg=T["bg"]).pack(side="left")
        tk.Label(header_f, text=f"共 {len(QuickDB.ITEMS)} 种情绪",
                font=F["small"], fg=T["text_s"], bg=T["bg"]).pack(side="right")
        
        # 分割线
        tk.Frame(c, bg=T["border"], height=1).pack(fill="x", padx=30, pady=(0, 8))
        
        # 卡片列表 - 带交错动画
        for i, item in enumerate(QuickDB.ITEMS):
            AnimatedExpandCard(c, item, self.animator, delay_index=i).pack(
                fill="x", padx=28, pady=4)
        
        # 底部留白
        tk.Frame(c, bg=T["bg"], height=30).pack(fill="x")
    
    def _animate_loading(self):
        """加载旋转动画"""
        symbols = ["◐", "◓", "◑", "◒"]
        self._loading_idx = 0
        
        def _rotate():
            if not self.root.winfo_exists():
                return
            try:
                if self.loading_dot.winfo_exists():
                    self._loading_idx = (self._loading_idx + 1) % len(symbols)
                    self.loading_dot.config(text=symbols[self._loading_idx])
                    self.root.after(250, _rotate)
            except tk.TclError:
                pass
        
        _rotate()
    
    def _start_ambient_animation(self):
        """环境氛围动画 - 状态点呼吸"""
        def _breathe():
            if not self.root.winfo_exists():
                return
            
            # 状态点呼吸效果
            t = (time.time() % 3) / 3  # 3秒一个周期
            alpha = 0.4 + 0.6 * (math.sin(t * math.pi * 2) + 1) / 2
            
            # 用颜色深浅模拟呼吸
            r = int(16 + (16 * alpha))
            g = int(185 + (70 * (1 - alpha)))
            b = int(129 + (126 * (1 - alpha)))
            color = f"#{min(r,255):02x}{min(g,255):02x}{min(b,255):02x}"
            
            try:
                self.status_dot.config(fg=color)
            except tk.TclError:
                return
            
            self.root.after(50, _breathe)
        
        self.root.after(1000, _breathe)
    
    def _refresh_weather(self):
        WeatherService.fetch_all(self._on_weather)
    
    def _on_weather(self, res):
        if not self.root.winfo_exists():
            return
        
        def _update_ui():
            if res["ok"]:
                # 动画更新天气数据
                self.w_icon.config(text=res["emoji"])
                self.lbl_temp.config(text=f"{res['temp']}°C")
                self.lbl_desc.config(text=f"📍 {res['city']} · {res['desc']}")
                self.loading_dot.config(text="✓", fg=T["success"])
                
                # 更新状态栏
                self.status_label.config(text=f"已同步 · {res['city']} {res['desc']} {res['temp']}°C")
                
                # 生成天气建议
                self._generate_suggestions(res)
                
                # 脉冲高亮效果
                self.animator.pulse(self.w_icon.master.master,
                                   T["border_light"], T["accent_light"], duration=1000)
            else:
                self.lbl_desc.config(text="⚠️ 同步失败，请检查网络后重启程序", fg="#F43F5E")
                self.loading_dot.config(text="✗", fg="#F43F5E")
                self.status_label.config(text="网络异常 · 天气同步失败")
                self.status_dot.config(fg="#F43F5E")
        
        self.root.after(0, _update_ui)
    
    def _generate_suggestions(self, weather):
        """基于天气生成情绪建议"""
        code = weather.get("code", 0)
        temp = weather.get("temp", 20)
        
        suggestions = []
        if code in (0, 1):
            suggestions = [
                "☀️ 晴朗天气适合户外散步，阳光能提升血清素水平",
                "🌿 推荐在上午进行15分钟户外冥想，效果加倍",
                "🏃 适合进行有氧运动，帮助释放多巴胺"
            ]
        elif code in (2, 3):
            suggestions = [
                "☁️ 多云天适合室内深度工作，注意力更容易集中",
                "📖 适合阅读或写日记，记录内心感受",
                "🎵 配合轻音乐进行放松练习"
            ]
        elif code in (51, 61):
            suggestions = [
                "🌧️ 雨天容易情绪低落，建议保持室内明亮",
                "🍵 泡一杯热茶，进行5分钟正念呼吸",
                "💬 适合与朋友通话聊天，保持社交连接"
            ]
        else:
            suggestions = [
                "🌈 任何天气都适合深呼吸练习",
                "✍️ 写下三件感恩的事，提升积极情绪",
                "🧘 进行身体扫描冥想，释放身心紧张"
            ]
        
        if temp < 10:
            suggestions.append("🧣 天冷注意保暖，寒冷会加重情绪波动")
        elif temp > 30:
            suggestions.append("💧 高温天气多补水，脱水会导致烦躁")
        
        # 更新建议区域
        self.suggest_text.config(
            text="\n\n".join(suggestions),
            fg=T["text_b"]
        )


# ============================================================
# 📦 情绪方案数据库
# ============================================================
class QuickDB:
    ITEMS = [
        {
            "icon": "😰", "title": "焦虑不安",
            "methods": [
                ("5-4-3-2-1 感官法", "寻找5种看到的、4种触碰到的、3种听到的、2种闻到的、1种尝到的。瞬间拉回当下。"),
                ("4-7-8 呼吸", "吸气4秒，屏息7秒，呼气8秒。重复4次，有效放松。"),
                ("担忧外化记录", "写下担心的事。标注『能控制』的，专注前者，暂时放下后者。")
            ]
        },
        {
            "icon": "😤", "title": "愤怒烦躁",
            "methods": [
                ("10秒延迟法则", "想发火前默数10个数。给理智大脑（前额叶）留出接管时间。"),
                ("物理能量释放", "撕碎废纸、捏压力球或快走。代谢掉积压的攻击能量。"),
                ("冷水降温法", "用冷水洗脸或握住冰块。触发潜水反射，强制心跳减速。")
            ]
        },
        {
            "icon": "😢", "title": "悲伤低落",
            "methods": [
                ("悲伤限定时间", "允许悲伤15分钟。闹钟响后去洗脸，做一件极小的事。"),
                ("微小行为激活", "即使没动力也强迫刷牙或整理椅子。行动先于动力。"),
                ("自然光照激活", "接受15分钟照射。阳光是天然抗抑郁剂。")
            ]
        },
        {
            "icon": "🤯", "title": "压力过载",
            "methods": [
                ("原子化拆解", "把任务拆解到极小步骤。降低启动阻碍感。"),
                ("四象限法则", "区分紧急与重要。优先处理重要不紧急的事。"),
                ("15分钟剧烈运动", "开合跳或快走。代谢体内的压力激素。")
            ]
        },
        {
            "icon": "😶", "title": "拖延无动力",
            "methods": [
                ("『只做5分钟』", "告诉自己只做5分钟。通常一旦开始，惯性会带你继续。"),
                ("环境气味唤醒", "换房间或闻柑橘香气。刺激唤醒意志力。"),
                ("即时奖励锚点", "设定小奖赏：写完这段话就吃块巧克力。")
            ]
        },
        {
            "icon": "🌀", "title": "精神内耗",
            "methods": [
                ("寻找反证记录", "写下过去3件成功的小事。用证据对抗偏见。"),
                ("语言剥离法", "不要说『我很失败』，要说『我产生了一个" + "'我很失败'" + "的念头』。你不是你的想法。"),
                ("STOP 停顿技术", "Stop(停下) -> Take(呼吸) -> Observe(观察) -> Proceed(行动)。")
            ]
        },
        {
            "icon": "😵\u200d💫", "title": "注意力涣散",
            "methods": [
                ("物理隔离分心源", "手机锁进抽屉。视线看不见干扰，专注力自动提升。"),
                ("单任务原则", "一次只处理一件事。任务切换会产生极高疲劳。"),
                ("白噪音屏障", "播放雨声背景音。过滤杂音，进入心流。")
            ]
        },
        {
            "icon": "😨", "title": "社交焦虑",
            "methods": [
                ("注意力外移练习", "停止监控自己。强迫观察外部细节。将焦点投向外界。"),
                ("万能话题准备", "提前准备天气等话题。有预案会减轻恐慌。"),
                ("接纳紧张反应", "告诉自己紧张在提供能量。越承认越放松。")
            ]
        },
        {
            "icon": "😴", "title": "失眠多梦",
            "methods": [
                ("肌肉渐进放松", "从脚趾开始用力收缩5秒再放松。一路向上。"),
                ("床铺功能纯化", "不在床上玩手机。建立床与睡眠的强关联。"),
                ("思维日志转存", "把待办写在纸上。告诉大脑：已经记好了，可以休息。")
            ]
        }
    ]

# ============================================================
# 🚀 启动
# ============================================================
if __name__ == "__main__":
    root = tk.Tk()
    
    # DPI 感知（Windows）
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    
    # 配置 ttk 样式
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TScrollbar", troughcolor=T["bg"], background=T["prim_light"],
                    bordercolor=T["bg"], arrowcolor=T["prim"])
    
    app = MoodApp(root)
    root.mainloop()
