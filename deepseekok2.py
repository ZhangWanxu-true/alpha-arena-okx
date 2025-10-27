"""
BTC/USDT 自动交易机器人 - 按USDT金额计算版本

配置说明：
-----------
交易方式已改为按 USDT 金额计算，更加直观：

例如：
- margin_usdt = 100  （投入100 USDT保证金）
- leverage = 10      （10倍杠杆）
- 实际开仓金额 = 100 * 10 = 1000 USDT 的BTC

BTC数量会根据实时价格自动计算：
- 当BTC价格 = 100,000 USDT时，买入 0.01 BTC
- 当BTC价格 = 115,000 USDT时，买入 0.00869565 BTC

修改配置：
-----------
在 TRADE_CONFIG 中修改：
- margin_usdt: 每次交易投入的保证金（单位：USDT）
- leverage: 杠杆倍数
- position_usdt: 会自动计算（margin_usdt * leverage）
"""

import os
import time
import schedule
from openai import OpenAI
import ccxt
import pandas as pd
import re
from dotenv import load_dotenv
import json
import requests
from datetime import datetime, timedelta
load_dotenv()

# 初始化AI客户端
# 支持DeepSeek和阿里百炼Qwen
AI_PROVIDER = os.getenv('AI_PROVIDER', 'deepseek').lower()  # 'deepseek' 或 'qwen'

if AI_PROVIDER == 'qwen':
    # 阿里百炼Qwen客户端
    ai_client = OpenAI(
        api_key=os.getenv('DASHSCOPE_API_KEY'),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    AI_MODEL = "qwen-max"
    print(f"使用AI模型: 阿里百炼 {AI_MODEL}")
else:
    # DeepSeek客户端（默认）
    ai_client = OpenAI(
        api_key=os.getenv('DEEPSEEK_API_KEY'),
        base_url="https://api.deepseek.com"
    )
    AI_MODEL = "deepseek-chat"
    print(f"使用AI模型: DeepSeek {AI_MODEL}")

# 保持向后兼容
deepseek_client = ai_client

# 初始化OKX交易所
exchange = ccxt.okx({
    'options': {
        'defaultType': 'swap',  # OKX使用swap表示永续合约
    },
    'apiKey': os.getenv('OKX_API_KEY'),
    'secret': os.getenv('OKX_SECRET'),
    'password': os.getenv('OKX_PASSWORD'),  # OKX需要交易密码
})

# 交易参数配置 - 按USDT金额计算
# ============================================
# 配置示例：
# 1. 小额测试：margin_usdt = 10  -> 开仓 100 USDT (10x杠杆)
# 2. 中等仓位：margin_usdt = 100 -> 开仓 1000 USDT (10x杠杆)
# 3. 大额交易：margin_usdt = 500 -> 开仓 5000 USDT (10x杠杆)
#
# ✨ 自动调整功能：
# - 可以自由设置任意金额（如50、100 USDT等）
# - 如果低于最小订单量，程序会自动调整到0.01 BTC
# - OKX合约最小订单量：0.01 BTC (≈115 USDT保证金，10x杠杆)
# - 示例：配置100 USDT → 自动调整为115 USDT买入0.01 BTC
# ============================================
TRADE_CONFIG = {
    'symbol': 'BTC/USDT:USDT',  # OKX的合约符号格式
    'margin_usdt': 120,  # 🔧 修改这里：每次交易投入的保证金(USDT)
    'leverage': 10,  # 🔧 修改这里：杠杆倍数 (建议10-20倍)
    'position_usdt': None,  # 自动计算：实际开仓金额 = margin_usdt * leverage
    'timeframe': '15m',  # 使用15分钟K线
    'test_mode': False,  # 🔧 测试模式：True=模拟不下单，False=真实交易
    'data_points': 96,  # 24小时数据（96根15分钟K线）
    'analysis_periods': {
        'short_term': 20,  # 短期均线
        'medium_term': 50,  # 中期均线
        'long_term': 96  # 长期趋势
    },
}

# 自动计算实际开仓金额（不要修改）
TRADE_CONFIG['position_usdt'] = TRADE_CONFIG['margin_usdt'] * TRADE_CONFIG['leverage']

# 全局变量存储历史数据
price_history = []
signal_history = []
position = None

# Web展示相关的全局数据存储
web_data = {
    'account_info': {},
    'current_position': None,
    'current_price': 0,
    'trade_history': [],
    'ai_decisions': [],
    'performance': {
        'total_profit': 0,
        'win_rate': 0,
        'total_trades': 0
    },
    'kline_data': [],
    'profit_curve': [],  # 收益曲线数据
    'last_update': None,
    'ai_model_info': {
        'provider': AI_PROVIDER,
        'model': AI_MODEL,
        'status': 'unknown',  # unknown, connected, error
        'last_check': None,
        'error_message': None
    }
}

# 初始余额（用于计算收益率）
initial_balance = None


def setup_exchange():
    """设置交易所参数"""
    try:
        # 获取合约市场信息
        markets = exchange.load_markets()
        market_info = markets.get(TRADE_CONFIG['symbol'])
        
        if market_info:
            print(f"\n{'='*60}")
            print(f"📋 合约市场信息:")
            print(f"   交易对: {market_info['symbol']}")
            print(f"   合约类型: {market_info.get('type', 'N/A')}")
            print(f"   合约大小: {market_info.get('contractSize', 'N/A')}")
            print(f"   最小订单量: {market_info.get('limits', {}).get('amount', {}).get('min', 'N/A')}")
            print(f"   价格精度: {market_info.get('precision', {}).get('price', 'N/A')}")
            print(f"   数量精度: {market_info.get('precision', {}).get('amount', 'N/A')}")
            print(f"{'='*60}\n")
        
        # OKX设置杠杆
        exchange.set_leverage(
            TRADE_CONFIG['leverage'],
            TRADE_CONFIG['symbol'],
            {'mgnMode': 'cross'}  # 全仓模式
        )
        print(f"✅ 设置杠杆倍数: {TRADE_CONFIG['leverage']}x")

        # 获取余额
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['free']
        total_equity = balance['USDT']['total']
        print(f"💰 当前USDT余额: {usdt_balance:.2f} USDT")
        print(f"💰 账户总权益: {total_equity:.2f} USDT")
        print(f"\n💡 交易配置:")
        print(f"   每次投入保证金: {TRADE_CONFIG['margin_usdt']:.2f} USDT")
        print(f"   杠杆倍数: {TRADE_CONFIG['leverage']}x")
        print(f"   实际开仓金额: {TRADE_CONFIG['position_usdt']:.2f} USDT")
        print(f"   可交易次数: {int(usdt_balance / TRADE_CONFIG['margin_usdt'])} 次")

        return True
    except Exception as e:
        print(f"❌ 交易所设置失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def calculate_technical_indicators(df):
    """计算技术指标 - 来自第一个策略"""
    try:
        # 移动平均线
        df['sma_5'] = df['close'].rolling(window=5, min_periods=1).mean()
        df['sma_20'] = df['close'].rolling(window=20, min_periods=1).mean()
        df['sma_50'] = df['close'].rolling(window=50, min_periods=1).mean()

        # 指数移动平均线
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']

        # 相对强弱指数 (RSI)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # 布林带
        df['bb_middle'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # 成交量均线
        df['volume_ma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']

        # 支撑阻力位
        df['resistance'] = df['high'].rolling(20).max()
        df['support'] = df['low'].rolling(20).min()

        # 填充NaN值
        df = df.bfill().ffill()

        return df
    except Exception as e:
        print(f"技术指标计算失败: {e}")
        return df


def get_support_resistance_levels(df, lookback=20):
    """计算支撑阻力位"""
    try:
        recent_high = df['high'].tail(lookback).max()
        recent_low = df['low'].tail(lookback).min()
        current_price = df['close'].iloc[-1]

        resistance_level = recent_high
        support_level = recent_low

        # 动态支撑阻力（基于布林带）
        bb_upper = df['bb_upper'].iloc[-1]
        bb_lower = df['bb_lower'].iloc[-1]

        return {
            'static_resistance': resistance_level,
            'static_support': support_level,
            'dynamic_resistance': bb_upper,
            'dynamic_support': bb_lower,
            'price_vs_resistance': ((resistance_level - current_price) / current_price) * 100,
            'price_vs_support': ((current_price - support_level) / support_level) * 100
        }
    except Exception as e:
        print(f"支撑阻力计算失败: {e}")
        return {}


def get_sentiment_indicators():
    """获取情绪指标 - 简洁版本"""
    try:
        API_URL = "https://service.cryptoracle.network/openapi/v2/endpoint"
        API_KEY = "b54bcf4d-1bca-4e8e-9a24-22ff2c3d76d5"

        # 获取最近4小时数据
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=4)

        request_body = {
            "apiKey": API_KEY,
            "endpoints": ["CO-A-02-01", "CO-A-02-02"],  # 只保留核心指标
            "startTime": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "endTime": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "timeType": "15m",
            "token": ["BTC"]
        }

        headers = {"Content-Type": "application/json", "X-API-KEY": API_KEY}
        response = requests.post(API_URL, json=request_body, headers=headers)

        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200 and data.get("data"):
                time_periods = data["data"][0]["timePeriods"]

                # 查找第一个有有效数据的时间段
                for period in time_periods:
                    period_data = period.get("data", [])

                    sentiment = {}
                    valid_data_found = False

                    for item in period_data:
                        endpoint = item.get("endpoint")
                        value = item.get("value", "").strip()

                        if value:  # 只处理非空值
                            try:
                                if endpoint in ["CO-A-02-01", "CO-A-02-02"]:
                                    sentiment[endpoint] = float(value)
                                    valid_data_found = True
                            except (ValueError, TypeError):
                                continue

                    # 如果找到有效数据
                    if valid_data_found and "CO-A-02-01" in sentiment and "CO-A-02-02" in sentiment:
                        positive = sentiment['CO-A-02-01']
                        negative = sentiment['CO-A-02-02']
                        net_sentiment = positive - negative

                        # 正确的时间延迟计算
                        data_delay = int((datetime.now() - datetime.strptime(
                            period['startTime'], '%Y-%m-%d %H:%M:%S')).total_seconds() // 60)

                        print(f"✅ 使用情绪数据时间: {period['startTime']} (延迟: {data_delay}分钟)")

                        return {
                            'positive_ratio': positive,
                            'negative_ratio': negative,
                            'net_sentiment': net_sentiment,
                            'data_time': period['startTime'],
                            'data_delay_minutes': data_delay
                        }

                print("❌ 所有时间段数据都为空")
                return None

        return None
    except Exception as e:
        print(f"情绪指标获取失败: {e}")
        return None


def get_market_trend(df):
    """判断市场趋势"""
    try:
        current_price = df['close'].iloc[-1]

        # 多时间框架趋势分析
        trend_short = "上涨" if current_price > df['sma_20'].iloc[-1] else "下跌"
        trend_medium = "上涨" if current_price > df['sma_50'].iloc[-1] else "下跌"

        # MACD趋势
        macd_trend = "bullish" if df['macd'].iloc[-1] > df['macd_signal'].iloc[-1] else "bearish"

        # 综合趋势判断
        if trend_short == "上涨" and trend_medium == "上涨":
            overall_trend = "强势上涨"
        elif trend_short == "下跌" and trend_medium == "下跌":
            overall_trend = "强势下跌"
        else:
            overall_trend = "震荡整理"

        return {
            'short_term': trend_short,
            'medium_term': trend_medium,
            'macd': macd_trend,
            'overall': overall_trend,
            'rsi_level': df['rsi'].iloc[-1]
        }
    except Exception as e:
        print(f"趋势分析失败: {e}")
        return {}


def get_btc_ohlcv_enhanced():
    """增强版：获取BTC K线数据并计算技术指标"""
    try:
        # 获取K线数据
        ohlcv = exchange.fetch_ohlcv(TRADE_CONFIG['symbol'], TRADE_CONFIG['timeframe'],
                                     limit=TRADE_CONFIG['data_points'])

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        # 计算技术指标
        df = calculate_technical_indicators(df)

        current_data = df.iloc[-1]
        previous_data = df.iloc[-2]

        # 获取技术分析数据
        trend_analysis = get_market_trend(df)
        levels_analysis = get_support_resistance_levels(df)

        return {
            'price': current_data['close'],
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'high': current_data['high'],
            'low': current_data['low'],
            'volume': current_data['volume'],
            'timeframe': TRADE_CONFIG['timeframe'],
            'price_change': ((current_data['close'] - previous_data['close']) / previous_data['close']) * 100,
            'kline_data': df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].tail(10).to_dict('records'),
            'technical_data': {
                'sma_5': current_data.get('sma_5', 0),
                'sma_20': current_data.get('sma_20', 0),
                'sma_50': current_data.get('sma_50', 0),
                'rsi': current_data.get('rsi', 0),
                'macd': current_data.get('macd', 0),
                'macd_signal': current_data.get('macd_signal', 0),
                'macd_histogram': current_data.get('macd_histogram', 0),
                'bb_upper': current_data.get('bb_upper', 0),
                'bb_lower': current_data.get('bb_lower', 0),
                'bb_position': current_data.get('bb_position', 0),
                'volume_ratio': current_data.get('volume_ratio', 0)
            },
            'trend_analysis': trend_analysis,
            'levels_analysis': levels_analysis,
            'full_data': df
        }
    except Exception as e:
        print(f"获取增强K线数据失败: {e}")
        return None


def generate_technical_analysis_text(price_data):
    """生成技术分析文本"""
    if 'technical_data' not in price_data:
        return "技术指标数据不可用"

    tech = price_data['technical_data']
    trend = price_data.get('trend_analysis', {})
    levels = price_data.get('levels_analysis', {})

    # 检查数据有效性
    def safe_float(value, default=0):
        return float(value) if value and pd.notna(value) else default

    analysis_text = f"""
    【技术指标分析】
    📈 移动平均线:
    - 5周期: {safe_float(tech['sma_5']):.2f} | 价格相对: {(price_data['price'] - safe_float(tech['sma_5'])) / safe_float(tech['sma_5']) * 100:+.2f}%
    - 20周期: {safe_float(tech['sma_20']):.2f} | 价格相对: {(price_data['price'] - safe_float(tech['sma_20'])) / safe_float(tech['sma_20']) * 100:+.2f}%
    - 50周期: {safe_float(tech['sma_50']):.2f} | 价格相对: {(price_data['price'] - safe_float(tech['sma_50'])) / safe_float(tech['sma_50']) * 100:+.2f}%

    🎯 趋势分析:
    - 短期趋势: {trend.get('short_term', 'N/A')}
    - 中期趋势: {trend.get('medium_term', 'N/A')}
    - 整体趋势: {trend.get('overall', 'N/A')}
    - MACD方向: {trend.get('macd', 'N/A')}

    📊 动量指标:
    - RSI: {safe_float(tech['rsi']):.2f} ({'超买' if safe_float(tech['rsi']) > 70 else '超卖' if safe_float(tech['rsi']) < 30 else '中性'})
    - MACD: {safe_float(tech['macd']):.4f}
    - 信号线: {safe_float(tech['macd_signal']):.4f}

    🎚️ 布林带位置: {safe_float(tech['bb_position']):.2%} ({'上部' if safe_float(tech['bb_position']) > 0.7 else '下部' if safe_float(tech['bb_position']) < 0.3 else '中部'})

    💰 关键水平:
    - 静态阻力: {safe_float(levels.get('static_resistance', 0)):.2f}
    - 静态支撑: {safe_float(levels.get('static_support', 0)):.2f}
    """
    return analysis_text


def get_current_position():
    """获取当前持仓情况 - OKX版本"""
    try:
        positions = exchange.fetch_positions([TRADE_CONFIG['symbol']])

        for pos in positions:
            if pos['symbol'] == TRADE_CONFIG['symbol']:
                contracts = float(pos['contracts']) if pos['contracts'] else 0

                if contracts > 0:
                    return {
                        'side': pos['side'],  # 'long' or 'short'
                        'size': contracts,
                        'entry_price': float(pos['entryPrice']) if pos['entryPrice'] else 0,
                        'unrealized_pnl': float(pos['unrealizedPnl']) if pos['unrealizedPnl'] else 0,
                        'leverage': float(pos['leverage']) if pos['leverage'] else TRADE_CONFIG['leverage'],
                        'symbol': pos['symbol']
                    }

        return None

    except Exception as e:
        print(f"获取持仓失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def safe_json_parse(json_str):
    """安全解析JSON，处理格式不规范的情况"""
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        try:
            # 尝试提取JSON代码块（如果AI包在```json```中）
            if '```json' in json_str:
                start = json_str.find('```json') + 7
                end = json_str.find('```', start)
                if end != -1:
                    json_str = json_str[start:end].strip()
            elif '```' in json_str:
                start = json_str.find('```') + 3
                end = json_str.find('```', start)
                if end != -1:
                    json_str = json_str[start:end].strip()
            
            # 尝试直接解析
            try:
                return json.loads(json_str)
            except:
                pass
            
            # 修复常见的JSON格式问题
            json_str = json_str.replace("'", '"')
            json_str = re.sub(r'(\w+):', r'"\1":', json_str)
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"JSON解析失败，原始内容: {json_str[:200]}")
            print(f"错误详情: {e}")
            return None


def test_ai_connection():
    """测试AI模型连接状态"""
    global web_data
    try:
        print(f"🔍 测试 {AI_PROVIDER.upper()} 连接...")
        response = ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "user", "content": "Hello"}
            ],
            max_tokens=10,
            timeout=10.0
        )
        
        if response and response.choices:
            web_data['ai_model_info']['status'] = 'connected'
            web_data['ai_model_info']['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            web_data['ai_model_info']['error_message'] = None
            print(f"✓ {AI_PROVIDER.upper()} 连接正常")
            return True
        else:
            web_data['ai_model_info']['status'] = 'error'
            web_data['ai_model_info']['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            web_data['ai_model_info']['error_message'] = '响应为空'
            print(f"❌ {AI_PROVIDER.upper()} 连接失败: 响应为空")
            return False
            
    except Exception as e:
        web_data['ai_model_info']['status'] = 'error'
        web_data['ai_model_info']['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        web_data['ai_model_info']['error_message'] = str(e)
        print(f"❌ {AI_PROVIDER.upper()} 连接失败: {e}")
        return False


def create_fallback_signal(price_data):
    """创建备用交易信号"""
    return {
        "signal": "HOLD",
        "reason": "因技术分析暂时不可用，采取保守策略",
        "stop_loss": price_data['price'] * 0.98,  # -2%
        "take_profit": price_data['price'] * 1.02,  # +2%
        "confidence": "LOW",
        "is_fallback": True
    }


def analyze_with_deepseek(price_data):
    """使用DeepSeek分析市场并生成交易信号（增强版）"""

    # 生成技术分析文本
    technical_analysis = generate_technical_analysis_text(price_data)

    # 构建K线数据文本
    kline_text = f"【最近5根{TRADE_CONFIG['timeframe']}K线数据】\n"
    for i, kline in enumerate(price_data['kline_data'][-5:]):
        trend = "阳线" if kline['close'] > kline['open'] else "阴线"
        change = ((kline['close'] - kline['open']) / kline['open']) * 100
        kline_text += f"K线{i + 1}: {trend} 开盘:{kline['open']:.2f} 收盘:{kline['close']:.2f} 涨跌:{change:+.2f}%\n"

    # 添加上次交易信号
    signal_text = ""
    if signal_history:
        last_signal = signal_history[-1]
        signal_text = f"\n【上次交易信号】\n信号: {last_signal.get('signal', 'N/A')}\n信心: {last_signal.get('confidence', 'N/A')}"

    # 获取情绪数据
    sentiment_data = get_sentiment_indicators()
    # 简化情绪文本（多了没用）
    if sentiment_data:
        sign = '+' if sentiment_data['net_sentiment'] >= 0 else ''
        sentiment_text = f"【市场情绪】乐观{sentiment_data['positive_ratio']:.1%} 悲观{sentiment_data['negative_ratio']:.1%} 净值{sign}{sentiment_data['net_sentiment']:.3f}"
    else:
        sentiment_text = "【市场情绪】数据暂不可用"

    print(sentiment_text)

    # 添加当前持仓信息
    current_pos = get_current_position()
    position_text = "无持仓" if not current_pos else f"{current_pos['side']}仓, 数量: {current_pos['size']}, 盈亏: {current_pos['unrealized_pnl']:.2f}USDT"
    pnl_text = f", 持仓盈亏: {current_pos['unrealized_pnl']:.2f} USDT" if current_pos else ""

    prompt = f"""
    你是一个专业的加密货币交易分析师。请基于以下BTC/USDT {TRADE_CONFIG['timeframe']}周期数据进行分析：

    {kline_text}

    {technical_analysis}

    {signal_text}

    {sentiment_text}  # 添加情绪分析

    【当前行情】
    - 当前价格: ${price_data['price']:,.2f}
    - 时间: {price_data['timestamp']}
    - 本K线最高: ${price_data['high']:,.2f}
    - 本K线最低: ${price_data['low']:,.2f}
    - 本K线成交量: {price_data['volume']:.2f} BTC
    - 价格变化: {price_data['price_change']:+.2f}%
    - 当前持仓: {position_text}{pnl_text}

    【防频繁交易重要原则】
    1. **趋势持续性优先**: 不要因单根K线或短期波动改变整体趋势判断
    2. **持仓稳定性**: 除非趋势明确强烈反转，否则保持现有持仓方向
    3. **反转确认**: 需要至少2-3个技术指标同时确认趋势反转才改变信号
    4. **成本意识**: 减少不必要的仓位调整，每次交易都有成本

    【交易指导原则 - 必须遵守】
    1. **技术分析主导** (权重60%)：趋势、支撑阻力、K线形态是主要依据
    2. **市场情绪辅助** (权重30%)：情绪数据用于验证技术信号，不能单独作为交易理由  
    - 情绪与技术同向 → 增强信号信心
    - 情绪与技术背离 → 以技术分析为主，情绪仅作参考
    - 情绪数据延迟 → 降低权重，以实时技术指标为准
    3. **风险管理** (权重10%)：考虑持仓、盈亏状况和止损位置
    4. **趋势跟随**: 明确趋势出现时立即行动，不要过度等待
    5. 因为做的是btc，做多权重可以大一点点
    6. **信号明确性**:
    - 强势上涨趋势 → BUY信号
    - 强势下跌趋势 → SELL信号  
    - 仅在窄幅震荡、无明确方向时 → HOLD信号
    7. **技术指标权重**:
    - 趋势(均线排列) > RSI > MACD > 布林带
    - 价格突破关键支撑/阻力位是重要信号

    【当前技术状况分析】
    - 整体趋势: {price_data['trend_analysis'].get('overall', 'N/A')}
    - 短期趋势: {price_data['trend_analysis'].get('short_term', 'N/A')} 
    - RSI状态: {price_data['technical_data'].get('rsi', 0):.1f} ({'超买' if price_data['technical_data'].get('rsi', 0) > 70 else '超卖' if price_data['technical_data'].get('rsi', 0) < 30 else '中性'})
    - MACD方向: {price_data['trend_analysis'].get('macd', 'N/A')}

    【分析要求】
    基于以上分析，请给出明确的交易信号

    请用以下JSON格式回复：
    {{
        "signal": "BUY|SELL|HOLD",
        "reason": "简要分析理由(包含趋势判断和技术依据)",
        "stop_loss": 具体价格,
        "take_profit": 具体价格, 
        "confidence": "HIGH|MEDIUM|LOW"
    }}
    """

    try:
        print(f"⏳ 正在调用{AI_PROVIDER.upper()} API ({AI_MODEL})...")
        response = ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system",
                 "content": f"您是一位专业的交易员，专注于{TRADE_CONFIG['timeframe']}周期趋势分析。请结合K线形态和技术指标做出判断，并严格遵循JSON格式要求。"},
                {"role": "user", "content": prompt}
            ],
            stream=False,
            temperature=0.1,
            timeout=30.0  # 30秒超时
        )
        print("✓ API调用成功")
        
        # 更新AI连接状态
        web_data['ai_model_info']['status'] = 'connected'
        web_data['ai_model_info']['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        web_data['ai_model_info']['error_message'] = None

        # 检查响应
        if not response or not response.choices:
            print(f"❌ {AI_PROVIDER.upper()}返回空响应")
            web_data['ai_model_info']['status'] = 'error'
            web_data['ai_model_info']['error_message'] = '响应为空'
            return create_fallback_signal(price_data)
        
        # 安全解析JSON
        result = response.choices[0].message.content
        if not result:
            print(f"❌ {AI_PROVIDER.upper()}返回空内容")
            return create_fallback_signal(price_data)
            
        print(f"\n{'='*60}")
        print(f"{AI_PROVIDER.upper()}原始回复:")
        print(result)
        print(f"{'='*60}\n")

        # 提取JSON部分
        start_idx = result.find('{')
        end_idx = result.rfind('}') + 1

        if start_idx != -1 and end_idx != 0:
            json_str = result[start_idx:end_idx]
            signal_data = safe_json_parse(json_str)

            if signal_data is None:
                print("⚠️ JSON解析失败，使用备用信号")
                signal_data = create_fallback_signal(price_data)
            else:
                print(f"✓ 成功解析AI决策: {signal_data.get('signal')} - {signal_data.get('confidence')}")
        else:
            print("⚠️ 未找到JSON格式，使用备用信号")
            signal_data = create_fallback_signal(price_data)

        # 验证必需字段
        required_fields = ['signal', 'reason', 'stop_loss', 'take_profit', 'confidence']
        if not all(field in signal_data for field in required_fields):
            missing = [f for f in required_fields if f not in signal_data]
            print(f"⚠️ 缺少必需字段: {missing}，使用备用信号")
            signal_data = create_fallback_signal(price_data)

        # 保存信号到历史记录
        signal_data['timestamp'] = price_data['timestamp']
        signal_history.append(signal_data)
        if len(signal_history) > 30:
            signal_history.pop(0)

        # 信号统计
        signal_count = len([s for s in signal_history if s.get('signal') == signal_data['signal']])
        total_signals = len(signal_history)
        print(f"信号统计: {signal_data['signal']} (最近{total_signals}次中出现{signal_count}次)")

        # 信号连续性检查
        if len(signal_history) >= 3:
            last_three = [s['signal'] for s in signal_history[-3:]]
            if len(set(last_three)) == 1:
                print(f"⚠️ 注意：连续3次{signal_data['signal']}信号")

        return signal_data

    except Exception as e:
        print(f"{AI_PROVIDER.upper()}分析失败: {e}")
        # 更新AI连接状态
        web_data['ai_model_info']['status'] = 'error'
        web_data['ai_model_info']['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        web_data['ai_model_info']['error_message'] = str(e)
        return create_fallback_signal(price_data)


def execute_trade(signal_data, price_data):
    """执行交易 - OKX版本（修复保证金检查）"""
    global position, web_data

    current_position = get_current_position()

    # 🔴 紧急修复：防止频繁反转
    if current_position and signal_data['signal'] != 'HOLD':
        current_side = current_position['side']
        # 修正：正确处理HOLD情况
        if signal_data['signal'] == 'BUY':
            new_side = 'long'
        elif signal_data['signal'] == 'SELL':
            new_side = 'short'
        else:  # HOLD
            new_side = None

        # 如果只是方向反转，需要高信心才执行
        if new_side != current_side:
            if signal_data['confidence'] != 'HIGH':
                print(f"🔒 非高信心反转信号，保持现有{current_side}仓")
                return

            # 检查最近信号历史，避免频繁反转
            if len(signal_history) >= 2:
                last_signals = [s['signal'] for s in signal_history[-2:]]
                if signal_data['signal'] in last_signals:
                    print(f"🔒 近期已出现{signal_data['signal']}信号，避免频繁反转")
                    return

    print(f"交易信号: {signal_data['signal']}")
    print(f"信心程度: {signal_data['confidence']}")
    print(f"理由: {signal_data['reason']}")
    print(f"止损: ${signal_data['stop_loss']:,.2f}")
    print(f"止盈: ${signal_data['take_profit']:,.2f}")
    print(f"当前持仓: {current_position}")

    # 风险管理：低信心信号不执行
    if signal_data['confidence'] == 'LOW' and not TRADE_CONFIG['test_mode']:
        print("⚠️ 低信心信号，跳过执行")
        return

    if TRADE_CONFIG['test_mode']:
        print("测试模式 - 仅模拟交易")
        return

    try:
        # 获取账户余额
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['free']
        
        # 🔄 根据USDT金额计算BTC数量
        margin_usdt = TRADE_CONFIG['margin_usdt']  # 保证金
        position_usdt = TRADE_CONFIG['position_usdt']  # 实际开仓金额（保证金 * 杠杆）
        btc_amount = position_usdt / price_data['price']  # 买入的BTC数量
        
        # ✨ 自动调整到最小订单量（OKX要求≥0.01 BTC）
        MIN_ORDER_SIZE = 0.01  # OKX永续合约最小订单量
        original_amount = btc_amount
        
        if btc_amount < MIN_ORDER_SIZE:
            btc_amount = MIN_ORDER_SIZE
            actual_position_usdt = btc_amount * price_data['price']
            actual_margin_usdt = actual_position_usdt / TRADE_CONFIG['leverage']
            
            print(f"\n⚠️ 订单量自动调整:")
            print(f"   原计划买入: {original_amount:.6f} BTC (价值 {position_usdt:.2f} USDT)")
            print(f"   调整为最小量: {btc_amount:.2f} BTC (价值 {actual_position_usdt:.2f} USDT)")
            print(f"   所需保证金: {actual_margin_usdt:.2f} USDT (原计划 {margin_usdt:.2f} USDT)")
            
            # 更新实际使用的金额
            margin_usdt = actual_margin_usdt
            position_usdt = actual_position_usdt
        
        # 🔥 关键修复：OKX合约需要转换为张数
        # OKX的BTC永续合约: 1张 = 0.01 BTC (contractSize = 0.01)
        # 我们需要传入的是"张数"而不是BTC数量
        try:
            markets = exchange.load_markets()
            market = markets.get(TRADE_CONFIG['symbol'])
            contract_size = market.get('contractSize', 1) if market else 1
            
            # 转换：BTC数量 → 张数
            contracts_amount = btc_amount / contract_size if contract_size > 0 else btc_amount
            
            print(f"\n🔄 合约数量转换:")
            print(f"   目标BTC数量: {btc_amount:.8f} BTC")
            print(f"   合约大小(contractSize): {contract_size}")
            print(f"   下单张数: {contracts_amount:.8f} 张")
            print(f"   验证: {contracts_amount:.8f} × {contract_size} = {contracts_amount * contract_size:.8f} BTC")
            
            # 使用转换后的张数
            btc_amount = contracts_amount
            
        except Exception as e:
            print(f"⚠️ 获取合约信息失败，使用原始数量: {e}")
            # 如果获取失败，保持原值
        
        # 检查保证金是否充足（使用调整后的金额）
        if margin_usdt > usdt_balance * 0.8:  # 使用不超过80%的余额
            print(f"\n❌ 保证金不足，跳过交易。")
            print(f"   需要: {margin_usdt:.2f} USDT")
            print(f"   可用: {usdt_balance:.2f} USDT")
            print(f"   💡 建议: 充值至少 {margin_usdt - usdt_balance:.2f} USDT")
            return

        # 📊 显示交易详情
        print(f"\n{'='*50}")
        print(f"📊 交易前信息检查:")
        print(f"   当前价格: ${price_data['price']:,.2f}")
        print(f"   投入保证金: {margin_usdt:.2f} USDT")
        print(f"   杠杆倍数: {TRADE_CONFIG['leverage']}x")
        print(f"   开仓金额: {position_usdt:.2f} USDT")
        print(f"   下单张数: {btc_amount:.6f} 张")
        
        # 显示实际会买入的BTC数量
        try:
            actual_btc = btc_amount * contract_size
            print(f"   实际买入: {actual_btc:.8f} BTC ({btc_amount:.6f} 张 × {contract_size} BTC/张)")
        except:
            print(f"   实际买入: ~{btc_amount:.6f} BTC")
        
        print(f"   可用余额: {usdt_balance:.2f} USDT")
        print(f"   剩余余额: {usdt_balance - margin_usdt:.2f} USDT")
        print(f"{'='*50}\n")

        # OKX永续合约需要的参数
        order_params = {
            'tdMode': 'cross',  # 全仓模式
            'tag': '60bb4a8d3416BCDE'
        }
        
        if signal_data['signal'] == 'BUY':
            if current_position and current_position['side'] == 'short':
                print("平空仓并开多仓...")
                # 平空仓
                close_params = order_params.copy()
                close_params['reduceOnly'] = True
                exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'buy',
                    current_position['size'],
                    params=close_params
                )
                time.sleep(1)
                # 开多仓（使用计算的张数）
                try:
                    display_btc = btc_amount * contract_size
                    print(f"   准备买入: {btc_amount:.6f} 张 = {display_btc:.8f} BTC (价值 {position_usdt:.2f} USDT)")
                except:
                    print(f"   准备买入: {btc_amount:.6f} 张 (价值 {position_usdt:.2f} USDT)")
                print(f"   📊 订单参数: {order_params}")
                
                order_response = exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'buy',
                    btc_amount,
                    params=order_params
                )
                
                print(f"\n   📄 订单响应:")
                print(f"   订单ID: {order_response.get('id', 'N/A')}")
                print(f"   实际数量: {order_response.get('amount', 'N/A')} BTC")
                print(f"   成交数量: {order_response.get('filled', 'N/A')} BTC")
            elif current_position and current_position['side'] == 'long':
                print("已有多头持仓，保持现状")
            else:
                # 无持仓时开多仓
                print("开多仓...")
                try:
                    display_btc = btc_amount * contract_size
                    print(f"   准备买入: {btc_amount:.6f} 张 = {display_btc:.8f} BTC (价值 {position_usdt:.2f} USDT)")
                except:
                    print(f"   准备买入: {btc_amount:.6f} 张 (价值 {position_usdt:.2f} USDT)")
                print(f"   📊 订单参数: {order_params}")
                
                # 下单并获取订单响应
                order_response = exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'buy',
                    btc_amount,
                    params=order_params
                )
                
                # 打印订单响应详情
                print(f"\n   📄 订单响应:")
                print(f"   订单ID: {order_response.get('id', 'N/A')}")
                print(f"   状态: {order_response.get('status', 'N/A')}")
                print(f"   实际数量: {order_response.get('amount', 'N/A')} BTC")
                print(f"   成交数量: {order_response.get('filled', 'N/A')} BTC")
                print(f"   成交价格: ${order_response.get('price', order_response.get('average', 'N/A'))}")
                if order_response.get('cost'):
                    print(f"   成交金额: {order_response.get('cost', 'N/A')} USDT")

        elif signal_data['signal'] == 'SELL':
            if current_position and current_position['side'] == 'long':
                print("平多仓并开空仓...")
                # 平多仓
                close_params = order_params.copy()
                close_params['reduceOnly'] = True
                exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'sell',
                    current_position['size'],
                    params=close_params
                )
                time.sleep(1)
                # 开空仓（使用计算的张数）
                try:
                    display_btc = btc_amount * contract_size
                    print(f"   准备卖出: {btc_amount:.6f} 张 = {display_btc:.8f} BTC (价值 {position_usdt:.2f} USDT)")
                except:
                    print(f"   准备卖出: {btc_amount:.6f} 张 (价值 {position_usdt:.2f} USDT)")
                print(f"   📊 订单参数: {order_params}")
                
                order_response = exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'sell',
                    btc_amount,
                    params=order_params
                )
                
                print(f"\n   📄 订单响应:")
                print(f"   订单ID: {order_response.get('id', 'N/A')}")
                print(f"   实际数量: {order_response.get('amount', 'N/A')} BTC")
                print(f"   成交数量: {order_response.get('filled', 'N/A')} BTC")
            elif current_position and current_position['side'] == 'short':
                print("已有空头持仓，保持现状")
            else:
                # 无持仓时开空仓
                print("开空仓...")
                try:
                    display_btc = btc_amount * contract_size
                    print(f"   准备卖出: {btc_amount:.6f} 张 = {display_btc:.8f} BTC (价值 {position_usdt:.2f} USDT)")
                except:
                    print(f"   准备卖出: {btc_amount:.6f} 张 (价值 {position_usdt:.2f} USDT)")
                print(f"   📊 订单参数: {order_params}")
                
                order_response = exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'sell',
                    btc_amount,
                    params=order_params
                )
                
                print(f"\n   📄 订单响应:")
                print(f"   订单ID: {order_response.get('id', 'N/A')}")
                print(f"   状态: {order_response.get('status', 'N/A')}")
                print(f"   实际数量: {order_response.get('amount', 'N/A')} BTC")
                print(f"   成交数量: {order_response.get('filled', 'N/A')} BTC")
                print(f"   成交价格: ${order_response.get('price', order_response.get('average', 'N/A'))}")
                if order_response.get('cost'):
                    print(f"   成交金额: {order_response.get('cost', 'N/A')} USDT")

        print("✅ 订单提交成功")
        time.sleep(2)
        
        # 获取最新持仓并显示详细信息
        position = get_current_position()
        print(f"\n{'='*50}")
        print(f"📈 更新后持仓信息:")
        if position:
            print(f"   方向: {position['side']}")
            print(f"   数量: {position['size']} BTC")
            print(f"   开仓价: ${position['entry_price']:,.2f}")
            print(f"   未实现盈亏: {position['unrealized_pnl']:+.2f} USDT")
            print(f"   杠杆: {position['leverage']}x")
        else:
            print(f"   无持仓")
        print(f"{'='*50}\n")
        
        # 记录交易历史
        trade_record = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'signal': signal_data['signal'],
            'price': price_data['price'],
            'amount': btc_amount,  # BTC数量
            'margin_usdt': margin_usdt,  # 保证金
            'position_usdt': position_usdt,  # 开仓金额
            'confidence': signal_data['confidence'],
            'reason': signal_data['reason']
        }
        web_data['trade_history'].append(trade_record)
        if len(web_data['trade_history']) > 100:  # 只保留最近100条
            web_data['trade_history'].pop(0)

    except Exception as e:
        error_msg = str(e).lower()
        print(f"\n❌ 订单执行失败: {e}")
        
        # 检查是否是最小数量限制错误
        if 'min' in error_msg or 'amount' in error_msg or 'size' in error_msg:
            print(f"\n💡 可能原因：订单数量低于交易所最小限制")
            print(f"   解决方法1：增加保证金至 115-120 USDT")
            print(f"   解决方法2：联系交易所了解实际最小限制")
            print(f"   当前配置：{TRADE_CONFIG['margin_usdt']} USDT × {TRADE_CONFIG['leverage']}x = {TRADE_CONFIG['position_usdt']} USDT")
        
        import traceback
        traceback.print_exc()


def analyze_with_deepseek_with_retry(price_data, max_retries=2):
    """带重试的DeepSeek分析"""
    for attempt in range(max_retries):
        try:
            signal_data = analyze_with_deepseek(price_data)
            if signal_data and not signal_data.get('is_fallback', False):
                return signal_data

            print(f"第{attempt + 1}次尝试失败，进行重试...")
            time.sleep(2)

        except Exception as e:
            print(f"第{attempt + 1}次尝试异常: {e}")
            import traceback
            traceback.print_exc()
            if attempt == max_retries - 1:
                return create_fallback_signal(price_data)
            time.sleep(2)

    return create_fallback_signal(price_data)


def wait_for_next_period():
    """等待到下一个15分钟整点"""
    now = datetime.now()
    current_minute = now.minute
    current_second = now.second

    # 计算下一个整点时间（00, 15, 30, 45分钟）
    next_period_minute = ((current_minute // 15) + 1) * 15
    if next_period_minute == 60:
        next_period_minute = 0

    # 计算需要等待的总秒数
    if next_period_minute > current_minute:
        minutes_to_wait = next_period_minute - current_minute
    else:
        minutes_to_wait = 60 - current_minute + next_period_minute

    seconds_to_wait = minutes_to_wait * 60 - current_second

    # 显示友好的等待时间
    display_minutes = minutes_to_wait - 1 if current_second > 0 else minutes_to_wait
    display_seconds = 60 - current_second if current_second > 0 else 0

    if display_minutes > 0:
        print(f"🕒 等待 {display_minutes} 分 {display_seconds} 秒到整点...")
    else:
        print(f"🕒 等待 {display_seconds} 秒到整点...")

    return seconds_to_wait


def test_order_amount():
    """测试订单数量是否正确（按USDT计算）"""
    try:
        print(f"\n{'='*60}")
        print(f"🧪 订单数量测试模式 (按USDT金额计算)")
        print(f"{'='*60}")
        
        # 获取市场信息
        markets = exchange.load_markets()
        market = markets.get(TRADE_CONFIG['symbol'])
        
        # 获取当前价格
        ticker = exchange.fetch_ticker(TRADE_CONFIG['symbol'])
        current_price = ticker['last']
        
        # 根据USDT金额计算BTC数量
        margin_usdt = TRADE_CONFIG['margin_usdt']
        position_usdt = TRADE_CONFIG['position_usdt']
        btc_amount = position_usdt / current_price
        
        # 检查并模拟自动调整
        MIN_ORDER_SIZE = 0.01
        original_amount = btc_amount
        will_adjust = False
        
        if btc_amount < MIN_ORDER_SIZE:
            will_adjust = True
            btc_amount = MIN_ORDER_SIZE
            actual_position_usdt = btc_amount * current_price
            actual_margin_usdt = actual_position_usdt / TRADE_CONFIG['leverage']
        
        print(f"📊 测试参数:")
        print(f"   交易对: {TRADE_CONFIG['symbol']}")
        print(f"   当前价格: ${current_price:,.2f}")
        print(f"   配置保证金: {margin_usdt:.2f} USDT")
        print(f"   杠杆倍数: {TRADE_CONFIG['leverage']}x")
        print(f"   配置开仓金额: {position_usdt:.2f} USDT")
        print(f"   计算买入数量: {original_amount:.6f} BTC")
        
        if market:
            contract_size = market.get('contractSize', 1)
            min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
            print(f"\n   合约大小: {contract_size}")
            print(f"   最小数量: {min_amount}")
            
            # 显示自动调整信息
            if will_adjust:
                print(f"\n   ✨ 自动调整（实际下单时）:")
                print(f"   ├─ 调整买入量: {btc_amount:.2f} BTC")
                print(f"   ├─ 实际开仓金额: {actual_position_usdt:.2f} USDT")
                print(f"   └─ 实际所需保证金: {actual_margin_usdt:.2f} USDT")
            else:
                print(f"\n   ✅ 订单量满足最小要求，无需调整")
        
        print(f"{'='*60}\n")
        
        # 获取账户余额
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['free']
        
        if margin_usdt > usdt_balance:
            print(f"⚠️ 警告: 保证金不足！")
            print(f"   需要: {margin_usdt:.2f} USDT")
            print(f"   可用: {usdt_balance:.2f} USDT")
            print(f"   建议调整保证金为: {usdt_balance * 0.8:.2f} USDT")
        else:
            print(f"✅ 保证金充足")
            print(f"   需要: {margin_usdt:.2f} USDT")
            print(f"   可用: {usdt_balance:.2f} USDT")
            print(f"   剩余: {usdt_balance - margin_usdt:.2f} USDT")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


def trading_bot():
    # 等待到整点再执行
    wait_seconds = wait_for_next_period()
    if wait_seconds > 0:
        time.sleep(wait_seconds)

    """主交易机器人函数"""
    global web_data, initial_balance
    
    print("\n" + "=" * 60)
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 获取增强版K线数据
    price_data = get_btc_ohlcv_enhanced()
    if not price_data:
        return

    print(f"BTC当前价格: ${price_data['price']:,.2f}")
    print(f"数据周期: {TRADE_CONFIG['timeframe']}")
    print(f"价格变化: {price_data['price_change']:+.2f}%")

    # 2. 使用DeepSeek分析（带重试）
    signal_data = analyze_with_deepseek_with_retry(price_data)

    if signal_data.get('is_fallback', False):
        print("⚠️ 使用备用交易信号")

    # 3. 更新Web数据
    try:
        balance = exchange.fetch_balance()
        current_equity = balance['USDT']['total']
        
        # 设置初始余额
        if initial_balance is None:
            initial_balance = current_equity
        
        web_data['account_info'] = {
            'usdt_balance': balance['USDT']['free'],
            'total_equity': current_equity
        }
        
        # 记录收益曲线数据
        current_position = get_current_position()
        unrealized_pnl = current_position.get('unrealized_pnl', 0) if current_position else 0
        total_profit = current_equity - initial_balance
        profit_rate = (total_profit / initial_balance * 100) if initial_balance > 0 else 0
        
        profit_point = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'equity': current_equity,
            'profit': total_profit,
            'profit_rate': profit_rate,
            'unrealized_pnl': unrealized_pnl
        }
        web_data['profit_curve'].append(profit_point)
        
        # 只保留最近200个数据点（约50小时）
        if len(web_data['profit_curve']) > 200:
            web_data['profit_curve'].pop(0)
            
    except Exception as e:
        print(f"更新余额失败: {e}")
    
    web_data['current_price'] = price_data['price']
    web_data['current_position'] = get_current_position()
    web_data['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 保存K线数据
    web_data['kline_data'] = price_data['kline_data']
    
    # 保存AI决策
    ai_decision = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'signal': signal_data['signal'],
        'confidence': signal_data['confidence'],
        'reason': signal_data['reason'],
        'stop_loss': signal_data.get('stop_loss', 0),
        'take_profit': signal_data.get('take_profit', 0),
        'price': price_data['price']
    }
    web_data['ai_decisions'].append(ai_decision)
    if len(web_data['ai_decisions']) > 50:  # 只保留最近50条
        web_data['ai_decisions'].pop(0)
    
    # 更新性能统计
    if web_data['current_position']:
        web_data['performance']['total_profit'] = web_data['current_position'].get('unrealized_pnl', 0)

    # 4. 执行交易
    execute_trade(signal_data, price_data)


def main():
    """主函数"""
    print("\n" + "="*60)
    print("🤖 BTC/USDT OKX自动交易机器人")
    print("="*60)
    print(f"AI模型: {AI_PROVIDER.upper()} ({AI_MODEL})")
    print("融合技术指标策略 + OKX实盘接口")
    print(f"交易周期: {TRADE_CONFIG['timeframe']}")
    print(f"\n💰 交易配置 (按USDT金额计算):")
    print(f"   投入保证金: {TRADE_CONFIG['margin_usdt']} USDT")
    print(f"   杠杆倍数: {TRADE_CONFIG['leverage']}x")
    print(f"   实际开仓金额: {TRADE_CONFIG['position_usdt']} USDT")

    if TRADE_CONFIG['test_mode']:
        print("\n⚠️  当前为模拟模式，不会真实下单")
    else:
        print("\n🔴 实盘交易模式，请谨慎操作！")

    # 设置交易所
    if not setup_exchange():
        print("❌ 交易所初始化失败，程序退出")
        return

    # 运行测试检查
    print("\n" + "="*60)
    print("🔍 运行订单数量测试...")
    print("="*60)
    test_order_amount()
    
    # 询问是否继续
    if not TRADE_CONFIG['test_mode']:
        print("\n⚠️  请确认上述信息正确后继续")
        print("如果需要调整金额，请修改 TRADE_CONFIG['margin_usdt'] 参数")
        print(f"当前配置: 每次投入 {TRADE_CONFIG['margin_usdt']} USDT，开仓 {TRADE_CONFIG['position_usdt']} USDT 的BTC")
        print("按 Ctrl+C 可随时停止程序\n")
        time.sleep(5)  # 给用户5秒时间检查

    print("\n" + "="*60)
    print("🚀 开始交易循环")
    print("执行频率: 每15分钟整点执行")
    print("="*60 + "\n")

    # 循环执行（不使用schedule）
    while True:
        trading_bot()  # 函数内部会自己等待整点

        # 执行完后等待一段时间再检查（避免频繁循环）
        time.sleep(60)  # 每分钟检查一次


if __name__ == "__main__":
    main()