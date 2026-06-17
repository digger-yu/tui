"""
Twitter to Feishu Bot - 主程序

功能:
1. 定时获取多个 Twitter 用户的最新推文
2. 将推文翻译成中文
3. 通过飞书发送翻译后的推文到指定手机号

使用方法:
1. 复制 .env.example 为 .env，填写你的 API 密钥
2. 在 config.py 中配置多账户映射
3. 安装依赖: pip install -r requirements.txt
4. 运行程序: python main.py

GitHub Actions 使用:
- 设置环境变量 ACCOUNTS_JSON
- 设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET
- 工作流会每 15 分钟自动运行一次
"""
import os
import sys
import time
import logging
from datetime import datetime
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

import config
from twitter_client import get_twitter_client, Tweet
from translator import translate_tweet
from feishu_client import get_feishu_client, FeishuClient
from storage import TweetStorage

# 配置日志
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class TwitterToFeishuBot:
    """Twitter 到飞书机器人 - 支持多账户"""
    
    def __init__(self):
        self.twitter_client = get_twitter_client()
        self.feishu_client = get_feishu_client()
        self.storage = TweetStorage()
        self.running = False
    
    def process_all_accounts(self):
        """处理所有配置的账户"""
        logger.info(f"开始处理 {len(config.ACCOUNTS)} 个账户...")
        
        for account in config.ACCOUNTS:
            twitter_user = account.get("twitter_user", "")
            phones = account.get("phones", [])
            
            if not twitter_user or not phones:
                logger.warning(f"账户配置不完整: {account}")
                continue
            
            logger.info(f"处理账户: @{twitter_user} -> 手机号: {phones}")
            
            try:
                self.process_account(twitter_user, phones)
            except Exception as e:
                logger.error(f"处理账户 @{twitter_user} 时出错: {e}")
            
            # 账户之间添加延迟，避免请求过快
            time.sleep(2)
        
        logger.info("所有账户处理完成")
    
    def process_account(self, twitter_user: str, phones: list):
        """处理单个 Twitter 账户的推文"""
        # 1. 获取推文
        tweets = self.twitter_client.get_user_tweets(
            twitter_user, 
            max_results=config.TWEETS_COUNT
        )
        
        if not tweets:
            logger.info(f"用户 @{twitter_user} 没有新推文")
            return
        
        # 2. 筛选未处理的推文
        new_tweets = [t for t in tweets if not self.storage.is_processed(t.tweet_id)]
        logger.info(f"用户 @{twitter_user} 发现 {len(new_tweets)} 条新推文")
        
        if not new_tweets:
            return
        
        # 3. 处理每条新推文
        for tweet in new_tweets:
            try:
                self._process_single_tweet(tweet, phones)
                # 标记为已处理
                self.storage.mark_processed(tweet.tweet_id)
                # 避免发送过快
                time.sleep(1)
            except Exception as e:
                logger.error(f"处理推文 {tweet.tweet_id} 时出错: {e}")
    
    def _process_single_tweet(self, tweet: Tweet, phones: list):
        """处理单条推文并发送到多个手机号"""
        logger.info(f"处理推文: {tweet.tweet_id}")
        
        # 1. 翻译推文
        translation = translate_tweet(tweet.text)
        original = translation["original"]
        translated = translation["translated"]
        
        logger.info(f"原文: {original[:100]}...")
        logger.info(f"译文: {translated[:100]}...")
        
        # 2. 构建消息内容
        message_content = self._build_message(tweet, original, translated)
        
        # 3. 发送消息到所有配置的手机号
        for phone in phones:
            try:
                success = self.feishu_client.send_message_by_phone(phone, message_content)
                if success:
                    logger.info(f"推文 {tweet.tweet_id} 已成功发送到 {phone}")
                else:
                    logger.error(f"发送推文 {tweet.tweet_id} 到 {phone} 失败")
                time.sleep(0.5)  # 手机号之间添加小延迟
            except Exception as e:
                logger.error(f"发送到 {phone} 时出错: {e}")
    
    def _build_message(self, tweet: Tweet, original: str, translated: str) -> str:
        """构建消息文本"""
        # 格式化时间
        created_time = tweet.created_at
        try:
            dt = datetime.strptime(created_time, '%a, %d %b %Y %H:%M:%S %Z')
            created_time = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            pass
        
        message = f"""🐦 Twitter 推文翻译

👤 作者: @{tweet.author}
🕐 时间: {created_time}
🔗 链接: {tweet.url}

📄 原文:
{original}

━━━━━━━━━━━━━━

🇨🇳 中文翻译:
{translated}
"""
        
        # 如果有媒体，添加媒体链接
        if tweet.media_urls:
            message += "\n📎 媒体:\n"
            for i, url in enumerate(tweet.media_urls, 1):
                message += f"  [{i}] {url}\n"
        
        return message
    
    def run_once(self):
        """运行一次（用于 GitHub Actions）"""
        logger.info("=" * 50)
        logger.info("Twitter to Feishu Bot - 单次运行")
        logger.info("=" * 50)
        
        try:
            self.process_all_accounts()
        except Exception as e:
            logger.error(f"运行出错: {e}")
        
        logger.info("单次运行完成")
    
    def run_continuously(self):
        """持续运行，定时检查"""
        import schedule
        
        logger.info("=" * 50)
        logger.info("Twitter to Feishu Bot - 持续运行模式")
        logger.info(f"检查间隔: {config.POLLING_INTERVAL} 秒")
        logger.info("按 Ctrl+C 停止")
        logger.info("=" * 50)
        
        # 设置定时任务
        schedule.every(config.POLLING_INTERVAL).seconds.do(self.process_all_accounts)
        
        # 立即执行一次
        self.process_all_accounts()
        
        self.running = True
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(1)
            except KeyboardInterrupt:
                logger.info("收到停止信号，正在退出...")
                self.running = False
            except Exception as e:
                logger.error(f"运行时出错: {e}")
                time.sleep(10)
        
        logger.info("程序已停止")
    
    def send_test_message(self):
        """发送测试消息"""
        logger.info("发送测试消息...")
        
        # 获取第一个账户的配置
        if not config.ACCOUNTS:
            logger.error("没有配置任何账户")
            return
        
        first_account = config.ACCOUNTS[0]
        phones = first_account.get("phones", [])
        
        if not phones:
            logger.error("第一个账户没有配置手机号")
            return
        
        test_content = """🧪 测试消息

这是 Twitter to Feishu Bot 的测试消息。
如果收到此消息，说明飞书配置正确！

当前配置账户:
"""
        for acc in config.ACCOUNTS:
            test_content += f"- @{acc.get('twitter_user', '')} -> {acc.get('phones', [])}\n"
        
        for phone in phones:
            success = self.feishu_client.send_message_by_phone(phone, test_content)
            if success:
                logger.info(f"测试消息发送成功到 {phone}！")
            else:
                logger.error(f"测试消息发送到 {phone} 失败")


def check_config():
    """检查配置是否完整"""
    errors = []
    
    # 检查飞书配置 (必须)
    if not config.FEISHU_APP_ID or not config.FEISHU_APP_SECRET:
        errors.append("未配置飞书应用凭证 (FEISHU_APP_ID 和 FEISHU_APP_SECRET)")
    
    # 检查账户配置
    if not config.ACCOUNTS:
        errors.append("没有配置任何 Twitter 账户")
    else:
        for i, account in enumerate(config.ACCOUNTS):
            if not account.get("twitter_user"):
                errors.append(f"账户 {i+1} 未配置 twitter_user")
            if not account.get("phones"):
                errors.append(f"账户 {i+1} 未配置 phones")
    
    if errors:
        logger.error("配置检查失败:")
        for error in errors:
            logger.error(f"  - {error}")
        logger.error("\n请检查 config.py 或 .env 文件")
        return False
    
    logger.info(f"配置检查通过，监控 {len(config.ACCOUNTS)} 个账户")
    for acc in config.ACCOUNTS:
        logger.info(f"  - @{acc['twitter_user']} -> {acc['phones']}")
    return True


def main():
    """主函数"""
    # 检查是否是 GitHub Actions 环境
    if os.getenv("GITHUB_ACTIONS") == "true":
        logger.info("运行在 GitHub Actions 环境")
        if not check_config():
            sys.exit(1)
        bot = TwitterToFeishuBot()
        bot.run_once()
        return
    
    # 本地运行模式
    print("""
╔══════════════════════════════════════════╗
║     Twitter to Feishu Bot                ║
║     Twitter 推文翻译转发机器人            ║
╚══════════════════════════════════════════╝

功能: 获取 Twitter 推文 → 翻译为中文 → 发送到飞书

请选择运行模式:
1. 单次运行 (获取一次推文并发送)
2. 持续运行 (定时检查新推文)
3. 发送测试消息 (验证飞书配置)
4. 退出
    """)
    
    choice = input("请输入选项 (1-4): ").strip()
    
    if choice == "4":
        print("再见！")
        return
    
    # 检查配置
    if not check_config():
        return
    
    # 创建机器人实例
    bot = TwitterToFeishuBot()
    
    if choice == "1":
        bot.run_once()
    elif choice == "2":
        bot.run_continuously()
    elif choice == "3":
        bot.send_test_message()
    else:
        print("无效选项")


if __name__ == "__main__":
    main()
