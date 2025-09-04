#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPTV搜索器接口定义
提供通用的搜索器抽象基类，支持多种站点的扩展
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class IPTVChannel:
    """IPTV频道数据类"""
    name: str                    # 频道名称
    url: str                     # 播放链接
    resolution: str = "未知"      # 分辨率
    quality: str = "标清"        # 画质描述
    source: str = "未知"         # 来源站点
    
    def __post_init__(self):
        """数据验证和标准化"""
        if not self.name or not self.url:
            raise ValueError("频道名称和链接不能为空")
        
        # 标准化分辨率格式
        if self.resolution and self.resolution != "未知":
            # 提取数字部分作为高度
            import re
            match = re.search(r'(\d+)', self.resolution)
            if match:
                height = int(match.group(1))
                if height >= 1080:
                    self.quality = "高清"
                elif height >= 720:
                    self.quality = "标清"
                else:
                    self.quality = "普清"


@dataclass 
class SearchConfig:
    """搜索配置类"""
    max_results: int = 10           # 最大结果数
    timeout: int = 20              # 超时时间(秒) - 增加到20秒以适应tonkiang.us的响应时间
    min_resolution: int = 0        # 最小分辨率要求
    enable_validation: bool = True  # 是否启用链接验证
    enable_cache: bool = True      # 是否启用缓存
    max_pages: int = 2            # 最大搜索页数 - 限制为2页
    concurrent_workers: int = 16   # 并发线程数 - 从6增加到16
    min_valid_links: int = 3       # 每个频道最少有效链接数 - 从5减少到3


class BaseIPTVSearcher(ABC):
    """IPTV搜索器抽象基类"""
    
    def __init__(self, config: SearchConfig = None):
        """
        初始化搜索器
        
        Args:
            config: 搜索配置，如果为None则使用默认配置
        """
        self.config = config if config else SearchConfig()
        # 子类应该在调用super().__init__()前设置这些属性
        if not hasattr(self, 'site_name'):
            self.site_name = "未知站点"
        if not hasattr(self, 'base_url'):
            self.base_url = ""
        
        self._search_cache = {} if self.config.enable_cache else None
        
        # 子类需要设置的属性
        self._setup_session()
        
    @abstractmethod
    def _setup_session(self):
        """设置HTTP会话 - 子类必须实现"""
        pass
    
    @abstractmethod
    def _send_search_request(self, keyword: str, page: int = 1) -> str:
        """
        发送搜索请求 - 子类必须实现
        
        Args:
            keyword: 搜索关键词
            page: 页码
            
        Returns:
            str: 响应内容
        """
        pass
    
    @abstractmethod
    def _parse_search_results(self, html_content: str, keyword: str) -> List[IPTVChannel]:
        """
        解析搜索结果 - 子类必须实现
        
        Args:
            html_content: HTML响应内容
            keyword: 搜索关键词
            
        Returns:
            List[IPTVChannel]: 解析出的频道列表
        """
        pass
    
    @abstractmethod
    def _validate_link(self, channel: IPTVChannel) -> bool:
        """
        验证链接有效性 - 子类必须实现
        
        Args:
            channel: 频道对象
            
        Returns:
            bool: 链接是否有效
        """
        pass
    
    def _validate_links_concurrent(self, channels: List[IPTVChannel], remaining_needed: int = None) -> List[IPTVChannel]:
        """
        并发验证多个链接的有效性，达到目标数量后停止
        
        Args:
            channels: 待验证的频道列表
            remaining_needed: 还需要找到的有效链接数，如果为None则使用默认的min_valid_links
            
        Returns:
            List[IPTVChannel]: 验证通过的频道列表
        """
        if not self.config.enable_validation or not channels:
            needed = remaining_needed if remaining_needed is not None else self.config.min_valid_links
            return channels[:needed]  # 如果不验证，也返回限定数量
        
        valid_channels = []
        # 增加并发数，提高验证效率
        max_workers = min(self.config.concurrent_workers, len(channels), 16)  # 从8增加到16
        target_count = remaining_needed if remaining_needed is not None else self.config.min_valid_links
        
        logger.info(f"[{self.site_name}] 开始并发验证 {len(channels)} 个链接 (目标: {target_count} 个有效链接)")
        
        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            # 提交验证任务
            future_to_channel = {
                executor.submit(self._validate_link, channel): channel
                for channel in channels
            }
            
            # 收集验证结果，达到目标数量后停止
            completed_count = 0
            start_time = time.time()
            should_exit = False
            
            for future in as_completed(future_to_channel, timeout=12):  # 增加总超时到12秒
                if should_exit:
                    break  # 如果已标记退出，跳出循环
                    
                channel = future_to_channel[future]
                completed_count += 1
                
                try:
                    is_valid = future.result(timeout=8)  # 单个任务超时8秒，给质量验证足够时间
                    if is_valid:
                        valid_channels.append(channel)
                        logger.debug(f"[{self.site_name}] 验证通过: {channel.name} - {channel.url[:50]}...")
                        
                        # 检查是否达到目标数量
                        if len(valid_channels) >= target_count:
                            should_exit = True  # 标记需要退出，但继续处理当前批次
                            
                except Exception as e:
                    logger.debug(f"[{self.site_name}] 验证异常 {channel.url}: {e}")
                
                # 每3个显示一次进度
                if completed_count % 3 == 0:
                    elapsed = time.time() - start_time
                    logger.info(f"[{self.site_name}] 验证进度: {len(valid_channels)}个有效/{completed_count}个已验证 ({elapsed:.1f}s)")
                
                # 超时保护 - 如果超过10秒还没完成，直接返回已找到的结果
                if time.time() - start_time > 10:
                    logger.info(f"[{self.site_name}] 验证超时({time.time() - start_time:.1f}s)，返回已找到的 {len(valid_channels)} 个有效链接")
                    should_exit = True
                    break
                    
                # 如果达到目标且当前批次处理完毕，退出
                if should_exit and len(valid_channels) >= target_count:
                    break
        
        except Exception as e:
            logger.warning(f"[{self.site_name}] 并发验证超时或异常: {e}")
            # 如果并发验证失败，返回已经验证的结果
        finally:
            # 正确关闭executor，等待已提交的任务完成但不等太久
            try:
                executor.shutdown(wait=True)
                # 等待最多2秒让正在执行的任务完成
                import concurrent.futures
                if not executor._threads:  # 如果没有线程，直接继续
                    pass
            except:
                executor.shutdown(wait=False)
        
        # 统一的结果日志
        result_count = len(valid_channels)
        if result_count >= target_count:
            logger.info(f"[{self.site_name}] 已找到足够的有效链接，提前结束验证")
            status = "达标"
        else:
            status = f"不足({result_count}/{target_count})"
            
        logger.info(f"[{self.site_name}] 验证完成: {result_count} 个有效链接 [{status}]")
        
        return valid_channels
    
    def search_channels(self, keyword: str) -> List[IPTVChannel]:
        """
        搜索频道 - 通用接口
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            List[IPTVChannel]: 搜索结果
        """
        # 检查缓存
        if self._search_cache and keyword in self._search_cache:
            logger.info(f"[{self.site_name}] 使用缓存结果: {keyword}")
            return self._search_cache[keyword][:self.config.max_results]
        
        logger.info(f"[{self.site_name}] 开始搜索: {keyword}")
        
        all_channels = []
        page = 1
        
        # 分页搜索
        while len(all_channels) < self.config.max_results and page <= self.config.max_pages:
            try:
                logger.info(f"[{self.site_name}] 搜索第 {page} 页...")
                
                # 发送搜索请求
                html_content = self._send_search_request(keyword, page)
                
                # 解析结果
                page_channels = self._parse_search_results(html_content, keyword)
                
                if not page_channels:
                    logger.info(f"[{self.site_name}] 第 {page} 页无结果，停止搜索")
                    break
                
                # 链接验证 - 改为并发验证
                if self.config.enable_validation:
                    # 计算还需要多少个有效链接
                    remaining_needed = max(0, self.config.min_valid_links - len(all_channels))
                    
                    if remaining_needed > 0:
                        valid_channels = self._validate_links_concurrent(page_channels, remaining_needed)
                        logger.info(f"[{self.site_name}] 第 {page} 页: {len(page_channels)} 个链接，{len(valid_channels)} 个有效")
                        all_channels.extend(valid_channels)
                        
                        # 如果已达到最少有效链接数要求，提前结束搜索
                        if len(all_channels) >= self.config.min_valid_links:
                            logger.info(f"[{self.site_name}] 已达到目标链接数({len(all_channels)}/{self.config.min_valid_links})，停止搜索")
                            break
                    else:
                        # 如果已经足够了，跳过验证
                        logger.info(f"[{self.site_name}] 已有足够链接({len(all_channels)}/{self.config.min_valid_links})，跳过第 {page} 页验证")
                        break
                else:
                    all_channels.extend(page_channels)
                    
                page += 1
                
            except Exception as e:
                logger.error(f"[{self.site_name}] 第 {page} 页搜索失败: {e}")
                break
        
        # 去重
        unique_channels = []
        seen_urls = set()
        for channel in all_channels:
            if channel.url not in seen_urls:
                seen_urls.add(channel.url)
                unique_channels.append(channel)
        
        # 限制数量
        final_channels = unique_channels[:self.config.max_results]
        
        # 检查搜索结果
        if len(final_channels) == 0:
            logger.warning(f"[{self.site_name}] 搜索完成: {keyword}, 未找到任何有效链接，将跳过该频道")
        elif len(final_channels) < self.config.min_valid_links:
            logger.info(f"[{self.site_name}] 搜索完成: {keyword}, 找到 {len(final_channels)} 个有效链接（目标 {self.config.min_valid_links} 个），保留所有结果")
        else:
            logger.info(f"[{self.site_name}] 搜索完成: {keyword}, 找到 {len(final_channels)} 个有效频道 [达标]")
        
        # 缓存结果
        if self._search_cache:
            self._search_cache[keyword] = final_channels
        
        return final_channels
    
    def get_site_info(self) -> Dict[str, str]:
        """获取站点信息"""
        return {
            "name": self.site_name,
            "url": self.base_url,
            "description": f"{self.site_name} IPTV搜索器"
        }
    
    def clear_cache(self):
        """清空缓存"""
        if self._search_cache:
            self._search_cache.clear()
            logger.info(f"[{self.site_name}] 缓存已清空")


class SearcherFactory:
    """搜索器工厂类"""
    
    _searchers = {}
    
    @classmethod
    def register_searcher(cls, name: str, searcher_class):
        """
        注册搜索器
        
        Args:
            name: 搜索器名称
            searcher_class: 搜索器类
        """
        cls._searchers[name] = searcher_class
        logger.info(f"搜索器已注册: {name}")
    
    @classmethod
    def create_searcher(cls, name: str, config: SearchConfig = None) -> BaseIPTVSearcher:
        """
        创建搜索器实例
        
        Args:
            name: 搜索器名称
            config: 搜索配置
            
        Returns:
            BaseIPTVSearcher: 搜索器实例
        """
        if name not in cls._searchers:
            raise ValueError(f"未找到搜索器: {name}，已注册的搜索器: {list(cls._searchers.keys())}")
        
        searcher_class = cls._searchers[name]
        return searcher_class(config)
    
    @classmethod
    def list_searchers(cls) -> List[str]:
        """获取已注册的搜索器列表"""
        return list(cls._searchers.keys())


# 导出主要类和函数
__all__ = [
    'IPTVChannel',
    'SearchConfig', 
    'BaseIPTVSearcher',
    'SearcherFactory'
]
