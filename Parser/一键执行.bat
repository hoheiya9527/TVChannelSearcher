@echo off
chcp 65001 >nul 2>&1
setlocal
title IPTV频道批量搜索工具

echo =========================================================
echo              IPTV频道批量处理工具
echo =========================================================
echo 功能: 模块化架构 + 多站点支持 + 易于扩展
echo 输入: LiveChannel.txt
echo 输出: result.txt
echo 预计用时: 1-2分钟 (72个频道，智能验证更快)
echo 特性: 智能验证 + 域名频率排序 + 提前终止
echo =========================================================
echo.

:: 检查Python环境
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误：未找到Python环境
    echo 请确保已安装Python 3.12或更高版本
    pause
    exit /b 1
)

:: 检查输入文件
if not exist "LiveChannel.txt" (
    if not exist "livechannel.txt" (
        echo ❌ 错误：未找到输入文件 LiveChannel.txt 或 livechannel.txt
        echo 请确保频道列表文件存在于当前目录
        pause
        exit /b 1
    )
)

:: 安装依赖
echo 📦 正在检查并安装依赖包...
python -m pip install -r requirements.txt --quiet

if %errorlevel% neq 0 (
    echo ⚠️  依赖安装失败，但将尝试继续运行...
)

echo.
echo 🚀 开始执行批量处理...
echo 🔧 使用模块化搜索器架构，支持多站点扩展
echo.

:: 记录开始时间
set start_time=%time%

:: 执行主程序
python modular_batch_processor.py

:: 记录结束时间并计算耗时
set end_time=%time%

:: 检查结果
if %errorlevel% equ 0 (
    echo.
    echo ✅ 批量处理完成！
    echo ⚡ 处理时间: %start_time% - %end_time%
    if exist "result.txt" (
        echo 📁 结果文件已生成: result.txt
        for %%A in (result.txt) do echo 📊 文件大小: %%~zA 字节
        echo 🔧 使用模块化架构，支持多站点扩展
        echo.
        echo 💡 扩展指南：
        echo   - 查看 示例_新搜索器.py 学习如何添加新站点
        echo   - 修改 ProcessorConfig 调整搜索参数
        echo   - 支持动态切换不同的搜索器
    ) else (
        echo ⚠️  未找到结果文件
    )
) else (
    echo.
    echo ❌ 处理失败，错误代码: %errorlevel%
)

echo.
echo 按任意键退出...
pause >nul
