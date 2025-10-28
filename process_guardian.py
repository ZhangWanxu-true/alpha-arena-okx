"""
进程守护机制 - 监控交易机器人健康状态
"""
import os
import time
import psutil
import subprocess
import sys
from datetime import datetime, timedelta
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('guardian.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ProcessGuardian:
    def __init__(self, 
                 script_name='web_server.py',
                 check_interval=60,  # 每60秒检查一次
                 max_no_response=300,  # 5分钟无响应则重启
                 max_restarts=5):  # 最大重启次数
        
        self.script_name = script_name
        self.check_interval = check_interval
        self.max_no_response = max_no_response
        self.max_restarts = max_restarts
        self.restart_count = 0
        self.process = None
        self.last_restart_time = None
        
    def start_process(self):
        """启动被监控的进程"""
        try:
            # 确定Python解释器路径
            if os.path.exists('venv/Scripts/python.exe'):
                python_exe = 'venv/Scripts/python.exe'
            elif os.path.exists('venv/bin/python'):
                python_exe = 'venv/bin/python'
            else:
                python_exe = sys.executable
            
            logger.info(f"启动进程: {python_exe} {self.script_name}")
            
            # 启动进程
            self.process = subprocess.Popen(
                [python_exe, self.script_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            self.last_restart_time = datetime.now()
            logger.info(f"进程启动成功，PID: {self.process.pid}")
            return True
            
        except Exception as e:
            logger.error(f"启动进程失败: {e}")
            return False
    
    def is_process_alive(self):
        """检查进程是否存活"""
        if self.process is None:
            return False
        
        # 检查进程是否还在运行
        if self.process.poll() is not None:
            logger.warning(f"进程已退出，退出码: {self.process.returncode}")
            return False
        
        # 检查进程是否真的存在
        try:
            proc = psutil.Process(self.process.pid)
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
    
    def check_health(self):
        """检查应用健康状态"""
        try:
            import requests
            
            # 检查Web服务是否响应
            response = requests.get('http://localhost:8080/api/dashboard', timeout=10)
            if response.status_code != 200:
                logger.warning(f"健康检查失败: HTTP {response.status_code}")
                return False
            
            data = response.json()
            
            # 检查最后更新时间
            last_update = data.get('last_update')
            if last_update:
                try:
                    last_time = datetime.strptime(last_update, '%Y-%m-%d %H:%M:%S')
                    time_diff = (datetime.now() - last_time).total_seconds()
                    
                    if time_diff > self.max_no_response:
                        logger.warning(f"AI决策超时无响应: {time_diff}秒")
                        return False
                except ValueError:
                    pass
            
            logger.info("健康检查通过 ✓")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"健康检查请求失败: {e}")
            return False
        except Exception as e:
            logger.error(f"健康检查异常: {e}")
            return False
    
    def restart_process(self):
        """重启进程"""
        self.restart_count += 1
        logger.warning(f"正在重启进程 (第{self.restart_count}次)...")
        
        # 停止现有进程
        self.stop_process()
        
        # 等待一段时间
        time.sleep(5)
        
        # 启动新进程
        if self.start_process():
            logger.info("进程重启成功")
            return True
        else:
            logger.error("进程重启失败")
            return False
    
    def stop_process(self):
        """停止进程"""
        if self.process is None:
            return
        
        try:
            logger.info(f"正在停止进程 PID: {self.process.pid}")
            
            # 首先尝试优雅地终止
            self.process.terminate()
            
            try:
                self.process.wait(timeout=10)
                logger.info("进程已优雅终止")
            except subprocess.TimeoutExpired:
                # 如果超时，强制杀死
                logger.warning("优雅终止超时，强制杀死进程")
                self.process.kill()
                self.process.wait()
                logger.info("进程已强制终止")
                
        except Exception as e:
            logger.error(f"停止进程失败: {e}")
        
        finally:
            self.process = None
    
    def run(self):
        """运行守护进程"""
        logger.info("=" * 60)
        logger.info("进程守护机制启动")
        logger.info(f"监控脚本: {self.script_name}")
        logger.info(f"检查间隔: {self.check_interval}秒")
        logger.info(f"超时阈值: {self.max_no_response}秒")
        logger.info("=" * 60)
        
        # 初始启动
        if not self.start_process():
            logger.error("初始启动失败，退出")
            return
        
        # 等待服务启动
        logger.info("等待服务启动...")
        time.sleep(15)
        
        # 监控循环
        consecutive_failures = 0
        
        while True:
            try:
                time.sleep(self.check_interval)
                
                # 检查进程是否存活
                if not self.is_process_alive():
                    logger.error("进程已死亡")
                    consecutive_failures += 1
                    
                    if self.restart_count >= self.max_restarts:
                        logger.critical(f"重启次数超过限制({self.max_restarts})，停止守护")
                        break
                    
                    if not self.restart_process():
                        consecutive_failures += 1
                        if consecutive_failures >= 3:
                            logger.critical("连续重启失败3次，停止守护")
                            break
                    else:
                        consecutive_failures = 0
                        time.sleep(15)  # 等待服务启动
                    continue
                
                # 检查应用健康状态
                if not self.check_health():
                    consecutive_failures += 1
                    logger.warning(f"健康检查失败 (连续{consecutive_failures}次)")
                    
                    # 连续失败3次才重启
                    if consecutive_failures >= 3:
                        logger.error("连续健康检查失败3次，触发重启")
                        
                        if self.restart_count >= self.max_restarts:
                            logger.critical(f"重启次数超过限制({self.max_restarts})，停止守护")
                            break
                        
                        if not self.restart_process():
                            logger.critical("重启失败，停止守护")
                            break
                        
                        consecutive_failures = 0
                        time.sleep(15)  # 等待服务启动
                else:
                    consecutive_failures = 0
                    
                    # 每小时重置重启计数
                    if self.last_restart_time and \
                       (datetime.now() - self.last_restart_time).total_seconds() > 3600:
                        self.restart_count = 0
                        logger.info("重启计数已重置")
                
            except KeyboardInterrupt:
                logger.info("收到中断信号，正在停止...")
                break
            except Exception as e:
                logger.error(f"守护循环异常: {e}")
                import traceback
                traceback.print_exc()
        
        # 清理
        self.stop_process()
        logger.info("进程守护已停止")

def main():
    """主函数"""
    guardian = ProcessGuardian(
        script_name='web_server.py',
        check_interval=60,  # 每分钟检查一次
        max_no_response=300,  # 5分钟无响应则重启
        max_restarts=10  # 最多重启10次
    )
    
    try:
        guardian.run()
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.critical(f"守护进程异常退出: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()

