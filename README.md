# Twitter to Feishu Bot

自动获取 X.com (Twitter) 用户推文，翻译为中文并发送到飞书的机器人。

## 功能

- 获取**多个** Twitter 用户的最新推文
- 将推文自动翻译成中文
- 通过飞书发送翻译后的推文到**多个**手机号
- 支持持续监控，自动推送新推文
- 避免重复发送，智能记录已处理推文
- 支持 GitHub Actions 定时运行（每 15 分钟）

## 项目结构

```
twitter-to-feishu-bot/
├── .github/
│   └── workflows/
│       └── bot.yml          # GitHub Actions 工作流配置
├── config.py                # 配置文件（支持多账户）
├── main.py                  # 主程序入口
├── twitter_client.py        # Twitter 客户端（Nitter RSS）
├── translator.py            # 翻译模块
├── feishu_client.py         # 飞书 API 客户端
├── storage.py               # 数据存储模块
├── requirements.txt         # Python 依赖
├── .env.example             # 环境变量模板
├── README.md                # 项目说明
└── .gitignore               # Git 忽略文件
```

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/yourusername/twitter-to-feishu-bot.git
cd twitter-to-feishu-bot
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env`，并填写你的配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# ============================================
# 多账户配置 (JSON 格式)
# ============================================
# 监控多个 Twitter 用户，每个用户可以发送到多个手机号
ACCOUNTS_JSON='[
  {"twitter_user":"aleabitoreddit","phones":["13xxxxxxxxx"]},
  {"twitter_user":"elonmusk","phones":["13xxxxxxxxx","13900139000"]}
]'

# ============================================
# 飞书应用凭证 (必须)
# ============================================
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 4. 运行程序

```bash
python main.py
```

选择运行模式：
- `1` - 单次运行：获取一次推文并发送
- `2` - 持续运行：定时检查新推文
- `3` - 发送测试消息：验证飞书配置

## 多账户配置说明

### 方式1: 环境变量 JSON（推荐用于 GitHub Actions）

在 `.env` 或 GitHub Secrets 中设置 `ACCOUNTS_JSON`：

```json
[
  {"twitter_user": "aleabitoreddit", "phones": ["13xxxxxxxxx"]},
  {"twitter_user": "elonmusk", "phones": ["13xxxxxxxxx", "13900139000"]},
  {"twitter_user": "NASA", "phones": ["13xxxxxxxxx"]}
]
```

### 方式2: 修改 config.py

编辑 `config.py` 中的 `DEFAULT_ACCOUNTS`：

```python
DEFAULT_ACCOUNTS = [
    {
        "twitter_user": "aleabitoreddit",
        "phones": ["13xxxxxxxxx"]
    },
    {
        "twitter_user": "elonmusk",
        "phones": ["13xxxxxxxxx", "13900139000"]
    },
]
```

### 配置说明

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `twitter_user` | Twitter 用户名（不含 @） | `aleabitoreddit` |
| `phones` | 接收消息的手机号列表 | `["13xxxxxxxxx", "13900139000"]` |

## GitHub Actions 部署

### 1. 创建 GitHub 仓库

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/yourusername/twitter-to-feishu-bot.git
git push -u origin main
```

### 2. 配置 GitHub Secrets

进入仓库 **Settings > Secrets and variables > Actions > New repository secret**，添加以下 Secrets：

| Secret 名称 | 说明 | 示例 |
|------------|------|------|
| `ACCOUNTS_JSON` | 多账户配置 JSON | `[{"twitter_user":"aleabitoreddit","phones":["13xxxxxxxxx"]}]` |
| `FEISHU_APP_ID` | 飞书应用 ID | `cli_xxxxxxxxxxxxxxxx` |
| `FEISHU_APP_SECRET` | 飞书应用密钥 | `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `TWEETS_COUNT` | 每次获取推文数（可选） | `10` |
| `TRANSLATOR_ENGINE` | 翻译引擎（可选） | `google` |

### 3. 启用 GitHub Actions

工作流文件已包含在 `.github/workflows/bot.yml` 中，推送代码后会自动启用。

- 每 **15 分钟**自动运行一次
- 支持手动触发（点击 Actions 页面的 "Run workflow"）
- 运行日志可在 Actions 页面查看

### GitHub Actions 工作流说明

```yaml
# .github/workflows/bot.yml
name: Twitter to Feishu Bot

on:
  schedule:
    - cron: '*/15 * * * *'  # 每 15 分钟
  workflow_dispatch:         # 允许手动触发

jobs:
  run-bot:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python main.py
        env:
          ACCOUNTS_JSON: ${{ secrets.ACCOUNTS_JSON }}
          FEISHU_APP_ID: ${{ secrets.FEISHU_APP_ID }}
          FEISHU_APP_SECRET: ${{ secrets.FEISHU_APP_SECRET }}
```

## 配置说明

### Twitter 获取方式

本项目使用 **Nitter RSS** 获取推文，**无需 Twitter API**：
- 免登录、免申请
- 通过 `https://nitter.net/{username}/rss` 获取公开推文
- 如果 nitter.net 不可用，会自动尝试其他 Nitter 实例

### 飞书配置

1. 访问 [飞书开放平台](https://open.feishu.cn/app)
2. 创建企业自建应用
3. 开启机器人能力
4. 获取 App ID 和 App Secret
5. 将应用发布到目标用户可见范围

### 翻译配置

默认使用 Google 翻译（免费，无需配置）。

如需使用其他翻译引擎，设置环境变量 `TRANSLATOR_ENGINE`：
- `google` - Google 翻译（默认）
- `baidu` - 百度翻译（需配置 `BAIDU_APP_ID` 和 `BAIDU_SECRET_KEY`）
- `deepl` - DeepL 翻译（需配置 `DEEPL_API_KEY`）

## 本地部署建议

### 使用 systemd (Linux)

创建服务文件 `/etc/systemd/system/twitter-to-feishu-bot.service`：

```ini
[Unit]
Description=Twitter to Feishu Bot
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/twitter-to-feishu-bot
Environment=FEISHU_APP_ID=your_app_id
Environment=FEISHU_APP_SECRET=your_app_secret
Environment=ACCOUNTS_JSON=[{"twitter_user":"aleabitoreddit","phones":["13xxxxxxxxx"]}]
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl enable twitter-to-feishu-bot
sudo systemctl start twitter-to-feishu-bot
```

## 常见问题

### Q: 如何添加更多 Twitter 账户？

A: 修改 `ACCOUNTS_JSON` 环境变量，添加更多对象到数组中：

```json
[
  {"twitter_user": "aleabitoreddit", "phones": ["13xxxxxxxxx"]},
  {"twitter_user": "elonmusk", "phones": ["13xxxxxxxxx"]},
  {"twitter_user": "NASA", "phones": ["13xxxxxxxxx", "13900139000"]}
]
```

### Q: 一个手机号可以接收多个账户的推文吗？

A: 可以！只需在不同账户的 `phones` 数组中添加相同的手机号。

### Q: GitHub Actions 运行失败？

A: 检查以下几点：
- GitHub Secrets 是否正确设置
- `ACCOUNTS_JSON` 格式是否正确（有效的 JSON）
- 飞书应用是否已发布
- 目标用户是否在应用可用范围内

### Q: 如何避免重复发送？

A: 程序会自动记录已处理的推文 ID 到 `processed_tweets.json`，GitHub Actions 每次运行都会读取此文件。建议将 `processed_tweets.json` 提交到仓库，或使用外部存储。

### Q: Nitter 无法访问？

A: 程序会自动尝试多个 Nitter 实例。如果全部不可用，可以：
- 等待一段时间后重试
- 在 `twitter_client.py` 中添加新的 Nitter 实例
- 考虑使用 Twitter API 作为备用方案

## 技术栈

- Python 3.8+
- requests - HTTP 请求
- beautifulsoup4 - HTML 解析
- deep-translator - 翻译库
- python-dotenv - 环境变量管理
- schedule - 定时任务（本地运行）

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 免责声明

本项目仅供学习和个人使用，请遵守 Twitter 和飞书的使用条款。使用本项目产生的任何后果由使用者自行承担。
