#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tonkiang.us IPTV搜索器实现
专门针对 https://tonkiang.us/ 站点的搜索逻辑
"""

import requests
import re
import time
import random
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
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # 确保调试信息显示


class TonkiangSearcher(BaseIPTVSearcher):
    """Tonkiang.us 搜索器实现 - 增强反反爬虫功能"""
    
    # 用户代理池 - 模拟不同的真实浏览器
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]
    
    def __init__(self, config: SearchConfig = None):
        """
        初始化 Tonkiang 搜索器
        
        Args:
            config: 搜索配置
        """
        self.site_name = "Tonkiang.us"
        self.base_url = "https://tonkiang.us"
        super().__init__(config)
    
    def _get_random_user_agent(self) -> str:
        """获取随机用户代理"""
        return random.choice(self.USER_AGENTS)
    
    def _random_delay(self, min_delay: float = 1.0, max_delay: float = 3.0) -> None:
        """随机延迟，模拟人类行为"""
        delay = random.uniform(min_delay, max_delay)
        logger.debug(f"[{self.site_name}] 随机延迟 {delay:.1f}秒...")
        time.sleep(delay)
    
    def _batch_delay(self) -> None:
        """批量处理时的额外延迟，避免请求过于频繁"""
        delay = random.uniform(3.0, 8.0)  # 批量处理时更长的延迟
        logger.debug(f"[{self.site_name}] 批量处理延迟 {delay:.1f}秒...")
        time.sleep(delay)
    
    def _setup_session(self):
        """设置HTTP会话"""
        self.session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"],
            backoff_factor=2,
            raise_on_status=False
        )
        
        adapter = HTTPAdapter(
            pool_connections=50,  # 增加连接池
            pool_maxsize=50,      # 增加连接池大小
            max_retries=retry_strategy,
            pool_block=False
        )
        
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # 使用随机用户代理和完整的请求头模拟真实浏览器
        random_ua = self._get_random_user_agent()
        logger.debug(f"[{self.site_name}] 使用用户代理: {random_ua[:50]}...")
        
        self.session.headers.update({
            'User-Agent': random_ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'Accept-Encoding': 'gzip, deflate, br',  # 重新启用压缩
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',  # 改为none，模拟直接访问
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'Sec-CH-UA': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-CH-UA-Mobile': '?0',
            'Sec-CH-UA-Platform': '"Windows"',
        })
        
        logger.info(f"[{self.site_name}] HTTP会话已配置")
    
    def _send_search_request(self, keyword: str, page: int = 1) -> str:
        """
        发送搜索请求到 Tonkiang.us (增强反反爬虫)
        
        Args:
            keyword: 搜索关键词
            page: 页码
            
        Returns:
            str: 响应HTML内容，None表示网络异常
        """
        import time
        import random
        
        try:
            # 第一步：检查是否为批量处理，如果是则增加延迟
            if hasattr(self, '_last_request_time'):
                time_since_last = time.time() - self._last_request_time
                if time_since_last < 5.0:  # 如果距离上次请求少于5秒
                    logger.debug(f"[{self.site_name}] 检测到频繁请求，增加批量延迟...")
                    self._batch_delay()
            
            # 第二步：随机延迟开始，避免请求过于规律
            self._random_delay(1.0, 3.0)
            
            # 第三步：先访问主页获取cookies和session，使用新的用户代理
            logger.debug(f"[{self.site_name}] 预热访问主页...")
            
            # 为每次搜索更换用户代理
            new_ua = self._get_random_user_agent()
            self.session.headers.update({
                'User-Agent': new_ua,
                'Referer': '',  # 模拟直接访问
                'Sec-Fetch-Site': 'none',
            })
            logger.debug(f"[{self.site_name}] 更新用户代理: {new_ua[:50]}...")
            
            homepage_response = self.session.get(
                self.base_url, 
                timeout=(15, 20),  # 增加超时时间
                allow_redirects=True
            )
            
            if homepage_response.status_code == 200:
                logger.debug(f"[{self.site_name}] 主页访问成功，获取到cookies")
                # 检查是否有有效的cookies
                if self.session.cookies:
                    logger.debug(f"[{self.site_name}] 获得 {len(self.session.cookies)} 个cookies")
            elif homepage_response.status_code == 503:
                logger.warning(f"[{self.site_name}] 主页访问被拦截(503)，尝试更长延迟...")
                self._batch_delay()  # 使用批量延迟
            else:
                logger.warning(f"[{self.site_name}] 主页访问失败: {homepage_response.status_code}")
            
            # 随机延迟，模拟人类浏览行为
            self._random_delay(2.0, 5.0)
            
            # 第二步：发送搜索请求
            search_url = f"{self.base_url}/"
            search_data = {'seerch': keyword}  # 注意：seerch 是故意的拼写
            
            # 更新请求头，模拟从主页提交表单
            self.session.headers.update({
                'Referer': f'{self.base_url}/',
                'Origin': self.base_url,
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-User': '?1',
            })
            
            logger.debug(f"[{self.site_name}] 发送搜索请求: {keyword}")
            
            response = self.session.post(
                search_url, 
                data=search_data, 
                timeout=(15, self.config.timeout + 5),  # 增加超时时间
                allow_redirects=True,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                }
            )
            
            logger.debug(f"[{self.site_name}] 搜索响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                logger.info(f"[{self.site_name}] 搜索请求成功: {keyword}")
                # 调试：检查响应信息
                logger.debug(f"[{self.site_name}] 响应编码: {response.encoding}")
                logger.debug(f"[{self.site_name}] Content-Type: {response.headers.get('Content-Type')}")
                logger.debug(f"[{self.site_name}] Content-Encoding: {response.headers.get('Content-Encoding')}")
                
                # 确保正确解码内容
                if response.encoding is None:
                    response.encoding = 'utf-8'
                content = response.text
                logger.debug(f"[{self.site_name}] 返回内容长度: {len(content)} 字符")
                if len(content) < 1000:
                    logger.warning(f"[{self.site_name}] 返回内容过短，可能被反爬虫拦截: {content[:200]}...")
                elif 'About' in content and 'results' in content:
                    logger.debug(f"[{self.site_name}] 检测到正常搜索结果页面")
                elif 'tba' in content or 'resultplus' in content or 'search' in content.lower():
                    logger.debug(f"[{self.site_name}] 检测到可能的搜索结果页面")
                else:
                    logger.warning(f"[{self.site_name}] 返回内容不像搜索结果页面")
                    # 打印内容的前200字符用于调试
                    logger.debug(f"[{self.site_name}] 内容预览: {content[:200]}")
                    # 保存异常内容用于调试
                    with open('debug_response.html', 'w', encoding='utf-8') as f:
                        f.write(content)
                    logger.debug(f"[{self.site_name}] 异常响应已保存到 debug_response.html")
                # 记录请求时间，用于批量处理延迟控制
                self._last_request_time = time.time()
                return content
            elif response.status_code == 503:
                logger.warning(f"[{self.site_name}] 服务不可用(503)，可能触发反爬虫，尝试多次重试...")
                
                # 多次重试策略
                for retry_count in range(3):
                    logger.debug(f"[{self.site_name}] 第 {retry_count + 1} 次重试...")
                    
                    # 更长时间的随机延迟
                    self._random_delay(5.0 + retry_count * 2, 10.0 + retry_count * 3)
                    
                    # 更换用户代理
                    new_ua = self._get_random_user_agent()
                    self.session.headers.update({'User-Agent': new_ua})
                    logger.debug(f"[{self.site_name}] 重试时更换用户代理: {new_ua[:50]}...")
                    
                    try:
                        retry_response = self.session.post(
                            search_url, 
                            data=search_data, 
                            timeout=(20, self.config.timeout + 10),
                            allow_redirects=True,
                            headers={'Content-Type': 'application/x-www-form-urlencoded'}
                        )
                        
                        if retry_response.status_code == 200:
                            logger.info(f"[{self.site_name}] 第 {retry_count + 1} 次重试成功: {keyword}")
                            # 记录请求时间
                            self._last_request_time = time.time()
                            return retry_response.text
                        elif retry_response.status_code != 503:
                            logger.warning(f"[{self.site_name}] 重试返回状态码: {retry_response.status_code}")
                            break
                    except Exception as e:
                        logger.warning(f"[{self.site_name}] 重试异常: {e}")
                        continue
                
                logger.error(f"[{self.site_name}] 所有重试均失败")
                return None
            else:
                logger.warning(f"[{self.site_name}] 搜索请求失败，状态码: {response.status_code}")
                return ""
                
        except Exception as e:
            logger.error(f"[{self.site_name}] 搜索请求异常: {keyword} - {e}")
            # 即使异常也记录时间，避免频繁重试
            self._last_request_time = time.time()
            return None  # 返回None表示网络异常
    
    def _parse_search_results(self, html_content: str, keyword: str) -> List[IPTVChannel]:
        """
        解析 Tonkiang.us 的搜索结果
        
        Args:
            html_content: HTML响应内容，如果为None表示网络异常
            keyword: 搜索关键词
            
        Returns:
            List[IPTVChannel]: 匹配的频道列表
        """
        channels = []
        
        # 处理网络异常
        if html_content is None:
            logger.error(f"[{self.site_name}] 网络异常，无法获取搜索结果: {keyword}")
            return channels
        
        # 处理空响应
        if not html_content.strip():
            logger.warning(f"[{self.site_name}] 搜索响应为空: {keyword}")
            return channels
        
        try:
            logger.debug(f"[{self.site_name}] 开始解析HTML内容，长度: {len(html_content)} 字符")
            
            # 解析HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 查找所有 tba 标签（这是最稳定的特征，包含流媒体链接）
            tba_elements = soup.find_all('tba')
            logger.debug(f"[{self.site_name}] 找到 {len(tba_elements)} 个tba标签")
            
            for tba in tba_elements:
                try:
                    # 获取tba标签内容
                    tba_text = tba.get_text(strip=True)
                    
                    # 检查是否包含有效的流媒体URL
                    if not self._is_valid_stream_url(tba_text):
                        continue
                    
                    stream_url = tba_text
                    logger.debug(f"[{self.site_name}] 找到流媒体URL: {stream_url}")
                    
                    # 向上查找包含频道名称的容器
                    channel_name = self._find_channel_name_near_tba(tba, keyword)
                    if not channel_name:
                        logger.debug(f"[{self.site_name}] 未找到匹配的频道名称")
                        continue
                    
                    # 验证找到的频道名称是否真的匹配搜索关键词
                    if not self._is_channel_match(channel_name, keyword):
                        logger.debug(f"[{self.site_name}] 过滤: 频道名称 '{channel_name}' 不匹配搜索关键词 '{keyword}' - {stream_url[:50]}...")
                        continue
                    
                    # 查找分辨率信息
                    resolution = self._find_resolution_near_tba(tba)
                    
                    # 创建频道对象
                    channel = IPTVChannel(
                        name=channel_name,
                        url=stream_url,
                        resolution=resolution,
                        source=self.site_name
                    )
                    channels.append(channel)
                    logger.debug(f"[{self.site_name}] 添加频道: 搜索'{keyword}' -> 找到'{channel_name}' [{resolution}] - {stream_url[:50]}...")
                    
                except Exception as e:
                    logger.debug(f"[{self.site_name}] 解析单个tba异常: {e}")
                    continue
            
            logger.info(f"[{self.site_name}] 解析完成: {keyword}, 找到 {len(channels)} 个频道")
            
        except Exception as e:
            logger.error(f"[{self.site_name}] 解析异常: {keyword} - {e}")
        
        return channels
    
    def _is_channel_match(self, text: str, keyword: str) -> bool:
        """
        检查文本是否匹配频道名称（忽略大小写）
        
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
        
        # 精确匹配优先
        if text_lower == keyword_lower:
            return True
        
        # 处理常见的频道名称格式变化
        # 移除常见的分隔符和空格进行比较
        text_clean = text_lower.replace('-', '').replace('_', '').replace(' ', '')
        keyword_clean = keyword_lower.replace('-', '').replace('_', '').replace(' ', '')
        
        if text_clean == keyword_clean:
            return True
        
        # 对于CCTV类频道，进行更严格的匹配
        if 'cctv' in keyword_lower:
            # 提取数字部分进行精确匹配
            import re
            keyword_num = re.findall(r'cctv[_-]?(\d+)', keyword_lower)
            text_num = re.findall(r'cctv[_-]?(\d+)', text_lower)
            
            if keyword_num and text_num:
                # 数字必须完全匹配
                return keyword_num[0] == text_num[0]
        
        # 对于其他频道，使用包含匹配，但要避免部分匹配问题
        # 例如：搜索"湖南卫视"不应该匹配"湖南卫视HD"以外的其他内容
        if len(keyword_lower) >= 3:  # 关键词足够长时才使用包含匹配
            return keyword_lower in text_lower
        
        return False
    
    def _find_channel_name_near_tba(self, tba_element, keyword: str) -> str:
        """
        从tba标签附近查找频道名称
        
        Args:
            tba_element: tba标签元素
            keyword: 搜索关键词 (用于判断搜索范围)
            
        Returns:
            str: 找到的频道名称，如果没找到返回None
        """
        try:
            # 向上查找父容器，通常是table或div
            current = tba_element
            for _ in range(10):  # 最多向上10层
                current = current.parent
                if not current:
                    break
                
                # 在当前容器中查找所有div和a标签
                potential_names = []
                for element in current.find_all(['div', 'a']):
                    text = element.get_text(strip=True)
                    
                    # 检查文本长度是否合理（频道名称通常不会太长）
                    if len(text) > 50 or len(text) < 2:
                        continue
                    
                    # 进一步检查是否真的是频道名称（不包含URL等）
                    if not any(x in text.lower() for x in ['http', '.m3u8', '.ts', 'onclick', 'copy', 'play']):
                        # 检查是否看起来像频道名称
                        if any(pattern in text.lower() for pattern in ['cctv', '卫视', 'tv', '频道']):
                            potential_names.append(text)
                            logger.debug(f"[{self.site_name}] 找到潜在频道名称: {text}")
                
                # 如果找到了潜在的频道名称，返回第一个
                if potential_names:
                    return potential_names[0]
                            
            return None
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 查找频道名称异常: {e}")
            return None
    
    def _find_resolution_near_tba(self, tba_element) -> str:
        """
        从tba标签附近查找分辨率信息
        
        Args:
            tba_element: tba标签元素
            
        Returns:
            str: 找到的分辨率信息
        """
        try:
            # 向上查找父容器
            current = tba_element
            for _ in range(10):  # 最多向上10层
                current = current.parent
                if not current:
                    break
                
                # 在当前容器中查找i标签（分辨率通常在i标签中）
                for i_elem in current.find_all('i'):
                    text = i_elem.get_text(strip=True)
                    # 处理HTML实体
                    text = text.replace('&#8226;', ' ').replace('•', ' ')
                    resolution = self._extract_resolution_from_text(text)
                    if resolution != "未知":
                        return resolution
                
                # 如果i标签中没找到，在整个容器文本中搜索
                container_text = current.get_text()
                container_text = container_text.replace('&#8226;', ' ').replace('•', ' ')
                resolution = self._extract_resolution_from_text(container_text)
                if resolution != "未知":
                    return resolution
                    
            return "未知"
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 查找分辨率异常: {e}")
            return "未知"
    
    def _find_stream_url_in_container(self, start_element) -> str:
        """
        从指定元素开始，查找流媒体URL
        
        Args:
            start_element: 开始查找的元素
            
        Returns:
            str: 找到的流媒体URL，如果没找到返回None
        """
        try:
            # 向上找到父容器
            container = start_element
            for _ in range(5):  # 最多向上5层
                if container.parent:
                    container = container.parent
                    if container.name == 'div':
                        break
                else:
                    break
            
            # 在容器中查找tba标签（流媒体链接通常在tba标签中）
            tba_elements = container.find_all('tba')
            for tba in tba_elements:
                text = tba.get_text(strip=True)
                if self._is_valid_stream_url(text):
                    return text
            
            # 如果tba中没找到，在整个容器文本中搜索
            container_text = container.get_text()
            urls = self._extract_streaming_urls(container_text)
            if urls:
                return urls[0]
            
            return None
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 查找流媒体链接异常: {e}")
            return None
    
    def _find_resolution_in_container(self, start_element) -> str:
        """
        从指定元素开始，查找分辨率信息
        
        Args:
            start_element: 开始查找的元素
            
        Returns:
            str: 找到的分辨率信息
        """
        try:
            # 向上找到父容器
            container = start_element
            for _ in range(5):  # 最多向上5层
                if container.parent:
                    container = container.parent
                    if container.name == 'div':
                        break
                else:
                    break
            
            # 在容器中查找i标签（分辨率信息通常在i标签中）
            i_elements = container.find_all('i')
            for i_elem in i_elements:
                text = i_elem.get_text(strip=True)
                # 处理HTML实体
                text = text.replace('&#8226;', ' ').replace('•', ' ')
                resolution = self._extract_resolution_from_text(text)
                if resolution != "未知":
                    return resolution
            
            # 如果i标签中没找到，在整个容器文本中搜索
            container_text = container.get_text()
            container_text = container_text.replace('&#8226;', ' ').replace('•', ' ')
            resolution = self._extract_resolution_from_text(container_text)
            return resolution
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 查找分辨率异常: {e}")
            return "未知"
    
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
            r'(https?://[^\s<>"\']+\.ts[^\s<>"\']*)',
            r'(https?://[^\s<>"\']+:\d{4,5}/[^\s<>"\']*)',
            r'(rtmp://[^\s<>"\']+)',
            r'(rtsp://[^\s<>"\']+)',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                url = match.group(1).strip()
                url = re.sub(r'[<>"\'\s]+.*$', '', url)  # 清理URL
                
                if self._is_valid_stream_url(url):
                    urls.append(url)
        
        return urls
    
    def _extract_resolution_from_text(self, text: str) -> str:
        """
        从文本中提取标准分辨率格式
        
        Args:
            text: 信息文本
            
        Returns:
            str: 分辨率信息
        """
        if not text:
            return "未知"
        
        # 标准分辨率格式
        standard_patterns = [
            r'\b(1920x1080)\b',   # 1080p
            r'\b(1280x720)\b',    # 720p  
            r'\b(3840x2160)\b',   # 4K
            r'\b(2560x1440)\b',   # 1440p
            r'\b(1366x768)\b',    # 768p
            r'\b(1024x576)\b',    # 576p
            r'\b(854x480)\b',     # 480p
            r'\b(640x360)\b',     # 360p
        ]
        
        for pattern in standard_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        # 尝试匹配 p 格式
        p_pattern = r'\b(1080|720|480|360)p\b'
        match = re.search(p_pattern, text, re.IGNORECASE)
        if match:
            height = match.group(1)
            if height == '1080':
                return '1920x1080'
            elif height == '720':
                return '1280x720'
            elif height == '480':
                return '854x480'
            elif height == '360':
                return '640x360'
            else:
                return f"{height}p"
        
        return "未知"
    
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
        
        url_lower = url.lower()
        
        # 排除无法通过HTTP验证的协议类型
        invalid_protocols = ['udp://', 'rtp://', 'rtsp://']
        for protocol in invalid_protocols:
            if protocol in url_lower:
                logger.debug(f"[{self.site_name}] 跳过不支持验证的协议: {url[:50]}...")
                return False
        
        # 检查协议 (包括IPv6地址支持)
        if not re.match(r'^(https?|rtmp)://', url, re.IGNORECASE):
            return False
        
        # 检查IPv6地址格式，标记但仍然接受
        if '[' in url and ']:' in url:
            logger.debug(f"[{self.site_name}] 检测到IPv6地址: {url[:50]}...")
        
        # 检查是否包含流媒体格式
        stream_formats = ['.m3u8', '.ts', '.flv', '.mp4', '.mkv']
        has_format = any(fmt in url_lower for fmt in stream_formats)
        
        # 或者包含端口号 (通常是IPTV服务)
        has_port = re.search(r':\d{2,5}/', url)
        
        return has_format or has_port
    
    def _validate_link(self, channel: IPTVChannel) -> bool:
        """
        验证链接的有效性 (质量优化版本)
        
        Args:
            channel: 频道对象
            
        Returns:
            bool: 链接是否有效且质量良好
        """
        if not self.config.enable_validation:
            return True
        
        try:
            # IPv6地址可能在某些环境下无法访问，先检查
            if '[' in channel.url and ']:' in channel.url:
                logger.debug(f"[{self.site_name}] IPv6地址可能不稳定，降低验证标准: {channel.url[:50]}...")
                # IPv6地址验证可能失败，但不一定意味着链接无效
                # 在某些网络环境下可能可用，所以给予更宽松的验证
                try:
                    timeout = 1  # 减少IPv6验证超时
                    if '.m3u8' in channel.url.lower():
                        return self._validate_m3u8_quality(channel.url, timeout)
                    else:
                        return self._validate_stream_basic(channel.url, timeout)
                except:
                    # IPv6验证失败时，假设链接可能有效（用户网络环境可能支持）
                    logger.debug(f"[{self.site_name}] IPv6链接验证失败，但保留链接: {channel.url[:50]}...")
                    return True
            
            timeout = 3  # 稍微增加超时以确保质量检测
            
            # 对于m3u8文件，进行深度质量验证
            if '.m3u8' in channel.url.lower():
                return self._validate_m3u8_quality(channel.url, timeout)
            
            # 对于其他类型流，进行基本验证
            return self._validate_stream_basic(channel.url, timeout)
                
        except Exception as e:
            logger.debug(f"[{self.site_name}] 链接验证异常: {channel.url}: {e}")
            return False
    
    def _validate_m3u8_quality(self, url: str, timeout: int) -> bool:
        """
        验证m3u8流的质量
        
        Args:
            url: m3u8链接
            timeout: 超时时间
            
        Returns:
            bool: 是否为高质量流
        """
        try:
            # 第一步：获取m3u8播放列表
            response = self.session.get(url, timeout=timeout)
            if response.status_code != 200:
                logger.debug(f"[{self.site_name}] m3u8状态码异常: {response.status_code}")
                return False
            
            playlist_content = response.text
            
            # 检查是否为有效的m3u8格式
            if not ('#EXTM3U' in playlist_content or '#EXT-X-' in playlist_content):
                logger.debug(f"[{self.site_name}] 无效的m3u8格式")
                return False
            
            # 第二步：检查播放列表类型和质量
            if '#EXT-X-STREAM-INF' in playlist_content:
                # 主播放列表，提取实际流URL
                import re
                stream_urls = re.findall(r'(https?://[^\s]+\.m3u8[^\s]*)', playlist_content)
                if not stream_urls:
                    logger.debug(f"[{self.site_name}] 主播放列表中未找到流URL")
                    return False
                
                # 验证第一个流URL的质量
                return self._validate_m3u8_segments(stream_urls[0], timeout)
            else:
                # 直接的分片播放列表，验证分片质量
                return self._validate_m3u8_segments(url, timeout)
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] m3u8质量验证异常")
            return False
    
    def _validate_m3u8_segments(self, url: str, timeout: int) -> bool:
        """
        验证m3u8分片的质量
        
        Args:
            url: m3u8分片播放列表URL
            timeout: 超时时间
            
        Returns:
            bool: 分片质量是否良好
        """
        try:
            # 获取分片播放列表
            response = self.session.get(url, timeout=timeout)
            if response.status_code != 200:
                return False
            
            content = response.text
            
            # 检查是否有足够的分片
            segment_count = content.count('#EXTINF')
            if segment_count < 2:  # 至少需要2个分片
                logger.debug(f"[{self.site_name}] 分片数量不足: {segment_count}")
                return False
            
            # 提取第一个分片URL进行质量测试
            import re
            from urllib.parse import urljoin
            
            # 查找第一个分片文件
            lines = content.strip().split('\n')
            segment_url = None
            for i, line in enumerate(lines):
                if line.startswith('#EXTINF'):
                    if i + 1 < len(lines):
                        segment_file = lines[i + 1].strip()
                        if segment_file and not segment_file.startswith('#'):
                            # 构建完整URL
                            if segment_file.startswith('http'):
                                segment_url = segment_file
                            else:
                                segment_url = urljoin(url, segment_file)
                            break
            
            if not segment_url:
                logger.debug(f"[{self.site_name}] 未找到有效分片URL")
                return False
            
            # 测试分片下载速度和质量
            return self._test_segment_quality(segment_url, timeout)
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 分片验证异常: {e}")
            return False
    
    def _test_segment_quality(self, segment_url: str, timeout: int) -> bool:
        """
        测试视频分片的质量
        
        Args:
            segment_url: 分片URL
            timeout: 超时时间
            
        Returns:
            bool: 分片质量是否良好
        """
        try:
            import time
            start_time = time.time()
            
            # 下载分片的前几KB来测试速度和可用性
            response = self.session.get(segment_url, timeout=timeout, stream=True)
            if response.status_code != 200:
                logger.debug(f"[{self.site_name}] 分片状态码异常: {response.status_code}")
                return False
            
            # 检查响应头，确保是视频内容
            content_type = response.headers.get('Content-Type', '').lower()
            content_length = response.headers.get('Content-Length')
            
            # 如果Content-Type明确不是视频，直接失败
            if content_type and 'text' in content_type:
                logger.debug(f"[{self.site_name}] 分片返回文本内容: {content_type}")
                response.close()
                return False
            
            # 下载前32KB测试速度和内容
            downloaded_bytes = 0
            target_bytes = 32 * 1024  # 32KB
            first_chunk = None
            
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    if first_chunk is None:
                        first_chunk = chunk
                    downloaded_bytes += len(chunk)
                    if downloaded_bytes >= target_bytes:
                        break
            
            response.close()
            elapsed = time.time() - start_time
            
            # 检查下载是否成功
            if downloaded_bytes < 1024:  # 至少下载1KB
                logger.debug(f"[{self.site_name}] 下载数据不足: {downloaded_bytes} 字节")
                return False
            
            # 检查第一个chunk是否像视频数据
            if first_chunk:
                # 简单检查：视频文件通常不会以HTML标签开头
                chunk_start = first_chunk[:100].lower()
                if b'<html' in chunk_start or b'<!doctype' in chunk_start or b'<body' in chunk_start:
                    logger.debug(f"[{self.site_name}] 分片返回HTML内容，非视频数据")
                    return False
            
            # 检查下载速度 (至少50KB/s)
            if elapsed > 0:
                speed_kbps = (downloaded_bytes / 1024) / elapsed
                if speed_kbps < 50:
                    logger.debug(f"[{self.site_name}] 下载速度过慢: {speed_kbps:.1f}KB/s")
                    return False
                
                logger.debug(f"[{self.site_name}] 分片质量验证通过: {speed_kbps:.1f}KB/s, {downloaded_bytes} 字节")
                return True
            
            return True
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 分片质量测试异常: {e}")
            return False
    
    def _validate_stream_basic(self, url: str, timeout: int) -> bool:
        """
        对非m3u8流进行基本验证
        
        Args:
            url: 流URL
            timeout: 超时时间
            
        Returns:
            bool: 是否为有效流
        """
        try:
            # 尝试HEAD请求
            response = self.session.head(url, timeout=timeout, allow_redirects=True)
            if response.status_code in [200, 206, 302, 301]:
                return True
            
            # HEAD失败，尝试GET
            response = self.session.get(url, timeout=timeout, stream=True)
            if response.status_code in [200, 206]:
                # 尝试下载一点数据验证
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        response.close()
                        return True
                        
            response.close()
            return False
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 基本流验证异常")
            return False
    



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
    
    # 创建配置 - 启用验证测试修复后的验证逻辑
    config = SearchConfig(
        max_results=5,
        timeout=20,
        min_resolution=720,
        enable_validation=True,  # 启用验证测试修复后的逻辑
        enable_cache=True
    )
    
    # 创建搜索器
    searcher = create_tonkiang_searcher(config)
    
    # 测试搜索
    print(f"搜索器信息: {searcher.get_site_info()}")
    
    test_keywords = ["CCTV-1"]
    
    for keyword in test_keywords:
        print(f"\n测试搜索: {keyword}")
        channels = searcher.search_channels(keyword)
        
        if channels:
            print(f"找到 {len(channels)} 个频道:")
            for i, ch in enumerate(channels[:10], 1):  # 显示前10个
                print(f"  {i}. {ch.name} - {ch.resolution} - {ch.url}")
        else:
            print("  未找到结果")
    
    print(f"\n缓存状态: {len(searcher._search_cache)} 个关键词已缓存")
    print("=" * 50)