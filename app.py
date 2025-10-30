"""
宝塔面板部署入口文件
整合Web服务 + 进程守护 + 交易机器人
"""
from flask import Flask, jsonify, render_template, request, abort
from flask_cors import CORS
import threading
import time
import sys
import os
from datetime import datetime
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 获取当前文件所在目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 导入主程序
import deepseekok2

# 创建Flask应用
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))
CORS(app)

# ==================== 基础安全防护（基于实际攻击日志） ====================
# 拦截常见扫描/敏感路径与异常协议请求，减少 400/404 垃圾流量
FORBIDDEN_PATH_KEYWORDS = [
    ".git", ".env", "/admin", "wp-login", "phpmyadmin", "/etc/passwd", "/login",
    "geoserver", "shadowserver", "/web/"
]

@app.before_request
def security_filters():
    # 1) 仅允许常规方法
    if request.method not in ("GET", "POST"):
        abort(405)

    # 2) 拦截 CONNECT（代理/端口扫描特征）
    if request.method == "CONNECT":
        abort(405)

    # 3) 路径关键词黑名单（.git/.env/geoserver/wp-login 等）
    path_lower = (request.path or "").lower()
    if any(k in path_lower for k in FORBIDDEN_PATH_KEYWORDS):
        abort(403)

    # 4) 基础协议健壮性：必须是 HTTP 协议，UA 不得为空
    if not (request.environ.get('SERVER_PROTOCOL', 'HTTP/1.1').startswith('HTTP/')):
        abort(400)
    ua = request.headers.get('User-Agent', '')
    if not ua or len(ua) < 4:
        abort(400)

@app.errorhandler(400)
def _bad_request(e):
    return jsonify({"error": "BAD_REQUEST"}), 400

@app.errorhandler(403)
def _forbidden(e):
    return jsonify({"error": "FORBIDDEN"}), 403

@app.errorhandler(404)
def _not_found(e):
    return jsonify({"error": "NOT_FOUND"}), 404

@app.errorhandler(405)
def _method_not_allowed(e):
    return jsonify({"error": "METHOD_NOT_ALLOWED"}), 405

# 全局变量
trading_bot_thread = None
health_monitor_thread = None
last_health_check = datetime.now()
health_check_interval = 60  # 60秒检查一次
max_no_response = 300  # 5分钟无响应

# ==================== Flask路由 ====================

@app.route('/')
def index():
    """主页"""
    try:
        return render_template('index.html')
    except Exception as e:
        return f"<h1>模板加载错误</h1><p>{str(e)}</p><p>模板路径: {app.template_folder}</p>"

@app.route('/api/dashboard')
def get_dashboard_data():
    """获取仪表板数据"""
    try:
        data = {
            'account_info': deepseekok2.web_data['account_info'],
            'current_position': deepseekok2.web_data['current_position'],
            'current_price': deepseekok2.web_data['current_price'],
            'last_update': deepseekok2.web_data['last_update'],
            'performance': deepseekok2.web_data['performance'],
            'config': {
                'symbol': deepseekok2.TRADE_CONFIG['symbol'],
                'leverage': deepseekok2.TRADE_CONFIG['leverage'],
                'timeframe': deepseekok2.TRADE_CONFIG['timeframe'],
                'test_mode': deepseekok2.TRADE_CONFIG['test_mode']
            }
        }
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/kline')
def get_kline_data():
    """获取K线数据"""
    try:
        return jsonify(deepseekok2.web_data['kline_data'])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/trades')
def get_trade_history():
    """获取交易历史"""
    try:
        return jsonify(deepseekok2.web_data['trade_history'])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai_decisions')
def get_ai_decisions():
    """获取AI决策历史"""
    try:
        return jsonify(deepseekok2.web_data['ai_decisions'])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/signals')
def get_signal_history():
    """获取信号历史统计"""
    try:
        signals = deepseekok2.signal_history

        signal_stats = {'BUY': 0, 'SELL': 0, 'HOLD': 0}
        confidence_stats = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}

        for signal in signals:
            signal_type = signal.get('signal', 'HOLD')
            confidence = signal.get('confidence', 'LOW')
            signal_stats[signal_type] = signal_stats.get(signal_type, 0) + 1
            confidence_stats[confidence] = confidence_stats.get(confidence, 0) + 1

        return jsonify({
            'signal_stats': signal_stats,
            'confidence_stats': confidence_stats,
            'total_signals': len(signals),
            'recent_signals': signals[-10:] if signals else []
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/profit_curve')
def get_profit_curve():
    """获取收益曲线数据"""
    try:
        return jsonify(deepseekok2.web_data['profit_curve'])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai_model_info')
def get_ai_model_info():
    """获取AI模型信息和连接状态"""
    try:
        return jsonify(deepseekok2.web_data['ai_model_info'])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/test_ai')
def test_ai_connection():
    """手动测试AI连接"""
    try:
        result = deepseekok2.test_ai_connection()
        return jsonify({
            'success': result,
            'info': deepseekok2.web_data['ai_model_info']
        })
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/api/time')
def get_time_info():
    """获取时间信息（北京时间和服务器时间）"""
    try:
        import pytz

        # 服务器时间（本地时间）
        server_time = datetime.now()

        # 北京时间 (UTC+8)
        beijing_tz = pytz.timezone('Asia/Shanghai')
        beijing_time = datetime.now(beijing_tz)

        return jsonify({
            'server_time': server_time.strftime('%Y-%m-%d %H:%M:%S'),
            'beijing_time': beijing_time.strftime('%Y-%m-%d %H:%M:%S'),
            'timestamp': int(server_time.timestamp())
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    """健康检查接口（供宝塔监控使用）"""
    try:
        last_update = deepseekok2.web_data.get('last_update')

        if last_update:
            last_time = datetime.strptime(last_update, '%Y-%m-%d %H:%M:%S')
            time_diff = (datetime.now() - last_time).total_seconds()

            if time_diff > max_no_response:
                return jsonify({
                    'status': 'unhealthy',
                    'reason': f'AI决策超时 {int(time_diff)}秒',
                    'last_update': last_update
                }), 503

        return jsonify({
            'status': 'healthy',
            'last_update': last_update,
            'uptime': int((datetime.now() - start_time).total_seconds())
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

# ==================== 交易机器人线程 ====================

def run_trading_bot():
    """在独立线程中运行交易机器人"""
    logger.info("交易机器人线程启动")

    # 初始化交易所（重试机制）
    max_setup_retries = 10
    setup_retry_count = 0

    while setup_retry_count < max_setup_retries:
        if deepseekok2.setup_exchange():
            logger.info("✅ 交易所初始化成功")
            break
        else:
            setup_retry_count += 1
            if setup_retry_count >= max_setup_retries:
                logger.error(f"❌ 交易所初始化失败，已达到最大重试次数({max_setup_retries})")
                logger.info("⚠️  交易机器人将定期重试连接...")
            else:
                wait_time = min(60 * setup_retry_count, 300)
                logger.warning(f"⏳ 交易所初始化失败，{wait_time}秒后重试 ({setup_retry_count}/{max_setup_retries})")
                time.sleep(wait_time)

    # 运行交易循环
    consecutive_errors = 0
    max_consecutive_errors = 5

    while True:
        try:
            # 如果交易所未初始化，尝试重新初始化
            if not hasattr(deepseekok2, 'exchange') or deepseekok2.exchange is None:
                logger.info("🔄 重新初始化交易所...")
                if deepseekok2.setup_exchange():
                    logger.info("✅ 交易所重新初始化成功")
                    consecutive_errors = 0
                else:
                    logger.warning("⚠️  交易所初始化失败，等待下次重试...")
                    time.sleep(300)
                    continue

            deepseekok2.trading_bot()
            consecutive_errors = 0
            time.sleep(60)

        except KeyboardInterrupt:
            logger.info("交易机器人收到停止信号")
            break
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"交易循环异常 (连续{consecutive_errors}次): {e}")

            if consecutive_errors >= max_consecutive_errors:
                logger.critical(f"连续错误达到{max_consecutive_errors}次，重置交易所连接")
                # 清空交易所对象，下次循环重新初始化
                deepseekok2.exchange = None
                consecutive_errors = 0

            wait_time = min(60 * consecutive_errors, 300)
            time.sleep(wait_time)

# ==================== 健康监控线程 ====================

def health_monitor():
    """健康监控线程，检测AI决策超时"""
    global trading_bot_thread

    logger.info("健康监控线程启动")
    restart_count = 0
    max_restarts = 5

    # 等待交易机器人初始化
    time.sleep(30)

    while True:
        try:
            time.sleep(health_check_interval)

            last_update = deepseekok2.web_data.get('last_update')

            if last_update:
                try:
                    last_time = datetime.strptime(last_update, '%Y-%m-%d %H:%M:%S')
                    time_diff = (datetime.now() - last_time).total_seconds()

                    if time_diff > max_no_response:
                        logger.warning(f"⚠️ AI决策超时 {int(time_diff)}秒，准备重启交易线程")
                        restart_count += 1

                        if restart_count >= max_restarts:
                            logger.critical(f"重启次数超过{max_restarts}次，停止监控")
                            break

                        # 重启交易机器人线程
                        if trading_bot_thread and trading_bot_thread.is_alive():
                            logger.info("等待旧线程结束...")
                            # 注意：Python线程不能强制终止，这里只是停止创建新线程
                            # 实际的重启需要交易机器人自己检测并退出

                        # 启动新线程
                        trading_bot_thread = threading.Thread(target=run_trading_bot, daemon=True)
                        trading_bot_thread.start()
                        logger.info("交易机器人线程已重启")

                        # 等待重启完成
                        time.sleep(60)
                    else:
                        logger.info(f"✓ 健康检查通过 (最后更新: {int(time_diff)}秒前)")
                        restart_count = 0  # 重置重启计数

                except ValueError as e:
                    logger.error(f"时间解析错误: {e}")
            else:
                logger.warning("未找到最后更新时间")

        except Exception as e:
            logger.error(f"健康监控异常: {e}")
            import traceback
            traceback.print_exc()

# ==================== 初始化 ====================

def initialize_data():
    """启动时立即初始化一次数据"""
    try:
        logger.info("正在初始化数据...")

        # 测试AI连接
        logger.info("测试AI模型连接...")
        deepseekok2.test_ai_connection()

        # 设置交易所
        try:
            deepseekok2.exchange.fetch_balance()
        except:
            if not deepseekok2.setup_exchange():
                logger.warning("交易所初始化失败")
                return

        # 获取初始数据
        price_data = deepseekok2.get_btc_ohlcv_enhanced()
        if price_data:
            try:
                balance = deepseekok2.exchange.fetch_balance()
                deepseekok2.web_data['account_info'] = {
                    'usdt_balance': balance['USDT']['free'],
                    'total_equity': balance['USDT']['total']
                }
            except Exception as e:
                logger.error(f"获取账户信息失败: {e}")

            deepseekok2.web_data['current_price'] = price_data['price']
            deepseekok2.web_data['current_position'] = deepseekok2.get_current_position()
            deepseekok2.web_data['kline_data'] = price_data['kline_data']
            deepseekok2.web_data['last_update'] = deepseekok2.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if deepseekok2.web_data['current_position']:
                deepseekok2.web_data['performance']['total_profit'] = deepseekok2.web_data['current_position'].get('unrealized_pnl', 0)

            logger.info(f"✅ 初始化完成 - BTC价格: ${price_data['price']:,.2f}")
        else:
            logger.warning("获取K线数据失败")

    except Exception as e:
        logger.error(f"初始化失败: {e}")
        import traceback
        traceback.print_exc()

# ==================== 主函数 ====================

# 记录启动时间
start_time = datetime.now()

def main():
    """主函数"""
    global trading_bot_thread, health_monitor_thread

    logger.info("=" * 60)
    logger.info("🚀 BTC交易机器人启动 (宝塔面板部署)")
    logger.info("=" * 60)
    logger.info(f"AI模型: {deepseekok2.AI_PROVIDER.upper()} ({deepseekok2.AI_MODEL})")
    logger.info(f"交易周期: {deepseekok2.TRADE_CONFIG['timeframe']}")
    logger.info(f"投入保证金: {deepseekok2.TRADE_CONFIG['margin_usdt']} USDT")
    logger.info(f"杠杆倍数: {deepseekok2.TRADE_CONFIG['leverage']}x")

    if deepseekok2.TRADE_CONFIG['test_mode']:
        logger.warning("⚠️ 当前为模拟模式，不会真实下单")
    else:
        logger.warning("🔴 实盘交易模式，请谨慎操作！")

    logger.info("=" * 60)

    # 初始化数据
    initialize_data()

    # 启动交易机器人线程
    logger.info("启动交易机器人线程...")
    trading_bot_thread = threading.Thread(target=run_trading_bot, daemon=True)
    trading_bot_thread.start()

    # 启动健康监控线程
    logger.info("启动健康监控线程...")
    health_monitor_thread = threading.Thread(target=health_monitor, daemon=True)
    health_monitor_thread.start()

    # 启动Web服务器
    PORT = int(os.getenv('PORT', 8080))
    logger.info("=" * 60)
    logger.info("🌐 Web管理界面启动")
    logger.info(f"📊 访问地址: http://localhost:{PORT}")
    logger.info("=" * 60)

    # 宝塔面板使用 0.0.0.0 监听所有接口
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n用户中断程序")
    except Exception as e:
        logger.critical(f"程序异常退出: {e}")
        import traceback
        traceback.print_exc()
