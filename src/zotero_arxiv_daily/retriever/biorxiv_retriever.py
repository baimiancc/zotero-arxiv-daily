from datetime import datetime
import xml.etree.ElementTree as ET
import requests
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
        # 1. 构造 RSS 请求 URL（使用 connect 域名，绕过 API 封锁）
        rss_url = f"https://connect.{self.server}.org/{self.server}_xml.php?subject=all"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        
        retry_num = 5
        delay_time = 10
        response = None

        for i in range(retry_num):
            try:
                # 2. 直接请求，不加 proxies
                response = requests.get(rss_url, headers=headers, timeout=60)
                response.raise_for_status()
                break
            except Exception as e:
                if i == retry_num - 1:
                    logger.error(f"Failed to fetch RSS: {e}")
                    raise e
                else:
                    logger.warning(f"Failed to retrieve papers: {e}. Retry in {delay_time} seconds.")
                    sleep(delay_time)

        # 3. 解析 XML
        try:
            root = ET.fromstring(response.content)
            # 移除 XML 的命名空间，方便查找元素
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]
            
            items = root.findall(".//item")
        except Exception as e:
            logger.error(f"Failed to parse XML: {e}")
            return []

        collection = []
        for item in items:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            description = item.findtext("description", "")
            
            # 提取作者（通常在 creator 或 author 中）
            authors = item.findtext("creator", "") or item.findtext("author", "")
            
            # 从链接中提取 DOI 和版本 (链接格式类似 .../content/10.1101/2023.10.24.563789v1)
            doi = ""
            version = "1"
            if link:
                parts = link.split('/')
                if parts:
                    raw_doi = parts[-1]
                    if 'v' in raw_doi:
                        doi, version = raw_doi.rsplit('v', 1)
                    else:
                        doi = raw_doi

            pub_date_str = item.findtext("pubDate", "")
            category = item.findtext("category", "")
            
            # 统一日期格式为 YYYY-MM-DD
            date_str = datetime.now().strftime("%Y-%m-%d") # 默认今天
            if pub_date_str:
                try:
                    # RSS 日期格式通常是 "Tue, 24 Sep 2026 00:00:00 GMT"
                    # 截取前16个字符转换
                    dt = datetime.strptime(pub_date_str[:16], "%a, %d %b %Y")
                    date_str = dt.strftime("%Y-%m-%d")
                except Exception:
                    pass

            collection.append({
                "title": title,
                "authors": authors,
                "abstract": description,
                "doi": doi,
                "version": version,
                "date": date_str,
                "category": category.lower()
            })

        # 4. 按类别过滤
        categories = [c.lower() for c in self.retriever_config.category]
        collection = [c for c in collection if c["category"] in categories]
        
        # 5. 过滤出最新日期的论文（保留原有逻辑）
        if collection:
            dated_collection = [
                (datetime.strptime(c['date'], "%Y-%m-%d").date(), c)
                for c in collection
            ]
            latest_date = max(date for date, _ in dated_collection)
            collection = [c for date, c in dated_collection if date == latest_date]

        if self.config.executor.debug:
            collection = collection[:10]

        return collection

    def convert_to_paper(self, raw_paper: dict[str, Any]) -> Paper | None:
        title = raw_paper['title']
        authors = [a.strip() for a in raw_paper['authors'].split(';')]
        abstract = raw_paper['abstract']
        pdf_url = f"https://www.{self.server}.org/content/{raw_paper['doi']}v{raw_paper['version']}.full.pdf"
        full_text = None
        return Paper(
            source=self.name,
            title=title,
            authors=authors,
            abstract=abstract,
            url=pdf_url,
            pdf_url=pdf_url,
            full_text=full_text,
        )
