#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import time
import random
import re
import logging
from typing import List, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from searcher_interface import BaseIPTVSearcher, IPTVChannel, SearchConfig, SearcherFactory

logger = logging.getLogger(__name__)

class TonkiangSearcher(BaseIPTVSearcher):
    """Tonkiang.us IPTV搜索器 - 重写版本"""
    
    def __init__(self, config: SearchConfig = None):
        super().__init__(config)
        self.site_name = "Tonkiang.us"
        self.base_url = "https://tonkiang.us"
        self._setup_session()
        self._last_request_time = 0
        
        # 默认高效率配置
        self.min_delay = 3.0
        self.retry_delay = 10.0
        self.max_retries = 3
        self.target_host_ip = None
        self.mobile_mode = False
        
        # 会话轮换配置
        self.session_rotation_enabled = True
        self.requests_per_session = 3  # 每个会话最多请求次数
        
        # 更丰富的用户代理池 - 包含多种设备和版本
        if self.mobile_mode:
            self.USER_AGENTS = [
                'Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
                'Mozilla/5.0 (iPhone; CPU iPhone OS 16_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
                'Mozilla/5.0 (iPad; CPU OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
                'Mozilla/5.0 (Linux; Android 14; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
                'Mozilla/5.0 (Linux; Android 13; SM-A515F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36',
                'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36'
            ]
        else:
            self.USER_AGENTS = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/127.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/126.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
            ]
    
    def get_searcher_info(self) -> dict:
        """获取搜索器信息"""
        return {
            'name': self.site_name,
            'url': self.base_url,
            'description': 'Tonkiang.us IPTV搜索器'
        }
    
    def _setup_session(self):
        """设置HTTP会话"""
        # 全局禁用SSL警告
        import urllib3
        import ssl
        urllib3.disable_warnings()
        
        self.session = requests.Session()
        self.current_session_requests = 0  # 当前会话请求计数
        
        # 完全禁用SSL证书验证
        self.session.verify = False
        
        # 设置SSL上下文 - 完全禁用SSL验证
        self.session.trust_env = False
        
        # 设置重试策略 - 减少重试次数和日志
        retry_strategy = Retry(
            total=1,  # 减少重试次数
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False  # 不抛出状态异常
        )
        
        # 创建自定义适配器，强制禁用SSL验证
        class NoSSLAdapter(HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                kwargs['ssl_context'] = ssl.create_default_context()
                kwargs['ssl_context'].check_hostname = False
                kwargs['ssl_context'].verify_mode = ssl.CERT_NONE
                return super().init_poolmanager(*args, **kwargs)
        
        adapter = NoSSLAdapter(
            max_retries=retry_strategy,
            pool_connections=50,
            pool_maxsize=50
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # 设置更完整的请求头，模拟真实浏览器，增加随机化
        base_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': random.choice(['no-cache', 'max-age=0']),
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': random.choice(['none', 'cross-site']),
            'Sec-Fetch-User': '?1',
        }
        
        # 随机添加一些可选请求头
        if random.random() < 0.7:  # 70%概率添加Chrome特征头
            chrome_version = random.choice(['127', '126', '125', '128'])
            base_headers.update({
                'sec-ch-ua': f'"Chromium";v="{chrome_version}", "Not(A:Brand";v="24", "Google Chrome";v="{chrome_version}"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': random.choice(['"Windows"', '"macOS"', '"Linux"']),
            })
        
        if random.random() < 0.3:  # 30%概率添加Pragma
            base_headers['Pragma'] = 'no-cache'
            
        self.session.headers.update(base_headers)
        
        # 减少urllib3的警告日志
        logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)
        
        logger.info(f"[{self.site_name}] HTTP会话已配置")
    
    def _get_random_user_agent(self) -> str:
        """获取随机用户代理"""
        return random.choice(self.USER_AGENTS)
    
    def _create_fresh_session(self):
        """创建全新的会话"""
        logger.debug(f"[{self.site_name}] 创建新会话，重置反爬虫特征")
        
        # 关闭旧会话
        if hasattr(self, 'session'):
            self.session.close()
        
        # 重新设置会话
        self._setup_session()
        
        # 重置计数器
        self.current_session_requests = 0
        
        # 随机延迟以模拟新用户访问
        self._random_delay(2.0, 5.0)
    
    def _simulate_human_behavior(self):
        """模拟人类浏览行为"""
        # 检查是否需要轮换会话
        if (self.session_rotation_enabled and 
            self.current_session_requests >= self.requests_per_session):
            self._create_fresh_session()
        
        # 随机添加一些人类行为模拟
        behavior_delay = random.uniform(0.5, 2.0)
        time.sleep(behavior_delay)
        
        # 随机更新多种请求头
        if random.random() < 0.4:  # 40%的概率更新Referer
            referers = [
                'https://www.google.com/search?q=iptv+live',
                'https://www.google.com/search?q=tv+stream',
                'https://www.google.com/search?q=live+tv',
                'https://www.sogou.com/web?query=IPTV',
                'https://tonkiang.us/',
                'https://www.google.com/',
                ''  # 有时不设置Referer
            ]
            referer = random.choice(referers)
            if referer:
                self.session.headers['Referer'] = referer
            elif 'Referer' in self.session.headers:
                del self.session.headers['Referer']
        
        # 随机更新其他请求头
        if random.random() < 0.2:  # 20%的概率更新Accept-Language
            languages = [
                'en-US,en;q=0.9',
                'en-US,en;q=0.9,de;q=0.8',
                'en-GB,en-US;q=0.9,en;q=0.8',
                'en-US,en;q=0.9,fr;q=0.8',
            ]
            self.session.headers['Accept-Language'] = random.choice(languages)
        
        # 随机设置屏幕分辨率相关头（某些网站会检查）
        if random.random() < 0.1:  # 10%的概率
            viewport_width = random.choice([1920, 1366, 1536, 1440, 1280])
            self.session.headers['Viewport-Width'] = str(viewport_width)
    
    def _random_delay(self, min_delay: float = 1.0, max_delay: float = 3.0):
        """随机延迟"""
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)
    
    def _batch_delay(self):
        """批量处理延迟 - 增加延迟时间应对反爬虫"""
        delay = random.uniform(8.0, 15.0)  # 增加延迟时间
        logger.debug(f"[{self.site_name}] 批量处理延迟 {delay:.1f}秒")
        time.sleep(delay)
    
    def _send_search_request(self, keyword: str, page: int = 1) -> Optional[str]:
        """发送搜索请求"""
        try:
                # 频率控制 - 平衡的频率限制
            if hasattr(self, '_last_request_time'):
                time_since_last = time.time() - self._last_request_time
                min_interval = 6.0  # 适中的间隔时间
                if time_since_last < min_interval:
                    remaining_time = min_interval - time_since_last
                    logger.debug(f"[{self.site_name}] 频率控制等待 {remaining_time:.1f}秒")
                    time.sleep(remaining_time + random.uniform(0.5, 1.5))  # 适中的随机延迟
            
            # 预热访问 - 适中延迟时间
            self._random_delay(2.0, 4.0)
            logger.debug(f"[{self.site_name}] 预热访问主页...")
            
            # 模拟人类行为
            self._simulate_human_behavior()
            self.session.headers['User-Agent'] = self._get_random_user_agent()
            
            # 构建请求URL（支持直接IP访问）
            if self.target_host_ip:
                # 直接IP访问模式
                ip = self.target_host_ip
                # IPv6地址需要用方括号包围
                if ':' in ip and not ip.startswith('['):
                    ip = f"[{ip}]"
                base_url = f"https://{ip}"
                self.session.headers['Host'] = 'tonkiang.us'  # 设置Host头
                logger.debug(f"[{self.site_name}] 使用直接IP访问: {ip}")
            else:
                base_url = self.base_url
            
            # **简化策略: 直接搜索，避免复杂逻辑导致的内容截断**
            logger.debug(f"[{self.site_name}] 使用简化策略直接搜索: {keyword}")
            
            # 设置基础请求头（纯ASCII避免编码问题）
            self.session.headers.clear()  # 清除所有可能有问题的头部
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',  # 使用纯英文避免编码问题
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://tonkiang.us',
                'Referer': 'https://tonkiang.us/'
            })
            
            # 简单延迟
            self._random_delay(2.0, 4.0)
            logger.debug(f"[{self.site_name}] 发送搜索请求: {keyword}")
            
            search_url = f"{base_url}/"
            search_data = {'seerch': keyword}
            
            # 单次搜索请求，避免复杂重试逻辑
            try:
                response = self.session.post(
                    search_url,
                    data=search_data,
                    timeout=30,
                    verify=False
                )
                
                if response.encoding is None:
                    response.encoding = 'utf-8'
                content = response.text
                
                # 简化的响应检查（仿照调试脚本）
                logger.info(f"[{self.site_name}] 状态码: {response.status_code}, 内容长度: {len(content)} 字符")
                
                if response.status_code == 200:
                    # 基础质量检查
                    has_tba = 'tba>' in content
                    has_keyword = any(kw in content for kw in [keyword, 'CCTV', 'channel', 'live'])
                    
                    if has_tba and has_keyword:
                        logger.info(f"[{self.site_name}] 搜索成功: {keyword}")
                        self._last_request_time = time.time()
                        return content
                    else:
                        logger.warning(f"[{self.site_name}] 内容质量检查失败: tba={has_tba}, keyword={has_keyword}")
                        # 调试信息
                        preview = content[:300] + "..." if len(content) > 300 else content
                        logger.debug(f"[{self.site_name}] 内容预览: {repr(preview)}")
                else:
                    logger.warning(f"[{self.site_name}] HTTP错误: {response.status_code}")
                
            except requests.exceptions.RequestException as e:
                logger.error(f"[{self.site_name}] 请求异常: {e}")
                
            return None
            
        except Exception as e:
            logger.error(f"[{self.site_name}] 搜索请求异常: {keyword} - {e}")
            self._last_request_time = time.time()
            return None
    
    def _parse_search_results(self, html_content: str, keyword: str) -> List[IPTVChannel]:
        """解析搜索结果"""
        channels = []
        
        if not html_content:
            return channels
        
        try:
            logger.debug(f"[{self.site_name}] 开始解析HTML内容，长度: {len(html_content)} 字符")
            
            soup = BeautifulSoup(html_content, 'html.parser')
            tba_elements = soup.find_all('tba')
            logger.debug(f"[{self.site_name}] 找到 {len(tba_elements)} 个流媒体链接")
            
            for tba in tba_elements:
                try:
                    # 获取URL
                    stream_url = tba.get_text(strip=True)
                    if not self._is_valid_stream_url(stream_url):
                        continue
                    
                    # 查找频道名称
                    channel_name = self._find_channel_name_near_tba(tba, keyword)
                    if not channel_name:
                        continue
                    
                    # 验证名称匹配
                    if not self._is_channel_match(channel_name, keyword):
                        logger.debug(f"[{self.site_name}] 过滤: '{channel_name}' 不匹配 '{keyword}'")
                        continue
                    
                    # 查找分辨率
                    resolution = self._find_resolution_near_tba(tba)
                    
                    # 创建频道对象
                    channel = IPTVChannel(
                        name=channel_name,
                        url=stream_url,
                        resolution=resolution,
                        source=self.site_name
                    )
                    channels.append(channel)
                    logger.debug(f"[{self.site_name}] 添加频道: {channel_name} [{resolution}]")
                    
                except Exception as e:
                    logger.debug(f"[{self.site_name}] 解析单个tba异常: {e}")
                    continue
            
            logger.info(f"[{self.site_name}] 解析完成: {keyword}, 找到 {len(channels)} 个频道")
            
        except Exception as e:
            logger.error(f"[{self.site_name}] 解析异常: {keyword} - {e}")
        
        return channels
    
    def _is_valid_stream_url(self, url: str) -> bool:
        """检查是否为有效的流媒体URL"""
        if not url or len(url) < 10:
            return False
        
        url_lower = url.lower()
        
        # 过滤不支持的协议
        invalid_protocols = ['udp://', 'rtp://', 'rtsp://']
        for protocol in invalid_protocols:
            if protocol in url_lower:
                logger.debug(f"[{self.site_name}] 跳过不支持的协议: {url[:50]}...")
                return False
        
        # 检查协议
        if not re.match(r'^(https?|rtmp)://', url, re.IGNORECASE):
            return False
        
        # IPv6地址检查
        if '[' in url and ']:' in url:
            logger.debug(f"[{self.site_name}] 检测到IPv6地址: {url[:50]}...")
        
        # 检查流媒体格式或端口
        stream_formats = ['.m3u8', '.ts', '.flv', '.mp4', '.mkv']
        has_format = any(fmt in url_lower for fmt in stream_formats)
        has_port = re.search(r':\d{2,5}/', url)
        
        return has_format or has_port
    
    def _find_channel_name_near_tba(self, tba_element, keyword: str) -> Optional[str]:
        """在tba元素附近查找频道名称"""
        try:
            # 向上查找父级容器
            for level in range(1, 6):
                parent = tba_element
                for _ in range(level):
                    parent = parent.parent
                    if not parent:
                        break
                
                if not parent:
                    continue
                
                # 在父级容器中查找文本
                texts = []
                for elem in parent.find_all(text=True):
                    text = elem.strip()
                    if text and len(text) > 1:
                        texts.append(text)
                
                # 查找匹配的频道名称
                potential_names = []
                for text in texts:
                    if len(text) > 50:
                        continue
                    if any(x in text.lower() for x in ['http', '.m3u8', '.ts', 'onclick', 'copy', 'play']):
                        continue
                    if any(pattern in text.lower() for pattern in ['cctv', 'tv', 'channel', 'live']):
                        potential_names.append(text)
                
                if potential_names:
                    return potential_names[0]
            
            return None
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 查找频道名称异常: {e}")
            return None
    
    def _find_resolution_near_tba(self, tba_element) -> str:
        """查找分辨率信息"""
        try:
            # 在附近查找分辨率信息
            for level in range(1, 4):
                parent = tba_element
                for _ in range(level):
                    parent = parent.parent
                    if not parent:
                        break
                
                if not parent:
                    continue
                
                parent_text = parent.get_text()
                
                # 查找分辨率模式
                resolution_patterns = [
                    r'(\d{3,4})[x×](\d{3,4})',
                    r'(\d{3,4})[pP]',
                    r'(4K|8K|HD|FHD|UHD)',
                ]
                
                for pattern in resolution_patterns:
                    match = re.search(pattern, parent_text, re.IGNORECASE)
                    if match:
                        if 'x' in pattern or '×' in pattern:
                            return f"{match.group(1)}x{match.group(2)}"
                        elif 'p' in pattern.lower():
                            return f"{match.group(1)}p"
                        else:
                            return match.group(1)
            
            return "1920x1080"  # 默认分辨率
            
        except Exception:
            return "1920x1080"
    
    def _is_channel_match(self, channel_name: str, keyword: str) -> bool:
        """检查频道名称是否匹配关键词"""
        if not channel_name or not keyword:
            return False
        
        channel_lower = channel_name.lower().strip()
        keyword_lower = keyword.lower().strip()
        
        # 精确匹配
        if channel_lower == keyword_lower:
            return True
        
        # 清理后匹配
        channel_clean = re.sub(r'[^\w\d]', '', channel_lower)
        keyword_clean = re.sub(r'[^\w\d]', '', keyword_lower)
        if channel_clean == keyword_clean:
            return True
        
        # CCTV特殊处理
        if 'cctv' in keyword_lower:
            keyword_num_match = re.search(r'cctv[^\d]*(\d+)', keyword_lower)
            channel_num_match = re.search(r'cctv[^\d]*(\d+)', channel_lower)
            
            if keyword_num_match and channel_num_match:
                return keyword_num_match.group(1) == channel_num_match.group(1)
        
        # 包含匹配（作为最后选择）
        return keyword_lower in channel_lower
    
    def _validate_link(self, channel: IPTVChannel) -> bool:
        """验证链接有效性"""
        if not self.config.enable_validation:
            return True
        
        try:
            # IPv6地址宽松验证
            if '[' in channel.url and ']:' in channel.url:
                logger.debug(f"[{self.site_name}] IPv6地址，降低验证标准: {channel.url[:50]}...")
                try:
                    timeout = 1
                    if '.m3u8' in channel.url.lower():
                        return self._validate_m3u8_quality(channel.url, timeout)
                    else:
                        return self._validate_stream_basic(channel.url, timeout)
                except:
                    logger.debug(f"[{self.site_name}] IPv6链接验证失败，但保留链接: {channel.url[:50]}...")
                    return True
            
            # 常规验证 - 减少超时时间
            timeout = 2  # 从3秒减少到2秒
            if '.m3u8' in channel.url.lower():
                return self._validate_m3u8_quality(channel.url, timeout)
            return self._validate_stream_basic(channel.url, timeout)
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 链接验证异常: {channel.url}: {e}")
            return False
    
    def _validate_m3u8_quality(self, url: str, timeout: int) -> bool:
        """验证M3U8流质量"""
        try:
            # 简化验证，只检查M3U8文件本身
            response = self.session.get(url, timeout=timeout)
            if response.status_code != 200:
                return False
            
            content = response.text[:5000]  # 只读取前5KB
            
            # 检查是否为有效的M3U8
            if '#EXTM3U' not in content:
                return False
            
            return True
            
        except Exception:
            return False
    

    
    def _validate_stream_basic(self, url: str, timeout: int) -> bool:
        """基本流验证"""
        try:
            # 只做HEAD请求，避免下载数据
            response = self.session.head(url, timeout=timeout, allow_redirects=True)
            return response.status_code in [200, 206, 302, 301]
            
        except Exception:
            return False


# 注册搜索器
SearcherFactory.register_searcher("tonkiang", TonkiangSearcher)


# 测试代码
if __name__ == "__main__":
    import sys
    
    # 配置日志
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    print("=" * 50)
    print("Tonkiang.us 搜索器测试")
    print("=" * 50)
    
    # 创建搜索器
    config = SearchConfig(
        max_results=10,
        timeout=30,
        enable_validation=True,
        min_valid_links=3
    )
    
    searcher = TonkiangSearcher(config)
    print(f"搜索器信息: {searcher.get_searcher_info()}")
    print()
    
    # 测试搜索
    test_keyword = "CCTV1"
    print(f"测试搜索: {test_keyword}")
    
    channels = searcher.search_channels(test_keyword)
    
    print(f"找到 {len(channels)} 个频道:")
    for i, channel in enumerate(channels, 1):
        print(f"  {i}. {channel.name} - {channel.resolution} - {channel.url}")
    
    # 显示缓存状态
    if hasattr(searcher, '_search_cache') and searcher._search_cache:
        cached_count = len(searcher._search_cache)
        print(f"\n缓存状态: {cached_count} 个关键词已缓存")
    else:
        print(f"\n缓存状态: 缓存未启用或为空")
    print("=" * 50)