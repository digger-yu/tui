"""
X.com (Twitter) 推文获取模块
支持多种方式获取推文:
1. Syndication API - Twitter 官方嵌入式推文端点，无需认证，最稳定
2. Vanlett HTML - 免登录，需浏览器绕过 Cloudflare（仅本地桌面）
3. Nitter RSS Feed - 免登录，无需API（Nitter 实例已大多失效）
4. Twitter API v2 (官方，需申请开发者账号)
5. 第三方 Twitter API 代理服务
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


class VanlettClient:
    """
    Vanlett HTML 客户端 - 免登录获取 Twitter 推文
    Vanlett 是 Nitter 的替代前端，通过解析 HTML 页面获取推文
    注意: Vanlett 不提供 RSS，需解析 HTML；且使用 Cloudflare Turnstile 防护，
    需通过 patchright（Playwright 反检测补丁）以 headful 浏览器模式绕过验证

    依赖:
      pip install patchright
      python -m patchright install chromium
    Linux 服务器/GitHub Actions 需配合 xvfb 运行 headful 模式:
      sudo apt-get install -y xvfb
      xvfb-run python main.py
    """

    BASE_URL = "https://vanlett.com"
    # Cloudflare 验证最大等待秒数
    CF_TIMEOUT = 60

    def __init__(self):
        self._playwright = None
        self._browser = None

    def _ensure_browser(self):
        """懒启动 patchright 浏览器（headful 模式以绕过 Cloudflare 检测）"""
        if self._browser is not None:
            return self._browser

        try:
            from patchright.sync_api import sync_playwright
        except ImportError:
            logger.error(
                "patchright 未安装，无法绕过 Vanlett 的 Cloudflare 验证。"
                "请运行: pip install patchright && python -m patchright install chromium"
            )
            return None

        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
        ]

        try:
            self._playwright = sync_playwright().start()
            # 优先使用系统安装的 Chrome（真实浏览器更不容易被检测）
            # GitHub Actions ubuntu-latest 预装了 Google Chrome
            try:
                self._browser = self._playwright.chromium.launch(
                    headless=False,
                    channel='chrome',
                    args=launch_args,
                )
                logger.info("patchright 浏览器已启动（Chrome headful 模式）")
            except Exception:
                # 回退到 patchright 自带的 Chromium
                self._browser = self._playwright.chromium.launch(
                    headless=False,
                    args=launch_args,
                )
                logger.info("patchright 浏览器已启动（Chromium headful 模式）")
        except Exception as e:
            logger.error(
                f"启动浏览器失败: {e}。"
                "Linux 环境请使用 xvfb-run 运行程序。"
            )
            self._browser = None
        return self._browser

    def _fetch_html(self, url: str) -> Optional[str]:
        """通过浏览器获取页面 HTML，自动等待 Cloudflare 验证完成"""
        browser = self._ensure_browser()
        if browser is None:
            return None

        page = None
        try:
            page = browser.new_page()
            logger.info(f"浏览器导航至: {url}")
            page.goto(url, timeout=60000, wait_until='domcontentloaded')

            # 等待 Cloudflare Turnstile 验证完成
            import time
            for _ in range(self.CF_TIMEOUT // 2):
                time.sleep(2)
                title = page.title()
                if 'just a moment' not in title.lower() and '请稍候' not in title:
                    break

            # 等待推文元素出现
            try:
                page.wait_for_selector('.timeline-item', timeout=15000)
            except Exception:
                logger.warning(f"页面未找到推文元素: {url}")
                return None

            return page.content()
        except Exception as e:
            logger.error(f"获取页面 HTML 失败: {e}")
            return None
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass

    def get_user_tweets(self, username: str, max_results: int = 10) -> List[Tweet]:
        """
        通过 Vanlett HTML 页面获取指定用户的推文

        Args:
            username: Twitter 用户名 (不含 @)
            max_results: 最大获取数量

        Returns:
            List[Tweet]: 推文列表
        """
        try:
            url = f"{self.BASE_URL}/{username}"
            logger.info(f"通过 Vanlett 获取用户 @{username} 的推文: {url}")

            html = self._fetch_html(url)
            if not html:
                return []

            soup = BeautifulSoup(html, 'html.parser')
            items = soup.select('div.timeline-item')

            if not items:
                logger.warning(
                    f"Vanlett 页面未找到推文元素"
                    f"（用户 @{username} 可能不存在或页面结构已变化）"
                )
                return []

            logger.info(f"Vanlett 找到 {len(items)} 条推文")

            tweets = []
            for item in items[:max_results]:
                try:
                    tweet = self._parse_tweet(item, username)
                    if tweet:
                        tweets.append(tweet)
                except Exception as e:
                    logger.warning(f"解析推文时出错: {e}")
                    continue

            logger.info(f"成功解析 {len(tweets)} 条推文")
            return tweets

        except Exception as e:
            logger.error(f"获取推文时出错: {e}")
            return []

    def _parse_tweet(self, item, username: str) -> Optional[Tweet]:
        """解析单个推文 HTML 元素"""
        # 获取推文内容
        content_el = item.select_one('.post-content')
        if not content_el:
            return None

        text = content_el.get_text()
        text = ' '.join(text.split())  # 规范化空白字符
        if not text:
            return None

        # 获取发布时间（相对时间，如 "8h"、"11h"）
        date_el = item.select_one('.post-date')
        created_at = date_el.get_text(strip=True) if date_el else ""

        # 获取媒体链接（排除引用推文中的媒体）
        media_urls = []
        for a in item.select('.still-image'):
            if a.find_parent(class_='quote'):
                continue
            href = a.get('href', '')
            if href:
                media_urls.append(href)

        # Vanlett 不提供推文 ID，基于内容生成稳定 ID
        hash_val = hashlib.md5(text.encode()).hexdigest()[:16]
        tweet_id = f"vanlett_{hash_val}"

        # Vanlett 不提供单条推文链接
        tweet_url = f"https://x.com/{username}"

        return Tweet(
            tweet_id=tweet_id,
            text=text,
            created_at=created_at,
            author=username,
            url=tweet_url,
            media_urls=media_urls
        )

    def close(self):
        """关闭浏览器，释放资源"""
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def __del__(self):
        self.close()


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


class SyndicationClient:
    """
    Twitter 官方 syndication API 客户端
    无需认证，返回用户最近 ~20 条推文
    该端点为嵌入式推文卡片提供服务，非常稳定
    """

    BASE_URL = "https://syndication.twitter.com/srv/timeline-profile/screen-name"

    def get_user_tweets(self, username: str, max_results: int = 10) -> List[Tweet]:
        url = f"{self.BASE_URL}/{username}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            logger.info(f"通过 syndication API 获取用户 @{username} 的推文")
            resp = requests.get(url, headers=headers, timeout=15)

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After", "?")
                logger.warning(
                    f"syndication API 限流 (429), "
                    f"Retry-After: {retry_after}: @{username}"
                )
                return []

            resp.raise_for_status()

            import re
            m = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                resp.text, re.DOTALL,
            )
            if not m:
                logger.warning(f"syndication 响应中未找到 __NEXT_DATA__: @{username}")
                return []

            import json
            data = json.loads(m.group(1))
            entries = (
                data.get("props", {})
                .get("pageProps", {})
                .get("timeline", {})
                .get("entries", [])
            )

            tweets = []
            for entry in entries:
                tweet_data = entry.get("content", {}).get("tweet", {})
                if not tweet_data:
                    continue

                tweet_id = tweet_data.get("id_str", "")
                text = tweet_data.get("text", "")
                created_at = tweet_data.get("created_at", "")
                author = tweet_data.get("user", {}).get("screen_name", username)

                media_urls = []
                for media in tweet_data.get("media", []) or []:
                    m_url = media.get("media_url_https") or media.get("media_url")
                    if m_url:
                        media_urls.append(m_url)

                tweet = Tweet(
                    tweet_id=tweet_id,
                    text=text,
                    created_at=created_at,
                    author=author,
                    url=f"https://x.com/{author}/status/{tweet_id}",
                    media_urls=media_urls,
                )
                tweets.append(tweet)

                if len(tweets) >= max_results:
                    break

            logger.info(f"成功获取 {len(tweets)} 条推文")
            return tweets

        except requests.exceptions.HTTPError as e:
            logger.error(f"syndication API 请求失败: {e}")
            return []
        except Exception as e:
            logger.error(f"syndication API 请求失败: {e}")
            return []


class FallbackClient:
    """
    组合客户端 - 按优先级尝试多个数据源
    CI 环境: Twitter API (需 Bearer Token) -> Syndication -> Nitter
    本地环境: Syndication -> Vanlett -> Nitter
    """

    def __init__(self):
        self._twitter_api = None
        self._syndication = None
        self._vanlett = None
        self._nitter = None
        import os
        self._is_ci = os.getenv("GITHUB_ACTIONS") == "true"
        self._has_bearer = bool(getattr(config, "TWITTER_BEARER_TOKEN", ""))

    def _get_twitter_api(self):
        if self._twitter_api is None:
            self._twitter_api = TwitterAPIClient(config.TWITTER_BEARER_TOKEN)
        return self._twitter_api

    def _get_syndication(self):
        if self._syndication is None:
            self._syndication = SyndicationClient()
        return self._syndication

    def _get_vanlett(self):
        if self._vanlett is None:
            self._vanlett = VanlettClient()
        return self._vanlett

    def _get_nitter(self):
        if self._nitter is None:
            self._nitter = NitterRSSClient()
        return self._nitter

    def get_user_tweets(self, username: str, max_results: int = 10) -> List[Tweet]:
        # CI 优先用官方 API（如果配置了 Bearer Token）
        if self._is_ci and self._has_bearer:
            try:
                client = self._get_twitter_api()
                tweets = client.get_user_tweets(username, max_results)
                if tweets:
                    return tweets
                logger.info("Twitter API 未获取到推文，尝试 syndication")
            except Exception as e:
                logger.warning(f"Twitter API 失败，尝试 syndication: {e}")

        # Syndication API（CI 上可能被 429，本地可用）
        if not self._is_ci or not self._has_bearer:
            try:
                client = self._get_syndication()
                tweets = client.get_user_tweets(username, max_results)
                if tweets:
                    return tweets
                logger.info("syndication 未获取到推文")
            except Exception as e:
                logger.warning(f"syndication 失败: {e}")

        # Vanlett（仅本地，CI 跳过避免 Cloudflare 超时）
        if not self._is_ci:
            try:
                client = self._get_vanlett()
                tweets = client.get_user_tweets(username, max_results)
                if tweets:
                    return tweets
                logger.info("Vanlett 未获取到推文，回退到 Nitter RSS")
            except Exception as e:
                logger.warning(f"Vanlett 失败，回退到 Nitter RSS: {e}")

        # Nitter RSS（最后兜底）
        try:
            client = self._get_nitter()
            tweets = client.get_user_tweets(username, max_results)
            if tweets:
                return tweets
            logger.warning("Nitter RSS 也未获取到推文")
        except Exception as e:
            logger.error(f"Nitter RSS 也失败: {e}")

        return []

    def close(self):
        if self._vanlett is not None:
            self._vanlett.close()


def get_twitter_client():
    """
    获取可用的 Twitter 客户端
    CI: Twitter API (Bearer Token) -> Syndication -> Nitter
    本地: Syndication -> Vanlett -> Nitter
    """
    logger.info("使用 Fallback 客户端")
    return FallbackClient()


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    client = get_twitter_client()
    test_user = config.ACCOUNTS[0]["twitter_user"] if config.ACCOUNTS else "aleabitoreddit"
    tweets = client.get_user_tweets(test_user, max_results=5)
    
    for tweet in tweets:
        print(f"\n推文ID: {tweet.tweet_id}")
        print(f"内容: {tweet.text}")
        print(f"时间: {tweet.created_at}")
        print(f"链接: {tweet.url}")
        if tweet.media_urls:
            print(f"媒体: {tweet.media_urls}")
