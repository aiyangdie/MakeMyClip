@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   安装 MakeMyClip 运行依赖（隔离环境）
echo ============================================
python -m venv .venv
if errorlevel 1 (
    echo [错误] 创建隔离环境失败，请确认已安装 Python。
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo 安装完成。请运行 一键启动.bat
pause
