@echo off
chcp 65001 >nul
title OmniToys 一键编译构建程序

echo ========================================================
echo       OmniToys (PowerToys-style) 单文件 EXE 编译工具
echo ========================================================
echo.

:: 1. 检查 Python 环境
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python 环境，请先安装 Python 3.8+ 并勾选 "Add to PATH"。
    pause
    exit /b 1
)

:: 2. 安装必要构建依赖
echo [1/3] 正在检查并安装构建依赖 (pyinstaller, pywebview)...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [警告] 依赖安装遇到问题，尝试直接编译...
)

:: 3. 清理旧构建目录
echo [2/3] 清理旧编译缓存...
if exist "build" rd /s /q "build"
if exist "dist\OmniToys.exe" del /f /q "dist\OmniToys.exe"

:: 4. 开始 PyInstaller 编译打包
echo [3/3] 正在使用 PyInstaller 编译为单文件 EXE...
pyinstaller OmniToys.spec --clean --noconfirm

if exist "dist\OmniToys.exe" (
    echo.
    echo ========================================================
    echo  [成功!] 编译完成！
    echo  可执行文件位于: dist\OmniToys.exe
    echo  体积轻巧，无额外黑框窗口，双击即可直接运行！
    echo ========================================================
) else (
    echo.
    echo [失败] 未能在 dist 目录找到 OmniToys.exe，请检查上方日志。
)

echo.
pause
