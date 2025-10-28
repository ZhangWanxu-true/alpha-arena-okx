# 故障排查指南

## 当前状态

✅ **已解决的问题：**
- Docker 版本警告已移除
- `.env` 文件已创建
- Web 服务正常运行在 http://localhost:8080
- DeepSeek AI API 连接正常
- 容器自动重启机制工作正常
- 交易所连接失败时的重试机制已实现

❌ **待解决的问题：**
- Docker 容器无法连接到 OKX 交易所 API (`www.okx.com`)
  - 错误: `Connection refused (111)`
  - 原因: Docker Desktop for Mac 的网络限制

## 网络问题诊断

### 问题现象
容器无法连接到 OKX API，出现 `Connection refused` 错误。

### 测试结果
```bash
# 从宿主机可以访问 OKX
$ ping www.okx.com
64 bytes from 169.254.0.2

# 从容器无法访问 OKX
$ docker exec btc-trading-bot python3 -c "import socket; s = socket.socket(); result = s.connect_ex(('www.okx.com', 443)); print(result)"
111  # Connection refused
```

### 可能的原因
1. **Docker Desktop 网络限制**：Docker Desktop for Mac 的桥接网络可能有防火墙限制
2. **VPN/代理冲突**：系统代理可能影响容器网络
3. **DNS 解析问题**：虽然已经配置了 8.8.8.8 作为 DNS

## 解决方案

### 方案 1: 使用 host 网络模式（推荐）

修改 `docker-compose.yml` 使用宿主机网络：

```yaml
services:
  btc-trading-bot:
    # ... 其他配置 ...
    network_mode: "host"  # 使用宿主机网络
    # 注意：使用 host 模式时不需要 ports 映射
```

**优点：** 容器直接使用宿主机网络，完全绕过 Docker 网络限制
**缺点：** 失去网络隔离，端口映射需要调整

### 方案 2: 配置 Docker Desktop 网络

1. 打开 Docker Desktop
2. 进入 Settings → Resources → Network
3. 添加网络代理或调整 DNS 设置

### 方案 3: 使用代理服务器

如果系统有代理，配置容器使用代理：

```yaml
environment:
  - HTTP_PROXY=http://your-proxy:port
  - HTTPS_PROXY=http://your-proxy:port
```

### 方案 4: 暂时忽略网络问题

当前实现已经非常健壮：
- ✅ Web 界面正常工作
- ✅ AI 模型连接正常
- ✅ 交易所连接会自动重试（最多 10 次）
- ✅ 即使 OKX 无法连接，应用仍可正常运行

## 常用命令

### 查看容器状态
```bash
docker ps | grep btc-trading-bot
```

### 查看实时日志
```bash
docker logs -f btc-trading-bot
```

### 重启容器
```bash
docker-compose restart
```

### 停止容器
```bash
docker-compose down
```

### 进入容器调试
```bash
docker exec -it btc-trading-bot bash
```

### 测试 OKX 连接
```bash
docker exec btc-trading-bot python3 -c "
import requests
try:
    r = requests.get('https://www.okx.com/api/v5/public/time', timeout=5)
    print(f'OKX Reachable: {r.status_code}')
except Exception as e:
    print(f'OKX Unreachable: {e}')
"
```

## 当前功能状态

### ✅ 正常运行的功能
- Web 管理界面 (http://localhost:8080)
- AI 模型连接检测
- API 接口响应
- 日志记录
- 健康监控

### ⚠️ 受限的功能
- 交易所实时数据获取
- 自动交易执行

### 💡 工作流程
1. 应用启动时会尝试连接 OKX
2. 如果连接失败，会等待 60 秒后重试
3. 最多重试 10 次
4. 即使连接失败，Web 界面仍可正常使用
5. 每 5 分钟会重新尝试初始化交易所

## 建议

如果 OKX 连接对您很重要，建议：

1. **方案 A**: 在 Linux 服务器上部署（Docker 网络问题较少）
2. **方案 B**: 使用 Docker Desktop 的 host 网络模式
3. **方案 C**: 配置 VPN 或代理绕过网络限制
4. **方案 D**: 暂时使用 Web 界面查看功能，OKX 连接会自动恢复

## 相关文件

- `docker-compose.yml` - Docker 编排配置
- `app.py` - 主应用文件（包含重试逻辑）
- `deepseekok2.py` - 交易机器人核心代码
- `.env` - 环境配置文件

## 更新日志

### 2025-10-28
- ✅ 修复了 Docker Compose 版本警告
- ✅ 创建了 `.env` 文件
- ✅ 实现了交易所连接重试机制
- ✅ 优化了错误处理逻辑
- ✅ 配置了 DNS 服务器 (8.8.8.8)
- ⚠️ OKX 连接仍然被 Docker 网络限制
