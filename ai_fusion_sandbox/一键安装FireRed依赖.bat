@echo off
chcp 65001 >nul
REM ============================================================
REM  FireRed-OpenStoryline 沙盒依赖一键安装脚本
REM  用途：在 F:/AI_Clip_Lab/venv 这个隔离环境里装齐 FireRed 全部依赖
REM  特点：绝不装进 MakeMyClip 生产环境，两者物理隔离，只传 JSON
REM  生成时间：2026-11-22
REM ============================================================

set VENV=F:\AI_Clip_Lab\venv\Scripts\python.exe
set PROJ=F:\AI_Clip_Lab\projects\FireRed-OpenStoryline

echo.
echo ===== 第1步：确认虚拟环境 =====
if not exist "%VENV%" (
    echo [错误] 找不到虚拟环境：%VENV%
    echo 请先运行：python -m venv F:\AI_Clip_Lab\venv
    pause
    exit /b 1
)
"%VENV%" --version

echo.
echo ===== 第2步：确认pip源是官方源(已验证可用) =====
"%VENV%" -m pip config set global.index-url https://pypi.org/simple
"%VENV%" -m pip config list

echo.
echo ===== 第3步：升级pip =====
"%VENV%" -m pip install --upgrade pip

echo.
echo ===== 第4步：安装FireRed全部依赖(大包较多,可能要10-20分钟) =====
echo 提示：torch/torchaudio 有 100MB+，请耐心等待，不要中途关闭
"%VENV%" -m pip install -r "%PROJ%\requirements.txt"

echo.
echo ===== 第5步：验证安装结果 =====
"%VENV%" -c "import torch, torchaudio, funasr, faiss, av, sentence_transformers, librosa, moviepy, skillkit, mcp; print('全部依赖导入成功！')"

echo.
echo ===== 完成 =====
echo 如果第5步报错，把红色错误信息发给我，不要自己乱装。
pause
