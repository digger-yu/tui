"""
X.com (Twitter) 推文获取模块
支持多种方式获取推文:
1. Syndication API - Twitter 官方嵌入式推文端点，无需认证，最稳定
2. Vanlett HTML - 免登录，需浏览器绕过 Cloudflare（仅本地桌面）
3. Nitter RSS Feed - 免登录，无需API（Nitter 实例已大多失效）
4. Twitter API v2 (官方，需申请开发者账号)
5. 第三方 Twitter API 代理服务
"""
import re
import sys
import logging
import subprocess
import requests
import hashlib
from typing import List, Dict, Optional
from datetime import datetime
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import config

# Windows: 隐藏 subprocess 控制台窗口（定时任务静默运行）
# Linux/GitHub Actions: 无此标志，设为 0
_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0

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
    Nitter HTML 客户端 - 通过 curl subprocess 获取 HTML 并解析推文
    RSS feed 已被大多数实例关闭，但 HTML 页面仍然可用
    使用 curl subprocess 绕过 Python TLS 指纹被检测的问题
    """

    NITTER_INSTANCES = [
        "https://nitter.tiekoetter.com",
        "https://nitter.net",
        "https://xcancel.com",
        "https://nitter.poast.org",
        "https://nitter.privacyredirect.com",
        "https://nitter.space",
        "https://nitter.catsarch.com",
        "https://nitter.kareem.one",
        "https://lightbrd.com",
        "https://nuku.trabun.org",
    ]

    def __init__(self, instance: str = None):
        self.instance = instance

    def _fetch_html(self, url: str) -> Optional[str]:
        """通过 curl subprocess 获取 HTML（不发送 User-Agent 以避免触发反爬检测）"""
        import os, subprocess, shutil

        cmd = ['curl', '-s', '-m', '15', '--compressed']

        proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or \
                os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
        if proxy:
            cmd.extend(['-x', proxy])

        cmd.append(url)

        if shutil.which('curl') is None and shutil.which('curl.exe'):
            cmd[0] = 'curl.exe'

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=20,
                                     creationflags=_SUBPROCESS_FLAGS)
            return result.stdout.decode('utf-8', errors='replace')
        except Exception as e:
            logger.error(f"curl 请求失败: {e}")
            return None

    def _try_instances(self, username: str) -> Optional[tuple]:
        """尝试多个 Nitter 实例，返回 (instance, html)"""
        import time

        for i, instance in enumerate(self.NITTER_INSTANCES):
            if i > 0:
                time.sleep(2)

            url = f"{instance}/{username}"
            logger.info(f"尝试 Nitter: {instance}")

            html = self._fetch_html(url)
            if html and len(html) > 500 and 'tweet-content' in html:
                logger.info(f"成功使用 Nitter 实例: {instance}")
                self.instance = instance
                return (instance, html)
            elif html and len(html) > 500:
                logger.warning(f"实例 {instance} 返回了非推文内容 (len={len(html)})")
            else:
                logger.warning(f"实例 {instance} 未返回有效数据 (len={len(html) if html else 0})")

        logger.error("所有 Nitter 实例都不可用")
        return None

    def get_user_tweets(self, username: str, max_results: int = 10) -> List[Tweet]:
        """通过 Nitter HTML 页面获取指定用户的推文"""
        try:
            result = self._try_instances(username)
            if not result:
                return []

            instance, html = result
            soup = BeautifulSoup(html, 'html.parser')

            bodies = soup.find_all('div', class_='tweet-body')
            logger.info(f"找到 {len(bodies)} 条推文")

            tweets = []
            for body in bodies[:max_results]:
                tweet = self._parse_html_item(body, username, instance)
                if tweet:
                    tweets.append(tweet)

            logger.info(f"成功解析 {len(tweets)} 条推文")
            return tweets

        except Exception as e:
            logger.error(f"获取推文时出错: {e}")
            return []

    def _parse_html_item(self, body, username: str, instance: str) -> Optional[Tweet]:
        """解析单个 tweet-body HTML 元素"""
        # 推文文本
        content = body.find('div', class_='tweet-content')
        text = content.get_text(strip=True) if content else ""
        if not text:
            return None

        # 推文 ID 从链接提取
        link = body.find('a', href=re.compile(r'/status/'))
        tweet_id = ""
        tweet_url = ""
        if link:
            href = link.get('href', '')
            m = re.search(r'/status/(\d+)', href)
            if m:
                tweet_id = m.group(1)
                tweet_url = f"https://x.com/{username}/status/{tweet_id}"

        if not tweet_id:
            hash_val = hashlib.md5(text.encode()).hexdigest()[:16]
            tweet_id = f"nitter_{hash_val}"

        # 日期
        date_span = body.find('span', class_='tweet-date')
        created_at = ""
        if date_span:
            a = date_span.find('a')
            if a:
                created_at = a.get('title', a.get_text())

        # 媒体
        media_urls = []
        for img in body.find_all('a', class_='still-image'):
            href = img.get('href', '')
            if href and not href.startswith('http'):
                href = f"https://pbs.twimg.com{href}" if href.startswith('/') else href
            if href:
                media_urls.append(href)

        return Tweet(
            tweet_id=tweet_id,
            text=text,
            created_at=created_at,
            author=username,
            url=tweet_url,
            media_urls=media_urls,
        )


class BrowserClient:
    """
    浏览器 HTML 客户端 - 用 patchright 浏览器获取推文
    可访问 Vanlett 或 Nitter 实例（均需 JS 验证）
    headful 模式以绕过 Cloudflare/反爬检测

    依赖:
      pip install patchright
      python -m patchright install chromium
    """

    BASE_URL = "https://vanlett.com"
    NITTER_URL = "https://nitter.tiekoetter.com"
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
            '--disable-quic',
            '--disable-http2',
            '--ignore-certificate-errors',
        ]

        # 检测系统代理（本地环境可能需要代理访问 vanlett.com）
        import os
        proxy_server = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or \
                       os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
        # WinHTTP 代理（SYSTEM 用户环境下 requests 库不自动读取）
        if not proxy_server:
            try:
                import subprocess
                result = subprocess.run(
                    ['netsh', 'winhttp', 'show', 'proxy'],
                    capture_output=True, text=True, timeout=5,
                    creationflags=_SUBPROCESS_FLAGS,
                )
                m = re.search(r'Proxy Server\(s\)\s*:\s*http=([^;]+)', result.stdout)
                if m:
                    proxy_server = f"http://{m.group(1)}"
            except Exception:
                pass

        if proxy_server:
            launch_args.append(f'--proxy-server={proxy_server}')
            logger.info(f"浏览器使用代理: {proxy_server}")

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

            # 等待 Cloudflare/反爬验证完成
            import time
            for _ in range(self.CF_TIMEOUT // 2):
                time.sleep(2)
                title = page.title()
                if 'just a moment' not in title.lower() and \
                   '请稍候' not in title and \
                   'not a bot' not in title.lower():
                    break

            # 等待推文元素出现
            try:
                page.wait_for_selector(
                    '.timeline-item, .tweet-body', timeout=15000
                )
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
        """通过浏览器获取推文，先试 Nitter，再试 Vanlett"""
        for source_name, base_url, selector, parser in [
            ("Nitter", self.NITTER_URL, 'div.tweet-body', self._parse_nitter_item),
            ("Vanlett", self.BASE_URL, 'div.timeline-item', self._parse_vanlett_item),
        ]:
            url = f"{base_url}/{username}"
            logger.info(f"通过 {source_name} 获取用户 @{username} 的推文: {url}")

            html = self._fetch_html(url)
            if not html:
                continue

            soup = BeautifulSoup(html, 'html.parser')
            items = soup.select(selector)

            if not items:
                logger.warning(f"{source_name} 页面未找到推文元素")
                continue

            logger.info(f"{source_name} 找到 {len(items)} 条推文")

            tweets = []
            for item in items[:max_results]:
                try:
                    tweet = parser(item, username)
                    if tweet:
                        tweets.append(tweet)
                except Exception as e:
                    logger.warning(f"解析推文时出错: {e}")
                    continue

            if tweets:
                logger.info(f"{source_name} 成功解析 {len(tweets)} 条推文")
                return tweets

        return []

    def _parse_nitter_item(self, body, username: str) -> Optional[Tweet]:
        """解析 Nitter tweet-body HTML 元素"""
        content = body.find('div', class_='tweet-content')
        text = content.get_text(strip=True) if content else ""
        if not text:
            return None

        link = body.find('a', href=re.compile(r'/status/'))
        tweet_id = ""
        tweet_url = ""
        if link:
            href = link.get('href', '')
            m = re.search(r'/status/(\d+)', href)
            if m:
                tweet_id = m.group(1)
                tweet_url = f"https://x.com/{username}/status/{tweet_id}"

        if not tweet_id:
            hash_val = hashlib.md5(text.encode()).hexdigest()[:16]
            tweet_id = f"nitter_{hash_val}"

        date_span = body.find('span', class_='tweet-date')
        created_at = ""
        if date_span:
            a = date_span.find('a')
            if a:
                created_at = a.get('title', a.get_text())

        media_urls = []
        for img in body.find_all('a', class_='still-image'):
            href = img.get('href', '')
            if href and not href.startswith('http'):
                href = f"https://pbs.twimg.com{href}" if href.startswith('/') else href
            if href:
                media_urls.append(href)

        return Tweet(
            tweet_id=tweet_id,
            text=text,
            created_at=created_at,
            author=username,
            url=tweet_url,
            media_urls=media_urls,
        )

    def _parse_vanlett_item(self, item, username: str) -> Optional[Tweet]:
        """解析 Vanlett timeline-item HTML 元素"""
        content_el = item.select_one('.post-content')
        if not content_el:
            return None

        text = content_el.get_text()
        text = ' '.join(text.split())
        if not text:
            return None

        date_el = item.select_one('.post-date')
        created_at = date_el.get_text(strip=True) if date_el else ""

        media_urls = []
        for a in item.select('.still-image'):
            if a.find_parent(class_='quote'):
                continue
            href = a.get('href', '')
            if href:
                media_urls.append(href)

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
    使用 curl subprocess 绕过 Python TLS 指纹被 Twitter 识别的问题
    """

    BASE_URL = "https://syndication.twitter.com/srv/timeline-profile/screen-name"

    def _fetch_html(self, url: str) -> Optional[str]:
        """通过 curl subprocess 获取 HTML（绕过 Python TLS 指纹检测）"""
        import os, subprocess, shutil

        cmd = ['curl', '-s', '-m', '15', '--compressed', '-A',
               'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
               'AppleWebKit/537.36 (KHTML, like Gecko) '
               'Chrome/131.0.0.0 Safari/537.36']

        proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or \
                os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
        if proxy:
            cmd.extend(['-x', proxy])

        cmd.append(url)

        # Windows: curl.exe
        if shutil.which('curl') is None and shutil.which('curl.exe'):
            cmd[0] = 'curl.exe'

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=20,
                                     creationflags=_SUBPROCESS_FLAGS)
            return result.stdout.decode('utf-8', errors='replace')
        except Exception as e:
            logger.error(f"curl 请求失败: {e}")
            return None

    def get_user_tweets(self, username: str, max_results: int = 10) -> List[Tweet]:
        url = f"{self.BASE_URL}/{username}"

        try:
            logger.info(f"通过 syndication API 获取用户 @{username} 的推文")
            html = self._fetch_html(url)

            if not html:
                logger.warning(f"syndication API 返回空响应: @{username}")
                return []

            import re
            m = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                html, re.DOTALL,
            )
            if not m:
                if 'Rate limit exceeded' in html:
                    logger.warning(f"syndication API 限流 (429): @{username}")
                else:
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

        except Exception as e:
            logger.error(f"syndication API 请求失败: {e}")
            return []


class FallbackClient:
    """
    组合客户端 - 按优先级尝试多个数据源
    Nitter HTML (curl) -> Syndication (curl) -> Browser (本地)
    -> Twitter API (CI, 付费)
    """

    def __init__(self):
        self._twitter_api = None
        self._syndication = None
        self._browser = None
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

    def _get_browser(self):
        if self._browser is None:
            self._browser = BrowserClient()
        return self._browser

    def _get_nitter(self):
        if self._nitter is None:
            self._nitter = NitterRSSClient()
        return self._nitter

    def get_user_tweets(self, username: str, max_results: int = 10) -> List[Tweet]:
        # 1. Nitter HTML (curl, 返回最新推文)
        try:
            client = self._get_nitter()
            tweets = client.get_user_tweets(username, max_results)
            if tweets:
                return tweets
            logger.info("Nitter 未获取到推文")
        except Exception as e:
            logger.warning(f"Nitter 失败: {e}")

        # 2. Syndication API (curl, 可能返回旧推文)
        try:
            client = self._get_syndication()
            tweets = client.get_user_tweets(username, max_results)
            if tweets:
                return tweets
            logger.info("syndication 未获取到推文")
        except Exception as e:
            logger.warning(f"syndication 失败: {e}")

        # 3. Browser (本地浏览器, 仅非 CI)
        if not self._is_ci:
            try:
                client = self._get_browser()
                tweets = client.get_user_tweets(username, max_results)
                if tweets:
                    return tweets
                logger.info("Browser 未获取到推文")
            except Exception as e:
                logger.warning(f"Browser 失败: {e}")

        # 4. Twitter API (CI, 需 Bearer Token)
        if self._has_bearer:
            try:
                client = self._get_twitter_api()
                tweets = client.get_user_tweets(username, max_results)
                if tweets:
                    return tweets
                logger.info("Twitter API 未获取到推文")
            except Exception as e:
                logger.warning(f"Twitter API 失败: {e}")

        return []

    def close(self):
        if self._browser is not None:
            self._browser.close()


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
    from dotenv import load_dotenv
    load_dotenv()
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
