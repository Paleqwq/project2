@echo off
chcp 65001 >nul
REM Windows 双击即可打包：单文件 + 无控制台 + 自动生成彩虹图标
setlocal
cd /d "%~dp0"

echo [build] 进入: %cd%
where python >nul 2>nul
if errorlevel 1 (
    echo [error] 没有检测到 python，请先安装 Python 3.x 并加入 PATH
    pause
    exit /b 1
)

python build.py %*
if errorlevel 1 (
    echo [error] 打包失败，请查看上方日志
    pause
    exit /b 1
)

echo.
echo 打包完成，产物在 dist 目录里。
pause
