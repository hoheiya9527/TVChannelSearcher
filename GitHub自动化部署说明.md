# GitHub自动化部署说明

## 🎯 功能概述

本项目已配置GitHub Actions自动化工作流，可以实现：

- ✅ **定时自动执行** - 每天北京时间14:00自动运行频道搜索
- ✅ **智能更新检测** - 只有在result.txt有变化时才提交
- ✅ **跨平台兼容** - 支持Linux/Windows/macOS环境
- ✅ **错误处理** - 完整的错误处理和日志记录
- ✅ **手动触发** - 支持手动执行工作流
- ✅ **状态通知** - 详细的执行状态和统计信息
- ✅ **自动时间戳** - 自动在第一个频道前添加更新时间频道，方便播放器查看

## 🚀 快速开始

### 1. 部署到GitHub

1. **Fork或创建仓库**：
   ```bash
   # 如果是新项目，创建仓库并上传代码
   git init
   git add .
   git commit -m "初始提交：IPTV频道搜索工具"
   git remote add origin https://github.com/你的用户名/你的仓库名.git
   git push -u origin main
   ```

2. **确保文件结构**：
   ```
   你的仓库/
   ├── .github/workflows/auto-update-channels.yml  # GitHub Actions配置
   ├── LiveChannel.txt                            # 频道列表文件
   ├── modular_batch_processor.py                 # 主处理程序
   ├── searcher_interface.py                      # 搜索器接口
   ├── tonkiang_searcher.py                       # Tonkiang搜索器
   ├── run_processor.py                           # 跨平台启动脚本
   ├── requirements.txt                           # Python依赖
   └── 其他文件...
   ```

### 2. 配置GitHub Actions权限

GitHub Actions默认有足够权限进行自动提交，无需额外配置。

### 3. 测试自动化

1. **手动触发测试**：
   - 进入GitHub仓库页面
   - 点击 `Actions` 标签
   - 选择 `自动更新IPTV频道列表` 工作流
   - 点击 `Run workflow` 按钮手动执行

2. **查看执行日志**：
   - 在Actions页面查看工作流执行状态
   - 点击具体的执行记录查看详细日志

## ⏰ 执行计划

### 默认执行时间
- **定时执行**：每天两次自动执行
  - 北京时间06:00（UTC时间22:00）
  - 北京时间16:00（UTC时间08:00）
- **触发条件**：自动检测到频道列表需要更新时

### 修改执行时间
编辑 `.github/workflows/auto-update-channels.yml` 文件中的cron表达式：

```yaml
schedule:
  # 每天两次执行（北京时间）
  - cron: '0 22 * * *'  # UTC 22:00（北京时间06:00）
  - cron: '0 8 * * *'   # UTC 08:00（北京时间16:00）
  
  # 其他时间配置示例（北京时间）：
  # 单次执行：
  # - cron: '0 0 * * *'    # UTC 00:00（北京时间08:00）
  # - cron: '0 12 * * *'   # UTC 12:00（北京时间20:00）
  # - cron: '0 14 * * *'   # UTC 14:00（北京时间22:00）
  # 
  # 特殊时间：
  # - cron: '0 22 * * 1'   # 每周一北京时间06:00
  # - cron: '0 22 1 * *'   # 每月1日北京时间06:00
  #
  # 三次执行示例（北京时间）：
  # - cron: '0 22 * * *'   # 北京时间06:00
  # - cron: '0 4 * * *'    # 北京时间12:00
  # - cron: '0 10 * * *'   # 北京时间18:00
  
  # 时区转换提示：北京时间 = UTC时间 + 8小时
```

## 🔧 自定义配置

### 1. 修改搜索参数

编辑 `modular_batch_processor.py` 中的配置：

```python
config = ProcessorConfig(
    searcher_name="tonkiang",           # 搜索器名称
    max_results_per_channel=10,         # 每频道最大链接数
    search_timeout=15,                  # 搜索超时时间
    min_resolution=0,                   # 最小分辨率要求
    enable_validation=True,             # 启用链接验证
    enable_cache=True,                  # 启用缓存
    concurrent_groups=2,                # 并发分组数
    max_workers_per_group=4             # 每分组并发数
)
```

### 2. 添加新的搜索器

参考 `示例_新搜索器.py` 添加新的站点支持。

### 3. 修改通知设置

在 `.github/workflows/auto-update-channels.yml` 中可以添加邮件或其他通知方式。

## ⏰ 时间戳功能

### 自动时间戳频道
系统会自动在result.txt的第一个频道前添加一个特殊的时间戳频道：

**格式**: `更新时间(yyMMddHHmm),链接`
**示例**: `更新时间(2401151430),http://example.com/stream.m3u8`

**优势**:
- 🕒 在播放器中直接显示最后更新时间
- 📱 无需打开文件即可查看更新状态  
- 🔄 每次自动更新都会刷新时间戳
- 🎯 使用第一个有效频道的链接，确保可正常播放

**时间格式说明**:
- `yy` - 年份后两位（如：24代表2024年）
- `MM` - 月份（01-12）
- `dd` - 日期（01-31）
- `HH` - 小时（00-23）
- `mm` - 分钟（00-59）

## 📊 执行结果

### 自动提交信息格式
```
🔄 自动更新IPTV频道列表 - 2024-01-15 14:30:25 UTC

📊 更新统计:
- 频道分组: 12 个  
- 有效链接: 368 个
- 文件大小: 45.2K
- 更新时间: 2024-01-15 14:30:25 UTC
```

### 查看更新历史
- 在GitHub仓库的 `Commits` 页面查看自动提交历史
- 每次提交都包含详细的统计信息
- 可以比较不同版本的result.txt文件

## 🛠 故障排除

### 1. 工作流执行失败

**检查步骤**：
1. 查看Actions页面的错误日志
2. 确认LiveChannel.txt文件存在且格式正确
3. 检查网络连接（GitHub Actions环境访问外部网站）

**常见问题**：
- `requirements.txt` 中的依赖包版本不兼容
- 网络超时或目标站点不可访问
- Python代码中的语法错误

### 2. 没有自动提交

**可能原因**：
- result.txt文件没有变化
- Git配置问题
- 权限不足

**解决方案**：
```bash
# 本地测试脚本
python run_processor.py

# 检查生成的result.txt是否正常
```

### 3. 执行时间问题

确认时区设置：
- GitHub Actions使用UTC时间
- 需要转换为本地时区
- 北京时间 = UTC时间 + 8小时

## 🎛 高级配置

### 1. 添加Webhook通知

在工作流中添加通知步骤：

```yaml
- name: 发送通知
  if: steps.check_changes.outputs.has_changes == 'true'
  run: |
    # 添加你的通知逻辑
    # 例如：发送到Slack、微信、邮件等
```

### 2. 多分支策略

```yaml
on:
  schedule:
    - cron: '0 6 * * *'
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]
```

### 3. 条件执行

```yaml
- name: 检查是否工作日
  run: |
    if [ $(date +%u) -le 5 ]; then
      echo "工作日，执行任务"
    else
      echo "周末，跳过执行"
      exit 0
    fi
```

## 📱 本地开发

### 使用跨平台脚本

```bash
# Linux/macOS
python3 run_processor.py

# Windows
python run_processor.py
```

### 使用原始批处理文件（仅Windows）

```cmd
一键执行.bat
```

## 🔍 监控和日志

### 1. GitHub Actions日志
- 每次执行的完整日志都保存在Actions页面
- 包含详细的执行步骤和错误信息
- 日志保留期限遵循GitHub政策

### 2. 执行统计
- 执行时间统计
- 成功/失败率
- 生成的链接数量趋势

### 3. 结果对比
- 自动记录每次更新的统计信息
- 可以追踪频道链接的变化趋势
- 便于分析搜索质量

## 💡 最佳实践

1. **定期检查日志** - 确保自动化正常运行
2. **监控结果质量** - 关注有效链接数量的变化
3. **及时更新依赖** - 保持Python包的版本更新
4. **备份重要配置** - 定期备份频道列表和配置文件
5. **测试新功能** - 在添加新搜索器前先本地测试

## 🆘 获取帮助

如果遇到问题：

1. 查看GitHub Actions的执行日志
2. 检查项目的Issues页面
3. 确认LiveChannel.txt格式正确
4. 尝试手动执行脚本进行调试

---

**注意**：首次设置后，建议手动触发一次工作流来测试是否正常工作。
