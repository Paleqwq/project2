# -*- coding: utf-8 -*-
"""
情绪调节小工具 — 稳定修复版 (Fluid UI v3.6)
1. 彻底修复语法错误：修正引号嵌套冲突（line 311）
2. 修复初始化顺序：解决 AttributeError
3. 修复自适应滚动：解决封包后内容残缺问题
4. 增强打包兼容性：优化 DPI 缩放及网络请求超时
"""

import tkinter as tk
from tkinter import ttk
import threading
import requests
import os
from datetime import datetime

# ============================================================
# 🎨 视觉主题
# ============================================================
T = {
    "bg":         "#F8FAFC",
    "card":       "#FFFFFF",
    "nav_bg":     "#E2E8F0",
    "prim":       "#6366F1",
    "prim_l":     "#EEF2FF",
    "text_h":     "#1E293B",
    "text_b":     "#475569",
    "text_s":     "#94A3B8",
    "border":     "#E2E8F0",
    "white":      "#FFFFFF",
}

F = {
    "title": ("Microsoft YaHei UI", 20, "bold"),
    "head":  ("Microsoft YaHei UI", 13, "bold"),
    "body":  ("Microsoft YaHei UI", 11),
    "small": ("Microsoft YaHei UI", 10),
    "emoji_l": ("Segoe UI Emoji", 40),
    "emoji_m": ("Segoe UI Emoji", 22),
}

# ============================================================
# ⚙️ 逻辑服务
# ============================================================
class WeatherService:
    @classmethod
    def fetch_all(cls, cb):
        def _run():
            try:
                loc = requests.get("http://ip-api.com/json/?fields=city,lat,lon,status", timeout=6).json()
                if loc.get("status") != "success": raise Exception()
                
                p = {"latitude": loc["lat"], "longitude": loc["lon"], "current_weather": True, "timezone": "auto"}
                w = requests.get("https://api.open-meteo.com/v1/forecast", params=p, timeout=6).json()
                cw = w.get("current_weather", {})
                code = cw.get("weathercode", 0)
                
                w_map = {
                    0: ("☀️", "晴朗"), 1: ("🌤️", "少云"), 2: ("⛅", "多云"), 3: ("☁️", "阴天"), 
                    51: ("🌧️", "细雨"), 61: ("🌧️", "小雨"), 71: ("🌨️", "小雪"), 95: ("⛈️", "雷雨")
                }
                emoji, desc = w_map.get(code, ("🌈", "舒适"))
                cb({"ok": True, "city": loc["city"], "emoji": emoji, "desc": desc, "temp": cw["temperature"], "code": code})
            except:
                cb({"ok": False})
        threading.Thread(target=_run, daemon=True).start()

# ============================================================
# 🧱 核心 UI 组件
# ============================================================
class ScrollContainer(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=T["bg"])
        self.canvas = tk.Canvas(self, bg=T["bg"], highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=T["bg"])
        
        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas_win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_win, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

class QuickActionCard(tk.Frame):
    def __init__(self, parent, item_data):
        super().__init__(parent, bg=T["card"], bd=0, highlightthickness=1, highlightbackground=T["border"])
        self.data = item_data
        self.expanded = False
        
        self.header = tk.Frame(self, bg=T["card"], padx=20, pady=18, cursor="hand2")
        self.header.pack(fill="x")
        
        icon_lbl = tk.Label(self.header, text=item_data["icon"], font=F["emoji_m"], bg=T["card"])
        icon_lbl.pack(side="left", padx=(0, 15))
        
        title_lbl = tk.Label(self.header, text=item_data["title"], font=F["head"], fg=T["text_h"], bg=T["card"])
        title_lbl.pack(side="left")
        
        self.lbl_arrow = tk.Label(self.header, text="展开方案 ❯", font=F["small"], fg=T["prim"], bg=T["card"])
        self.lbl_arrow.pack(side="right")
        
        for widget in (self.header, icon_lbl, title_lbl, self.lbl_arrow):
            widget.bind("<Button-1>", lambda e: self._toggle())
        
        self.body = None

    def _toggle(self):
        if self.expanded:
            if self.body: self.body.destroy()
            self.lbl_arrow.config(text="展开方案 ❯")
        else:
            self.body = tk.Frame(self, bg=T["prim_l"], padx=20, pady=10)
            self.body.pack(fill="x")
            for i, (m_title, m_desc) in enumerate(self.data["methods"], 1):
                f = tk.Frame(self.body, bg=T["card"], padx=15, pady=12, highlightthickness=1, highlightbackground=T["border"])
                f.pack(fill="x", pady=4)
                tk.Label(f, text=f"{i}. {m_title}", font=F["head"], fg=T["prim"], bg=T["card"], anchor="w").pack(fill="x")
                tk.Label(f, text=m_desc, font=F["body"], fg=T["text_b"], bg=T["card"], wraplength=650, justify="left", anchor="w").pack(fill="x", pady=(2,0))
            self.lbl_arrow.config(text="收起方案 ︾")
        self.expanded = not self.expanded

# ============================================================
# 🏠 主程序
# ============================================================
class MoodApp:
    def __init__(self, root):
        self.root = root
        self.root.title("情绪调节小工具 v3.6")
        self.root.geometry("920x720")
        self.root.minsize(850, 650)
        self.root.configure(bg=T["bg"])
        
        self._init_header()
        self._init_content()
        self._init_nav()
        
        self._refresh_weather()

    def _init_header(self):
        self.header_frame = tk.Frame(self.root, bg=T["prim"], height=120)
        self.header_frame.pack(fill="x")
        self.header_frame.pack_propagate(False)
        
        hour = datetime.now().hour
        greeting = "早安，开启舒心的一天" if 5 <= hour < 12 else "午后好，恢复能量" if 12 <= hour < 18 else "晚安，静享安宁"
        
        content = tk.Frame(self.header_frame, bg=T["prim"])
        content.pack(expand=True, padx=50)
        
        tk.Label(content, text="🌈", font=F["emoji_l"], bg=T["prim"]).pack(side="left", padx=15)
        txt = tk.Frame(content, bg=T["prim"])
        txt.pack(side="left")
        tk.Label(txt, text=greeting, font=F["title"], fg="white", bg=T["prim"]).pack(anchor="w")
        tk.Label(txt, text="基于心理学方案 · 陪你调节每一份情绪", font=F["body"], fg="#E0E7FF", bg=T["prim"]).pack(anchor="w")

    def _init_content(self):
        self.main_container = tk.Frame(self.root, bg=T["bg"])
        self.main_container.pack(fill="both", expand=True, padx=25, pady=10)
        
        self.page_weather = ScrollContainer(self.main_container)
        self.page_quick = ScrollContainer(self.main_container)

    def _init_nav(self):
        nav_wrap = tk.Frame(self.root, bg=T["bg"], pady=10)
        nav_wrap.pack(fill="x")
        
        pill = tk.Frame(nav_wrap, bg=T["nav_bg"], padx=3, pady=3)
        pill.pack(anchor="center")
        
        self.btns = []
        for i, name in enumerate(["🌤 天气建议", "⚡ 快捷调节"]):
            b = tk.Label(pill, text=name, font=F["body"], padx=30, pady=8, cursor="hand2", bg=T["nav_bg"], fg=T["text_s"])
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, idx=i: self._switch(idx))
            self.btns.append(b)
        
        self._switch(0)

    def _switch(self, idx):
        for i, b in enumerate(self.btns):
            if i == idx: b.config(bg=T["white"], fg=T["prim"])
            else: b.config(bg=T["nav_bg"], fg=T["text_s"])
        
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
        if c.winfo_children(): return
        
        card = tk.Frame(c, bg=T["card"], padx=40, pady=30, highlightthickness=1, highlightbackground=T["border"])
        card.pack(fill="x", padx=20, pady=20)
        
        self.w_icon = tk.Label(card, text="⌛", font=F["emoji_l"], bg=T["card"])
        self.w_icon.pack(side="left")
        
        info = tk.Frame(card, bg=T["card"])
        info.pack(side="left", padx=30)
        self.lbl_temp = tk.Label(info, text="--°C", font=F["title"], fg=T["text_h"], bg=T["card"])
        self.lbl_temp.pack(anchor="w")
        self.lbl_desc = tk.Label(info, text="正在同步天气数据...", font=F["body"], fg=T["text_s"], bg=T["card"])
        self.lbl_desc.pack(anchor="w")
        
        tk.Label(c, text="💡 今日建议", font=F["head"], bg=T["bg"], fg=T["text_h"]).pack(anchor="w", padx=25, pady=10)
        
        sug_f = tk.Frame(c, bg=T["bg"])
        sug_f.pack(fill="x", padx=20)
        tk.Label(sug_f, text="获取天气后将为您展示专属的情绪调节策略。", font=F["body"], fg=T["text_s"], bg=T["bg"]).pack(anchor="w")

    def _render_quick(self):
        c = self.page_quick.inner
        if c.winfo_children(): return
        
        tk.Label(c, text="针对性情绪方案", font=F["head"], bg=T["bg"], fg=T["text_h"]).pack(anchor="w", padx=25, pady=15)
        for item in QuickDB.ITEMS:
            QuickActionCard(c, item).pack(fill="x", padx=25, pady=6)

    def _refresh_weather(self):
        WeatherService.fetch_all(self._on_weather)

    def _on_weather(self, res):
        if not self.root.winfo_exists(): return
        if res["ok"]:
            self.lbl_temp.config(text=f"{res['temp']}°C")
            self.lbl_desc.config(text=f"当前位于 {res['city']} · {res['desc']}")
            self.w_icon.config(text=res["emoji"])
        else:
            self.lbl_desc.config(text="同步失败，请检查网络后重启程序", fg="#F43F5E")

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
            "icon": "😵‍", "title": "注意力涣散", 
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
if __name__ == "__main__":
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    
    app = MoodApp(root)
    root.mainloop()