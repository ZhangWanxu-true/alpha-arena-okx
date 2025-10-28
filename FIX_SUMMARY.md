# OKX 错误修复总结

## 问题描述

OKX API 返回错误：
```json
{
  "sCode": "51000",
  "sMsg": "Parameter posSide error"
}
```

## 根本原因

在 OKX 永续合约交易中，开仓时必须明确指定 `posSide` 参数：
- **开多仓**: `posSide: "long"`
- **开空仓**: `posSide: "short"`

代码中缺少此参数导致下单失败。

## 修复内容

### 修改文件：`deepseekok2.py`

**1. 开多仓时添加 posSide 参数（第1194-1216行）**

```python
# 修复前
order_params = {
    'tdMode': 'cross',
    'tag': '60bb4a8d3416BCDE'
}
order_response = exchange.create_market_order(
    TRADE_CONFIG['symbol'],
    'buy',
    btc_amount,
    params=order_params
)

# 修复后
order_params_with_posside = {
    'tdMode': 'cross',
    'posSide': 'long',  # ✅ 开多仓必须指定
    'tag': '60bb4a8d3416BCDE'
}
order_response = exchange.create_market_order(
    TRADE_CONFIG['symbol'],
    'buy',
    btc_amount,
    params=order_params_with_posside
)
```

**2. 开空仓时添加 posSide 参数（第1228-1249行）**

```python
# 修复前
order_params = {
    'tdMode': 'cross',
    'tag': '60bb4a8d3416BCDE'
}
order_response = exchange.create_market_order(
    TRADE_CONFIG['symbol'],
    'sell',
    btc_amount,
    params=order_params
)

# 修复后
order_params_with_posside = {
    'tdMode': 'cross',
    'posSide': 'short',  # ✅ 开空仓必须指定
    'tag': '60bb4a8d3416BCDE'
}
order_response = exchange.create_market_order(
    TRADE_CONFIG['symbol'],
    'sell',
    btc_amount,
    params=order_params_with_posside
)
```

### 修改文件：`docker-compose.yml`

移除了无效的 extra_hosts 配置，修复容器启动问题。

## 已部署

✅ 代码已更新到容器
✅ 容器已重启
✅ 新代码已生效

## 已修复的额外问题

### 平仓操作也需要 posSide（新增）
**问题**: 平仓时也缺少 `posSide` 参数
**位置**: `execute_close_position()` 函数（第1032-1050行）
**修复**: 添加根据持仓方向设置的 `posSide` 参数

```python
# 平仓时根据持仓方向设置 posSide
posSide = 'long' if side == 'long' else 'short'
close_params = {
    'tdMode': 'cross',
    'posSide': posSide,  # ✅ 必须指定
    'reduceOnly': True,
    'tag': '60bb4a8d3416BCDE'
}
```

### 止盈止损订单也需要 posSide（新增）
**问题**: 设置止盈止损时缺少 `posSide` 参数
**位置**: `set_stop_orders()` 函数（第777-840行）
**修复**: 为所有止盈止损订单添加 `posSide` 参数

- 多仓止盈止损: `posSide: 'long'`
- 空仓止盈止损: `posSide: 'short'`

## 验证方法

1. **查看日志**
   ```bash
   docker logs -f btc-trading-bot
   ```

2. **等待自动交易**
   - 应用会自动重试交易所连接（每60秒）
   - 连接成功后，下次交易信号将使用新参数
   - 观察日志中是否有 "Parameter posSide error"

3. **手动测试（如有持仓）**
   - 当前持仓会被检测
   - 下次交易信号触发时会使用修复后的代码

## 预期结果

- ✅ 开多仓时：`posSide: 'long'`，不应再出现 51000 错误
- ✅ 开空仓时：`posSide: 'short'`，不应再出现 51000 错误
- ✅ 平仓时：根据持仓方向设置正确的 `posSide`
- ✅ 止盈止损：根据持仓方向设置正确的 `posSide`
- ✅ 订单应成功提交到 OKX

## 相关文档

- `OKX_ERROR_ANALYSIS.md` - 详细的错误分析
- `TROUBLESHOOTING.md` - 故障排查指南

## 注意事项

1. **网络问题仍然存在**：Docker 容器暂时无法连接到 OKX（Error 111）
   - 这是 Docker Desktop for Mac 的网络限制
   - 代码已实现自动重试机制（最多10次）

2. **代码修复已生效**：一旦网络连接恢复，交易将使用正确的 `posSide` 参数

3. **平仓操作**：使用 `reduceOnly: True` 时不需要指定 `posSide`

## 后续建议

1. 等待网络自动恢复，或
2. 考虑在 Linux 服务器上部署（网络限制较少），或
3. 使用 Docker host 网络模式
