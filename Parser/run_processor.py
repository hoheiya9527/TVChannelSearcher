#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨平台IPTV频道批量处理启动脚本
替代Windows批处理文件，支持Linux/macOS/Windows
"""

import os
import sys
import time
import subprocess
import platform
from pathlib import Path


def print_banner():
    """显示程序横幅"""
    print("=" * 65)
    print("              IPTV频道批量处理工具")
    print("=" * 65)
    print("功能: 模块化架构 + 多站点支持 + 易于扩展")
    print("输入: LiveChannel.txt")
    print("输出: result.txt")
    print("预计用时: 1-2分钟 (72个频道，智能验证更快)")
    print("特性: 智能验证 + 域名频率排序 + 自动时间戳")
    print("✨ 新功能: 自动添加更新时间频道，方便播放器查看")
    print("=" * 65)
    print()


def check_python_version():
    """检查Python版本"""
    print("检查Python环境...")
    
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("错误：Python版本过低")
        print("请安装Python 3.8或更高版本")
        print(f"当前版本: {sys.version}")
        return False
    
    print(f"✅ Python环境正常: {platform.python_version()}")
    print(f"📍 运行平台: {platform.system()} {platform.release()}")
    return True


def check_input_files():
    """检查输入文件"""
    print("📁 检查输入文件...")
    
    input_files = ["LiveChannel.txt", "livechannel.txt"]
    found_file = None
    
    for filename in input_files:
        if os.path.exists(filename):
            found_file = filename
            break
    
    if not found_file:
        print("❌ 错误：未找到输入文件")
        print(f"请确保以下文件之一存在于当前目录:")
        for filename in input_files:
            print(f"  - {filename}")
        return False, None
    
    print(f"✅ 找到输入文件: {found_file}")
    
    # 显示文件信息
    try:
        with open(found_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            channel_count = len([line for line in lines if line.strip() and not line.startswith('#')])
            group_count = len([line for line in lines if line.strip().startswith('#')])
            
        print(f"📊 频道统计: {group_count} 个分组, {channel_count} 个频道")
        
    except Exception as e:
        print(f"⚠️  读取文件信息失败: {e}")
    
    return True, found_file


def install_dependencies():
    """安装Python依赖包"""
    print("📦 检查并安装依赖包...")
    
    requirements_file = "requirements.txt"
    if not os.path.exists(requirements_file):
        print(f"⚠️  未找到依赖文件: {requirements_file}")
        return True  # 继续执行，可能依赖已经安装
    
    try:
        # 使用subprocess运行pip install
        cmd = [sys.executable, "-m", "pip", "install", "-r", requirements_file, "--quiet"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("✅ 依赖安装完成")
            return True
        else:
            print("⚠️  依赖安装失败，但将尝试继续运行...")
            if result.stderr:
                print(f"错误信息: {result.stderr.strip()}")
            return True  # 继续执行
            
    except subprocess.TimeoutExpired:
        print("⚠️  依赖安装超时，但将尝试继续运行...")
        return True
    except Exception as e:
        print(f"⚠️  依赖安装异常: {e}")
        return True


def run_main_processor():
    """执行主处理程序"""
    print("🚀 开始执行批量处理...")
    print("🔧 使用模块化搜索器架构，支持多站点扩展")
    print()
    
    start_time = time.time()
    
    try:
        # 执行主程序
        main_script = "modular_batch_processor.py"
        
        if not os.path.exists(main_script):
            print(f"❌ 错误：未找到主程序文件 {main_script}")
            return False
        
        # 使用subprocess执行主程序
        result = subprocess.run([sys.executable, main_script], 
                              capture_output=False, text=True)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        if result.returncode == 0:
            print()
            print("✅ 批量处理完成！")
            print(f"⚡ 处理时间: {processing_time:.2f} 秒")
            return True
        else:
            print()
            print(f"❌ 处理失败，错误代码: {result.returncode}")
            return False
            
    except Exception as e:
        print(f"❌ 执行异常: {e}")
        return False


def check_results():
    """检查处理结果"""
    print("📊 检查处理结果...")
    
    output_file = "result.txt"
    
    if not os.path.exists(output_file):
        print("⚠️  未找到结果文件")
        return False
    
    try:
        # 获取文件信息
        file_size = os.path.getsize(output_file)
        
        # 统计内容
        with open(output_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            total_lines = len(lines)
            link_count = len([line for line in lines if 'http' in line])
            group_count = len([line for line in lines if '#genre#' in line])
        
        print(f"📁 结果文件已生成: {output_file}")
        print(f"📊 文件大小: {file_size:,} 字节")
        print(f"📊 总行数: {total_lines:,}")
        print(f"📊 有效链接: {link_count:,} 个")
        print(f"📊 频道分组: {group_count:,} 个")
        print("🔧 使用模块化架构，支持多站点扩展")
        
        # 显示结果预览
        if total_lines > 0:
            print()
            print("💡 结果文件预览 (前10行):")
            for i, line in enumerate(lines[:10], 1):
                print(f"  {i:2d}: {line.rstrip()}")
            
            if total_lines > 10:
                print(f"  ... (共 {total_lines} 行)")
        
        print()
        print("💡 扩展指南：")
        print("   - 查看 示例_新搜索器.py 学习如何添加新站点")
        print("   - 修改 ProcessorConfig 调整搜索参数")
        print("   - 支持动态切换不同的搜索器")
        
        return True
        
    except Exception as e:
        print(f"❌ 检查结果文件失败: {e}")
        return False


def main():
    """主程序入口"""
    # 显示横幅
    print_banner()
    
    # 检查Python版本
    if not check_python_version():
        return 1
    
    print()
    
    # 检查输入文件
    success, input_file = check_input_files()
    if not success:
        return 1
    
    print()
    
    # 安装依赖
    if not install_dependencies():
        return 1
    
    print()
    
    # 执行主处理程序
    if not run_main_processor():
        return 1
    
    # 检查结果
    if not check_results():
        return 1
    
    print()
    print("🎉 所有任务完成！")
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  用户中断执行")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")
        sys.exit(1)
