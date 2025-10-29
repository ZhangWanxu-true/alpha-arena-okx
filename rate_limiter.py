"""
OKX API 限流控制模块
基于 https://blog.csdn.net/gitblog_00153/article/details/152588607 的最佳实践

实现功能：
1. 令牌桶算法 - 平滑控制请求频率
2. 自适应限流 - 根据API响应动态调整
3. 请求监控 - 记录和分析API调用
4. 错误重试 - 智能重试机制
"""

import time
import logging
from datetime import datetime
from collections import deque
from typing import Optional, Dict, Any
import threading

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('api_requests.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TokenBucket:
    """令牌桶算法实现"""

    def __init__(self, capacity: int, refill_rate: float):
        """
        初始化令牌桶

        Args:
            capacity: 令牌桶容量
            refill_rate: 令牌生成速率(个/秒)
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self.lock = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        """
        消费令牌

        Args:
            tokens: 需要消费的令牌数量

        Returns:
            bool: 是否成功消费令牌
        """
        with self.lock:
            now = time.time()
            # 计算新生成的令牌数
            self.tokens += (now - self.last_refill) * self.refill_rate
            self.tokens = min(self.capacity, self.tokens)
            self.last_refill = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            else:
                # 计算需要等待的时间
                wait_time = (tokens - self.tokens) / self.refill_rate
                logger.info(f"⏳ 令牌不足，等待 {wait_time:.2f} 秒")
                time.sleep(wait_time)
                self.tokens = 0
                return True


class AdaptiveRateLimiter:
    """自适应限流控制器"""

    def __init__(self):
        # OKX API 限流规则
        self.limits = {
            'public': {'requests': 600, 'window': 60},  # 公共接口：600次/分钟
            'private': {'requests': 10, 'window': 2},  # 私有接口：10次/2秒
        }

        # 令牌桶配置
        self.buckets = {
            'public': TokenBucket(capacity=20, refill_rate=10),  # 20个令牌，每秒生成10个
            'private': TokenBucket(capacity=5, refill_rate=5),    # 5个令牌，每秒生成5个
        }

        # 请求统计
        self.request_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'rate_limited_requests': 0,
            'last_reset': time.time()
        }

        # 错误重试配置
        self.retry_config = {
            'max_retries': 3,
            'base_delay': 1,
            'max_delay': 60,
            'backoff_factor': 2
        }

    def get_bucket_type(self, endpoint: str) -> str:
        """根据端点判断使用哪个令牌桶"""
        if any(keyword in endpoint.lower() for keyword in ['balance', 'position', 'order', 'trade']):
            return 'private'
        return 'public'

    def wait_for_token(self, endpoint: str) -> None:
        """等待令牌可用"""
        bucket_type = self.get_bucket_type(endpoint)
        bucket = self.buckets[bucket_type]

        if not bucket.consume():
            logger.warning(f"⚠️ {bucket_type} 令牌桶消费失败")

    def handle_rate_limit_error(self, error: Exception, endpoint: str) -> int:
        """
        处理限流错误

        Args:
            error: 限流错误
            endpoint: API端点

        Returns:
            int: 建议等待时间（秒）
        """
        self.request_stats['rate_limited_requests'] += 1

        # 解析错误信息
        error_msg = str(error).lower()

        if '429' in error_msg or 'too many requests' in error_msg:
            # 标准限流错误
            wait_time = 60  # 默认等待60秒
            logger.warning(f"🚫 API限流: {endpoint}, 等待 {wait_time} 秒")
            return wait_time

        elif '50001' in error_msg or 'rate limit exceeded' in error_msg:
            # OKX特定限流错误
            wait_time = 2  # OKX通常2秒后恢复
            logger.warning(f"🚫 OKX限流: {endpoint}, 等待 {wait_time} 秒")
            return wait_time

        else:
            # 其他错误，使用指数退避
            wait_time = min(
                self.retry_config['base_delay'] * self.retry_config['backoff_factor'],
                self.retry_config['max_delay']
            )
            logger.warning(f"⚠️ API错误: {endpoint}, 等待 {wait_time} 秒")
            return wait_time

    def adaptive_request(self, func, *args, **kwargs):
        """
        自适应请求包装器

        Args:
            func: 要调用的API函数
            *args: 函数参数
            **kwargs: 函数关键字参数

        Returns:
            API响应结果
        """
        endpoint = getattr(func, '__name__', 'unknown')
        retry_count = 0

        while retry_count < self.retry_config['max_retries']:
            try:
                # 等待令牌
                self.wait_for_token(endpoint)

                # 记录请求开始
                start_time = time.time()
                self.request_stats['total_requests'] += 1

                # 执行请求
                result = func(*args, **kwargs)

                # 记录成功请求
                duration = time.time() - start_time
                self.request_stats['successful_requests'] += 1

                logger.info(f"✅ {endpoint} 成功 ({duration:.2f}s)")
                return result

            except Exception as e:
                retry_count += 1
                error_msg = str(e)

                # 检查是否是限流错误
                if any(keyword in error_msg.lower() for keyword in ['429', '50001', 'rate limit', 'too many requests']):
                    wait_time = self.handle_rate_limit_error(e, endpoint)
                    logger.error(f"❌ {endpoint} 限流 (重试 {retry_count}/{self.retry_config['max_retries']})")

                    if retry_count < self.retry_config['max_retries']:
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"🔴 {endpoint} 达到最大重试次数")
                        raise
                else:
                    # 非限流错误，直接抛出
                    logger.error(f"❌ {endpoint} 错误: {error_msg}")
                    raise

        raise Exception(f"达到最大重试次数: {endpoint}")

    def get_stats(self) -> Dict[str, Any]:
        """获取请求统计信息"""
        now = time.time()
        time_window = now - self.request_stats['last_reset']

        return {
            'total_requests': self.request_stats['total_requests'],
            'successful_requests': self.request_stats['successful_requests'],
            'rate_limited_requests': self.request_stats['rate_limited_requests'],
            'success_rate': (
                self.request_stats['successful_requests'] / self.request_stats['total_requests'] * 100
                if self.request_stats['total_requests'] > 0 else 0
            ),
            'requests_per_minute': (
                self.request_stats['total_requests'] / time_window * 60
                if time_window > 0 else 0
            ),
            'time_window_minutes': time_window / 60
        }

    def reset_stats(self) -> None:
        """重置统计信息"""
        self.request_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'rate_limited_requests': 0,
            'last_reset': time.time()
        }
        logger.info("📊 统计信息已重置")


# 全局限流器实例
rate_limiter = AdaptiveRateLimiter()


def monitored_request(func):
    """
    请求监控装饰器

    使用示例:
    @monitored_request
    def fetch_balance():
        return exchange.fetch_balance()
    """
    def wrapper(*args, **kwargs):
        return rate_limiter.adaptive_request(func, *args, **kwargs)
    return wrapper


def get_rate_limit_stats() -> Dict[str, Any]:
    """获取限流统计信息"""
    return rate_limiter.get_stats()


def reset_rate_limit_stats() -> None:
    """重置限流统计信息"""
    rate_limiter.reset_stats()


# 使用示例
if __name__ == "__main__":
    # 测试令牌桶
    bucket = TokenBucket(capacity=5, refill_rate=2)

    print("测试令牌桶算法:")
    for i in range(10):
        if bucket.consume():
            print(f"请求 {i+1}: 成功")
        else:
            print(f"请求 {i+1}: 等待令牌")

    # 测试自适应限流
    print("\n测试自适应限流:")
    stats = get_rate_limit_stats()
    print(f"统计信息: {stats}")
