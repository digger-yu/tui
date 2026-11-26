"""
翻译模块 - 将推文从英文翻译成中文

引擎链（自动按顺序尝试，失败自动降级）:
1. google   - 免费，无需 API Key，译文质量最好；GitHub Actions / 海外网络可用，中国大陆需代理
2. mymemory - 免费，无需 API Key，中国大陆可直连；共享 IP 有每日额度
3. baidu    - 需 BAIDU_APP_ID + BAIDU_SECRET_KEY，配置后优先使用
4. deepl    - 需 DEEPL_API_KEY，配置后优先使用

TRANSLATOR_ENGINE 可指定优先引擎，默认 auto（按上面的顺序自动尝试）。
所有免费接口都不保证 100% 可用，因此每次翻译都会校验结果是否真的是中文，
失败时换下一个引擎，避免把英文原文当成"译文"推到飞书。
"""
import hashlib
import logging
import random
import re
from typing import List, Optional

import requests

import config

logger = logging.getLogger(__name__)

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
# 单引擎请求超时 (连接, 读取)
_TIMEOUT = (6, 20)


# ==================== 工具函数 ====================

def _cjk_count(text: str) -> int:
    return len(_CJK_RE.findall(text or ""))


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    return _cjk_count(text) / len(text)


def looks_chinese(text: str) -> bool:
    """判断文本是否像中文译文（至少 2 个汉字且占比 >= 5%）"""
    if not text:
        return False
    return _cjk_count(text) >= 2 and _cjk_ratio(text) >= 0.05


def is_good_translation(source: str, translated: str) -> bool:
    """校验译文是否有效：非空、不等于原文、确实是中文（纯符号/链接文本除外）"""
    if not translated or not translated.strip():
        return False
    if translated.strip() == (source or "").strip():
        return False
    if looks_chinese(translated):
        return True
    # 原文本身几乎没有可翻译的英文（纯链接/数字/表情），保留原样即可
    return len(_LATIN_RE.findall(source or "")) < 4


def chunk_text(text: str, max_length: int) -> List[str]:
    """把长文本切成不超过 max_length 的片段，原样保留字符（不插入换行/空格）"""
    if len(text) <= max_length:
        return [text]

    chunks, start, total = [], 0, len(text)
    while start < total:
        end = min(start + max_length, total)
        if end < total:
            window = text[start:end]
            cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "),
                      window.rfind("\n"), window.rfind(" "))
            if cut > max_length // 2:
                end = start + cut + 1
        chunks.append(text[start:end])
        start = end
    return chunks or [text]


_URL_RE = re.compile(r"https?://\S+")
_NOISE_RE = re.compile(r"[@#$][A-Za-z0-9_]+")
_WORD_RE = re.compile(r"[A-Za-z]{2,}")


def needs_translation(text: str) -> bool:
    """判断是否值得翻译：纯链接/表情/股票代码/短词就不翻了"""
    if not text or not text.strip():
        return False
    if looks_chinese(text) and _cjk_ratio(text) >= 0.3:
        return False
    cleaned = _NOISE_RE.sub(" ", _URL_RE.sub(" ", text))
    return len(_WORD_RE.findall(cleaned)) >= 2


# ==================== 引擎实现 ====================

class BaseTranslator:
    """翻译器基类：失败时返回 None，由上层链式降级"""

    name = "base"

    def translate(self, text: str, source_lang: str = "auto",
                  target_lang: str = "zh-CN") -> Optional[str]:
        raise NotImplementedError


class GoogleTranslator(BaseTranslator):
    """Google 免费翻译接口（无需 Key）

    使用 translate_a/single?client=gtx 端点（质量最好），
    备用 clients5.google.com/translate_a/t（dict-chrome-ex）。
    中国大陆网络不可直连，需要 HTTPS_PROXY；连接失败会快速跳过。
    """

    name = "google"
    ENDPOINTS = (
        "https://translate.googleapis.com/translate_a/single",
        "https://translate.google.com/translate_a/single",
    )
    MAX_LENGTH = 4000

    def __init__(self):
        self._unreachable = False

    def translate(self, text: str, source_lang: str = "auto",
                  target_lang: str = "zh-CN") -> Optional[str]:
        if not text or not text.strip():
            return ""
        if self._unreachable:
            return None

        sl = source_lang if source_lang and source_lang.lower() != "auto" else "auto"
        tl = "zh-CN" if (target_lang or "").lower() in ("zh", "zh-cn", "zh-hans") else target_lang

        results = []
        for chunk in chunk_text(text, self.MAX_LENGTH):
            piece = self._translate_chunk(chunk, sl, tl)
            if piece is None:
                return None
            results.append(piece)
        return "".join(results)

    def _translate_chunk(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        params = {"client": "gtx", "sl": source_lang, "tl": target_lang, "dt": "t", "q": text}
        connect_failures = 0

        for url in self.ENDPOINTS:
            try:
                if len(text) > 1200:
                    resp = requests.post(url, data=params, headers=HEADERS, timeout=_TIMEOUT)
                else:
                    resp = requests.get(url, params=params, headers=HEADERS, timeout=_TIMEOUT)
                if resp.status_code != 200:
                    logger.warning(f"Google 返回 HTTP {resp.status_code}: {url}")
                    continue
                translated = self._parse_single(resp.json())
                if translated:
                    return translated
            except requests.exceptions.ConnectTimeout:
                connect_failures += 1
            except requests.exceptions.RequestException as e:
                logger.warning(f"Google 请求失败({url}): {type(e).__name__}: {e}")
            except ValueError as e:
                logger.warning(f"Google 返回非 JSON({url}): {e}")

        if connect_failures == len(self.ENDPOINTS):
            logger.warning("Google 接口不可达（可能需要代理），本次运行跳过 Google")
            self._unreachable = True
            return None

        # 备用端点
        return self._translate_via_clients5(text, source_lang, target_lang)

    @staticmethod
    def _parse_single(data) -> Optional[str]:
        if not isinstance(data, list) or not data:
            return None
        segments = data[0]
        if not isinstance(segments, list):
            return None
        text = "".join(seg[0] for seg in segments
                       if isinstance(seg, list) and seg and isinstance(seg[0], str))
        return text or None

    def _translate_via_clients5(self, text: str, source_lang: str,
                                target_lang: str) -> Optional[str]:
        try:
            resp = requests.get(
                "https://clients5.google.com/translate_a/t",
                params={"client": "dict-chrome-ex", "sl": source_lang,
                        "tl": target_lang, "q": text},
                headers=HEADERS, timeout=_TIMEOUT,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not isinstance(data, list) or not data:
                return None
            first = data[0]
            if isinstance(first, list) and first:
                return first[0] if isinstance(first[0], str) else None
            if isinstance(first, str):
                return first
            return None
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.warning(f"Google 备用接口失败: {type(e).__name__}: {e}")
            return None


class MyMemoryTranslator(BaseTranslator):
    """MyMemory 免费翻译接口（无需 Key，中国大陆可直连）

    匿名额度按 IP 计（约 5000 字符/天），配置 MYMEMORY_EMAIL 可提高额度。
    GitHub Actions 的共享 IP 可能额度耗尽，此时 responseStatus 会返回 429/403。
    """

    name = "mymemory"
    API_URL = "https://api.mymemory.translated.net/get"
    MAX_LENGTH = 450

    def translate(self, text: str, source_lang: str = "auto",
                  target_lang: str = "zh-CN") -> Optional[str]:
        if not text or not text.strip():
            return ""

        sl = source_lang if source_lang and source_lang.lower() != "auto" else "en"
        tl = target_lang or "zh-CN"
        if tl.lower() == "zh":
            tl = "zh-CN"

        results = []
        for chunk in chunk_text(text, self.MAX_LENGTH):
            piece = self._translate_chunk(chunk, sl, tl)
            if piece is None:
                return None
            results.append(piece)
        return " ".join(results)

    def _translate_chunk(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        params = {"q": text, "langpair": f"{source_lang}|{target_lang}"}
        email = getattr(config, "MYMEMORY_EMAIL", "") or ""
        if email:
            params["de"] = email

        try:
            resp = self._get(params)
        except requests.exceptions.RequestException as e:
            logger.warning(f"MyMemory 请求失败: {type(e).__name__}: {e}")
            return None

        try:
            data = resp.json()
        except ValueError as e:
            logger.warning(f"MyMemory 返回非 JSON: {e}")
            return None

        translated = (data.get("responseData") or {}).get("translatedText") or ""
        status = data.get("responseStatus")
        if data.get("quotaFinished"):
            logger.warning("MyMemory 今日免费额度已用完")
            return None
        if status not in (None, 200, "200"):
            logger.warning(f"MyMemory 返回错误状态 {status}: {translated[:120]}")
            return None
        if translated.upper().startswith("MYMEMORY WARNING"):
            logger.warning(f"MyMemory 额度告警: {translated[:120]}")
            return None
        return translated or None

    @staticmethod
    def _get(params: dict):
        """先按默认网络（含代理）请求，失败后强制直连再试一次"""
        try:
            return requests.get(MyMemoryTranslator.API_URL, params=params,
                                headers=HEADERS, timeout=_TIMEOUT)
        except requests.exceptions.RequestException:
            return requests.get(MyMemoryTranslator.API_URL, params=params,
                                headers=HEADERS, timeout=_TIMEOUT,
                                proxies={"http": None, "https": None})


class BaiduTranslator(BaseTranslator):
    """百度翻译 API（需要 BAIDU_APP_ID + BAIDU_SECRET_KEY）"""

    name = "baidu"
    API_URL = "https://fanyi-api.baidu.com/api/trans/vip/translate"
    MAX_LENGTH = 3000

    def __init__(self, app_id: str = None, secret_key: str = None):
        self.app_id = app_id or config.BAIDU_APP_ID
        self.secret_key = secret_key or config.BAIDU_SECRET_KEY

    @property
    def available(self) -> bool:
        return bool(self.app_id and self.secret_key)

    def translate(self, text: str, source_lang: str = "auto",
                  target_lang: str = "zh-CN") -> Optional[str]:
        if not text or not text.strip():
            return ""
        if not self.available:
            logger.debug("百度翻译未配置凭证，跳过")
            return None

        src = "auto" if not source_lang or source_lang.lower() == "auto" else source_lang
        dst = "zh" if (target_lang or "").lower().startswith("zh") else target_lang

        results = []
        for chunk in chunk_text(text, self.MAX_LENGTH):
            piece = self._translate_chunk(chunk, src, dst)
            if piece is None:
                return None
            results.append(piece)
        return "".join(results)

    def _translate_chunk(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        salt = str(random.randint(32768, 65536))
        sign = hashlib.md5(
            (self.app_id + text + salt + self.secret_key).encode("utf-8")
        ).hexdigest()
        params = {"q": text, "from": source_lang, "to": target_lang,
                  "appid": self.app_id, "salt": salt, "sign": sign}
        try:
            resp = requests.get(self.API_URL, params=params, headers=HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.warning(f"百度翻译请求失败: {type(e).__name__}: {e}")
            return None

        if "trans_result" in data:
            return "".join(item.get("dst", "") for item in data["trans_result"]) or None
        logger.warning(f"百度翻译返回错误: {data}")
        return None


class DeepLTranslator(BaseTranslator):
    """DeepL 翻译 API（需要 DEEPL_API_KEY）"""

    name = "deepl"
    API_URL = "https://api-free.deepl.com/v2/translate"
    MAX_LENGTH = 4000

    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.DEEPL_API_KEY

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def translate(self, text: str, source_lang: str = "auto",
                  target_lang: str = "zh-CN") -> Optional[str]:
        if not text or not text.strip():
            return ""
        if not self.available:
            logger.debug("DeepL 未配置 API Key，跳过")
            return None

        results = []
        for chunk in chunk_text(text, self.MAX_LENGTH):
            piece = self._translate_chunk(chunk, source_lang, target_lang)
            if piece is None:
                return None
            results.append(piece)
        return "".join(results)

    def _translate_chunk(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        payload = {"text": [text], "target_lang": "ZH"}
        if source_lang and source_lang.lower() != "auto":
            payload["source_lang"] = source_lang[:2].upper()
        try:
            resp = requests.post(
                self.API_URL,
                json=payload,
                headers={**HEADERS, "Authorization": f"DeepL-Auth-Key {self.api_key}"},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.warning(f"DeepL 请求失败: {type(e).__name__}: {e}")
            return None

        translations = data.get("translations") or []
        if translations:
            return translations[0].get("text") or None
        logger.warning(f"DeepL 返回错误: {data}")
        return None


# ==================== 引擎链 ====================

_ENGINES = {
    "google": GoogleTranslator,
    "mymemory": MyMemoryTranslator,
    "baidu": BaiduTranslator,
    "deepl": DeepLTranslator,
}

_FREE_ORDER = ["google", "mymemory"]
_KEYED_ORDER = ["baidu", "deepl"]


def _build_translator(engine_name: str) -> Optional[BaseTranslator]:
    cls = _ENGINES.get((engine_name or "").lower())
    return cls() if cls else None


def _engine_chain(primary: str) -> List[BaseTranslator]:
    """构造引擎链：指定引擎 → 已配置的付费引擎 → 免费引擎"""
    order: List[str] = []
    name = (primary or "auto").lower()
    if name != "auto":
        if name in _ENGINES:
            order.append(name)
        else:
            logger.warning(f"未知翻译引擎 '{primary}'，使用自动选择")

    order.extend(_KEYED_ORDER)
    order.extend(_FREE_ORDER)

    chain, seen = [], set()
    for engine_name in order:
        if engine_name in seen:
            continue
        seen.add(engine_name)
        translator = _build_translator(engine_name)
        if translator is None:
            continue
        # 付费引擎没配 Key 就别浪费一次失败
        if isinstance(translator, (BaiduTranslator, DeepLTranslator)) and not translator.available:
            continue
        chain.append(translator)
    return chain


def get_translator(engine: str = None) -> BaseTranslator:
    """获取首选翻译器（兼容旧接口）"""
    chain = _engine_chain(engine or config.TRANSLATOR_ENGINE)
    if not chain:
        logger.warning("没有可用翻译引擎，回退到 MyMemory")
        return MyMemoryTranslator()
    logger.info(f"使用翻译引擎: {chain[0].name}")
    return chain[0]


def translate_tweet(tweet_text: str, engine: str = None) -> dict:
    """翻译推文，按引擎链自动降级。

    返回: {"original", "translated", "engine", "ok"}
    """
    original = tweet_text or ""
    if not original.strip():
        return {"original": original, "translated": original, "engine": "none", "ok": False}

    # 已经是中文，或只是链接/股票代码/表情，不需要翻译
    if not needs_translation(original):
        logger.info("原文无需翻译（中文/纯链接/股票代码），直接推送原文")
        return {"original": original, "translated": original, "engine": "none", "ok": True}

    chain = _engine_chain(engine or config.TRANSLATOR_ENGINE)
    if not chain:
        logger.error("没有可用翻译引擎，返回原文")
        return {"original": original, "translated": original, "engine": "none", "ok": False}

    for translator in chain:
        try:
            translated = translator.translate(original)
        except Exception as e:  # 单引擎异常不影响后续引擎
            logger.warning(f"引擎 {translator.name} 异常: {type(e).__name__}: {e}")
            continue

        if is_good_translation(original, translated):
            if translator.name != chain[0].name:
                logger.info(f"翻译降级成功: 使用 {translator.name}")
            return {"original": original, "translated": translated,
                    "engine": translator.name, "ok": True}

        logger.warning(f"引擎 {translator.name} 未产出有效中文译文，尝试下一个")

    logger.error("所有翻译引擎均失败，返回原文")
    return {"original": original, "translated": original, "engine": "none", "ok": False}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    sample = ("$CRWV bankers are preparing a $4.5B loan sale, secured by GPUs "
              "for its $META contract. Initial pricing is expected tomorrow. Thoughts?")
    print("原文:", sample)
    print("结果:", translate_tweet(sample))
