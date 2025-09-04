#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块化IPTV批量处理器
使用模块化搜索器接口，支持多种站点切换
"""

import os
import time
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from urllib.parse import urlparse
from collections import Counter

# 导入搜索器接口和实现
from searcher_interface import BaseIPTVSearcher, IPTVChannel, SearchConfig, SearcherFactory
from tonkiang_searcher import TonkiangSearcher

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class ChannelGroup:
    """频道分组数据类"""
    name: str              # 分组名称
    channels: List[str]    # 频道名称列表


class ChannelFileParser:
    """频道文件解析器"""
    
    @staticmethod
    def parse_channel_file(filename: str = "LiveChannel.txt") -> List[ChannelGroup]:
        """
        解析频道列表文件
        
        Args:
            filename: 输入文件名
            
        Returns:
            List[ChannelGroup]: 解析出的频道分组列表
        """
        groups = []
        current_group = None
        
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 检查是否为分组标题（以#开头）
                    if line.startswith('#'):
                        # 如果有当前分组，先保存
                        if current_group and current_group.channels:
                            groups.append(current_group)
                        
                        # 创建新分组
                        group_name = line[1:].strip()  # 移除#号
                        current_group = ChannelGroup(name=group_name, channels=[])
                    
                    else:
                        # 频道名称
                        if current_group is None:
                            # 如果没有分组，创建默认分组
                            current_group = ChannelGroup(name="默认分组", channels=[])
                        
                        current_group.channels.append(line)
                
                # 保存最后一个分组
                if current_group and current_group.channels:
                    groups.append(current_group)
        
        except FileNotFoundError:
            logger.error(f"未找到输入文件: {filename}")
            raise
        except Exception as e:
            logger.error(f"解析文件失败: {e}")
            raise
        
        return groups


class DomainFrequencyProcessor:
    """域名频率处理器 - 根据域名/IP出现频率排序链接"""
    
    def __init__(self):
        self.domain_counter = Counter()
    
    def extract_domain_or_ip(self, url: str) -> str:
        """
        从URL中提取域名或IP地址
        
        Args:
            url: 输入URL
            
        Returns:
            str: 域名或IP地址
        """
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            
            if hostname:
                # 检查是否为IP地址
                ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
                if re.match(ip_pattern, hostname):
                    return hostname  # 返回IP地址
                else:
                    return hostname  # 返回域名
            
            return url  # 如果解析失败，返回原URL作为fallback
            
        except Exception:
            return url
    
    def collect_domain_stats(self, all_channels: Dict[str, Dict[str, List[IPTVChannel]]]):
        """
        收集所有链接的域名统计
        
        Args:
            all_channels: 所有频道数据
        """
        logger.info("开始统计域名/IP出现频率...")
        
        for group_name, group_channels in all_channels.items():
            for channel_name, channels in group_channels.items():
                for channel in channels:
                    domain = self.extract_domain_or_ip(channel.url)
                    self.domain_counter[domain] += 1
        
        logger.info(f"统计完成，发现 {len(self.domain_counter)} 个不同的域名/IP")
        
        # 显示Top 10域名/IP
        top_domains = self.domain_counter.most_common(10)
        logger.info("出现频率最高的域名/IP:")
        for i, (domain, count) in enumerate(top_domains, 1):
            logger.info(f"  {i:2d}. {domain} ({count} 次)")
    
    def sort_channels_by_domain_frequency(self, channels: List[IPTVChannel]) -> List[IPTVChannel]:
        """
        根据域名频率排序频道列表
        
        Args:
            channels: 原始频道列表
            
        Returns:
            List[IPTVChannel]: 按域名频率排序后的频道列表
        """
        if not channels:
            return channels
        
        def get_domain_frequency(channel: IPTVChannel) -> Tuple[int, str]:
            """获取域名频率，用于排序"""
            domain = self.extract_domain_or_ip(channel.url)
            frequency = self.domain_counter.get(domain, 0)
            # 返回负的频率值，这样频率高的会排在前面
            # 第二个值是域名，用于相同频率时的二级排序
            return (-frequency, domain)
        
        sorted_channels = sorted(channels, key=get_domain_frequency)
        
        # 记录排序结果
        if len(channels) > 1:
            logger.debug(f"频道排序: {channels[0].name}")
            for i, channel in enumerate(sorted_channels[:3], 1):  # 只显示前3个
                domain = self.extract_domain_or_ip(channel.url)
                frequency = self.domain_counter.get(domain, 0)
                logger.debug(f"  {i}. {domain} (频率: {frequency})")
        
        return sorted_channels


class ResultFormatter:
    """结果格式化器"""
    
    def __init__(self, domain_processor: DomainFrequencyProcessor = None):
        self.domain_processor = domain_processor
    
    def write_results_to_file(self, all_results: Dict[str, Dict[str, List[IPTVChannel]]], 
                            output_file: str = "result.txt", 
                            original_groups: List[ChannelGroup] = None) -> int:
        """
        将结果写入文件，按输入文件顺序排序，并在第一个频道前添加时间戳频道
        
        Args:
            all_results: 所有搜索结果
            output_file: 输出文件名
            original_groups: 原始频道分组列表（用于保持顺序）
            
        Returns:
            int: 总的有效链接数
        """
        total_links = 0
        
        # 获取第一个有效频道的链接，用于时间戳频道
        first_channel_url = self._get_first_valid_channel_url(all_results)
        
        # 生成时间戳频道名称（yyyy-MM-dd HH:mm格式，北京时间）
        beijing_tz = timezone(timedelta(hours=8))  # 北京时间 UTC+8
        timestamp = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M")
        timestamp_channel_name = f"更新时间({timestamp})"
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                is_first_group = True
                
                # 如果有原始分组信息，按照原始顺序输出
                if original_groups:
                    for group in original_groups:
                        group_name = group.name
                        
                        # 检查该分组是否有结果
                        if group_name not in all_results:
                            continue
                            
                        group_channels = all_results[group_name]
                        
                        # 写入分组标题
                        f.write(f"{group_name},#genre#\n")
                        
                        # 在第一个分组的第一个频道前添加时间戳频道
                        if is_first_group and first_channel_url:
                            f.write(f"{timestamp_channel_name},{first_channel_url}\n")
                            total_links += 1
                            logger.info(f"添加时间戳频道: {timestamp_channel_name}")
                            is_first_group = False
                        
                        # 按照输入文件中的频道顺序输出
                        for channel_name in group.channels:
                            if channel_name in group_channels:
                                channels = group_channels[channel_name]
                                if channels and len(channels) > 0:
                                    # 如果有域名处理器，按频率排序
                                    if self.domain_processor:
                                        channels = self.domain_processor.sort_channels_by_domain_frequency(channels)
                                    
                                    # 写入频道链接 - 有一个算一个
                                    for channel in channels:
                                        f.write(f"{channel.name},{channel.url}\n")
                                        total_links += 1
                                    logger.debug(f"输出频道 {channel_name}: {len(channels)} 个链接")
                                else:
                                    # 只有完全没有有效链接（0个）的频道才跳过
                                    logger.info(f"跳过无有效链接的频道: {channel_name}")
                                    continue
                else:
                    # 回退到原来的逻辑（如果没有原始分组信息）
                    for group_name, group_channels in all_results.items():
                        # 写入分组标题
                        f.write(f"{group_name},#genre#\n")
                        
                        # 在第一个分组的第一个频道前添加时间戳频道
                        if is_first_group and first_channel_url:
                            f.write(f"{timestamp_channel_name},{first_channel_url}\n")
                            total_links += 1
                            logger.info(f"添加时间戳频道: {timestamp_channel_name}")
                            is_first_group = False
                        
                        for channel_name, channels in group_channels.items():
                            if channels and len(channels) > 0:
                                # 如果有域名处理器，按频率排序
                                if self.domain_processor:
                                    channels = self.domain_processor.sort_channels_by_domain_frequency(channels)
                                
                                # 写入频道链接 - 有一个算一个
                                for channel in channels:
                                    f.write(f"{channel.name},{channel.url}\n")
                                    total_links += 1
                                logger.debug(f"输出频道 {channel_name}: {len(channels)} 个链接")
                            else:
                                # 只有完全没有有效链接（0个）的频道才跳过
                                logger.info(f"跳过无有效链接的频道: {channel_name}")
                                continue
            
            logger.info(f"结果已写入文件: {output_file}")
            logger.info(f"总计有效链接: {total_links} 个 (包含1个时间戳频道)")
            
            if self.domain_processor:
                logger.info("链接已按域名/IP出现频率排序，频率高的排在前面")
            
        except Exception as e:
            logger.error(f"写入结果文件失败: {e}")
            raise
        
        return total_links
    
    def _get_first_valid_channel_url(self, all_results: Dict[str, Dict[str, List[IPTVChannel]]]) -> Optional[str]:
        """
        获取第一个有效频道的链接，用于时间戳频道
        
        Args:
            all_results: 所有搜索结果
            
        Returns:
            Optional[str]: 第一个有效频道的URL，如果没有则返回None
        """
        for group_name, group_channels in all_results.items():
            for channel_name, channels in group_channels.items():
                if channels and len(channels) > 0:
                    # 返回第一个频道的第一个链接
                    return channels[0].url
        
        # 如果没有找到有效链接，返回一个默认的占位URL
        logger.warning("未找到有效频道链接，时间戳频道将使用占位链接")
        return "http://placeholder.example/timestamp.m3u8"


@dataclass
class ProcessorConfig:
    """批量处理器配置"""
    searcher_name: str = "tonkiang"      # 使用的搜索器名称
    input_file: str = "LiveChannel.txt"  # 输入文件
    output_file: str = "result.txt"      # 输出文件
    concurrent_groups: int = 2           # 并发处理的分组数
    max_workers_per_group: int = 4       # 每个分组的最大并发数
    
    # 搜索器配置
    max_results_per_channel: int = 10    # 每个频道最大结果数
    search_timeout: int = 15             # 搜索超时时间
    min_resolution: int = 0              # 最小分辨率要求 (0=不限制, 720=720p+, 1080=1080p+)
    enable_validation: bool = True       # 是否启用链接验证
    enable_cache: bool = True            # 是否启用搜索缓存
    min_valid_links: int = 5             # 每个频道最少有效链接数，达到后停止验证
    
    def to_search_config(self) -> SearchConfig:
        """转换为搜索器配置"""
        return SearchConfig(
            max_results=self.max_results_per_channel,
            timeout=self.search_timeout,
            min_resolution=self.min_resolution,
            enable_validation=self.enable_validation,
            enable_cache=self.enable_cache,
            concurrent_workers=self.max_workers_per_group,
            min_valid_links=self.min_valid_links
        )


class ModularBatchProcessor:
    """模块化批量处理器"""
    
    def __init__(self, config: ProcessorConfig = None):
        """
        初始化批量处理器
        
        Args:
            config: 处理器配置，如果为None则使用默认配置
        """
        self.config = config if config else ProcessorConfig()
        self.file_parser = ChannelFileParser()
        
        # 创建域名频率处理器
        self.domain_processor = DomainFrequencyProcessor()
        self.result_formatter = ResultFormatter(domain_processor=self.domain_processor)
        
        # 创建搜索器
        self.searcher = self._create_searcher()
        
        logger.info(f"模块化批量处理器已初始化，使用搜索器: {self.searcher.site_name}")
        logger.info("启用域名频率排序功能，高频域名/IP的链接将优先显示")
    
    def _create_searcher(self) -> BaseIPTVSearcher:
        """创建搜索器实例"""
        try:
            search_config = self.config.to_search_config()
            searcher = SearcherFactory.create_searcher(self.config.searcher_name, search_config)
            logger.info(f"搜索器创建成功: {searcher.get_site_info()}")
            return searcher
        except Exception as e:
            logger.error(f"创建搜索器失败: {e}")
            # 回退到默认的 Tonkiang 搜索器
            logger.info("回退到默认 Tonkiang 搜索器")
            return TonkiangSearcher(self.config.to_search_config())
    
    def switch_searcher(self, searcher_name: str):
        """
        切换搜索器
        
        Args:
            searcher_name: 新的搜索器名称
        """
        old_name = self.searcher.site_name
        try:
            self.config.searcher_name = searcher_name
            self.searcher = self._create_searcher()
            logger.info(f"搜索器切换成功: {old_name} -> {self.searcher.site_name}")
        except Exception as e:
            logger.error(f"切换搜索器失败: {e}")
            logger.info(f"保持使用原搜索器: {old_name}")
    
    def list_available_searchers(self) -> List[str]:
        """获取可用的搜索器列表"""
        return SearcherFactory.list_searchers()
    
    def process_single_channel(self, channel_name: str) -> List[IPTVChannel]:
        """
        处理单个频道
        
        Args:
            channel_name: 频道名称
            
        Returns:
            List[IPTVChannel]: 找到的有效频道列表
        """
        try:
            start_time = time.time()
            
            # 使用搜索器搜索频道
            channels = self.searcher.search_channels(channel_name)
            
            search_time = time.time() - start_time
            
            if channels:
                logger.info(f"    ✓ {channel_name}: {len(channels)} 个有效链接 ({search_time:.2f}s)")
            else:
                logger.warning(f"    ✗ {channel_name}: 无有效链接")
            
            return channels
            
        except Exception as e:
            logger.error(f"    ✗ {channel_name}: 处理失败 - {e}")
            return []
    
    def process_group_concurrent(self, group: ChannelGroup) -> Dict[str, List[IPTVChannel]]:
        """
        处理分组中的所有频道 - 支持串行和并发模式
        
        Args:
            group: 频道分组
            
        Returns:
            Dict[str, List[IPTVChannel]]: 频道名称到频道列表的映射
        """
        group_channels = {}
        
        # 检查是否强制串行模式（反爬虫需要）
        force_serial = self.config.max_workers_per_group == 1
        
        if force_serial:
            logger.info(f"  使用串行模式处理 {len(group.channels)} 个频道")
            # 串行处理，完全避免并发
            for i, channel_name in enumerate(group.channels, 1):
                logger.info(f"  [{i}/{len(group.channels)}] 处理频道: {channel_name}")
                try:
                    channels = self.process_single_channel(channel_name)
                    group_channels[channel_name] = channels
                    
                    # 频道间额外延迟（反爬虫）
                    if i < len(group.channels):  # 不是最后一个频道
                        import time
                        import random
                        delay = random.uniform(2.0, 5.0)
                        logger.debug(f"  频道间延迟 {delay:.1f}秒")
                        time.sleep(delay)
                        
                except Exception as e:
                    logger.error(f"    ✗ {channel_name}: 处理异常 - {e}")
                    group_channels[channel_name] = []
        else:
            # 原来的并发处理
            with ThreadPoolExecutor(max_workers=self.config.max_workers_per_group) as executor:
                # 提交所有搜索任务
                future_to_channel = {
                    executor.submit(self.process_single_channel, channel_name): channel_name
                    for channel_name in group.channels
                }
                
                # 收集结果
                for future in as_completed(future_to_channel):
                    channel_name = future_to_channel[future]
                    try:
                        channels = future.result()
                        group_channels[channel_name] = channels
                    except Exception as e:
                        logger.error(f"    ✗ {channel_name}: 处理异常 - {e}")
                        group_channels[channel_name] = []
        
        return group_channels
    
    def process_all_groups(self, groups: List[ChannelGroup]) -> Dict[str, Dict[str, List[IPTVChannel]]]:
        """
        处理所有分组
        
        Args:
            groups: 频道分组列表
            
        Returns:
            Dict[str, Dict[str, List[IPTVChannel]]]: 分组结果
        """
        all_results = {}
        
        # 串行处理分组（避免过高并发）
        for i, group in enumerate(groups, 1):
            logger.info(f"处理分组 {i}/{len(groups)}: {group.name} ({len(group.channels)} 个频道)")
            
            group_start_time = time.time()
            
            # 并发处理分组内的频道
            group_result = self.process_group_concurrent(group)
            
            group_time = time.time() - group_start_time
            valid_count = sum(len(channels) for channels in group_result.values())
            
            logger.info(f"    分组 {group.name} 完成: {valid_count} 个有效链接 ({group_time:.2f}s)")
            
            all_results[group.name] = group_result
        
        return all_results
    
    def run(self):
        """运行批量处理"""
        start_time = time.time()
        
        print("=" * 60)
        print("模块化IPTV频道批量搜索和链接提取工具")
        print(f"当前搜索器: {self.searcher.site_name}")
        print(f"验证策略: 每频道找到{self.config.min_valid_links}个有效链接后停止 (极简模式)")
        print(f"搜索配置: 最大{self.config.max_results_per_channel}链接/频道, "
              f"分辨率≥{self.config.min_resolution}p, 验证{'开启' if self.config.enable_validation else '关闭'}")
        print("智能特性: 跳过主页访问 + 直接搜索 + 完全串行")
        print("=" * 60)
        
        # 检查输入文件
        if not os.path.exists(self.config.input_file):
            input_files = ["LiveChannel.txt", "livechannel.txt"]
            found_file = None
            for file in input_files:
                if os.path.exists(file):
                    found_file = file
                    break
            
            if found_file:
                self.config.input_file = found_file
                logger.info(f"找到输入文件: {found_file}")
            else:
                logger.error(f"未找到输入文件: {input_files}")
                print(f"❌ 错误：未找到输入文件 {self.config.input_file}")
                return
        
        # 解析输入文件
        logger.info("1. 解析频道列表文件...")
        try:
            groups = self.file_parser.parse_channel_file(self.config.input_file)
            total_channels = sum(len(g.channels) for g in groups)
            logger.info(f"解析完成，共 {len(groups)} 个分组，{total_channels} 个频道")
            
            print(f"输入文件: {self.config.input_file}")
            print(f"频道分组: {len(groups)} 个")
            print(f"频道数量: {total_channels} 个")
            print(f"预计用时: {total_channels * 0.8:.0f} 秒 (模块化处理)")
            
        except Exception as e:
            logger.error(f"解析输入文件失败: {e}")
            print(f"❌ 解析输入文件失败: {e}")
            return
        
        print(f"\n🚀 自动开始模块化批量处理...")
        print("-" * 40)
        
        # 处理所有分组
        logger.info("2. 开始模块化搜索频道播放链接...")
        try:
            all_results = self.process_all_groups(groups)
        except Exception as e:
            logger.error(f"处理失败: {e}")
            print(f"❌ 处理失败: {e}")
            return
        
        # 统计域名频率
        logger.info("3. 统计域名/IP出现频率...")
        try:
            self.domain_processor.collect_domain_stats(all_results)
        except Exception as e:
            logger.warning(f"域名频率统计失败: {e}")
        
        # 生成结果文件（包含域名频率排序）
        logger.info("4. 生成结果文件...")
        try:
            total_valid = self.result_formatter.write_results_to_file(
                all_results, self.config.output_file, groups
            )
            
            processing_time = time.time() - start_time
            
            logger.info("=" * 60)
            logger.info("批量处理完成")
            logger.info(f"总用时: {processing_time:.2f} 秒")
            logger.info(f"有效链接: {total_valid} 个")
            logger.info(f"输出文件: {self.config.output_file}")
            logger.info("=" * 60)
            
            print(f"\n模块化处理完成！")
            print(f"总用时: {processing_time:.2f} 秒")
            print(f"有效链接: {total_valid} 个")
            print(f"结果文件: {self.config.output_file}")
            print(f"链接已按域名/IP频率智能排序")
            
            # 显示结果文件的前几行
            if os.path.exists(self.config.output_file):
                print(f"\n结果文件前10行预览:")
                with open(self.config.output_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()[:10]
                    for i, line in enumerate(lines, 1):
                        print(f"  {i:2d}: {line.rstrip()}")
                
                if len(lines) == 10:
                    with open(self.config.output_file, 'r', encoding='utf-8') as f:
                        total_lines = len(f.readlines())
                        print(f"  ... (共 {total_lines} 行)")
            
        except Exception as e:
            logger.error(f"生成结果文件失败: {e}")
            print(f"❌ 生成结果文件失败: {e}")


def main():
    """主程序入口"""
    
    # 显示可用的搜索器
    print("可用搜索器:")
    for name in SearcherFactory.list_searchers():
        print(f"  - {name}")
    print()
    
    # 使用正常并发配置 - 重新分析内容过短问题
    print("配置: 使用正常并发配置（分析内容过短问题）")
    config = ProcessorConfig(
        searcher_name="tonkiang",
        max_results_per_channel=8,     # 恢复正常请求数量
        search_timeout=30,             # 正常超时
        min_resolution=0,
        enable_validation=True,        # 启用验证
        enable_cache=True,
        concurrent_groups=2,           # 2个并发组
        max_workers_per_group=4,       # 每组3个工作线程
        min_valid_links=3              # 正常要求
    )
    
    # 创建并运行处理器
    processor = ModularBatchProcessor(config)
    processor.run()


if __name__ == "__main__":
    main()
