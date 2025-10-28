#!/bin/bash

# 进程守护启动脚本 (Linux/macOS)
echo "=================================================="
echo "BTC交易机器人 - 进程守护系统"
echo "=================================================="
echo ""

# 检查Python环境
if [ ! -d "venv" ]; then
    echo "错误: 未找到虚拟环境 venv"
    echo "请先运行: python3 -m venv venv"
    exit 1
fi

# 激活虚拟环境
echo "激活虚拟环境..."
source venv/bin/activate

# 检查依赖
echo "检查依赖..."
if ! python -c "import psutil" 2>/dev/null; then
    echo "安装缺失的依赖..."
    pip install psutil requests
fi

# 检查配置文件
if [ ! -f ".env" ]; then
    echo "警告: 未找到 .env 配置文件"
    echo "请创建 .env 文件并配置 API 密钥"
    exit 1
fi

echo ""
echo "=================================================="
echo "启动进程守护..."
echo "=================================================="
echo ""
echo "守护功能:"
echo "  ✓ 自动监控进程健康状态"
echo "  ✓ AI决策超时自动重启"
echo "  ✓ 进程崩溃自动恢复"
echo "  ✓ 连接失败指数退避重试"
echo ""
echo "按 Ctrl+C 停止守护进程"
echo ""

# 启动守护进程
python process_guardian.py

echo ""
echo "守护进程已停止"

