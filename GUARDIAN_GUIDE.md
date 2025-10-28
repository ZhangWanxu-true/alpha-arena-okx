# 进程守护机制使用指南

## 📋 概述

进程守护机制是为了解决**运行时间长了AI决策没有输出**的问题而设计的。它会自动监控交易机器人的健康状态，在出现异常时自动重启恢复。

## 🎯 解决的问题

1. **AI API调用超时** - 网络波动导致API无响应
2. **进程意外退出** - 未捕获的异常导致程序崩溃
3. **内存泄漏** - 长时间运行后性能下降
4. **连接中断** - 交易所或AI服务连接断开

## ✨ 核心功能

### 1. 健康检查
- ✅ 每60秒检查一次进程状态
- ✅ 监控AI决策是否正常输出
- ✅ 检测Web服务是否响应
- ✅ 5分钟无AI输出自动重启

### 2. 自动重启
- ✅ 进程崩溃立即重启
- ✅ 连续失败3次才触发重启
- ✅ 指数退避重试机制
- ✅ 最多重启10次（每小时重置计数）

### 3. 异常处理
- ✅ 捕获所有未处理异常
- ✅ API调用失败自动重试3次
- ✅ 网络错误延迟重试
- ✅ 详细错误日志记录

### 4. 日志管理
- ✅ 所有事件记录到 `guardian.log`
- ✅ 同时输出到控制台
- ✅ 包含时间戳和错误详情

## 🚀 快速开始

### 方式一：使用启动脚本（推荐）

#### Windows
```bash
# 双击运行或命令行执行
start_guardian.bat
```

#### Linux/macOS
```bash
# 添加执行权限（首次）
chmod +x start_guardian.sh

# 运行
./start_guardian.sh
```

### 方式二：手动启动

```bash
# 激活虚拟环境
# Windows
.\venv\Scripts\activate

# Linux/macOS
source venv/bin/activate

# 安装依赖
pip install psutil requests

# 启动守护进程
python process_guardian.py
```

## ⚙️ 配置参数

编辑 `process_guardian.py` 中的参数：

```python
guardian = ProcessGuardian(
    script_name='web_server.py',      # 被监控的脚本
    check_interval=60,                # 检查间隔（秒）
    max_no_response=300,              # 无响应超时（秒）
    max_restarts=10                   # 最大重启次数
)
```

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `script_name` | `web_server.py` | 要守护的Python脚本 |
| `check_interval` | `60` | 健康检查间隔（秒） |
| `max_no_response` | `300` | AI决策超时时间（5分钟） |
| `max_restarts` | `10` | 允许的最大重启次数 |

## 📊 工作流程

```
启动守护进程
    ↓
启动交易机器人
    ↓
等待15秒（服务启动）
    ↓
┌─────────────────────┐
│  每60秒健康检查     │
│                     │
│  1. 进程是否存活？  │
│  2. Web服务响应？   │
│  3. AI决策正常？    │
│  4. 超时检测        │
└─────────────────────┘
    ↓
  正常？
    ↓
  ┌─YES─→ 继续监控
  │
  NO
  ↓
连续失败3次？
  ↓
  YES
  ↓
重启进程
  ↓
重启次数 < 10？
  ↓
  ┌─YES─→ 返回监控
  │
  NO
  ↓
停止守护（需人工介入）
```

## 🔧 改进点说明

### 1. 主程序异常处理增强

在 `deepseekok2.py` 中添加了：

```python
def trading_bot():
    try:
        # 交易逻辑
        pass
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"❌ 交易循环异常: {e}")
        traceback.print_exc()
        time.sleep(10)  # 等待后继续
```

### 2. AI调用重试机制

```python
max_retries = 3
for retry in range(max_retries):
    try:
        response = ai_client.chat.completions.create(...)
        break
    except Exception as e:
        if retry < max_retries - 1:
            wait_time = 2 ** retry  # 指数退避
            time.sleep(wait_time)
```

### 3. 主循环容错

```python
consecutive_errors = 0
max_consecutive_errors = 5

while True:
    try:
        trading_bot()
        consecutive_errors = 0
    except Exception as e:
        consecutive_errors += 1
        if consecutive_errors >= max_consecutive_errors:
            break  # 退出让守护进程重启
        time.sleep(60 * consecutive_errors)
```

## 📝 日志查看

### 实时查看
```bash
# Windows
type guardian.log

# Linux/macOS
tail -f guardian.log
```

### 日志内容示例
```
2025-10-27 10:00:00 [INFO] 进程守护机制启动
2025-10-27 10:00:00 [INFO] 启动进程: python web_server.py
2025-10-27 10:00:15 [INFO] 健康检查通过 ✓
2025-10-27 10:01:15 [INFO] 健康检查通过 ✓
2025-10-27 10:02:15 [WARNING] 健康检查失败 (连续1次)
2025-10-27 10:03:15 [WARNING] 健康检查失败 (连续2次)
2025-10-27 10:04:15 [ERROR] 连续健康检查失败3次，触发重启
2025-10-27 10:04:15 [WARNING] 正在重启进程 (第1次)...
2025-10-27 10:04:20 [INFO] 进程重启成功
```

## 🐛 故障排查

### 1. 守护进程无法启动

**问题**: `ModuleNotFoundError: No module named 'psutil'`

**解决**:
```bash
pip install psutil requests
```

### 2. 频繁重启

**现象**: 日志显示不断重启

**可能原因**:
- API密钥无效
- 网络连接问题
- 配置文件错误

**解决**:
1. 检查 `.env` 文件配置
2. 测试网络连接
3. 查看详细错误日志

### 3. 守护进程自己停止

**现象**: `重启次数超过限制(10)，停止守护`

**原因**: 连续重启失败超过10次

**解决**:
1. 查看 `guardian.log` 找出根本原因
2. 修复问题后重新启动
3. 考虑增加 `max_restarts` 参数

### 4. 健康检查失败

**现象**: `健康检查失败: HTTP 500`

**原因**: Web服务内部错误

**解决**:
1. 查看交易机器人控制台输出
2. 检查API连接状态
3. 验证交易所API权限

## 🔒 安全建议

1. **监控日志大小**
   - 定期清理 `guardian.log`
   - 或使用日志轮转

2. **合理设置重启次数**
   - 避免无限重启浪费资源
   - 严重问题需要人工介入

3. **关键告警通知**
   - 可以集成邮件/短信通知
   - 重启超过阈值时发送告警

## 📈 性能优化建议

### 1. 调整检查间隔

如果AI决策频繁（< 5分钟）：
```python
check_interval=30  # 改为30秒
max_no_response=180  # 改为3分钟
```

### 2. 内存优化

长时间运行后定期重启：
```python
# 在守护进程中添加
if uptime > 12 * 3600:  # 12小时
    restart_process()
```

### 3. 日志轮转

```python
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    'guardian.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
```

## 📚 与其他功能配合

### Docker环境

Docker已内置重启策略：
```yaml
restart: unless-stopped
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/api/dashboard"]
  interval: 30s
  timeout: 10s
  retries: 3
```

Docker环境下**不需要额外的进程守护**。

### 测试模式

```python
TRADE_CONFIG = {
    'test_mode': True,  # 开启测试模式
    # ...
}
```

守护进程在测试模式下同样工作，只是不会真实下单。

## ⚡ 快速命令参考

```bash
# 启动守护进程
start_guardian.bat          # Windows
./start_guardian.sh         # Linux/macOS

# 查看日志
type guardian.log           # Windows
tail -f guardian.log        # Linux/macOS

# 停止守护进程
Ctrl + C

# 清理日志
del guardian.log            # Windows
rm guardian.log             # Linux/macOS

# 检查进程状态
tasklist | findstr python   # Windows
ps aux | grep python        # Linux/macOS
```

## 💡 最佳实践

1. **首次运行**：先用测试模式验证守护机制
2. **监控日志**：定期查看是否有异常重启
3. **合理配置**：根据实际情况调整参数
4. **及时响应**：收到告警后尽快处理
5. **定期检查**：每天查看一次运行状态

## ❓ 常见问题

**Q: 守护进程会消耗很多资源吗？**  
A: 不会。守护进程每分钟只检查一次，资源消耗极小（< 10MB内存）。

**Q: 可以同时运行多个守护进程吗？**  
A: 不建议。会导致冲突，建议只运行一个守护进程。

**Q: 重启会丢失交易数据吗？**  
A: 不会。持仓信息存储在交易所，重启后会自动获取。

**Q: Docker和守护进程哪个更好？**  
A: Docker更简单可靠，推荐使用Docker。守护进程适合Python环境部署。

**Q: 能否自定义重启策略？**  
A: 可以。编辑 `process_guardian.py` 中的 `restart_process()` 方法。

## 🆘 获取帮助

如果遇到问题：

1. 查看 `guardian.log` 日志
2. 检查 `.env` 配置
3. 测试网络连接
4. 验证API密钥
5. 查看主程序输出

---

**守护系统已就绪！** 🛡️✨

现在您的交易机器人可以长时间稳定运行，不用担心AI决策超时或进程崩溃的问题了。

