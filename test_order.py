"""
测试订单脚本 - 用于诊断订单数量问题
"""
import os
import sys
import ccxt
import time
from dotenv import load_dotenv
from datetime import datetime

# 设置UTF-8编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

# 初始化OKX交易所
exchange = ccxt.okx({
    'options': {
        'defaultType': 'swap',
    },
    'apiKey': os.getenv('OKX_API_KEY'),
    'secret': os.getenv('OKX_SECRET'),
    'password': os.getenv('OKX_PASSWORD'),
})

SYMBOL = 'BTC/USDT:USDT'
LEVERAGE = 10
MARGIN_USDT = 12  # 投入保证金

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def test_order():
    """测试订单执行"""
    
    print_section("1️⃣ 获取市场信息")
    
    # 加载市场
    markets = exchange.load_markets()
    market = markets.get(SYMBOL)
    
    print(f"交易对: {market['symbol']}")
    print(f"合约类型: {market.get('type')}")
    print(f"合约大小(contractSize): {market.get('contractSize')}")
    print(f"最小订单量: {market['limits']['amount']['min']}")
    print(f"数量精度: {market['precision']['amount']}")
    print(f"价格精度: {market['precision']['price']}")
    
    print_section("2️⃣ 获取当前价格")
    
    ticker = exchange.fetch_ticker(SYMBOL)
    current_price = ticker['last']
    print(f"当前价格: ${current_price:,.2f}")
    
    print_section("3️⃣ 计算订单参数")
    
    # 根据USDT金额计算BTC数量
    position_usdt = MARGIN_USDT * LEVERAGE
    btc_amount = position_usdt / current_price
    
    print(f"投入保证金: {MARGIN_USDT} USDT")
    print(f"杠杆倍数: {LEVERAGE}x")
    print(f"开仓金额: {position_usdt} USDT")
    print(f"计算BTC数量: {btc_amount:.8f} BTC")
    
    # 自动调整到最小值
    MIN_ORDER_SIZE = 0.01
    if btc_amount < MIN_ORDER_SIZE:
        print(f"\n⚠️ 数量小于最小值，调整为: {MIN_ORDER_SIZE} BTC")
        btc_amount = MIN_ORDER_SIZE
        actual_position_usdt = btc_amount * current_price
        actual_margin_usdt = actual_position_usdt / LEVERAGE
        print(f"调整后开仓金额: {actual_position_usdt:.2f} USDT")
        print(f"调整后所需保证金: {actual_margin_usdt:.2f} USDT")
    else:
        print(f"✅ 数量满足最小要求")
    
    # 🔥 关键修复：转换为合约张数
    contract_size = market.get('contractSize', 1)
    original_btc_amount = btc_amount
    contracts_amount = btc_amount / contract_size if contract_size > 0 else btc_amount
    
    print(f"\n🔄 合约数量转换:")
    print(f"   目标BTC数量: {original_btc_amount:.8f} BTC")
    print(f"   合约大小(contractSize): {contract_size}")
    print(f"   下单张数: {contracts_amount:.8f} 张")
    print(f"   验证: {contracts_amount:.8f} × {contract_size} = {contracts_amount * contract_size:.8f} BTC")
    
    # 使用转换后的张数
    btc_amount = contracts_amount
    
    print_section("4️⃣ 检查当前持仓")
    
    positions = exchange.fetch_positions([SYMBOL])
    current_position = None
    
    for pos in positions:
        if pos['symbol'] == SYMBOL:
            contracts = float(pos['contracts']) if pos['contracts'] else 0
            if contracts > 0:
                current_position = pos
                print(f"发现持仓:")
                print(f"  方向: {pos['side']}")
                print(f"  数量(contracts): {pos['contracts']}")
                print(f"  数量(contractSize): {pos.get('contractSize', 'N/A')}")
                print(f"  实际BTC数量: {contracts} BTC")
                print(f"  开仓价: ${float(pos['entryPrice']):,.2f}")
                print(f"  未实现盈亏: {float(pos['unrealizedPnl']):.2f} USDT")
                break
    
    if not current_position:
        print("当前无持仓")
    
    print_section("5️⃣ 检查账户余额")
    
    balance = exchange.fetch_balance()
    usdt_balance = balance['USDT']['free']
    total_equity = balance['USDT']['total']
    
    print(f"可用余额: {usdt_balance:.2f} USDT")
    print(f"账户总权益: {total_equity:.2f} USDT")
    
    # 使用原始BTC数量计算保证金（btc_amount已经被转换为张数了）
    required_margin = original_btc_amount * current_price / LEVERAGE
    print(f"\n💡 保证金计算:")
    print(f"   目标BTC: {original_btc_amount:.8f} BTC")
    print(f"   当前价格: ${current_price:,.2f}")
    print(f"   所需保证金: {required_margin:.2f} USDT")
    
    if required_margin > usdt_balance:
        print(f"\n❌ 保证金不足!")
        print(f"   需要: {required_margin:.2f} USDT")
        print(f"   可用: {usdt_balance:.2f} USDT")
        return
    else:
        print(f"\n✅ 保证金充足")
        print(f"   需要: {required_margin:.2f} USDT")
        print(f"   可用: {usdt_balance:.2f} USDT")
        print(f"   剩余: {usdt_balance - required_margin:.2f} USDT")
    
    print_section("6️⃣ 准备下单")
    
    print(f"下单参数:")
    print(f"  交易对: {SYMBOL}")
    print(f"  方向: 买入(做多)")
    print(f"  下单张数: {btc_amount:.8f} 张")
    print(f"  实际买入: {btc_amount * contract_size:.8f} BTC")
    print(f"  订单类型: 市价单")
    
    order_params = {
        'tdMode': 'cross',
        'tag': '60bb4a8d3416BCDE'
    }
    print(f"  额外参数: {order_params}")
    
    # 询问是否执行
    print(f"\n⚠️  确认执行测试订单？")
    print(f"   将下单: {btc_amount:.8f} 张")
    print(f"   实际买入: {btc_amount * contract_size:.8f} BTC (约 {btc_amount * contract_size * current_price:.2f} USDT)")
    response = input("   输入 'YES' 继续: ")
    
    if response.strip().upper() != 'YES':
        print("\n❌ 已取消测试")
        return
    
    print_section("7️⃣ 执行订单")
    
    try:
        # 如果有反向持仓，先平仓
        if current_position and current_position['side'] == 'short':
            print("检测到空头持仓，先平仓...")
            close_params = order_params.copy()
            close_params['reduceOnly'] = True
            exchange.create_market_order(
                SYMBOL,
                'buy',
                current_position['contracts'],
                params=close_params
            )
            print("✅ 平仓完成")
            time.sleep(2)
        
        # 下单
        print(f"正在下单: {btc_amount:.8f} 张 (实际买入 {btc_amount * contract_size:.8f} BTC)...")
        order = exchange.create_market_order(
            SYMBOL,
            'buy',
            btc_amount,
            params=order_params
        )
        
        print("\n✅ 订单提交成功!")
        
        print_section("8️⃣ 订单响应详情")
        
        print(f"订单ID: {order.get('id')}")
        print(f"订单状态: {order.get('status')}")
        print(f"订单类型: {order.get('type')}")
        print(f"交易方向: {order.get('side')}")
        print(f"订单数量: {order.get('amount')} BTC")
        print(f"成交数量: {order.get('filled')} BTC")
        print(f"剩余数量: {order.get('remaining')} BTC")
        print(f"成交价格: ${order.get('price', order.get('average', 'N/A'))}")
        print(f"成交金额: {order.get('cost', 'N/A')} USDT")
        print(f"手续费: {order.get('fee', 'N/A')}")
        
        print(f"\n原始响应:")
        print(f"{order}")
        
        # 等待订单完全成交
        print(f"\n等待2秒...")
        time.sleep(2)
        
        print_section("9️⃣ 查询实际持仓")
        
        positions = exchange.fetch_positions([SYMBOL])
        
        for pos in positions:
            if pos['symbol'] == SYMBOL:
                contracts = float(pos['contracts']) if pos['contracts'] else 0
                if contracts > 0:
                    print(f"✅ 持仓信息:")
                    print(f"  方向: {pos['side']}")
                    print(f"  合约数量(contracts): {pos['contracts']}")
                    print(f"  合约大小(contractSize): {pos.get('contractSize', 'N/A')}")
                    
                    # 关键：计算实际BTC数量
                    contract_size = float(pos.get('contractSize', 1))
                    actual_btc = contracts * contract_size if contract_size != 1 else contracts
                    
                    print(f"  实际BTC数量: {actual_btc:.8f} BTC")
                    print(f"  计算方式: {contracts} × {contract_size} = {actual_btc}")
                    print(f"  开仓价: ${float(pos['entryPrice']):,.2f}")
                    print(f"  未实现盈亏: {float(pos['unrealizedPnl']):.4f} USDT")
                    print(f"  杠杆: {float(pos['leverage'])}x")
                    print(f"  保证金模式: {pos.get('marginMode', 'N/A')}")
                    
                    print(f"\n原始持仓数据:")
                    print(f"{pos}")
                    
                    # 对比分析
                    print_section("🔍 对比分析")
                    
                    expected_btc = contracts_amount * contract_size if 'contracts_amount' in locals() else original_btc_amount
                    
                    print(f"配置保证金: {MARGIN_USDT} USDT")
                    print(f"杠杆倍数: {LEVERAGE}x")
                    print(f"目标开仓金额: {MARGIN_USDT * LEVERAGE} USDT")
                    print(f"目标BTC数量: {original_btc_amount:.8f} BTC")
                    print(f"\n下单张数: {btc_amount:.8f} 张")
                    print(f"预期买入: {expected_btc:.8f} BTC")
                    print(f"实际持仓: {actual_btc:.8f} BTC")
                    
                    diff = abs(actual_btc - expected_btc)
                    diff_percent = (diff / expected_btc * 100) if expected_btc > 0 else 0
                    
                    if diff < 0.00001:  # 允许极小误差
                        print(f"\n✅ 订单执行完美！")
                        print(f"   误差: {diff:.8f} BTC ({diff_percent:.4f}%)")
                    elif diff < 0.0001:
                        print(f"\n✅ 订单执行正常")
                        print(f"   误差: {diff:.8f} BTC ({diff_percent:.4f}%)")
                    else:
                        print(f"\n⚠️ 订单数量不符!")
                        print(f"   差异: {diff:.8f} BTC ({diff_percent:.2f}%)")
                    
                    break
        
        print_section("✅ 测试完成")
        
    except Exception as e:
        print(f"\n❌ 订单执行失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print(f"\n{'#'*60}")
    print(f"  OKX订单测试脚本")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")
    
    test_order()

