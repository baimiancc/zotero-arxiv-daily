from datetime import datetime

import requests
from .base import BaseRetriever, register_retriever
from ..protocol import Paper
from loguru import logger
from typing import Any
from time import sleep

@register_retriever("biorxiv")
class BiorxivRetriever(BaseRetriever):
    server = "biorxiv"

    def _retrieve_raw_papers(self) -> list[dict[str, Any]]:
        # 1. 伪装成浏览器，防止被bioRxiv服务器拦截
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        
        api_url = f"https://api.biorxiv.org/details/{self.server}/2d"
        retry_num = 10
        delay_time = 10
        response = None

        for i in range(retry_num):
            try:
                # 发送请求时带上伪装头（headers）
                response = requests.get(api_url, headers=headers, timeout=30)
                response.raise_for_status()
                break
            except Exception as e:
                if i == retry_num - 1:
                    raise e
                else:
                    logger.warning(f"Failed to retrieve papers: {str(e)}. Retry in {delay_time} seconds.")
                    sleep(delay_time)

        # 2. 检查服务器到底返回了什么（关键修复！）
        try:
            response_text = response.text or ""
        except Exception:
            logger.warning("无法读取 bioRxiv API 返回内容")
            return []
        if not response_text.strip():
            logger.warning("bioRxiv API 返回空内容")
            return []

        try:
            result = response.json()
        except Exception as e:
            # 如果解析JSON失败，不要直接崩溃，而是打印出服务器返回的前500个字符看看是什么
            logger.error("JSON解析失败！服务器返回的内容可能不是JSON格式。")
            logger.error(f"返回的原始内容前500字符: {response.text[:500]}")
            return []
            
        collection = result.get("collection", [])
        if len(collection) == 0:
            logger.warning(f"No paper found. API Message: {result.get('messages', '')}")
            return []
            
        dated_collection = [
            (datetime.strptime(c['date'], "%Y-%m-%d").date(), c)
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
