# -*- coding: utf-8 -*-
"""
情绪调节小工具 — 稳定修复版 (Fluid UI v3.7)
1. 修复天气读取：多源 IP 定位 + 证书兼容 + 超时与 UA 处理
2. 修复封包后天气建议不显示：补齐 WeatherTipsDB 预设方案与渲染管线
3. 渲染层提供独立挂载点 self.suggest_container，支持动态刷新
4. 网络失败时提供离线建议，避免空白页
"""

import os
import sys
import ssl
import threading
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
# 视觉主题
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
    "warn":       "#F43F5E",
}

F = {
    "title":   ("Microsoft YaHei UI", 20, "bold"),
    "head":    ("Microsoft YaHei UI", 13, "bold"),
    "body":    ("Microsoft YaHei UI", 11),
    "small":   ("Microsoft YaHei UI", 10),
    "emoji_l": ("Segoe UI Emoji", 40),
    "emoji_m": ("Segoe UI Emoji", 22),
}

# ============================================================
# 天气建议数据库（按天气大类预设）
# ============================================================
class WeatherTipsDB:
    """根据 Open-Meteo 的 weathercode 与温度返回建议方案。"""

    # WMO 天气分类
    _CATEGORY_MAP = {
        "sunny":  {0, 1},
        "cloudy": {2, 3},
        "fog":    {45, 48},
        "rain":   {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82},
        "snow":   {71, 73, 75, 77, 85, 86},
        "storm":  {95, 96, 99},
    }

    _TIPS = {
        "sunny": {
            "headline": "阳光充沛 · 把能量装进口袋",
            "items": [
                ("多巴胺漫步", "出门走 15 分钟，阳光直射皮肤可促进血清素与维生素 D 合成，是天然的情绪稳定剂。"),
                ("户外深呼吸", "找一处绿植区做 6 次腹式呼吸（吸 4 秒、呼 6 秒），降低皮质醇水平。"),
                ("补水提醒", "晴天容易脱水导致疲劳与烦躁，每隔 1 小时补充约 200ml 水。"),
            ],
        },
        "cloudy": {
            "headline": "多云时光 · 适合温和推进",
            "items": [
                ("番茄钟启动", "用 25 分钟专注 + 5 分钟休息推进一件事；柔和光线最适合深度工作。"),
                ("室内伸展", "肩颈环绕、靠墙站立 2 分钟，缓解久坐产生的低能量感。"),
                ("一杯温饮", "温水或淡茶，让身体在不刺眼的光线里慢慢『启动』。"),
            ],
        },
        "fog": {
            "headline": "雾气朦胧 · 放慢节奏更踏实",
            "items": [
                ("减速通勤", "雾天能见度低，预留多 10 分钟出行时间，降低焦躁感。"),
                ("书写式整理", "把脑中乱糟糟的事写到纸上，外化思绪，恢复清晰感。"),
                ("亮色光源", "打开暖白台灯或柑橘香薰，对抗雾天带来的低落。"),
            ],
        },
        "rain": {
            "headline": "雨天模式 · 把自己温柔包裹",
            "items": [
                ("白噪音陪伴", "雨声本身就是天然 ASMR，可放低音量作为背景，专注力会提升。"),
                ("一杯热饮仪式", "热可可、姜茶或牛奶。温热感会激活副交感神经，缓解紧绷。"),
                ("室内慢运动", "瑜伽或拉伸 10 分钟，代谢阴雨带来的钝痛与困倦。"),
            ],
        },
        "snow": {
            "headline": "雪日时刻 · 守住温度与节律",
            "items": [
                ("分层保暖", "重点护住颈部、脚踝。体温稳定，情绪更不易波动。"),
                ("热食满足感", "一碗热汤或燕麦粥，胃部温暖能直接降低焦虑感。"),
                ("窗边五分钟", "看雪 5 分钟，给视觉一个『慢镜头』，是最便宜的冥想。"),
            ],
        },
        "storm": {
            "headline": "雷雨天气 · 优先安全与安抚",
            "items": [
                ("远离窗户", "打雷时关好窗户、拔掉非必要电源，安全感是情绪稳定的前提。"),
                ("4-7-8 呼吸", "吸 4 秒、屏 7 秒、呼 8 秒，对抗雷声引发的惊吓反射。"),
                ("低刺激陪伴", "听轻音乐或有声书，避免强光、惊悚剧集叠加感官负担。"),
            ],
        },
        "default": {
            "headline": "舒适天气 · 顺势调节",
            "items": [
                ("十分钟轻活动", "散步、整理桌面或浇水，启动身体即启动情绪。"),
                ("一次主动联系", "给一位许久不见的朋友发条消息，建立微小连接。"),
                ("写下三件小确幸", "睡前回忆三件小好事，训练大脑捕捉积极信号。"),
            ],
        },
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
        if t >= 30:
            return "hot"
        if t >= 18:
            return "warm"
        if t >= 8:
            return "cool"
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
        return {
            "headline": "离线建议 · 网络未连接也能照顾自己",
            "items": [
                ("暂时不依赖网络", "把手机调成飞行模式 10 分钟，让神经系统从信息洪流中抽离。"),
                ("身体先动起来", "做 20 个深蹲或原地踏步 2 分钟，立即提升血氧与情绪基线。"),
                ("写一句感谢", "在纸上写下今天值得感谢的一件小事，训练积极注意力。"),
            ],
        }


# ============================================================
# 逻辑服务
# ============================================================
class WeatherService:
    """多源 IP 定位 + Open-Meteo 天气，封包后也稳。"""

    # 天气编码映射
    W_MAP = {
        0:  ("☀️", "晴朗"),
        1:  ("🌤️", "少云"),
        2:  ("⛅", "多云"),
        3:  ("☁️", "阴天"),
        45: ("🌫️", "有雾"),
        48: ("🌫️", "雾凇"),
        51: ("🌦️", "细雨"),
        53: ("🌦️", "小雨"),
        55: ("🌧️", "中雨"),
        61: ("🌧️", "小雨"),
        63: ("🌧️", "中雨"),
        65: ("🌧️", "大雨"),
        71: ("🌨️", "小雪"),
        73: ("🌨️", "中雪"),
        75: ("❄️", "大雪"),
        80: ("🌦️", "阵雨"),
        81: ("🌧️", "强阵雨"),
        82: ("⛈️", "暴雨"),
        95: ("⛈️", "雷雨"),
        96: ("⛈️", "雷雨夹雹"),
        99: ("⛈️", "强雷暴"),
    }

    HEADERS = {
        "User-Agent": "MoodTool/3.7 (+https://example.local)"
    }

    @classmethod
    def _locate(cls):
        """依次尝试多个 IP 定位服务，任意一个成功即返回。"""
        errors = []
        # 1) ip-api.com (HTTP, 国内可用率高)
        try:
            r = requests.get(
                "http://ip-api.com/json/?fields=city,lat,lon,status,message",
                timeout=6, headers=cls.HEADERS,
            )
            j = r.json()
            if j.get("status") == "success":
                return {"city": j.get("city") or "未知地区",
                        "lat": j["lat"], "lon": j["lon"]}
            errors.append(f"ip-api: {j.get('message')}")
        except Exception as e:
            errors.append(f"ip-api: {e}")

        # 2) ipapi.co (HTTPS 备用)
        try:
            r = requests.get(
                "https://ipapi.co/json/",
                timeout=6, headers=cls.HEADERS,
            )
            j = r.json()
            if j.get("latitude") is not None:
                return {"city": j.get("city") or j.get("region") or "未知地区",
                        "lat": j["latitude"], "lon": j["longitude"]}
            errors.append(f"ipapi.co: {j.get('reason')}")
        except Exception as e:
            errors.append(f"ipapi.co: {e}")

        # 3) ipwho.is (HTTPS 备用)
        try:
            r = requests.get(
                "https://ipwho.is/",
                timeout=6, headers=cls.HEADERS,
            )
            j = r.json()
            if j.get("success"):
                return {"city": j.get("city") or "未知地区",
                        "lat": j["latitude"], "lon": j["longitude"]}
            errors.append(f"ipwho: {j.get('message')}")
        except Exception as e:
            errors.append(f"ipwho: {e}")

        raise RuntimeError("定位失败 -> " + " | ".join(errors))

    @classmethod
    def _weather(cls, lat, lon):
        params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": True,
            "timezone": "auto",
        }
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params, timeout=8, headers=cls.HEADERS,
        )
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
                cb({
                    "ok":   True,
                    "city": loc["city"],
                    "emoji": emoji,
                    "desc": desc,
                    "temp": temp,
                    "code": code,
                })
            except Exception as e:
                cb({"ok": False, "err": str(e)})

        threading.Thread(target=_run, daemon=True).start()


# ============================================================
# 核心 UI 组件
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
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class QuickActionCard(tk.Frame):
    def __init__(self, parent, item_data):
        super().__init__(parent, bg=T["card"], bd=0,
                         highlightthickness=1, highlightbackground=T["border"])
        self.data = item_data
        self.expanded = False

        self.header = tk.Frame(self, bg=T["card"], padx=20, pady=18, cursor="hand2")
        self.header.pack(fill="x")

        icon_lbl = tk.Label(self.header, text=item_data["icon"],
                            font=F["emoji_m"], bg=T["card"])
        icon_lbl.pack(side="left", padx=(0, 15))

        title_lbl = tk.Label(self.header, text=item_data["title"],
                             font=F["head"], fg=T["text_h"], bg=T["card"])
        title_lbl.pack(side="left")

        self.lbl_arrow = tk.Label(self.header, text="展开方案 ❯",
                                  font=F["small"], fg=T["prim"], bg=T["card"])
        self.lbl_arrow.pack(side="right")

        for widget in (self.header, icon_lbl, title_lbl, self.lbl_arrow):
            widget.bind("<Button-1>", lambda e: self._toggle())

        self.body = None

    def _toggle(self):
        if self.expanded:
            if self.body:
                self.body.destroy()
            self.lbl_arrow.config(text="展开方案 ❯")
        else:
            self.body = tk.Frame(self, bg=T["prim_l"], padx=20, pady=10)
            self.body.pack(fill="x")
            for i, (m_title, m_desc) in enumerate(self.data["methods"], 1):
                f = tk.Frame(self.body, bg=T["card"], padx=15, pady=12,
                             highlightthickness=1, highlightbackground=T["border"])
                f.pack(fill="x", pady=4)
                tk.Label(f, text=f"{i}. {m_title}", font=F["head"],
                         fg=T["prim"], bg=T["card"], anchor="w").pack(fill="x")
                tk.Label(f, text=m_desc, font=F["body"], fg=T["text_b"],
                         bg=T["card"], wraplength=650, justify="left",
                         anchor="w").pack(fill="x", pady=(2, 0))
            self.lbl_arrow.config(text="收起方案 ︾")
        self.expanded = not self.expanded


# ============================================================
# 主程序
# ============================================================
class MoodApp:
    def __init__(self, root):
        self.root = root
        self.root.title("情绪调节小工具 v3.7")
        self.root.geometry("920x720")
        self.root.minsize(850, 650)
        self.root.configure(bg=T["bg"])

        # 渲染相关引用占位（避免 AttributeError）
        self.suggest_container = None
        self.suggest_headline = None
        self.lbl_temp = None
        self.lbl_desc = None
        self.w_icon = None

        self._init_header()
        self._init_content()
        self._init_nav()

        self._refresh_weather()

    def _init_header(self):
        self.header_frame = tk.Frame(self.root, bg=T["prim"], height=120)
        self.header_frame.pack(fill="x")
        self.header_frame.pack_propagate(False)

        hour = datetime.now().hour
        greeting = ("早安，开启舒心的一天" if 5 <= hour < 12
                    else "午后好，恢复能量" if 12 <= hour < 18
                    else "晚安，静享安宁")

        content = tk.Frame(self.header_frame, bg=T["prim"])
        content.pack(expand=True, padx=50)

        tk.Label(content, text="🌈", font=F["emoji_l"], bg=T["prim"]).pack(side="left", padx=15)
        txt = tk.Frame(content, bg=T["prim"])
        txt.pack(side="left")
        tk.Label(txt, text=greeting, font=F["title"],
                 fg="white", bg=T["prim"]).pack(anchor="w")
        tk.Label(txt, text="基于心理学方案 · 陪你调节每一份情绪",
                 font=F["body"], fg="#E0E7FF", bg=T["prim"]).pack(anchor="w")

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
            b = tk.Label(pill, text=name, font=F["body"], padx=30, pady=8,
                         cursor="hand2", bg=T["nav_bg"], fg=T["text_s"])
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, idx=i: self._switch(idx))
            self.btns.append(b)

        self._switch(0)

    def _switch(self, idx):
        for i, b in enumerate(self.btns):
            if i == idx:
                b.config(bg=T["white"], fg=T["prim"])
            else:
                b.config(bg=T["nav_bg"], fg=T["text_s"])

        if idx == 0:
            self.page_quick.pack_forget()
            self.page_weather.pack(fill="both", expand=True)
            self._render_weather()
        else:
            self.page_weather.pack_forget()
            self.page_quick.pack(fill="both", expand=True)
            self._render_quick()

    # -------- 天气页 --------
    def _render_weather(self):
        c = self.page_weather.inner
        if c.winfo_children():
            return

        # 顶部天气信息卡
        card = tk.Frame(c, bg=T["card"], padx=40, pady=30,
                        highlightthickness=1, highlightbackground=T["border"])
        card.pack(fill="x", padx=20, pady=20)

        self.w_icon = tk.Label(card, text="⌛", font=F["emoji_l"], bg=T["card"])
        self.w_icon.pack(side="left")

        info = tk.Frame(card, bg=T["card"])
        info.pack(side="left", padx=30)
        self.lbl_temp = tk.Label(info, text="--°C", font=F["title"],
                                 fg=T["text_h"], bg=T["card"])
        self.lbl_temp.pack(anchor="w")
        self.lbl_desc = tk.Label(info, text="正在同步天气数据...",
                                 font=F["body"], fg=T["text_s"], bg=T["card"])
        self.lbl_desc.pack(anchor="w")

        # 建议标题（headline 会被实际天气覆盖）
        self.suggest_headline = tk.Label(c, text="💡 今日建议",
                                         font=F["head"], bg=T["bg"], fg=T["text_h"])
        self.suggest_headline.pack(anchor="w", padx=25, pady=(5, 8))

        # 建议挂载点：每次刷新都会 destroy 内部子组件再重绘
        self.suggest_container = tk.Frame(c, bg=T["bg"])
        self.suggest_container.pack(fill="x", padx=20, pady=(0, 20))

        # 占位文字（拿到天气后会被替换）
        tk.Label(self.suggest_container,
                 text="正在为您匹配最契合当前天气的情绪调节方案...",
                 font=F["body"], fg=T["text_s"], bg=T["bg"]).pack(anchor="w", padx=5)

    def _populate_suggestions(self, tips):
        """根据 tips dict 渲染建议卡片到 self.suggest_container。"""
        if not self.suggest_container or not self.suggest_container.winfo_exists():
            return

        # 清空旧内容
        for w in self.suggest_container.winfo_children():
            w.destroy()

        # 更新 headline
        if self.suggest_headline and self.suggest_headline.winfo_exists():
            self.suggest_headline.config(text=f"💡 {tips['headline']}")

        # 渲染建议卡片
        for i, (title, desc) in enumerate(tips["items"], 1):
            f = tk.Frame(self.suggest_container, bg=T["card"], padx=18, pady=14,
                         highlightthickness=1, highlightbackground=T["border"])
            f.pack(fill="x", pady=6, padx=5)
            tk.Label(f, text=f"{i}. {title}", font=F["head"],
                     fg=T["prim"], bg=T["card"], anchor="w").pack(fill="x")
            tk.Label(f, text=desc, font=F["body"], fg=T["text_b"],
                     bg=T["card"], wraplength=720, justify="left",
                     anchor="w").pack(fill="x", pady=(4, 0))

    # -------- 快捷调节页 --------
    def _render_quick(self):
        c = self.page_quick.inner
        if c.winfo_children():
            return

        tk.Label(c, text="针对性情绪方案", font=F["head"],
                 bg=T["bg"], fg=T["text_h"]).pack(anchor="w", padx=25, pady=15)
        for item in QuickDB.ITEMS:
            QuickActionCard(c, item).pack(fill="x", padx=25, pady=6)

    # -------- 天气数据回调 --------
    def _refresh_weather(self):
        WeatherService.fetch_all(self._on_weather)

    def _on_weather(self, res):
        # 切回主线程更新 UI，避免 Tk 线程冲突
        self.root.after(0, lambda: self._apply_weather(res))

    def _apply_weather(self, res):
        if not self.root.winfo_exists():
            return

        # 若用户当前不在天气页，控件可能尚未创建 —— 先确保已经渲染过
        if self.lbl_temp is None:
            self._render_weather()

        if res.get("ok"):
            temp = res.get("temp")
            try:
                temp_text = f"{float(temp):.1f}°C"
            except (TypeError, ValueError):
                temp_text = "--°C"
            self.lbl_temp.config(text=temp_text, fg=T["text_h"])
            self.lbl_desc.config(text=f"当前位于 {res['city']} · {res['desc']}",
                                 fg=T["text_s"])
            self.w_icon.config(text=res["emoji"])
            tips = WeatherTipsDB.get(res["code"], temp)
            self._populate_suggestions(tips)
        else:
            self.lbl_temp.config(text="--°C", fg=T["warn"])
            self.lbl_desc.config(text="天气同步失败，已为您切换为离线建议",
                                 fg=T["warn"])
            self.w_icon.config(text="📵")
            self._populate_suggestions(WeatherTipsDB.offline())


class QuickDB:
    ITEMS = [
        {
            "icon": "😰", "title": "焦虑不安",
            "methods": [
                ("5-4-3-2-1 感官法", "寻找5种看到的、4种触碰到的、3种听到的、2种闻到的、1种尝到的。瞬间拉回当下。"),
                ("4-7-8 呼吸", "吸气4秒，屏息7秒，呼气8秒。重复4次，有效放松。"),
                ("担忧外化记录", "写下担心的事。标注『能控制』的，专注前者，暂时放下后者。"),
            ],
        },
        {
            "icon": "😤", "title": "愤怒烦躁",
            "methods": [
                ("10秒延迟法则", "想发火前默数10个数。给理智大脑（前额叶）留出接管时间。"),
                ("物理能量释放", "撕碎废纸、捏压力球或快走。代谢掉积压的攻击能量。"),
                ("冷水降温法", "用冷水洗脸或握住冰块。触发潜水反射，强制心跳减速。"),
            ],
        },
        {
            "icon": "😢", "title": "悲伤低落",
            "methods": [
                ("悲伤限定时间", "允许悲伤15分钟。闹钟响后去洗脸，做一件极小的事。"),
                ("微小行为激活", "即使没动力也强迫刷牙或整理椅子。行动先于动力。"),
                ("自然光照激活", "接受15分钟照射。阳光是天然抗抑郁剂。"),
            ],
        },
        {
            "icon": "🤯", "title": "压力过载",
            "methods": [
                ("原子化拆解", "把任务拆解到极小步骤。降低启动阻碍感。"),
                ("四象限法则", "区分紧急与重要。优先处理重要不紧急的事。"),
                ("15分钟剧烈运动", "开合跳或快走。代谢体内的压力激素。"),
            ],
        },
        {
            "icon": "😶", "title": "拖延无动力",
            "methods": [
                ("『只做5分钟』", "告诉自己只做5分钟。通常一旦开始，惯性会带你继续。"),
                ("环境气味唤醒", "换房间或闻柑橘香气。刺激唤醒意志力。"),
                ("即时奖励锚点", "设定小奖赏：写完这段话就吃块巧克力。"),
            ],
        },
        {
            "icon": "🌀", "title": "精神内耗",
            "methods": [
                ("寻找反证记录", "写下过去3件成功的小事。用证据对抗偏见。"),
                ("语言剥离法", "不要说『我很失败』，要说『我产生了一个 \"我很失败\" 的念头』。你不是你的想法。"),
                ("STOP 停顿技术", "Stop(停下) -> Take(呼吸) -> Observe(观察) -> Proceed(行动)。"),
            ],
        },
        {
            "icon": "😵‍", "title": "注意力涣散",
            "methods": [
                ("物理隔离分心源", "手机锁进抽屉。视线看不见干扰，专注力自动提升。"),
                ("单任务原则", "一次只处理一件事。任务切换会产生极高疲劳。"),
                ("白噪音屏障", "播放雨声背景音。过滤杂音，进入心流。"),
            ],
        },
        {
            "icon": "😨", "title": "社交焦虑",
            "methods": [
                ("注意力外移练习", "停止监控自己。强迫观察外部细节。将焦点投向外界。"),
                ("万能话题准备", "提前准备天气等话题。有预案会减轻恐慌。"),
                ("接纳紧张反应", "告诉自己紧张在提供能量。越承认越放松。"),
            ],
        },
        {
            "icon": "😴", "title": "失眠多梦",
            "methods": [
                ("肌肉渐进放松", "从脚趾开始用力收缩5秒再放松。一路向上。"),
                ("床铺功能纯化", "不在床上玩手机。建立床与睡眠的强关联。"),
                ("思维日志转存", "把待办写在纸上。告诉大脑：已经记好了，可以休息。"),
            ],
        },
    ]


# ============================================================
if __name__ == "__main__":
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = MoodApp(root)
    root.mainloop()
