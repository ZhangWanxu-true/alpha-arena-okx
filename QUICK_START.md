# 🚀 快速开始指南

## 问题：运行时间长了AI决策没有输出？

**✅ 已解决！** 现在提供进程守护机制，自动监控和恢复。

---

## 📦 新增功能

### 1. 进程守护系统 🛡️

自动监控交易机器人健康状态，解决长时间运行的稳定性问题：

- ✅ AI决策超时自动重启（5分钟无响应）
- ✅ 进程崩溃自动恢复
- ✅ API调用失败自动重试（指数退避）
- ✅ 网络异常自动恢复
- ✅ 详细日志记录

### 2. 主程序增强 🔧

- ✅ 异常捕获和容错处理
- ✅ AI API调用重试机制（3次）
- ✅ 连续错误计数和自动退出
- ✅ 更详细的错误提示

---

## 🎯 三种运行方式选择

### 方式一：Docker（最推荐） 🐳

**优点**: 环境隔离、自动重启、易于管理

```bash
# 启动
docker-compose up -d

# 查看日志
docker-compose logs -f
```

**适用**: 生产环境、服务器部署

---

### 方式二：进程守护（推荐长期运行） 🛡️

**优点**: 自动监控、故障恢复、Python环境

**Windows**:
```bash
start_guardian.bat
```

**Linux/macOS**:
```bash
chmod +x start_guardian.sh
./start_guardian.sh
```

**查看日志**:
```bash
tail -f guardian.log
```

**适用**: 7×24小时运行、需要自动恢复

---

### 方式三：直接运行（适合测试） 🧪

**优点**: 简单直接、便于调试

```bash
# 激活虚拟环境
.\venv\Scripts\activate   # Windows
source venv/bin/activate  # Linux/macOS

# 启动Web服务
python web_server.py
```

**适用**: 开发测试、短期运行

---

## ⚡ 快速测试

确保一切正常工作：

```bash
# 1. 启动Web服务
python web_server.py

# 2. 在另一个终端运行测试
python test_guardian.py
```

测试将检查：
- ✅ Web服务是否响应
- ✅ AI模型是否连接
- ✅ 数据是否新鲜
- ✅ AI决策是否正常

---

## 📋 完整部署流程

### 1. 环境准备

```bash
# 克隆项目
git clone <your-repo-url>
cd ds-main

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\activate      # Windows
source venv/bin/activate     # Linux/macOS

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置文件

创建 `.env` 文件：

```env
# AI模型选择 (deepseek 或 qwen)
AI_PROVIDER=deepseek

# DeepSeek API
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx

# OKX交易所API
OKX_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
OKX_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OKX_PASSWORD=xxxxxxxx
```

### 3. 测试配置

```bash
# 运行测试
python test_guardian.py
```

### 4. 启动守护进程

```bash
# Windows
start_guardian.bat

# Linux/macOS
./start_guardian.sh
```

### 5. 访问监控面板

打开浏览器访问: http://localhost:8080

---

## 🔧 关键配置

### 交易参数 (`deepseekok2.py`)

```python
TRADE_CONFIG = {
    'margin_usdt': 120,     # 投入保证金
    'leverage': 10,         # 杠杆倍数
    'test_mode': False,     # 测试模式
    'timeframe': '15m',     # K线周期
}
```

### 守护参数 (`process_guardian.py`)

```python
guardian = ProcessGuardian(
    check_interval=60,      # 检查间隔（秒）
    max_no_response=300,    # 超时阈值（秒）
    max_restarts=10         # 最大重启次数
)
```

---

## 📊 监控和日志

### 守护进程日志

```bash
# 实时查看
tail -f guardian.log          # Linux/macOS
Get-Content guardian.log -Wait  # PowerShell
type guardian.log             # Windows CMD

# 查看最近100行
tail -n 100 guardian.log      # Linux/macOS
```

### Web监控面板

访问 http://localhost:8080 查看：
- 账户信息和持仓
- BTC实时价格
- AI决策历史
- 收益曲线
- 交易记录

---

## 🐛 故障排查

### 问题1: AI决策长时间没有输出

**现象**: Web面板显示数据很久没更新

**解决**: 
```bash
# 使用守护模式，自动重启
start_guardian.bat

# 查看日志找出原因
tail -f guardian.log
```

### 问题2: 守护进程频繁重启

**现象**: guardian.log显示不断重启

**原因**: 
- API密钥错误
- 网络连接问题
- 配置文件错误

**解决**:
1. 检查 `.env` 配置
2. 测试网络连接
3. 运行 `python test_guardian.py`

### 问题3: 进程完全停止

**现象**: 守护进程退出

**原因**: 连续重启失败超过10次

**解决**:
1. 查看 `guardian.log` 找出根本原因
2. 修复问题后重新启动
3. 考虑增加 `max_restarts` 参数

---

## 💡 最佳实践

### 首次使用
1. ✅ 使用测试模式 (`test_mode: True`)
2. ✅ 小额资金测试
3. ✅ 运行守护测试验证功能

### 生产环境
1. ✅ 使用Docker或守护模式
2. ✅ 定期查看日志
3. ✅ 监控账户余额
4. ✅ 设置合理的止损

### 监控维护
1. ✅ 每天检查一次运行状态
2. ✅ 每周清理一次日志
3. ✅ 关注重启次数
4. ✅ 及时处理异常

---

## 📚 相关文档

- **详细守护指南**: [GUARDIAN_GUIDE.md](GUARDIAN_GUIDE.md)
- **Docker部署**: [DOCKER_GUIDE.md](DOCKER_GUIDE.md)
- **环境配置**: [ENV_CONFIG.md](ENV_CONFIG.md)
- **完整README**: [README.md](README.md)

---

## 📞 获取帮助

遇到问题时的检查清单：

- [ ] 查看 `guardian.log` 日志
- [ ] 检查 `.env` 配置文件
- [ ] 运行 `python test_guardian.py`
- [ ] 测试网络连接
- [ ] 验证API密钥
- [ ] 查看主程序输出

---

**现在开始享受稳定的7×24小时自动交易！** 🎉

```bash
# 一键启动
start_guardian.bat          # Windows
./start_guardian.sh         # Linux/macOS
```

