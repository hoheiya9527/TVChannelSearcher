#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tonkiang.us IPTV搜索器实现
专门针对 https://tonkiang.us/ 站点的搜索逻辑
"""

import requests
import re
import time
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging

# 导入搜索器接口
from searcher_interface import BaseIPTVSearcher, IPTVChannel, SearchConfig, SearcherFactory

# 配置日志 - 减少urllib3的警告信息
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


class TonkiangSearcher(BaseIPTVSearcher):
    """Tonkiang.us 搜索器实现"""
    
    def __init__(self, config: SearchConfig = None):
        """
        初始化 Tonkiang 搜索器
        
        Args:
            config: 搜索配置
        """
        # 先设置站点信息，再调用父类构造函数
        self.site_name = "Tonkiang.us"
        self.base_url = "https://tonkiang.us"
        super().__init__(config)
    
    def _setup_session(self):
        """设置HTTP会话"""
        self.session = requests.Session()
        
        # 配置连接池适配器 - 解决连接池溢出问题
        retry_strategy = Retry(
            total=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"],
            backoff_factor=1
        )
        
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=retry_strategy,
            pool_block=False
        )
        
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # 设置请求头模拟浏览器
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Referer': f'{self.base_url}/',
        })
        
        logger.info(f"[{self.site_name}] HTTP会话已配置")
    
    def _send_search_request(self, keyword: str, page: int = 1) -> str:
        """
        发送搜索请求到 Tonkiang.us
        
        Args:
            keyword: 搜索关键词
            page: 页码 (Tonkiang.us 可能不支持分页，但保留接口一致性)
            
        Returns:
            str: 响应HTML内容
        """
        search_url = f"{self.base_url}/"
        
        # Tonkiang.us 的特殊搜索参数 (注意：seerch 是故意的拼写)
        search_data = {'seerch': keyword}
        
        try:
            response = self.session.post(
                search_url, 
                data=search_data, 
                timeout=self.config.timeout
            )
            response.raise_for_status()
            
            if response.status_code == 200:
                logger.info(f"[{self.site_name}] 搜索请求成功: {keyword}")
                return response.text
            else:
                logger.warning(f"[{self.site_name}] 搜索请求失败，状态码: {response.status_code}")
                return ""
                
        except Exception as e:
            logger.error(f"[{self.site_name}] 搜索请求异常: {e}")
            return ""
    
    def _parse_search_results(self, html_content: str, keyword: str) -> List[IPTVChannel]:
        """
        解析 Tonkiang.us 的搜索结果
        
        Args:
            html_content: HTML响应内容
            keyword: 搜索关键词
            
        Returns:
            List[IPTVChannel]: 解析出的频道列表
        """
        channels = []
        
        try:
            # 使用正则表达式提取链接和分辨率信息
            patterns = [
                # 匹配 m3u8 链接模式
                r'(https?://[^\s<>"\']+\.m3u8[^\s<>"\']*)',
                # 匹配 ts 流链接
                r'(https?://[^\s<>"\']+/[^\s<>"\']*\.ts[^\s<>"\']*)',
                # 匹配其他流媒体链接
                r'(https?://[^\s<>"\']+:[0-9]+/[^\s<>"\']*)',
                # RTMP链接
                r'(rtmp://[^\s<>"\']+)',
                # RTSP链接  
                r'(rtsp://[^\s<>"\']+)'
            ]
            
            found_urls = set()
            
            for pattern in patterns:
                matches = re.finditer(pattern, html_content, re.IGNORECASE)
                for match in matches:
                    url = match.group(1).strip()
                    
                    # 清理URL (移除HTML标签残留)
                    url = re.sub(r'[<>"\'].*$', '', url)
                    
                    # 基本URL验证
                    if self._is_valid_stream_url(url):
                        found_urls.add(url)
            
            # 创建频道对象
            for url in found_urls:
                resolution = self._extract_resolution_from_url(url)
                
                channel = IPTVChannel(
                    name=keyword,
                    url=url,
                    resolution=resolution,
                    source=self.site_name
                )
                
                channels.append(channel)
            
            logger.info(f"[{self.site_name}] 解析完成: {keyword}, 找到 {len(channels)} 个链接")
            
        except Exception as e:
            logger.error(f"[{self.site_name}] 解析结果失败: {e}")
        
        return channels
    
    def _is_valid_stream_url(self, url: str) -> bool:
        """
        验证是否为有效的流媒体URL
        
        Args:
            url: 待验证的URL
            
        Returns:
            bool: 是否有效
        """
        if not url or len(url) < 10:
            return False
        
        # 检查协议
        if not re.match(r'^(https?|rtmp|rtsp)://', url, re.IGNORECASE):
            return False
        
        # 检查是否包含流媒体格式
        stream_formats = ['.m3u8', '.ts', '.flv', '.mp4', '.mkv']
        has_format = any(fmt in url.lower() for fmt in stream_formats)
        
        # 或者包含端口号 (通常是IPTV服务)
        has_port = re.search(r':\d{2,5}/', url)
        
        return has_format or has_port
    
    def _extract_resolution_from_url(self, url: str) -> str:
        """
        从URL中提取分辨率信息
        
        Args:
            url: 流媒体URL
            
        Returns:
            str: 分辨率字符串
        """
        # 常见分辨率模式
        resolution_patterns = [
            r'(\d{3,4})[px_-]?(\d{3,4})',  # 1920x1080, 1920_1080, 1920-1080
            r'(\d{3,4})p',                  # 1080p, 720p
            r'(\d{3,4})P',                  # 1080P
        ]
        
        for pattern in resolution_patterns:
            match = re.search(pattern, url)
            if match:
                if len(match.groups()) == 2:
                    width, height = match.groups()
                    return f"{width}x{height}"
                else:
                    height = match.group(1)
                    return f"{height}p"
        
        return "未知"
    
    def _validate_link(self, channel: IPTVChannel) -> bool:
        """
        验证链接的有效性
        
        Args:
            channel: 频道对象
            
        Returns:
            bool: 链接是否有效
        """
        if not self.config.enable_validation:
            return True
        
        try:
            # 使用HEAD请求检查链接可达性 - 减少超时时间
            response = self.session.head(channel.url, timeout=3, allow_redirects=True)
            
            # 检查状态码
            if response.status_code in [200, 206, 302, 301]:
                # 检查分辨率要求
                if self.config.min_resolution > 0:
                    resolution_height = self._get_resolution_height(channel.resolution)
                    if resolution_height < self.config.min_resolution:
                        return False
                
                return True
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 链接验证失败 {channel.url}: {e}")
        
        return False
    
    def _get_resolution_height(self, resolution: str) -> int:
        """
        从分辨率字符串提取高度数值
        
        Args:
            resolution: 分辨率字符串
            
        Returns:
            int: 高度像素值
        """
        if not resolution or resolution == "未知":
            return 0
        
        # 提取数字
        numbers = re.findall(r'\d+', resolution)
        if numbers:
            # 通常第二个数字是高度，如果只有一个数字则认为是高度
            if len(numbers) >= 2:
                return int(numbers[1])  # width x height
            else:
                return int(numbers[0])  # height only (like 1080p)
        
        return 0


# 注册搜索器到工厂
SearcherFactory.register_searcher("tonkiang", TonkiangSearcher)

# 快速创建函数
def create_tonkiang_searcher(config: SearchConfig = None) -> TonkiangSearcher:
    """
    快速创建 Tonkiang 搜索器
    
    Args:
        config: 搜索配置
        
    Returns:
        TonkiangSearcher: 搜索器实例
    """
    return TonkiangSearcher(config)


if __name__ == "__main__":
    # 测试代码
    print("=" * 50)
    print("Tonkiang.us 搜索器测试")
    print("=" * 50)
    
    # 创建配置
    config = SearchConfig(
        max_results=5,
        timeout=15,
        min_resolution=720,
        enable_validation=True,
        enable_cache=True
    )
    
    # 创建搜索器
    searcher = create_tonkiang_searcher(config)
    
    # 测试搜索
    print(f"搜索器信息: {searcher.get_site_info()}")
    
    test_keywords = ["CCTV1", "湖南卫视"]
    
    for keyword in test_keywords:
        print(f"\n测试搜索: {keyword}")
        channels = searcher.search_channels(keyword)
        
        if channels:
            print(f"找到 {len(channels)} 个频道:")
            for i, ch in enumerate(channels[:3], 1):  # 只显示前3个
                print(f"  {i}. {ch.name} - {ch.resolution} - {ch.url[:60]}...")
        else:
            print("  未找到结果")
    
    print(f"\n缓存状态: {len(searcher._search_cache)} 个关键词已缓存")
    print("=" * 50)
