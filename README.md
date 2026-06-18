# Twitter to Feishu Bot

自动获取 X.com (Twitter) 用户推文，翻译为中文并发送到飞书的机器人。

## 功能

- 获取**多个** Twitter 用户的最新推文（通过 Nitter RSS，无需 Twitter API）
- 将推文自动翻译成中文（Google 翻译，免费无需配置）
- 支持两种发送方式：**Webhook 群消息** 和 **应用 API 私聊**
- 每个账户可独立选择发送方式
- 避免重复发送，自动记录已处理推文
- 支持 GitHub Actions 定时运行（每 15 分钟）

## 项目结构

```
twitter-to-feishu-bot/
├── .github/workflows/bot.yml  # GitHub Actions 工作流
├── config.py                   # 配置定义（从环境变量读取）
├── main.py                     # 主程序入口
├── twitter_client.py           # Twitter 客户端（Nitter RSS）
├── translator.py               # 翻译模块
├── feishu_client.py            # 飞书客户端（API + Webhook）
├── storage.py                  # 推文去重存储
├── requirements.txt            # Python 依赖
├── .env.example                # 环境变量模板
└── .gitignore
```

## 快速开始

### 方式1: GitHub Actions（推荐）

1. Fork 或创建 GitHub 仓库
2. 编辑 `.github/workflows/bot.yml`，填写实际配置值
3. 推送代码，定时任务自动运行

### 方式2: 本地运行

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填写配置
python main.py
```

## 配置说明

### 发送方式

| 模式 | 说明 | 需要配置 |
|------|------|---------|
| `webhook` | 发到飞书群（推荐） | `FEISHU_WEBHOOK_URL` |
| `api` | 私聊到手机号 | `FEISHU_APP_ID` + `FEISHU_APP_SECRET` + `phones` |

### 多账户配置

在 `bot.yml` 或 `.env` 中设置 `ACCOUNTS_JSON`：

```json
[
  {"twitter_user": "aleabitoreddit", "send_mode": "webhook"},
  {"twitter_user": "elonmusk", "send_mode": "api", "phones": ["13xxxxxxxxx"]}
]
```

| 字段 | 说明 | 必填 |
|------|------|------|
| `twitter_user` | Twitter 用户名（不含 @） | 是 |
| `send_mode` | `webhook` 或 `api` | 是 |
| `phones` | 手机号列表（仅 api 模式需要） | api 模式必填 |

### 飞书 Webhook 配置

1. 打开飞书群 → 设置 → 群机器人
2. 添加「自定义机器人」
3. 复制 Webhook 地址，填入 `FEISHU_WEBHOOK_URL`
4. 如果开启了签名校验，还需填写 `FEISHU_WEBHOOK_SECRET`

### 飞书应用 API 配置（可选）

1. 访问 [飞书开放平台](https://open.feishu.cn/app)
2. 创建企业自建应用，开启机器人能力
3. 获取 App ID 和 App Secret

## GitHub Actions 工作流

`.github/workflows/bot.yml` 核心配置：

```yaml
on:
  schedule:
    - cron: '*/15 * * * *'  # 每 15 分钟
  workflow_dispatch:         # 手动触发

jobs:
  run-bot:
    runs-on: ubuntu-latest
    permissions:
      contents: write         # 允许提交 processed_tweets.json
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - run: python main.py
        env:
          ACCOUNTS_JSON: '[{"twitter_user": "aleabitoreddit", "send_mode": "webhook"}]'
          FEISHU_WEBHOOK_URL: 'https://open.feishu.cn/open-apis/bot/v2/hook/xxx'
      - run: |
          git add -f processed_tweets.json
          git commit -m "Update processed tweets [skip ci]"
          git push
```

**注意：**
- `schedule` 只在仓库默认分支生效
- `processed_tweets.json` 每次运行后自动提交到仓库，用于跨运行去重
- 运行日志通过 Actions Artifacts 保留 7 天

## 常见问题

### Q: 定时任务没有自动运行？

- 确认 workflow 文件在默认分支（通常是 `main`）
- 去 Actions 页面检查是否有禁用提示
- Settings → Actions → General 确认权限设置正确
- 新 workflow 可能需要等待 1-2 小时才开始首次定时运行

### Q: Nitter 获取推文失败？

程序会自动尝试多个 Nitter 实例。如果全部不可用：
- 等待一段时间后重试（实例可能临时过载）
- 在 `twitter_client.py` 的 `NITTER_INSTANCES` 中添加新实例

### Q: Webhook 发送失败，提示 sign match fail？

飞书机器人开启了签名校验，需要配置 `FEISHU_WEBHOOK_SECRET`，或在机器人设置中关闭签名校验。

### Q: 如何避免重复发送？

程序自动将已处理的推文 ID 保存到 `processed_tweets.json`，GitHub Actions 每次运行后自动提交该文件到仓库，下次运行时加载。

## 技术栈

- Python 3.8+
- requests - HTTP 请求
- beautifulsoup4 - HTML 解析
- deep-translator - 翻译库
- python-dotenv - 环境变量管理

## 免责声明

本项目仅供学习和个人使用，请遵守 Twitter 和飞书的使用条款。
