"""
翻译模块 - 将推文从英文翻译成中文
支持多种翻译引擎:
1. Google Translate (免费，无需API Key)
2. 百度翻译 API
3. DeepL API
"""
import logging
import hashlib
import requests
import json
from typing import Optional
from deep_translator import GoogleTranslator
import config

logger = logging.getLogger(__name__)


class BaseTranslator:
    """翻译器基类"""
    
    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "zh-CN") -> str:
        """翻译文本"""
        raise NotImplementedError


class GoogleTranslatorClient(BaseTranslator):
    """Google 翻译客户端 (使用 deep-translator 库)"""
    
    def __init__(self):
        self.translator = GoogleTranslator(source='auto', target='zh-CN')
    
    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "zh-CN") -> str:
        """使用 Google 翻译"""
        try:
            if not text or not text.strip():
                return ""
            
            # deep-translator 有长度限制，分段翻译
            max_length = 4000
            if len(text) <= max_length:
                result = self.translator.translate(text)
                return result
            
            # 长文本分段翻译
            chunks = self._split_text(text, max_length)
            translated_chunks = []
            for chunk in chunks:
                translated = self.translator.translate(chunk)
                translated_chunks.append(translated)
            
            return "".join(translated_chunks)
            
        except Exception as e:
            logger.error(f"Google 翻译失败: {e}")
            return text  # 翻译失败返回原文
    
    def _split_text(self, text: str, max_length: int) -> list:
        """将长文本分割成小段"""
        chunks = []
        current_chunk = ""
        
        for sentence in text.split('.'):
            if len(current_chunk) + len(sentence) < max_length:
                current_chunk += sentence + "."
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence + "."
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks


class BaiduTranslator(BaseTranslator):
    """百度翻译 API 客户端"""
    
    def __init__(self, app_id: str = None, secret_key: str = None):
        self.app_id = app_id or config.BAIDU_APP_ID
        self.secret_key = secret_key or config.BAIDU_SECRET_KEY
        self.base_url = "https://fanyi-api.baidu.com/api/trans/vip/translate"
    
    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "zh") -> str:
        """使用百度翻译 API"""
        try:
            if not self.app_id or not self.secret_key:
                logger.error("百度翻译 API 凭证未配置")
                return text
            
            if not text or not text.strip():
                return ""
            
            # 生成签名
            salt = str(hashlib.md5().hexdigest())[:16]
            sign_str = self.app_id + text + salt + self.secret_key
            sign = hashlib.md5(sign_str.encode()).hexdigest()
            
            # 构建请求
            params = {
                "q": text,
                "from": source_lang,
                "to": target_lang,
                "appid": self.app_id,
                "salt": salt,
                "sign": sign
            }
            
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if "trans_result" in data:
                result = "".join([item["dst"] for item in data["trans_result"]])
                return result
            else:
                logger.error(f"百度翻译返回错误: {data}")
                return text
                
        except Exception as e:
            logger.error(f"百度翻译失败: {e}")
            return text


class DeepLTranslator(BaseTranslator):
    """DeepL 翻译 API 客户端"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.DEEPL_API_KEY
        self.base_url = "https://api-free.deepl.com/v2/translate"
    
    def translate(self, text: str, source_lang: str = "EN", target_lang: str = "ZH") -> str:
        """使用 DeepL 翻译 API"""
        try:
            if not self.api_key:
                logger.error("DeepL API Key 未配置")
                return text
            
            if not text or not text.strip():
                return ""
            
            headers = {
                "Authorization": f"DeepL-Auth-Key {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "text": [text],
                "source_lang": source_lang,
                "target_lang": target_lang
            }
            
            response = requests.post(self.base_url, headers=headers, 
                                   json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if "translations" in result and len(result["translations"]) > 0:
                return result["translations"][0]["text"]
            else:
                logger.error(f"DeepL 翻译返回错误: {result}")
                return text
                
        except Exception as e:
            logger.error(f"DeepL 翻译失败: {e}")
            return text


def get_translator(engine: str = None) -> BaseTranslator:
    """
    获取翻译器实例
    
    Args:
        engine: 翻译引擎名称，可选: google, baidu, deepl
                如果不指定，使用配置文件中的设置
    
    Returns:
        BaseTranslator: 翻译器实例
    """
    engine = engine or config.TRANSLATOR_ENGINE
    
    if engine.lower() == "baidu":
        logger.info("使用百度翻译")
        return BaiduTranslator()
    elif engine.lower() == "deepl":
        logger.info("使用 DeepL 翻译")
        return DeepLTranslator()
    else:
        logger.info("使用 Google 翻译")
        return GoogleTranslatorClient()


def translate_tweet(tweet_text: str, engine: str = None) -> dict:
    """
    翻译推文，返回原文和译文
    
    Args:
        tweet_text: 推文原文
        engine: 翻译引擎
    
    Returns:
        dict: 包含原文和译文的字典
    """
    translator = get_translator(engine)
    translated = translator.translate(tweet_text)
    
    return {
        "original": tweet_text,
        "translated": translated,
        "engine": engine or config.TRANSLATOR_ENGINE
    }


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)
    
    test_text = "Hello, this is a test tweet. We are building a Twitter to Feishu bot!"
    
    print(f"原文: {test_text}")
    print("-" * 50)
    
    # 测试 Google 翻译
    google = GoogleTranslatorClient()
    result = google.translate(test_text)
    print(f"Google 翻译: {result}")
    print("-" * 50)
    
    # 测试完整功能
    result = translate_tweet(test_text)
    print(f"完整结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
