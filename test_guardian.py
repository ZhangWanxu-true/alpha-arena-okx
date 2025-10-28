"""
测试进程守护功能
"""
import time
import sys
import requests
from datetime import datetime

def test_web_health():
    """测试Web服务健康检查"""
    print("=" * 60)
    print("测试1: Web服务健康检查")
    print("=" * 60)
    
    try:
        response = requests.get('http://localhost:8080/api/dashboard', timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Web服务响应正常")
            print(f"   状态码: {response.status_code}")
            print(f"   最后更新: {data.get('last_update', 'N/A')}")
            print(f"   当前价格: ${data.get('current_price', 0):,.2f}")
            return True
        else:
            print(f"❌ Web服务响应异常: HTTP {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到Web服务")
        print("   请确保web_server.py正在运行")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_ai_status():
    """测试AI模型状态"""
    print("\n" + "=" * 60)
    print("测试2: AI模型连接状态")
    print("=" * 60)
    
    try:
        response = requests.get('http://localhost:8080/api/ai_model_info', timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            status = data.get('status', 'unknown')
            provider = data.get('provider', 'N/A')
            model = data.get('model', 'N/A')
            last_check = data.get('last_check', 'N/A')
            error = data.get('error_message')
            
            print(f"AI提供商: {provider.upper()}")
            print(f"AI模型: {model}")
            print(f"连接状态: {status}")
            print(f"最后检查: {last_check}")
            
            if status == 'connected':
                print("✅ AI模型连接正常")
                return True
            else:
                print(f"❌ AI模型连接失败")
                if error:
                    print(f"   错误信息: {error}")
                return False
        else:
            print(f"❌ 无法获取AI状态: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_data_freshness():
    """测试数据新鲜度"""
    print("\n" + "=" * 60)
    print("测试3: 数据新鲜度检查")
    print("=" * 60)
    
    try:
        response = requests.get('http://localhost:8080/api/dashboard', timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            last_update = data.get('last_update')
            
            if last_update:
                try:
                    last_time = datetime.strptime(last_update, '%Y-%m-%d %H:%M:%S')
                    now = datetime.now()
                    time_diff = (now - last_time).total_seconds()
                    
                    print(f"最后更新时间: {last_update}")
                    print(f"距离现在: {int(time_diff)}秒")
                    
                    if time_diff < 300:  # 5分钟内
                        print("✅ 数据新鲜（< 5分钟）")
                        return True
                    elif time_diff < 900:  # 15分钟内
                        print("⚠️ 数据稍旧（5-15分钟）")
                        return True
                    else:
                        print(f"❌ 数据过期（> 15分钟）")
                        print("   可能原因: AI决策超时或进程挂起")
                        return False
                        
                except ValueError as e:
                    print(f"❌ 时间格式错误: {e}")
                    return False
            else:
                print("⚠️ 未找到更新时间")
                return False
        else:
            print(f"❌ 无法获取数据: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_ai_decisions():
    """测试AI决策历史"""
    print("\n" + "=" * 60)
    print("测试4: AI决策历史")
    print("=" * 60)
    
    try:
        response = requests.get('http://localhost:8080/api/ai_decisions', timeout=10)
        
        if response.status_code == 200:
            decisions = response.json()
            
            if decisions:
                print(f"决策记录数量: {len(decisions)}")
                
                # 显示最近3条决策
                print("\n最近的决策:")
                for i, decision in enumerate(decisions[-3:], 1):
                    print(f"\n决策 {i}:")
                    print(f"  时间: {decision.get('timestamp', 'N/A')}")
                    print(f"  信号: {decision.get('signal', 'N/A')}")
                    print(f"  信心: {decision.get('confidence', 'N/A')}")
                    print(f"  理由: {decision.get('reason', 'N/A')[:50]}...")
                
                print("\n✅ AI决策正常")
                return True
            else:
                print("⚠️ 暂无决策记录")
                print("   可能原因: 尚未到达交易时间点（每15分钟整点）")
                return True
        else:
            print(f"❌ 无法获取决策历史: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("🔍 进程守护功能测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("注意事项:")
    print("  1. 请确保web_server.py已经启动")
    print("  2. 测试需要访问 http://localhost:8080")
    print("  3. 部分测试可能需要等待数据生成")
    print()
    
    input("按回车键开始测试...")
    
    # 运行所有测试
    results = []
    
    results.append(("Web服务健康检查", test_web_health()))
    time.sleep(1)
    
    results.append(("AI模型连接状态", test_ai_status()))
    time.sleep(1)
    
    results.append(("数据新鲜度检查", test_data_freshness()))
    time.sleep(1)
    
    results.append(("AI决策历史", test_ai_decisions()))
    
    # 显示测试结果汇总
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print()
    print(f"总计: {len(results)} 项测试")
    print(f"通过: {passed} 项")
    print(f"失败: {failed} 项")
    
    if failed == 0:
        print("\n🎉 所有测试通过！进程守护功能正常")
        print("\n建议:")
        print("  - 可以启动守护进程: start_guardian.bat")
        print("  - 守护进程将自动监控和恢复异常")
    else:
        print("\n⚠️ 部分测试失败，请检查:")
        print("  1. web_server.py 是否正在运行")
        print("  2. .env 配置文件是否正确")
        print("  3. API密钥是否有效")
        print("  4. 网络连接是否正常")
    
    print("\n" + "=" * 60)
    return failed == 0

if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 测试异常退出: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

