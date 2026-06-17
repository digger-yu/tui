"""
飞书消息发送模块
支持:
1. 通过飞书应用 API 发送消息到指定用户
2. 通过 Webhook 发送群消息
"""
import logging
import json
import requests
from typing import Optional, Dict
import config

logger = logging.getLogger(__name__)


class FeishuClient:
    """飞书 API 客户端"""
    
    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id or config.FEISHU_APP_ID
        self.app_secret = app_secret or config.FEISHU_APP_SECRET
        self.base_url = "https://open.feishu.cn/open-apis"
        self.tenant_access_token = None
    
    def _get_tenant_access_token(self) -> str:
        """获取 tenant_access_token"""
        try:
            url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
            headers = {
                "Content-Type": "application/json; charset=utf-8"
            }
            data = {
                "app_id": self.app_id,
                "app_secret": self.app_secret
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") == 0:
                self.tenant_access_token = result["tenant_access_token"]
                logger.info("成功获取 tenant_access_token")
                return self.tenant_access_token
            else:
                logger.error(f"获取 token 失败: {result}")
                return None
                
        except Exception as e:
            logger.error(f"获取 tenant_access_token 失败: {e}")
            return None
    
    def _get_headers(self) -> Dict:
        """获取请求头"""
        if not self.tenant_access_token:
            self._get_tenant_access_token()
        
        return {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
    
    def get_user_id_by_phone(self, phone: str) -> Optional[str]:
        """
        通过手机号获取用户 open_id
        
        Args:
            phone: 用户手机号
        
        Returns:
            用户 open_id 或 None
        """
        try:
            url = f"{self.base_url}/contact/v3/users/batch_get_id"
            headers = self._get_headers()
            
            # 关键：设置 user_id_type=open_id，这样返回的 user_id 就是 open_id
            params = {
                "user_id_type": "open_id"
            }
            
            data = {
                "mobiles": [phone],
                "include_resigned": False
            }
            
            response = requests.post(url, headers=headers, params=params,
                                   json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") == 0:
                users = result.get("data", {}).get("user_list", [])
                if users:
                    # 当 user_id_type=open_id 时，返回的 user_id 就是 open_id
                    open_id = users[0].get("user_id")
                    logger.info(f"成功获取用户 open_id: {open_id}")
                    return open_id
                else:
                    logger.warning(f"未找到手机号 {phone} 对应的用户")
                    return None
            else:
                logger.error(f"获取用户ID失败: {result}")
                return None
                
        except Exception as e:
            logger.error(f"获取用户ID时出错: {e}")
            return None
    
    def send_message(self, receive_id: str, content: str, 
                     receive_id_type: str = "open_id", 
                     msg_type: str = "text") -> bool:
        """
        发送消息到指定用户
        
        Args:
            receive_id: 接收者ID
            content: 消息内容
            receive_id_type: ID类型 (open_id/user_id/union_id/email/chat_id)
            msg_type: 消息类型 (text/post/image/interactive)
        
        Returns:
            bool: 是否发送成功
        """
        try:
            url = f"{self.base_url}/im/v1/messages"
            headers = self._get_headers()
            
            params = {
                "receive_id_type": receive_id_type
            }
            
            # 构建消息内容
            if msg_type == "text":
                msg_content = json.dumps({"text": content}, ensure_ascii=False)
            elif msg_type == "post":
                # 富文本消息
                msg_content = json.dumps({
                    "zh_cn": {
                        "title": "Twitter 推文翻译",
                        "content": [
                            [{
                                "tag": "text",
                                "text": content
                            }]
                        ]
                    }
                }, ensure_ascii=False)
            else:
                msg_content = content
            
            data = {
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": msg_content
            }
            
            response = requests.post(url, headers=headers, params=params, 
                                   json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") == 0:
                logger.info(f"消息发送成功: {result['data']['message_id']}")
                return True
            else:
                logger.error(f"消息发送失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"发送消息时出错: {e}")
            return False
    
    def send_message_by_phone(self, phone: str, content: str, 
                              msg_type: str = "text") -> bool:
        """
        通过手机号发送消息
        
        Args:
            phone: 目标手机号
            content: 消息内容
            msg_type: 消息类型
        
        Returns:
            bool: 是否发送成功
        """
        # 1. 获取用户 open_id
        open_id = self.get_user_id_by_phone(phone)
        if not open_id:
            logger.error(f"无法获取手机号 {phone} 对应的用户 open_id")
            return False
        
        # 2. 发送消息 (使用 open_id)
        return self.send_message(open_id, content, receive_id_type="open_id", 
                                msg_type=msg_type)
    
    def send_interactive_card(self, receive_id: str, title: str, 
                              original_text: str, translated_text: str,
                              author: str, tweet_url: str,
                              receive_id_type: str = "open_id") -> bool:
        """
        发送交互式卡片消息 (更美观的展示)
        
        Args:
            receive_id: 接收者ID
            title: 卡片标题
            original_text: 原文
            translated_text: 译文
            author: 作者
            tweet_url: 推文链接
            receive_id_type: ID类型
        
        Returns:
            bool: 是否发送成功
        """
        try:
            url = f"{self.base_url}/im/v1/messages"
            headers = self._get_headers()
            
            params = {
                "receive_id_type": receive_id_type
            }
            
            # 构建卡片内容
            card_content = {
                "config": {
                    "wide_screen_mode": True
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"🐦 {title}"
                    },
                    "template": "blue"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**作者:** @{author}"
                        }
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**原文:**\n{original_text}"
                        }
                    },
                    {
                        "tag": "hr"
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**中文翻译:**\n{translated_text}"
                        }
                    },
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "查看原文"
                                },
                                "type": "primary",
                                "url": tweet_url
                            }
                        ]
                    }
                ]
            }
            
            data = {
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": json.dumps(card_content, ensure_ascii=False)
            }
            
            response = requests.post(url, headers=headers, params=params, 
                                   json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") == 0:
                logger.info(f"卡片消息发送成功: {result['data']['message_id']}")
                return True
            else:
                logger.error(f"卡片消息发送失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"发送卡片消息时出错: {e}")
            return False


class FeishuWebhookClient:
    """飞书 Webhook 客户端 (用于群消息)"""
    
    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or config.FEISHU_WEBHOOK_URL
    
    def send_text(self, content: str) -> bool:
        """发送文本消息到群"""
        try:
            if not self.webhook_url:
                logger.error("Webhook URL 未配置")
                return False
            
            data = {
                "msg_type": "text",
                "content": {
                    "text": content
                }
            }
            
            response = requests.post(self.webhook_url, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") == 0:
                logger.info("Webhook 消息发送成功")
                return True
            else:
                logger.error(f"Webhook 消息发送失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"发送 Webhook 消息时出错: {e}")
            return False
    
    def send_rich_text(self, title: str, content: str) -> bool:
        """发送富文本消息到群"""
        try:
            if not self.webhook_url:
                logger.error("Webhook URL 未配置")
                return False
            
            data = {
                "msg_type": "post",
                "content": {
                    "post": {
                        "zh_cn": {
                            "title": title,
                            "content": [
                                [{
                                    "tag": "text",
                                    "text": content
                                }]
                            ]
                        }
                    }
                }
            }
            
            response = requests.post(self.webhook_url, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") == 0:
                logger.info("Webhook 富文本消息发送成功")
                return True
            else:
                logger.error(f"Webhook 富文本消息发送失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"发送 Webhook 富文本消息时出错: {e}")
            return False


def get_feishu_client():
    """获取飞书客户端"""
    return FeishuClient()


def get_webhook_client():
    """获取 Webhook 客户端"""
    return FeishuWebhookClient()


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)
    
    # 测试应用 API 发送
    client = get_feishu_client()
    
    # 测试发送文本消息
    # client.send_message_by_phone("13xxxxxxxxx", "测试消息: 这是一个测试")
    
    # 测试发送卡片消息
    # client.send_interactive_card(
    #     receive_id="user_id",
    #     title="Twitter 推文",
    #     original_text="Hello World!",
    #     translated_text="你好，世界！",
    #     author="test_user",
    #     tweet_url="https://x.com/test/status/123"
    # )
    
    print("飞书客户端测试完成")
