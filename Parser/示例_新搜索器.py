#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
示例：如何添加新的搜索器
演示如何扩展模块化搜索器系统，支持新的IPTV站点
"""

import requests
import re
import time
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import logging

# 导入搜索器接口
from searcher_interface import BaseIPTVSearcher, IPTVChannel, SearchConfig, SearcherFactory

logger = logging.getLogger(__name__)


class ExampleSearcher(BaseIPTVSearcher):
    """
    示例搜索器实现
    演示如何为新站点实现搜索器
    """
    
    def __init__(self, config: SearchConfig = None):
        """初始化示例搜索器"""
        self.site_name = "示例站点"
        self.base_url = "https://example-iptv-site.com"
        super().__init__(config)
    
    def _setup_session(self):
        """设置HTTP会话 - 根据目标站点的特点配置"""
        self.session = requests.Session()
        
        # 设置请求头（根据目标站点要求调整）
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json,text/html,application/xhtml+xml',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': f'{self.base_url}/',
        })
        
        logger.info(f"[{self.site_name}] HTTP会话已配置")
    
    def _send_search_request(self, keyword: str, page: int = 1) -> str:
        """
        发送搜索请求 - 根据目标站点的API格式实现
        
        不同站点可能使用：
        - GET请求 + URL参数
        - POST请求 + form data
        - POST请求 + JSON数据
        - 特殊的API端点
        """
        try:
            # 示例1: GET请求方式
            search_url = f"{self.base_url}/search"
            params = {
                'q': keyword,           # 搜索参数名可能不同
                'page': page,           # 分页参数
                'type': 'live'          # 可能需要指定类型
            }
            
            response = self.session.get(
                search_url, 
                params=params,
                timeout=self.config.timeout
            )
            
            # 示例2: POST请求方式（如果需要）
            # search_data = {
            #     'keyword': keyword,
            #     'page': page,
            #     'category': 'tv'
            # }
            # response = self.session.post(
            #     search_url,
            #     data=search_data,  # 或者 json=search_data
            #     timeout=self.config.timeout
            # )
            
            response.raise_for_status()
            
            if response.status_code == 200:
                logger.info(f"[{self.site_name}] 搜索请求成功: {keyword} (页码: {page})")
                return response.text
            else:
                logger.warning(f"[{self.site_name}] 搜索请求失败，状态码: {response.status_code}")
                return ""
                
        except Exception as e:
            logger.error(f"[{self.site_name}] 搜索请求异常: {e}")
            return ""
    
    def _parse_search_results(self, html_content: str, keyword: str) -> List[IPTVChannel]:
        """
        解析搜索结果 - 根据目标站点的HTML结构实现
        
        不同站点可能需要解析：
        - JSON响应
        - HTML表格
        - 特定的HTML标签
        - 嵌入的JavaScript数据
        """
        channels = []
        
        try:
            # 方法1: 如果返回JSON数据
            if html_content.strip().startswith('{'):
                import json
                data = json.loads(html_content)
                
                # 根据JSON结构提取数据
                if 'results' in data:
                    for item in data['results']:
                        channel = IPTVChannel(
                            name=item.get('title', keyword),
                            url=item.get('stream_url', ''),
                            resolution=item.get('quality', '未知'),
                            source=self.site_name
                        )
                        
                        if channel.url:
                            channels.append(channel)
            
            else:
                # 方法2: 解析HTML内容
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # 示例：查找包含链接的元素
                # 具体选择器根据目标站点的HTML结构调整
                link_elements = soup.find_all('a', href=re.compile(r'\.(m3u8|ts|flv)'))
                
                for element in link_elements:
                    url = element.get('href', '')
                    title = element.get_text(strip=True) or keyword
                    
                    # 提取分辨率信息（如果有）
                    resolution = "未知"
                    resolution_match = re.search(r'(\d+)p', element.get_text())
                    if resolution_match:
                        resolution = resolution_match.group(1) + 'p'
                    
                    channel = IPTVChannel(
                        name=title,
                        url=url,
                        resolution=resolution,
                        source=self.site_name
                    )
                    
                    channels.append(channel)
                
                # 方法3: 使用正则表达式直接提取链接
                url_patterns = [
                    r'(https?://[^\s<>"\']+\.m3u8[^\s<>"\']*)',
                    r'(https?://[^\s<>"\']+\.ts[^\s<>"\']*)',
                    # 添加更多模式...
                ]
                
                for pattern in url_patterns:
                    matches = re.finditer(pattern, html_content, re.IGNORECASE)
                    for match in matches:
                        url = match.group(1)
                        if self._is_valid_url(url):
                            channel = IPTVChannel(
                                name=keyword,
                                url=url,
                                resolution="未知",
                                source=self.site_name
                            )
                            channels.append(channel)
            
            logger.info(f"[{self.site_name}] 解析完成: {keyword}, 找到 {len(channels)} 个链接")
            
        except Exception as e:
            logger.error(f"[{self.site_name}] 解析结果失败: {e}")
        
        return channels
    
    def _validate_link(self, channel: IPTVChannel) -> bool:
        """
        验证链接有效性 - 根据需要实现不同的验证策略
        
        验证方式可以包括：
        - HTTP HEAD请求检查可达性
        - 下载前几个字节检查内容类型
        - 使用FFmpeg检查流的有效性
        - 检查特定的响应头
        """
        if not self.config.enable_validation:
            return True
        
        try:
            # 基础验证：HTTP HEAD请求
            response = self.session.head(
                channel.url, 
                timeout=5, 
                allow_redirects=True
            )
            
            # 检查状态码
            if response.status_code in [200, 206, 302, 301]:
                # 可选：检查Content-Type
                content_type = response.headers.get('Content-Type', '').lower()
                valid_types = ['application/vnd.apple.mpegurl', 'video/', 'application/octet-stream']
                
                if any(vtype in content_type for vtype in valid_types) or not content_type:
                    return True
            
        except Exception as e:
            logger.debug(f"[{self.site_name}] 链接验证失败 {channel.url}: {e}")
        
        return False
    
    def _is_valid_url(self, url: str) -> bool:
        """检查URL是否有效"""
        if not url or len(url) < 10:
            return False
        
        # 检查协议
        if not url.startswith(('http://', 'https://', 'rtmp://', 'rtsp://')):
            return False
        
        # 检查是否包含流媒体格式
        stream_extensions = ['.m3u8', '.ts', '.flv', '.mp4']
        return any(ext in url.lower() for ext in stream_extensions)


class AnotherExampleSearcher(BaseIPTVSearcher):
    """
    另一个示例搜索器
    展示不同的实现方式
    """
    
    def __init__(self, config: SearchConfig = None):
        self.site_name = "另一个示例站点"
        self.base_url = "https://another-example.com"
        super().__init__(config)
    
    def _setup_session(self):
        """针对特定站点的会话配置"""
        self.session = requests.Session()
        
        # 某些站点可能需要特殊的请求头
        self.session.headers.update({
            'User-Agent': 'IPTVSearchBot/1.0',
            'X-API-Key': 'your-api-key-if-needed',  # 如果需要API密钥
            'Accept': 'application/json',
        })
    
    def _send_search_request(self, keyword: str, page: int = 1) -> str:
        """API风格的搜索请求"""
        api_endpoint = f"{self.base_url}/api/search"
        
        payload = {
            'query': keyword,
            'page': page,
            'limit': 20,
            'category': 'live_tv'
        }
        
        try:
            response = self.session.post(
                api_endpoint,
                json=payload,  # 发送JSON数据
                timeout=self.config.timeout
            )
            
            response.raise_for_status()
            return response.text
            
        except Exception as e:
            logger.error(f"[{self.site_name}] API请求失败: {e}")
            return ""
    
    def _parse_search_results(self, json_content: str, keyword: str) -> List[IPTVChannel]:
        """解析JSON API响应"""
        channels = []
        
        try:
            import json
            data = json.loads(json_content)
            
            for item in data.get('channels', []):
                channel = IPTVChannel(
                    name=item.get('name', keyword),
                    url=item.get('stream_url', ''),
                    resolution=f"{item.get('resolution', {}).get('height', 0)}p",
                    source=self.site_name
                )
                
                if channel.url:
                    channels.append(channel)
                    
        except Exception as e:
            logger.error(f"[{self.site_name}] JSON解析失败: {e}")
        
        return channels
    
    def _validate_link(self, channel: IPTVChannel) -> bool:
        """简单的链接验证"""
        return channel.url and channel.url.startswith(('http', 'rtmp', 'rtsp'))


# 注册示例搜索器到工厂
def register_example_searchers():
    """注册示例搜索器"""
    SearcherFactory.register_searcher("example", ExampleSearcher)
    SearcherFactory.register_searcher("another_example", AnotherExampleSearcher)
    logger.info("示例搜索器已注册")


if __name__ == "__main__":
    # 演示如何使用新的搜索器
    print("=" * 50)
    print("新搜索器使用演示")
    print("=" * 50)
    
    # 注册搜索器
    register_example_searchers()
    
    # 显示所有可用搜索器
    print("可用搜索器:")
    for name in SearcherFactory.list_searchers():
        print(f"  - {name}")
    
    # 创建配置
    config = SearchConfig(
        max_results=5,
        timeout=10,
        enable_validation=False  # 示例搜索器，关闭验证
    )
    
    # 使用示例搜索器
    try:
        searcher = SearcherFactory.create_searcher("example", config)
        print(f"\n使用搜索器: {searcher.get_site_info()}")
        
        # 注意：这只是演示，实际的example站点不存在
        # 真实使用时需要配置正确的站点URL和解析逻辑
        print("注意：这只是代码结构演示，实际站点需要真实配置")
        
    except Exception as e:
        print(f"创建搜索器失败: {e}")
    
    print("\n" + "=" * 50)
    print("添加新搜索器的步骤:")
    print("1. 继承 BaseIPTVSearcher 类")
    print("2. 实现必需的抽象方法:")
    print("   - _setup_session(): 配置HTTP会话")
    print("   - _send_search_request(): 发送搜索请求")
    print("   - _parse_search_results(): 解析搜索结果")
    print("   - _validate_link(): 验证链接有效性")
    print("3. 注册到 SearcherFactory")
    print("4. 在 ProcessorConfig 中指定搜索器名称")
    print("=" * 50)
