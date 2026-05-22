# -*- coding: utf-8 -*-
"""
生成个性化图标 icon.ico
- 主题：圆角方块底 + 彩虹弧 + 小白云
- 颜色：与 App 主色 #6366F1 一致
- 输出：icon.ico（含多分辨率 16/32/48/64/128/256）

依赖：Pillow
    pip install pillow
"""

import os
import sys
from PIL import Image, ImageDraw, ImageFilter


# ---------- 颜色 ----------
BG_TOP    = (99, 102, 241)     # #6366F1 indigo
BG_BOT    = (139, 92, 246)     # #8B5CF6 violet
RAINBOW = [
    (244, 63, 94),    # rose
    (249, 115, 22),   # orange
    (250, 204, 21),   # yellow
    (34, 197, 94),    # green
    (14, 165, 233),   # sky
    (139, 92, 246),   # violet
]
CLOUD = (255, 255, 255, 240)
SHADOW = (0, 0, 0, 60)


def _vertical_gradient(size, top, bot):
    """垂直渐变背景"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        r = int(top[0] * (1 - t) + bot[0] * t)
        g = int(top[1] * (1 - t) + bot[1] * t)
        b = int(top[2] * (1 - t) + bot[2] * t)
        for x in range(size):
            px[x, y] = (r, g, b, 255)
    return img


def _rounded_mask(size, radius_ratio=0.22):
    """圆角矩形蒙版"""
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    r = int(size * radius_ratio)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=255)
    return mask


def _draw_rainbow(draw, size):
    """彩虹弧：6 个同心圆环"""
    cx, cy = size // 2, int(size * 0.62)
    outer = int(size * 0.42)
    band = max(1, int(size * 0.045))
    for i, color in enumerate(RAINBOW):
        r = outer - i * band
        bbox = (cx - r, cy - r, cx + r, cy + r)
        draw.arc(bbox, start=200, end=340, fill=color, width=band)


def _draw_clouds(img, size):
    """两朵小白云"""
    cloud = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cloud)

    # 左下云朵
    cx1 = int(size * 0.22)
    cy1 = int(size * 0.74)
    rr1 = int(size * 0.07)
    for dx, dy, k in [(-rr1, 0, 1.0), (0, -rr1 * 0.6, 1.2), (rr1, 0, 1.0)]:
        r = int(rr1 * k)
        cd.ellipse((cx1 + dx - r, cy1 + dy - r, cx1 + dx + r, cy1 + dy + r), fill=CLOUD)

    # 右下云朵
    cx2 = int(size * 0.78)
    cy2 = int(size * 0.78)
    rr2 = int(size * 0.06)
    for dx, dy, k in [(-rr2, 0, 1.0), (0, -rr2 * 0.6, 1.15), (rr2, 0, 1.0)]:
        r = int(rr2 * k)
        cd.ellipse((cx2 + dx - r, cy2 + dy - r, cx2 + dx + r, cy2 + dy + r), fill=CLOUD)

    img.alpha_composite(cloud)


def render(size):
    # 1. 渐变底
    base = _vertical_gradient(size, BG_TOP, BG_BOT)

    # 2. 高光（轻微提亮顶部）
    highlight = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hd = ImageDraw.Draw(highlight)
    hd.ellipse(
        (-size // 4, -size // 2, size + size // 4, size // 2),
        fill=(255, 255, 255, 40),
    )
    base.alpha_composite(highlight)

    # 3. 彩虹
    rainbow_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rainbow_layer)
    _draw_rainbow(rd, size)
    base.alpha_composite(rainbow_layer)

    # 4. 云朵
    _draw_clouds(base, size)

    # 5. 圆角裁切
    mask = _rounded_mask(size)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)

    # 6. 轻微阴影边缘
    if size >= 64:
        glow = out.filter(ImageFilter.GaussianBlur(radius=max(1, size // 80)))
        out = Image.alpha_composite(glow, out)

    return out


def main(out_path="icon.ico"):
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [render(s) for s in sizes]
    # ICO 容器以最大尺寸为基准，会内置全部 sizes
    images[-1].save(
        out_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[:-1],
    )
    print(f"[icon] 已生成: {os.path.abspath(out_path)}  尺寸: {sizes}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "icon.ico"
    main(target)
