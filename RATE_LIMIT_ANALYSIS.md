# OKX API 限流（429错误）分析报告

## 错误信息

```
HTTPError: 429 Client Error: Too Many Requests
ccxt.base.errors.RateLimitExceeded: okx {"msg":"Too Many Requests","code":"50011"}
```

## 错误原因

### 1. API 请求频率过高

**OKX API 限流规则：**
- **未验证API Key**: 每秒 20 次请求
- **已验证API Key**: 每秒 10 次请求
- **错误码 50011**: Too Many Requests

**限制窗口**:
- 通常在 60 秒内如果请求超过限制，会被限流
- 限流后需要等待 60 秒才能恢复

### 2. `get_current_position()` 调用位置统计

在 `trading_bot()` 函数的单次执行中，`get_current_position()` 被调用了 **至少 2-3 次**：

```
第 1526 行: 检查是否需要平仓
第 1581 行: 更新收益曲线
第 1603 行: 更新 Web 数据
```

另外还有：
- 第 596 行: AI 分析时获取持仓
- 第 1035 行: `execute_close_position()` 中重新获取
- 第 1084 行: 平仓后验证
- 第 1110 行: `execute_trade()` 中防御性检查
- 第 1295 行: 开仓后获取最新持仓

**单次循环的完整调用链**:

```python
trading_bot()
  ├─ get_current_position()        # 第 1526 行
  ├─ check_close_position()
  │   └─ get_current_position()    # 第 596 行
  ├─ execute_close_position()
  │   ├─ get_current_position()    # 第 1035 行
  │   └─ get_current_position()    # 第 1084 行
  ├─ get_current_position()        # 第 1581 行
  └─ get_current_position()        # 第 1603 行
```

**在同一个 trading_bot() 周期内，可能调用 4-6 次**！

### 3. 并发问题

如果交易机器人线程和健康监控线程同时运行：
- 健康监控每 60 秒检查一次，也会触发持仓查询
- Web API 每分钟更新一次持仓数据
- 多个线程可能同时调用 API

### 4. 没有请求间隔控制

代码中没有实现：
- ❌ 请求间隔限制（rate limiting）
- ❌ 请求队列
- ❌ 缓存机制

## 时间线分析

典型的交易循环：

1. **00:00** - `trading_bot()` 开始
2. **00:01** - 调用 `get_current_position()` (第1526行)
3. **00:01** - 调用 `get_current_position()` (第596行，AI分析)
4. **00:02** - 调用 `execute_close_position()`
5. **00:02** - 调用 `get_current_position()` (第1035行，重新验证)
6. **00:04** - 平仓后调用 `get_current_position()` (第1084行)
7. **00:05** - 调用 `get_current_position()` (第1581行，收益曲线)
8. **00:06** - 调用 `get_current_position()` (第1603行，Web数据)

**6 次 API 调用在 6 秒内完成** → 触发限流！

## 解决方案建议

### 方案 1: 实现缓存机制（推荐）

缓存持仓信息，避免重复调用：

```python
# 在模块级别添加缓存
position_cache = {
    'data': None,
    'timestamp': None,
    'ttl': 5  # 5秒缓存
}

def get_current_position(cached=False):
    """获取当前持仓情况（支持缓存）"""
    global position_cache

    # 检查缓存
    if cached and position_cache['data']:
        now = datetime.now()
        cache_age = (now - position_cache['timestamp']).total_seconds()
        if cache_age < position_cache['ttl']:
            return position_cache['data']

    # 调用 API
    try:
        positions = exchange.fetch_positions([TRADE_CONFIG['symbol']])
        # ... 处理数据

        # 更新缓存
        position_cache['data'] = result
        position_cache['timestamp'] = datetime.now()

        return result
    except Exception as e:
        # 如果有缓存，返回缓存数据
        if position_cache['data']:
            return position_cache['data']
        raise
```

### 方案 2: 减少重复调用

在一次 `trading_bot()` 执行中，只调用一次 `get_current_position()`，然后将结果传递：

```python
def trading_bot():
    # 只调用一次
    current_position = get_current_position()

    # 传递给需要的函数
    if current_position:
        execute_close_position(current_position, reason)

    # 更新数据时使用已获取的结果
    web_data['current_position'] = current_position
```

### 方案 3: 添加请求间隔

在每次 API 调用之间添加延迟：

```python
import time

last_api_call = 0
min_interval = 0.5  # 最小间隔 0.5 秒

def get_current_position():
    global last_api_call

    # 控制调用频率
    time_since_last = time.time() - last_api_call
    if time_since_last < min_interval:
        time.sleep(min_interval - time_since_last)

    last_api_call = time.time()

    # 调用 API
    positions = exchange.fetch_positions(...)
    ...
```

### 方案 4: 使用请求队列

使用队列机制，确保请求按顺序且间隔执行：

```python
import queue
import threading

request_queue = queue.Queue()

def api_worker():
    """后台线程处理 API 请求"""
    while True:
        func, args, kwargs, future = request_queue.get()
        try:
            result = func(*args, **kwargs)
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)
        time.sleep(0.2)  # 200ms 间隔
```

## 推荐解决方案组合

**最佳方案** = **方案 1（缓存）** + **方案 2（减少调用）**

1. 实现 5 秒缓存机制
2. 在 `trading_bot()` 中只调用一次，然后传递结果
3. 这样可以减少 80% 的 API 调用

**效果预估**:
- 当前: 单次循环 6 次调用
- 优化后: 单次循环 1-2 次调用
- 减少: **67-83%** 的 API 调用
- 限流可能性: **几乎为 0**

## 当前状态

- ❌ 未实现缓存机制
- ❌ 多次重复调用 API
- ❌ 没有请求间隔控制
- ✅ 已添加错误处理

## 临时缓解措施

如果需要立即缓解问题：

1. **增加 `time.sleep()`**: 在关键 API 调用之间添加延迟
2. **手动降低频率**: 延长交易周期（如从 15 分钟改为 30 分钟）
3. **等待限流解除**: 限流通常在 60 秒后解除

## OKX API 限流说明

参考: [OKX API 限流规则](https://www.okx.com/docs-v5/zh/#rest-api-rate-limit)

- 429 错误是保护机制，防止滥用
- 限流期间所有请求都会失败
- 需要等待限制时间过去才能恢复
