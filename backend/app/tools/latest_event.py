from app.es_client import get_es_client
from app.tools.search_logs import SOURCE_FIELDS
from app.tools.validators import validate_index_pattern

def get_latest_event(index: str) -> dict:
    index = validate_index_pattern(index)
    es = get_es_client()
    result = es.search(
        index=index,
        size=1,
        query={
            "match_all": {}
        },
        sort=[
            {
                "@timestamp": {
                    "order": "desc"
                }
            }
        ],
        source=SOURCE_FIELDS
    )
    hits = result["hits"]["hits"]
    
    if not hits:
        return {
            "index": index,
            "found": False,
            "event": None
        }
        
    return {
        "index": index,
        "found": True,
        "event": hits[0]["_source"]
    }
