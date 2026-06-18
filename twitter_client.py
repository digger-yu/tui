"""
X.com (Twitter) 推文获取模块
支持多种方式获取推文:
1. Nitter RSS Feed - 免登录，无需API，推荐
2. Twitter API v2 (官方，需申请开发者账号)
3. 第三方 Twitter API 代理服务
"""
import logging
import requests
import hashlib
from typing import List, Dict, Optional
from datetime import datetime
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import config

logger = logging.getLogger(__name__)


class Tweet:
    """推文数据模型"""
    def __init__(self, tweet_id: str, text: str, created_at: str, 
                 author: str, url: str, media_urls: List[str] = None):
        self.tweet_id = tweet_id
        self.text = text
        self.created_at = created_at
        self.author = author
        self.url = url
        self.media_urls = media_urls or []
    
    def to_dict(self) -> Dict:
        return {
            "tweet_id": self.tweet_id,
            "text": self.text,
            "created_at": self.created_at,
            "author": self.author,
            "url": self.url,
            "media_urls": self.media_urls
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Tweet":
        return cls(
            tweet_id=data["tweet_id"],
            text=data["text"],
            created_at=data["created_at"],
            author=data["author"],
            url=data["url"],
            media_urls=data.get("media_urls", [])
        )


class NitterRSSClient:
    """
    Nitter RSS Feed 客户端 - 免登录获取 Twitter 推文
    Nitter 提供 RSS feed，无需登录即可获取公开推文
    """
    
    # Nitter 实例列表（部分可能会失效，会自动尝试下一个）
    # 来源: https://github.com/zedeus/nitter/wiki/Instances
    NITTER_INSTANCES = [
        "https://nitter.net",
        "https://xcancel.com",
        "https://nitter.poast.org",
        "https://nitter.privacyredirect.com",
        "https://nitter.tiekoetter.com",
        "https://nitter.space",
        "https://nitter.catsarch.com",
        "https://nitter.kareem.one",
        "https://lightbrd.com",
        "https://nuku.trabun.org",
    ]
    
    def __init__(self, instance: str = None):
        self.instance = instance or self.NITTER_INSTANCES[0]
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml,application/xml,text/xml,*/*",
            "Accept-Language": "en-US,en;q=0.5",
        })
    
    def _try_instances(self, username: str) -> Optional[str]:
        """尝试多个 Nitter 实例，返回成功的 RSS XML"""
        import time
        
        for i, instance in enumerate(self.NITTER_INSTANCES):
            try:
                # 在实例之间添加延迟，避免 429 Too Many Requests
                if i > 0:
                    time.sleep(3)
                
                # xcancel.com 使用不同的 RSS URL 格式
                if "xcancel.com" in instance:
                    url = f"{instance}/{username}/rss"
                else:
                    url = f"{instance}/{username}/rss"
                
                logger.info(f"尝试 Nitter RSS: {instance}")
                
                response = self.session.get(url, timeout=20)
                
                # 检查是否成功获取到 RSS
                if response.status_code == 200 and len(response.text) > 500:
                    # 验证是否是有效的 RSS
                    if '<rss' in response.text and '<item>' in response.text:
                        logger.info(f"成功使用 Nitter 实例: {instance}")
                        self.instance = instance
                        return response.text
                    else:
                        logger.warning(f"实例 {instance} 返回了非 RSS 内容 (前200字符: {response.text[:200]})")
                else:
                    logger.warning(f"实例 {instance} 未返回有效数据 (status={response.status_code}, len={len(response.text)})")
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"实例 {instance} 请求失败: {e}")
                continue
        
        logger.error("所有 Nitter 实例都不可用")
        return None
    
    def get_user_tweets(self, username: str, max_results: int = 10) -> List[Tweet]:
        """
        通过 Nitter RSS 获取指定用户的推文
        
        Args:
            username: Twitter 用户名 (不含 @)
            max_results: 最大获取数量
        
        Returns:
            List[Tweet]: 推文列表
        """
        try:
            # 尝试获取 RSS 内容
            xml_content = self._try_instances(username)
            if not xml_content:
                return []
            
            # 解析 RSS XML
            root = ET.fromstring(xml_content)
            
            # 查找所有 item 元素
            items = root.findall('.//item')
            
            if not items:
                logger.warning(f"未找到用户 {username} 的推文")
                return []
            
            logger.info(f"找到 {len(items)} 条推文")
            
            # 解析每条推文
            tweets = []
            for item in items[:max_results]:
                try:
                    tweet = self._parse_rss_item(item, username)
                    if tweet:
                        tweets.append(tweet)
                except Exception as e:
                    logger.warning(f"解析推文时出错: {e}")
                    continue
            
            logger.info(f"成功解析 {len(tweets)} 条推文")
            return tweets
            
        except ET.ParseError as e:
            logger.error(f"解析 RSS XML 失败: {e}")
            return []
        except Exception as e:
            logger.error(f"获取推文时出错: {e}")
            return []
    
    def _parse_rss_item(self, item, username: str) -> Optional[Tweet]:
        """解析单个 RSS item"""
        # 获取标题/内容
        title_el = item.find('title')
        text = title_el.text if title_el is not None else ""
        
        if not text:
            return None
        
        # 获取链接
        link_el = item.find('link')
        tweet_url = link_el.text if link_el is not None else ""
        
        # 从链接提取推文ID
        tweet_id = ""
        if tweet_url:
            import re
            match = re.search(r'/status/(\d+)', tweet_url)
            if match:
                tweet_id = match.group(1)
        
        if not tweet_id:
            # 基于内容生成ID
            hash_val = hashlib.md5(text.encode()).hexdigest()[:16]
            tweet_id = f"rss_{hash_val}"
        
        # 获取发布时间
        pub_date_el = item.find('pubDate')
        created_at = pub_date_el.text if pub_date_el is not None else ""
        
        # 获取描述（可能包含 HTML 格式的完整内容）
        desc_el = item.find('description')
        description = ""
        if desc_el is not None and desc_el.text:
            description = desc_el.text
            # 如果描述比标题更完整，使用描述
            if len(description) > len(text):
                # 去除 HTML 标签
                soup = BeautifulSoup(description, 'html.parser')
                clean_text = soup.get_text(strip=True)
                if len(clean_text) > len(text):
                    text = clean_text
        
        # 获取媒体链接
        media_urls = []
        # 从 description 中提取图片
        if desc_el is not None and desc_el.text:
            soup = BeautifulSoup(desc_el.text, 'html.parser')
            images = soup.find_all('img')
            for img in images:
                src = img.get('src', '')
                if src:
                    media_urls.append(src)
        
        return Tweet(
            tweet_id=tweet_id,
            text=text,
            created_at=created_at,
            author=username,
            url=tweet_url,
            media_urls=media_urls
        )


class TwitterAPIClient:
    """Twitter API v2 客户端"""
    
    def __init__(self, bearer_token: str = None):
        self.bearer_token = bearer_token or config.TWITTER_BEARER_TOKEN
        self.base_url = "https://api.twitter.com/2"
        self.headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json"
        }
    
    def get_user_tweets(self, username: str, max_results: int = 10) -> List[Tweet]:
        """获取指定用户的最新推文"""
        try:
            # 1. 先获取用户ID
            user_url = f"{self.base_url}/users/by/username/{username}"
            user_response = requests.get(user_url, headers=self.headers, timeout=30)
            user_response.raise_for_status()
            user_data = user_response.json()
            
            if "data" not in user_data:
                logger.error(f"未找到用户: {username}")
                return []
            
            user_id = user_data["data"]["id"]
            
            # 2. 获取用户推文
            tweets_url = f"{self.base_url}/users/{user_id}/tweets"
            params = {
                "max_results": min(max_results, 100),
                "tweet.fields": "created_at,author_id,public_metrics,entities,attachments",
                "expansions": "attachments.media_keys",
                "media.fields": "url,preview_image_url"
            }
            
            tweets_response = requests.get(tweets_url, headers=self.headers, 
                                         params=params, timeout=30)
            tweets_response.raise_for_status()
            tweets_data = tweets_response.json()
            
            if "data" not in tweets_data:
                logger.warning(f"用户 {username} 没有推文")
                return []
            
            # 解析媒体信息
            media_dict = {}
            if "includes" in tweets_data and "media" in tweets_data["includes"]:
                for media in tweets_data["includes"]["media"]:
                    media_url = media.get("url") or media.get("preview_image_url", "")
                    media_dict[media["media_key"]] = media_url
            
            # 构建 Tweet 对象列表
            tweets = []
            for tweet_data in tweets_data["data"]:
                media_urls = []
                if "attachments" in tweet_data and "media_keys" in tweet_data["attachments"]:
                    for key in tweet_data["attachments"]["media_keys"]:
                        if key in media_dict:
                            media_urls.append(media_dict[key])
                
                tweet = Tweet(
                    tweet_id=tweet_data["id"],
                    text=tweet_data["text"],
                    created_at=tweet_data.get("created_at", ""),
                    author=username,
                    url=f"https://x.com/{username}/status/{tweet_data['id']}",
                    media_urls=media_urls
                )
                tweets.append(tweet)
            
            logger.info(f"成功获取 {len(tweets)} 条推文")
            return tweets
            
        except requests.exceptions.RequestException as e:
            logger.error(f"请求 Twitter API 失败: {e}")
            return []
        except Exception as e:
            logger.error(f"获取推文时出错: {e}")
            return []


class TwitterProxyClient:
    """第三方 Twitter API 代理客户端"""
    
    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or config.TWITTER_PROXY_API_KEY
        self.base_url = base_url or config.TWITTER_PROXY_API_URL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def get_user_tweets(self, username: str, max_results: int = 10) -> List[Tweet]:
        """通过代理API获取推文"""
        try:
            url = f"{self.base_url}/twitter/user/{username}/tweets"
            params = {
                "count": min(max_results, 100)
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            tweets = []
            for item in data.get("tweets", []):
                tweet = Tweet(
                    tweet_id=str(item.get("id", "")),
                    text=item.get("text", ""),
                    created_at=item.get("created_at", ""),
                    author=username,
                    url=f"https://x.com/{username}/status/{item.get('id', '')}",
                    media_urls=item.get("media_urls", [])
                )
                tweets.append(tweet)
            
            logger.info(f"通过代理API成功获取 {len(tweets)} 条推文")
            return tweets
            
        except Exception as e:
            logger.error(f"代理API请求失败: {e}")
            return []


def get_twitter_client():
    """
    获取可用的 Twitter 客户端
    默认使用 Nitter RSS（免登录，无需API）
    """
    logger.info("使用 Nitter RSS 客户端（免登录）")
    return NitterRSSClient()


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)
    
    client = get_twitter_client()
    tweets = client.get_user_tweets(config.TARGET_TWITTER_USER, max_results=5)
    
    for tweet in tweets:
        print(f"\n推文ID: {tweet.tweet_id}")
        print(f"内容: {tweet.text}")
        print(f"时间: {tweet.created_at}")
        print(f"链接: {tweet.url}")
        if tweet.media_urls:
            print(f"媒体: {tweet.media_urls}")
