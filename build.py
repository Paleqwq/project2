# -*- coding: utf-8 -*-
"""
情绪调节小工具 — 一键打包脚本
用法：
    python build.py                  # 默认：单文件 + 无控制台 + 自动生成图标
    python build.py --no-onefile     # 改为目录模式（启动更快）
    python build.py --console        # 保留控制台便于排查
    python build.py --icon my.ico    # 指定外部图标
    python build.py --clean          # 仅清理产物

打包后产物位置：dist/MoodTool[.exe]
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "mood_tool.py"
APP_NAME = "MoodTool"
DEFAULT_ICON = ROOT / "icon.ico"


# ============================================================
# 工具函数
# ============================================================
def run(cmd, **kwargs):
    print("[run]", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=True, **kwargs)


def ensure_pkg(import_name, pip_name=None):
    pip_name = pip_name or import_name
    try:
        __import__(import_name)
    except ImportError:
        print(f"[deps] 缺少 {pip_name}，正在安装...")
        run([sys.executable, "-m", "pip", "install", "--upgrade", pip_name])


def ensure_icon(path: Path):
    """没有图标就调用 make_icon.py 现场生成。"""
    if path.exists():
        print(f"[icon] 使用已存在图标: {path}")
        return
    maker = ROOT / "make_icon.py"
    if not maker.exists():
        print("[icon] 警告：未找到 make_icon.py，且 icon.ico 不存在，将不附带图标。")
        return
    ensure_pkg("PIL", "pillow")
    print("[icon] 现场生成默认彩虹图标...")
    run([sys.executable, str(maker), str(path)])


def clean_artifacts():
    for d in ("build", "dist", "__pycache__"):
        p = ROOT / d
        if p.exists():
            shutil.rmtree(p)
            print(f"[clean] 已删除 {p}")
    for f in ROOT.glob("*.spec"):
        f.unlink()
        print(f"[clean] 已删除 {f.name}")


# ============================================================
# 主流程
# ============================================================
def build(args):
    if not ENTRY.exists():
        sys.exit(f"[error] 找不到入口文件: {ENTRY}")

    # 1. 准备依赖
    ensure_pkg("PyInstaller", "pyinstaller")
    ensure_pkg("requests")
    ensure_pkg("certifi")

    # 2. 准备图标
    icon_path = Path(args.icon).resolve() if args.icon else DEFAULT_ICON
    if not args.no_icon:
        if not args.icon:
            ensure_icon(icon_path)
        elif not icon_path.exists():
            sys.exit(f"[error] 指定的图标不存在: {icon_path}")

    # 3. 组装 PyInstaller 命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name", APP_NAME,
        # 关键：把 certifi 的 CA 证书全部带进去，否则封包后 HTTPS 会挂
        "--collect-all", "certifi",
        # 仅包含使用到的 tkinter，避免误剔除
        "--collect-submodules", "tkinter",
    ]

    if not args.no_onefile:
        cmd.append("--onefile")
    if not args.console:
        cmd.append("--windowed")  # Windows 下隐藏黑窗口
    if not args.no_icon and icon_path.exists():
        cmd += ["--icon", str(icon_path)]

    # 一些可优化的小开关
    if args.upx:
        cmd += ["--upx-dir", args.upx]

    cmd.append(str(ENTRY))

    print("[build] 命令: " + " ".join(cmd))
    run(cmd, cwd=str(ROOT))

    # 4. 总结产物路径
    exe_name = f"{APP_NAME}.exe" if os.name == "nt" else APP_NAME
    out_path = ROOT / "dist" / (exe_name if args.no_onefile is False else exe_name)
    if args.no_onefile:
        out_path = ROOT / "dist" / APP_NAME / exe_name

    print("\n========================================")
    print("[ok] 打包完成 ✅")
    print(f"  产物: {out_path}")
    if out_path.exists():
        size_mb = out_path.stat().st_size / 1024 / 1024
        print(f"  体积: {size_mb:.1f} MB")
    print("========================================")


def main():
    ap = argparse.ArgumentParser(description="MoodTool packaging script")
    ap.add_argument("--clean", action="store_true", help="仅清理 build/dist/spec")
    ap.add_argument("--no-onefile", action="store_true", help="使用目录模式（启动快）")
    ap.add_argument("--console", action="store_true", help="保留控制台用于调试")
    ap.add_argument("--icon", help="指定 .ico 图标路径")
    ap.add_argument("--no-icon", action="store_true", help="不附带图标")
    ap.add_argument("--upx", help="UPX 压缩工具目录（可选，可让体积更小）")
    args = ap.parse_args()

    if args.clean:
        clean_artifacts()
        return

    build(args)


if __name__ == "__main__":
    main()
