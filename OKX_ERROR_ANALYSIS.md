# OKX 错误分析：posSide 参数错误

## 错误信息

```json
{
  "code": "1",
  "data": [{
    "clOrdId": "6b9ad766b55dBCDEf69041b83431a3a5",
    "ordId": "",
    "sCode": "51000",
    "sMsg": "Parameter posSide error",
    "tag": "60bb4a8d3416BCDE",
    "ts": "1761660015173"
  }],
  "msg": "All operations failed"
}
```

## 错误分析

### 根本原因
**错误码 51000**: `Parameter posSide error`

此错误表明在 OKX 永续合约下单时，缺少了必需的 `posSide` 参数。

### OKX 永续合约下单要求

在 OKX 永续合约交易中，下单时必须明确指定 `posSide`（持仓方向）：

1. **`posSide: "long"`** - 开多仓
2. **`posSide: "short"`** - 开空仓
3. **`posSide: "net"`** - 净持仓（仅在平仓时使用）

### 当前代码问题

在 `deepseekok2.py` 中，订单参数设置不完整：

```python
# 第1189-1192行：开仓时的参数
order_params = {
    'tdMode': 'cross',  # 全仓模式
    'tag': '60bb4a8d3416BCDE'
    # ❌ 缺少 posSide 参数
}

# 第1205-1210行：开多仓
order_response = exchange.create_market_order(
    TRADE_CONFIG['symbol'],
    'buy',
    btc_amount,
    params=order_params  # 缺少 posSide
)

# 第1232-1237行：开空仓
order_response = exchange.create_market_order(
    TRADE_CONFIG['symbol'],
    'sell',
    btc_amount,
    params=order_params  # 缺少 posSide
)
```

### 问题位置
- **文件**: `deepseekok2.py`
- **函数**: `execute_trade()` 约 1189-1246 行
- **问题**: 开仓时未指定 `posSide` 参数

## 解决方案

### 修复方案：添加 posSide 参数

根据交易方向自动设置 `posSide`：

```python
# 修复前
order_params = {
    'tdMode': 'cross',
    'tag': '60bb4a8d3416BCDE'
}

# 修复后 - 开多仓
order_params = {
    'tdMode': 'cross',
    'posSide': 'long',  # ✅ 开多仓必须指定
    'tag': '60bb4a8d3416BCDE'
}

# 修复后 - 开空仓
order_params = {
    'tdMode': 'cross',
    'posSide': 'short',  # ✅ 开空仓必须指定
    'tag': '60bb4a8d3416BCDE'
}
```

### 具体修改位置

1. **第1194-1220行** - BUY 信号开多仓
   ```python
   if signal_data['signal'] == 'BUY':
       order_params = {
           'tdMode': 'cross',
           'posSide': 'long',  # ✅ 添加
           'tag': '60bb4a8d3416BCDE'
       }
   ```

2. **第1222-1236行** - SELL 信号开空仓
   ```python
   elif signal_data['signal'] == 'SELL':
       order_params = {
           'tdMode': 'cross',
           'posSide': 'short',  # ✅ 添加
           'tag': '60bb4a8d3416BCDE'
       }
   ```

### 为什么会出现这个错误？

CCXT 库在调用 `create_market_order` 时，虽然传递了 `params`，但 OKX 的底层验证要求明确指定 `posSide`。当缺少此参数时，OKX API 返回错误码 51000。

### 额外注意事项

1. **平仓操作**：使用 `posSide: "net"` 或直接不指定（因为 `reduceOnly: True`）
2. **止盈止损订单**：也需要正确设置 `posSide`
3. **全仓模式**：`tdMode: "cross"` 配合 `posSide` 使用

## 修复验证

修复后，订单参数应该类似：

**开多仓示例：**
```python
{
  'tdMode': 'cross',
  'posSide': 'long',
  'tag': '60bb4a8d3416BCDE'
}
```

**开空仓示例：**
```python
{
  'tdMode': 'cross',
  'posSide': 'short',
  'tag': '60bb4a8d3416BCDE'
}
```

## 相关链接

- [OKX API 文档 - 下单](https://www.okx.com/docs-v5/zh/#rest-api-trade-place-order)
- [CCXT OKX 交换文档](https://docs.ccxt.com/#/README?id=okx)
- [OKX 错误码列表](https://www.okx.com/docs-v5/zh/#error-code)
