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
        
        # GitHub Actions 环境优化
        import os
        if os.getenv('GITHUB_ACTIONS'):
            logger.info(f"[{self.site_name}] 检测到GitHub Actions环境，启用快速模式")
            self.github_actions_mode = True
            # GitHub Actions 环境下使用快速策略
            search_delay = float(os.getenv('SEARCH_DELAY', 3))
            retry_delay = float(os.getenv('RETRY_DELAY', 10))
            self.min_delay = search_delay
            self.retry_delay = retry_delay
            self.max_retries = 3    # 适中重试次数
            
            # 特殊模式配置
            self.target_host_ip = os.getenv('TARGET_HOST_IP')
            self.mobile_mode = os.getenv('MOBILE_MODE') == 'true'
            
            if self.target_host_ip:
                logger.info(f"[{self.site_name}] 直接IP访问模式: {self.target_host_ip}")
            if self.mobile_mode:
                logger.info(f"[{self.site_name}] 移动端伪装模式")
            
            logger.info(f"[{self.site_name}] 快速模式配置: 延迟={search_delay}s, 重试延迟={retry_delay}s")
        else:
            self.github_actions_mode = False
            self.min_delay = 3.0
            self.retry_delay = 10.0
            self.max_retries = 4
            self.target_host_ip = None
            self.mobile_mode = False
        
        # 用户代理池
        if self.mobile_mode:
            self.USER_AGENTS = [
                'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
                'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
                'Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
            ]
        else:
            self.USER_AGENTS = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
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
        
        # 设置请求头
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        })
        
        # 减少urllib3的警告日志
        logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)
        
        logger.info(f"[{self.site_name}] HTTP会话已配置")
    
    def _get_random_user_agent(self) -> str:
        """获取随机用户代理"""
        return random.choice(self.USER_AGENTS)
    
    def _random_delay(self, min_delay: float = 1.0, max_delay: float = 3.0):
        """随机延迟"""
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)
    
    def _batch_delay(self):
        """批量处理延迟"""
        if self.github_actions_mode:
            # GitHub Actions 环境使用配置的延迟
            delay = random.uniform(self.min_delay, self.min_delay + 3)
            logger.debug(f"[{self.site_name}] 快速模式批量延迟 {delay:.1f}秒")
        else:
            delay = random.uniform(3.0, 8.0)
            logger.debug(f"[{self.site_name}] 批量处理延迟 {delay:.1f}秒")
        time.sleep(delay)
    
    def _send_search_request(self, keyword: str, page: int = 1) -> Optional[str]:
        """发送搜索请求"""
        try:
            # 频率控制
            if hasattr(self, '_last_request_time'):
                time_since_last = time.time() - self._last_request_time
                min_interval = self.min_delay if self.github_actions_mode else 5.0
                if time_since_last < min_interval:
                    self._batch_delay()
            
            # 预热访问
            if self.github_actions_mode:
                # GitHub Actions 环境下快速预热
                self._random_delay(1.0, 2.0)
                logger.debug(f"[{self.site_name}] 快速模式预热访问主页...")
            else:
                self._random_delay(1.0, 3.0)
                logger.debug(f"[{self.site_name}] 预热访问主页...")
            
            # 更新用户代理
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
            
            # 访问主页
            try:
                homepage_response = self.session.get(base_url, timeout=20)
                if homepage_response.status_code == 200:
                    logger.debug(f"[{self.site_name}] 主页访问成功")
                else:
                    logger.warning(f"[{self.site_name}] 主页访问失败: {homepage_response.status_code}")
            except Exception as e:
                logger.warning(f"[{self.site_name}] 主页访问异常: {e}")
            
            # 搜索请求
            if self.github_actions_mode:
                # GitHub Actions 环境下快速搜索
                self._random_delay(2.0, 3.0)
                logger.debug(f"[{self.site_name}] 快速模式发送搜索请求: {keyword}")
            else:
                self._random_delay(2.0, 5.0)
                logger.debug(f"[{self.site_name}] 发送搜索请求: {keyword}")
            
            search_url = f"{base_url}/"
            search_data = {'seerch': keyword}
            
            # 更新请求头
            origin_url = "https://tonkiang.us" if not self.target_host_ip else base_url
            self.session.headers.update({
                'Referer': f'{origin_url}/',
                'Origin': origin_url,
                'Content-Type': 'application/x-www-form-urlencoded',
            })
            
            # 尝试搜索，动态重试次数
            for attempt in range(self.max_retries):
                if attempt > 0:
                    logger.debug(f"[{self.site_name}] 第 {attempt} 次重试...")
                    if self.github_actions_mode:
                        # GitHub Actions 环境使用更长的重试延迟
                        retry_delay = self.retry_delay + attempt * 45  # 增加延迟倍数
                        self._random_delay(retry_delay, retry_delay + 30)  # 增加随机范围
                    else:
                        self._random_delay(5.0 + attempt * 2, 10.0 + attempt * 3)
                    self.session.headers['User-Agent'] = self._get_random_user_agent()
                
                try:
                    response = self.session.post(
                        search_url,
                        data=search_data,
                        timeout=30,
                        allow_redirects=True
                    )
                    
                    if response.encoding is None:
                        response.encoding = 'utf-8'
                    content = response.text
                    
                    # 检查响应质量
                    if response.status_code == 200 and len(content) >= 10000:
                        logger.info(f"[{self.site_name}] 搜索请求成功: {keyword}")
                        self._last_request_time = time.time()
                        return content
                    elif response.status_code == 200:
                        logger.warning(f"[{self.site_name}] 内容过短({len(content)}字符)")
                        # GitHub Actions 模式下，给更多重试机会
                        if self.github_actions_mode and attempt >= 2:  # 改为2次失败后才跳过
                            logger.info(f"[{self.site_name}] 智能模式：多次失败，跳过 {keyword}")
                            break
                    elif response.status_code == 503:
                        logger.warning(f"[{self.site_name}] 服务不可用(503)")
                    else:
                        logger.warning(f"[{self.site_name}] 状态码: {response.status_code}")
                        if response.status_code not in [503, 200]:
                            break
                            
                except Exception as e:
                    logger.warning(f"[{self.site_name}] 请求异常: {e}")
                    if attempt == 3:
                        break
            
            logger.error(f"[{self.site_name}] 所有尝试均失败")
            self._last_request_time = time.time()
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
                    if any(pattern in text.lower() for pattern in ['cctv', '卫视', 'tv', '频道']):
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
    test_keyword = "CCTV-1"
    print(f"测试搜索: {test_keyword}")
    
    channels = searcher.search_channels(test_keyword)
    
    print(f"找到 {len(channels)} 个频道:")
    for i, channel in enumerate(channels, 1):
        print(f"  {i}. {channel.name} - {channel.resolution} - {channel.url}")
    
    # 显示缓存状态
    cache_info = searcher.get_cache_info()
    print(f"\n缓存状态: {cache_info['cached_keywords']} 个关键词已缓存")
    print("=" * 50)