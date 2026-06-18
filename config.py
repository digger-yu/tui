"""
配置文件 - 所有配置项的定义和默认值
实际值通过环境变量或 .env 文件传入

配置优先级: 环境变量 > .env 文件 > 默认值
GitHub Actions: 配置直接写在 .github/workflows/bot.yml 的 env 中
本地运行: 复制 .env.example 为 .env，填写实际值
"""
import os
import json

# ==================== 多账户配置 ====================
# 格式: [{"twitter_user": "用户名", "send_mode": "webhook/api", "phones": ["手机号"]}]
# send_mode: "webhook" 发到群(需配 FEISHU_WEBHOOK_URL), "api" 私聊(需配 APP_ID/APP_SECRET + phones)

DEFAULT_ACCOUNTS = [
    {
        "twitter_user": "aleabitoreddit",
        "send_mode": "webhook",
        "phones": ["13xxxxxxxxx"]
    },
]

_accounts_json = os.getenv("ACCOUNTS_JSON", "")
if _accounts_json:
    try:
        ACCOUNTS = json.loads(_accounts_json)
    except json.JSONDecodeError:
        print("警告: ACCOUNTS_JSON 环境变量格式错误，使用默认配置")
        ACCOUNTS = DEFAULT_ACCOUNTS
else:
    ACCOUNTS = DEFAULT_ACCOUNTS

# ==================== 飞书配置 ====================
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "")
FEISHU_WEBHOOK_SECRET = os.getenv("FEISHU_WEBHOOK_SECRET", "")

# ==================== 翻译配置 ====================
TRANSLATOR_ENGINE = os.getenv("TRANSLATOR_ENGINE", "google")
BAIDU_APP_ID = os.getenv("BAIDU_APP_ID", "")
BAIDU_SECRET_KEY = os.getenv("BAIDU_SECRET_KEY", "")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "")

# ==================== 程序配置 ====================
TWEETS_COUNT = int(os.getenv("TWEETS_COUNT", "10"))
POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "300"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DATA_FILE = os.getenv("DATA_FILE", "processed_tweets.json")
