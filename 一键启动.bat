@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   MakeMyClip 第一阶段 - 基础工作台
echo ============================================
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到隔离环境 .venv，请先运行 安装依赖.bat
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo [程序异常退出] 请把上面的错误信息反馈给开发者。
    pause
)
