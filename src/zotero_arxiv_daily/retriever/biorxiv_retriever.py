from datetime import datetime
import json # 新增：用于处理 JSON 异常
import requests
import os
proxy_url = os.environ.get("BIORXIV_PROXY")
proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
from .base import BaseRetriever, register_retriever
from ..protocol import Paper
from loguru import logger
from typing import Any
from time import sleep

@register_retriever("biorxiv")
class BiorxivRetriever(BaseRetriever):
    server = "biorxiv"

    def __init__(self, config):
        super().__init__(config)
        if self.retriever_config.category is None:
            raise ValueError(f"category must be specified for {self.name}")

    def _retrieve_raw_papers(self) -> list[dict[str, Any]]:
        api_url = f"https://api.biorxiv.org/details/{self.server}/2d"
        retry_num = 10
        delay_time = 10
        
        # 2. 伪装成浏览器（绕过 Cloudflare 等反爬机制）
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }

        response = None
        for i in range(retry_num):
            try:
                # 3. 在请求中传入 headers 
                response = requests.get(
                    api_url, 
                    headers=headers,  
                    timeout=30,
                    proxies=proxies
                )
                response.raise_for_status()
                
                # 4. 先尝试解析 JSON，如果失败会抛出异常，被下面的 except 捕获
                result = response.json()
                break # 成功则跳出循环
                
            except Exception as e:
                if i == retry_num - 1:
                    # 最后一次重试仍然失败，打印详细的错误信息以便排查
                    if response is not None:
                        logger.error(f"API 返回状态码: {response.status_code}")
                        logger.error(f"API 返回内容: {response.text[:500]}") # 打印前500个字符
                    raise e
                else:
                    logger.warning(f"Failed to retrieve papers: {str(e)}. Retry in {delay_time} seconds.")
                    sleep(delay_time)

        collection = result.get("collection", [])
        if len(collection) == 0:
            logger.warning(f"No paper found. API Message: {result.get('messages')}")
            return []
            
        dated_collection = [
            (datetime.strptime(c["date"], "%Y-%m-%d").date(), c)
            for c in collection
        ]
        latest_date = max(date for date, _ in dated_collection)
        collection = [c for date, c in dated_collection if date == latest_date]
        categories = [c.lower() for c in self.retriever_config.category]
        collection = [c for c in collection if c["category"] in categories]
        if self.config.executor.debug:
            collection = collection[:10]
        return collection


    def convert_to_paper(self, raw_paper:dict[str, Any]) -> Paper | None:
        title = raw_paper['title']
        authors = [a.strip() for a in raw_paper['authors'].split(';')]
        abstract = raw_paper['abstract']
        pdf_url = f"https://www.{self.server}.org/content/{raw_paper['doi']}v{raw_paper['version']}.full.pdf"
        full_text = None # biorxiv forbids scraping its pdf
        return Paper(
            source=self.name,
            title=title,
            authors=authors,
            abstract=abstract,
            url=pdf_url,
            pdf_url=pdf_url,
            full_text=full_text
        )
