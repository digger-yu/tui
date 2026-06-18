"""
配置文件 - 存储所有敏感信息和配置项
支持多 Twitter 账户和多手机号
"""
import os
import json

# ==================== X.com (Twitter) 配置 ====================
# 方式1: 使用 Twitter API v2 (推荐，稳定但需申请)
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET", "")

# 方式2: 使用第三方 Twitter API 服务
TWITTER_PROXY_API_KEY = os.getenv("TWITTER_PROXY_API_KEY", "")
TWITTER_PROXY_API_URL = os.getenv("TWITTER_PROXY_API_URL", "https://api.twexapi.io")

# ==================== 多账户配置 ====================
# 监控的 Twitter 用户列表和对应的目标手机号
# 格式: [{"twitter_user": "用户名", "phones": ["手机号1", "手机号2"]}, ...]
# 可以从环境变量读取 JSON 字符串，或使用下面的默认配置

DEFAULT_ACCOUNTS = [
    {
        "twitter_user": "aleabitoreddit",
        "phones": ["13xxxxxxxxx"]
    },
    # 添加更多账户示例:
    # {
    #     "twitter_user": "elonmusk",
    #     "phones": ["13xxxxxxxxx", "13900139000"]
    # },
    # {
    #     "twitter_user": "NASA",
    #     "phones": ["13xxxxxxxxx"]
    # },
]

# 从环境变量读取多账户配置 (JSON 格式)
# 示例: ACCOUNTS_JSON='[{"twitter_user":"aleabitoreddit","phones":["13xxxxxxxxx"]}]'
_accounts_json = os.getenv("ACCOUNTS_JSON", "")
if _accounts_json:
    try:
        ACCOUNTS = json.loads(_accounts_json)
    except json.JSONDecodeError:
        print("警告: ACCOUNTS_JSON 环境变量格式错误，使用默认配置")
        ACCOUNTS = DEFAULT_ACCOUNTS
else:
    ACCOUNTS = DEFAULT_ACCOUNTS

# 兼容旧版单用户配置
TARGET_TWITTER_USER = os.getenv("TARGET_TWITTER_USER", "aleabitoreddit")
TARGET_PHONE = os.getenv("TARGET_PHONE", "13xxxxxxxxx")

# 如果环境变量设置了单用户但没有设置多账户，自动转换
if not _accounts_json and (TARGET_TWITTER_USER or TARGET_PHONE):
    ACCOUNTS = [{
        "twitter_user": TARGET_TWITTER_USER,
        "phones": [TARGET_PHONE] if TARGET_PHONE else []
    }]

# 每次获取的推文数量 (最大 100)
TWEETS_COUNT = int(os.getenv("TWEETS_COUNT", "1"))

# ==================== 翻译配置 ====================
TRANSLATOR_ENGINE = os.getenv("TRANSLATOR_ENGINE", "google")  # google, baidu, deepl

BAIDU_APP_ID = os.getenv("BAIDU_APP_ID", "")
BAIDU_SECRET_KEY = os.getenv("BAIDU_SECRET_KEY", "")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "")

# ==================== 飞书配置 ====================
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "")

# ==================== 程序配置 ====================
POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "300"))  # 秒
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DATA_FILE = os.getenv("DATA_FILE", "processed_tweets.json")
