"""
数据存储模块 - 管理已处理的推文ID，避免重复发送
"""
import json
import os
import logging
from typing import Set
import config

logger = logging.getLogger(__name__)


class TweetStorage:
    """推文存储管理器"""
    
    def __init__(self, filepath: str = None):
        self.filepath = filepath or config.DATA_FILE
        self.processed_ids = self._load()
    
    def _load(self) -> Set[str]:
        """从文件加载已处理的推文ID"""
        if not os.path.exists(self.filepath):
            logger.info(f"存储文件不存在，创建新文件: {self.filepath}")
            return set()
        
        # 检查文件是否为空（touch 创建的空文件）
        if os.path.getsize(self.filepath) == 0:
            logger.info(f"存储文件为空，初始化新记录: {self.filepath}")
            return set()
        
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                ids = set(data.get("processed_ids", []))
                logger.info(f"已加载 {len(ids)} 条已处理推文记录")
                return ids
        except json.JSONDecodeError as e:
            logger.error(f"存储文件 JSON 格式错误: {e}，将重置为空记录")
            return set()
        except Exception as e:
            logger.error(f"加载存储文件失败: {e}")
            return set()
    
    def save(self):
        """保存已处理的推文ID到文件"""
        try:
            data = {
                "processed_ids": list(self.processed_ids)
            }
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"已保存 {len(self.processed_ids)} 条记录")
        except Exception as e:
            logger.error(f"保存存储文件失败: {e}")
    
    def is_processed(self, tweet_id: str) -> bool:
        """检查推文是否已处理"""
        return tweet_id in self.processed_ids
    
    def mark_processed(self, tweet_id: str):
        """标记推文为已处理"""
        self.processed_ids.add(tweet_id)
        self.save()
        logger.info(f"标记推文 {tweet_id} 为已处理")
    
    def get_processed_count(self) -> int:
        """获取已处理的推文数量"""
        return len(self.processed_ids)
    
    def clear(self):
        """清空所有记录"""
        self.processed_ids.clear()
        self.save()
        logger.info("已清空所有记录")


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)
    
    storage = TweetStorage()
    
    # 测试添加
    storage.mark_processed("12345")
    storage.mark_processed("67890")
    
    # 测试检查
    print(f"12345 已处理: {storage.is_processed('12345')}")
    print(f"99999 已处理: {storage.is_processed('99999')}")
    print(f"已处理数量: {storage.get_processed_count()}")
    
    # 清空测试数据
    storage.clear()
