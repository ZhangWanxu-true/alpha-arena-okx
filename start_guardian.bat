@echo off
chcp 65001 >nul
echo ====================================
echo  BTC交易机器人 - 守护进程启动
echo ====================================
echo.

REM 激活虚拟环境
if exist "venv\Scripts\activate.bat" (
    echo [1/2] 激活虚拟环境...
    call venv\Scripts\activate.bat
) else (
    echo 警告: 未找到虚拟环境，使用系统Python
)

echo [2/2] 启动守护进程...
echo.
echo 守护进程将自动监控并重启交易机器人
echo 按 Ctrl+C 停止
echo.

python process_guardian.py

pause

