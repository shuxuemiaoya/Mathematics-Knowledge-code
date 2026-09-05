# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod

class BaseResourceAdapter(ABC):
    """资源获取策略基类"""
    
    @abstractmethod
    def match(self, url: str) -> bool:
        """判断当前页面 URL 是否由本适配器处理"""
        pass
        
    @abstractmethod
    def run(self, output_dir: str, **kwargs):
        """执行抓取与归档流水线"""
        pass
