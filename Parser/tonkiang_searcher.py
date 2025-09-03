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
        准确解析 Tonkiang.us 的搜索结果，匹配频道名称与对应链接
        
        Args:
            html_content: HTML响应内容
            keyword: 搜索关键词
            
        Returns:
            List[IPTVChannel]: 解析出的频道列表
        """
        channels = []
        
        try:
            # 使用BeautifulSoup解析HTML结构
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 方法1：查找包含频道名称的结构化数据
            matched_channels = self._extract_structured_channels(soup, keyword)
            if matched_channels:
                channels.extend(matched_channels)
                logger.info(f"[{self.site_name}] 结构化解析成功: {keyword}, 找到 {len(matched_channels)} 个匹配链接")
            else:
                # 方法2：回退到文本模式解析
                matched_channels = self._extract_text_based_channels(html_content, keyword)
                if matched_channels:
                    channels.extend(matched_channels)
                    logger.info(f"[{self.site_name}] 文本解析成功: {keyword}, 找到 {len(matched_channels)} 个匹配链接")
                else:
                    logger.warning(f"[{self.site_name}] 未找到与频道名称匹配的链接: {keyword}")
            
        except Exception as e:
            logger.error(f"[{self.site_name}] 解析结果失败: {e}")
        
        return channels
    
    def _extract_structured_channels(self, soup, keyword: str) -> List[IPTVChannel]:
        """
        从HTML结构中提取频道信息（优先方法）
        
        Args:
            soup: BeautifulSoup对象
            keyword: 搜索关键词
            
        Returns:
            List[IPTVChannel]: 匹配的频道列表
        """
        channels = []
        
        try:
            # 查找可能包含频道信息的元素
            # 常见的结构：<div>, <tr>, <li>, <p> 等包含频道名称和链接
            potential_containers = soup.find_all(['div', 'tr', 'li', 'p', 'span', 'td'])
            
            for container in potential_containers:
                text_content = container.get_text(strip=True)
                
                # 检查容器是否包含目标频道名称
                if self._is_channel_name_match(text_content, keyword):
                    # 在该容器及其附近查找流媒体链接
                    links = self._find_streaming_links_in_container(container)
                    
                    for link in links:
                        # 验证链接与频道名称的关联性
                        if self._validate_channel_link_association(text_content, link, keyword):
                            resolution = self._extract_resolution_from_context(container, link)
                            
                            channel = IPTVChannel(
                                name=keyword,
                                url=link,
                                resolution=resolution,
                                source=self.site_name
                            )
                            channels.append(channel)
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 结构化解析异常: {e}")
        
        return channels
    
    def _extract_text_based_channels(self, html_content: str, keyword: str) -> List[IPTVChannel]:
        """
        基于文本模式提取频道信息（回退方法）
        
        Args:
            html_content: HTML内容
            keyword: 搜索关键词
            
        Returns:
            List[IPTVChannel]: 匹配的频道列表
        """
        channels = []
        
        try:
            # 按行分割内容
            lines = html_content.split('\n')
            
            for i, line in enumerate(lines):
                line = line.strip()
                
                # 检查当前行是否包含频道名称
                if self._is_channel_name_match(line, keyword):
                    # 在当前行及其前后几行中查找流媒体链接
                    context_lines = []
                    start_idx = max(0, i - 2)
                    end_idx = min(len(lines), i + 3)
                    
                    for j in range(start_idx, end_idx):
                        context_lines.append(lines[j])
                    
                    context_text = '\n'.join(context_lines)
                    links = self._extract_streaming_urls(context_text)
                    
                    for link in links:
                        if self._validate_channel_link_association(line, link, keyword):
                            resolution = self._extract_resolution_from_url(link)
                            
                            channel = IPTVChannel(
                                name=keyword,
                                url=link,
                                resolution=resolution,
                                source=self.site_name
                            )
                            channels.append(channel)
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 文本解析异常: {e}")
        
        return channels
    
    def _is_channel_name_match(self, text: str, keyword: str) -> bool:
        """
        检查文本是否包含匹配的频道名称
        
        Args:
            text: 待检查的文本
            keyword: 搜索关键词
            
        Returns:
            bool: 是否匹配
        """
        if not text or not keyword:
            return False
        
        text_lower = text.lower().strip()
        keyword_lower = keyword.lower().strip()
        
        # 精确匹配
        if keyword_lower in text_lower:
            # 进一步验证是否为完整的频道名称匹配
            return self._validate_exact_match(text, keyword, keyword_lower)
        
        return False
    
    def _find_streaming_links_in_container(self, container) -> List[str]:
        """
        在HTML容器中查找流媒体链接
        
        Args:
            container: BeautifulSoup元素
            
        Returns:
            List[str]: 找到的链接列表
        """
        links = []
        
        try:
            # 查找href属性中的链接
            for link_tag in container.find_all(['a', 'link'], href=True):
                url = link_tag['href']
                if self._is_valid_stream_url(url):
                    links.append(url)
            
            # 查找文本中的链接
            text_content = container.get_text()
            text_links = self._extract_streaming_urls(text_content)
            links.extend(text_links)
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 容器链接提取异常: {e}")
        
        return list(set(links))  # 去重
    
    def _extract_streaming_urls(self, text: str) -> List[str]:
        """
        从文本中提取流媒体URL
        
        Args:
            text: 文本内容
            
        Returns:
            List[str]: URL列表
        """
        urls = []
        
        patterns = [
            r'(https?://[^\s<>"\']+\.m3u8[^\s<>"\']*)',
            r'(https?://[^\s<>"\']+/[^\s<>"\']*\.ts[^\s<>"\']*)',
            r'(https?://[^\s<>"\']+:[0-9]+/[^\s<>"\']*)',
            r'(rtmp://[^\s<>"\']+)',
            r'(rtsp://[^\s<>"\']+)'
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                url = match.group(1).strip()
                url = re.sub(r'[<>"\'].*$', '', url)  # 清理URL
                
                if self._is_valid_stream_url(url):
                    urls.append(url)
        
        return urls
    
    def _validate_channel_link_association(self, context_text: str, link: str, keyword: str) -> bool:
        """
        验证链接与频道名称的关联性
        
        Args:
            context_text: 上下文文本
            link: 流媒体链接
            keyword: 频道关键词
            
        Returns:
            bool: 是否关联
        """
        # 基本验证：链接必须有效
        if not self._is_valid_stream_url(link):
            return False
        
        # 检查链接是否在频道名称附近出现
        context_lower = context_text.lower()
        keyword_lower = keyword.lower()
        
        # 如果上下文中包含频道名称，认为链接相关
        if keyword_lower in context_lower:
            return True
        
        # 检查链接URL中是否包含频道相关信息
        link_lower = link.lower()
        keyword_parts = keyword_lower.replace('-', '').replace(' ', '')
        
        if keyword_parts in link_lower.replace('-', '').replace('_', ''):
            return True
        
        return False
    
    def _extract_resolution_from_context(self, container, link: str) -> str:
        """
        从上下文中提取分辨率信息
        
        Args:
            container: HTML容器
            link: 链接URL
            
        Returns:
            str: 分辨率信息
        """
        try:
            # 首先尝试从URL中提取
            resolution = self._extract_resolution_from_url(link)
            if resolution != "未知":
                return resolution
            
            # 然后从容器文本中提取
            text = container.get_text()
            resolution_patterns = [
                r'(\d{3,4})[px_-]?(\d{3,4})',
                r'(\d{3,4})p',
                r'(\d{3,4})P',
            ]
            
            for pattern in resolution_patterns:
                match = re.search(pattern, text)
                if match:
                    if len(match.groups()) == 2:
                        width, height = match.groups()
                        return f"{width}x{height}"
                    else:
                        height = match.group(1)
                        return f"{height}p"
        
        except Exception:
            pass
        
        return "未知"
    
    def _is_exact_channel_match(self, html_content: str, keyword: str) -> bool:
        """
        检查HTML内容是否包含精确的频道名称匹配
        
        Args:
            html_content: HTML响应内容
            keyword: 搜索关键词
            
        Returns:
            bool: 是否精确匹配
        """
        # 标准化关键词 - 转换为小写并移除空格
        normalized_keyword = keyword.lower().replace(' ', '').replace('-', '')
        
        # 在HTML中查找频道名称的多种可能形式
        search_patterns = [
            keyword,  # 原始关键词
            keyword.upper(),  # 大写
            keyword.lower(),  # 小写
            keyword.replace('-', ''),  # 移除连字符
            keyword.replace(' ', ''),  # 移除空格
        ]
        
        # 检查是否包含完整的关键词
        for pattern in search_patterns:
            if pattern in html_content:
                # 进一步验证：确保不是子字符串匹配
                # 例如：搜索"CCTV-1"不应该匹配到"CCTV-13"
                if self._validate_exact_match(html_content, pattern, normalized_keyword):
                    return True
        
        return False
    
    def _validate_exact_match(self, content: str, found_pattern: str, normalized_keyword: str) -> bool:
        """
        验证找到的模式是否为精确匹配
        
        Args:
            content: 内容
            found_pattern: 找到的模式
            normalized_keyword: 标准化的关键词
            
        Returns:
            bool: 是否为精确匹配
        """
        # 查找所有匹配的位置
        content_lower = content.lower()
        pattern_lower = found_pattern.lower()
        
        start = 0
        while True:
            pos = content_lower.find(pattern_lower, start)
            if pos == -1:
                break
            
            # 检查前后字符，确保是完整词汇
            before_char = content_lower[pos-1] if pos > 0 else ' '
            after_char = content_lower[pos+len(pattern_lower)] if pos+len(pattern_lower) < len(content_lower) else ' '
            
            # 如果前后都是非字母数字字符，认为是精确匹配
            if not before_char.isalnum() and not after_char.isalnum():
                return True
            
            # 特殊处理：如果后面紧跟数字，检查是否为不同的频道
            if after_char.isdigit():
                # 提取完整的数字部分
                end_pos = pos + len(pattern_lower)
                while end_pos < len(content_lower) and content_lower[end_pos].isdigit():
                    end_pos += 1
                
                full_match = content_lower[pos:end_pos]
                full_normalized = full_match.replace('-', '').replace(' ', '')
                
                # 如果标准化后完全相同，则匹配
                if full_normalized == normalized_keyword:
                    return True
            
            start = pos + 1
        
        return False
    
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
        验证链接的有效性，包括速度测试（平衡效率和质量）
        
        Args:
            channel: 频道对象
            
        Returns:
            bool: 链接是否有效
        """
        if not self.config.enable_validation:
            return True
        
        try:
            # 第一步：快速连通性检查
            try:
                response = self.session.head(channel.url, timeout=3, allow_redirects=True)
                status_code = response.status_code
            except:
                # HEAD失败时尝试GET请求的前几个字节
                try:
                    response = self.session.get(channel.url, timeout=3, allow_redirects=True, stream=True)
                    status_code = response.status_code
                    response.close()
                except:
                    logger.debug(f"[{self.site_name}] 连通性检查失败: {channel.url}")
                    return False
            
            # 检查状态码
            if status_code not in [200, 206, 302, 301]:
                if status_code in [403, 404]:
                    # 403/404可能是防盗链，继续进行速度测试
                    logger.debug(f"[{self.site_name}] 状态码 {status_code}，继续速度测试")
                else:
                    logger.debug(f"[{self.site_name}] 无效状态码: {status_code}")
                    return False
            
            # 第二步：速度测试（关键步骤）
            speed_valid = self._test_download_speed(channel.url)
            if not speed_valid:
                logger.debug(f"[{self.site_name}] 速度测试未通过: {channel.url}")
                return False
            
            return True
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 链接验证异常: {channel.url}: {e}")
            return False
    
    def _test_download_speed(self, url: str) -> bool:
        """
        高效的链接速度测试（平衡质量和效率）
        
        Args:
            url: 链接URL
            
        Returns:
            bool: 速度是否满足要求（>=100KB/s）
        """
        try:
            import time
            
            # 优化的测试参数
            test_duration = 2  # 测试2秒（减少测试时间）
            min_speed_kbps = 100  # 最小速度100KB/s（提高要求，过滤慢速链接）
            min_test_bytes = 30720  # 最少下载30KB来判断速度
            
            start_time = time.time()
            downloaded_bytes = 0
            
            # 使用流式下载测试速度
            with self.session.get(url, stream=True, timeout=5) as response:
                # 检查响应状态
                if response.status_code not in [200, 206]:
                    logger.debug(f"[{self.site_name}] 速度测试状态码异常: {response.status_code}")
                    return False
                
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        downloaded_bytes += len(chunk)
                        elapsed = time.time() - start_time
                        
                        # 如果已经下载足够数据，提前计算速度
                        if downloaded_bytes >= min_test_bytes:
                            speed_kbps = (downloaded_bytes / 1024) / elapsed
                            is_fast_enough = speed_kbps >= min_speed_kbps
                            logger.debug(f"[{self.site_name}] 速度测试: {speed_kbps:.1f}KB/s ({'通过' if is_fast_enough else '不通过'})")
                            return is_fast_enough
                        
                        # 如果测试时间已够，也进行判断
                        if elapsed >= test_duration:
                            if downloaded_bytes > 0:
                                speed_kbps = (downloaded_bytes / 1024) / elapsed
                                is_fast_enough = speed_kbps >= min_speed_kbps
                                logger.debug(f"[{self.site_name}] 速度测试: {speed_kbps:.1f}KB/s ({'通过' if is_fast_enough else '不通过'})")
                                return is_fast_enough
                            else:
                                logger.debug(f"[{self.site_name}] 速度测试: 无数据下载")
                                return False
            
            # 如果循环结束，计算最终速度
            elapsed = time.time() - start_time
            if elapsed > 0 and downloaded_bytes > 0:
                speed_kbps = (downloaded_bytes / 1024) / elapsed
                is_fast_enough = speed_kbps >= min_speed_kbps
                logger.debug(f"[{self.site_name}] 最终速度: {speed_kbps:.1f}KB/s ({'通过' if is_fast_enough else '不通过'})")
                return is_fast_enough
            
            logger.debug(f"[{self.site_name}] 速度测试: 无有效数据")
            return False
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 速度测试异常: {e}")
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
