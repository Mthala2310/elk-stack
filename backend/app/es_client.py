from functools import lru_cache

# pyrefly: ignore [missing-import]
from elasticsearch import Elasticsearch

from app.config import get_settings


@lru_cache
def get_es_client() -> Elasticsearch:
    settings = get_settings()
    return Elasticsearch(
        settings.elasticsearch_url,
        request_timeout=10,
        retry_on_timeout=True,
        max_retries=2,
    )
