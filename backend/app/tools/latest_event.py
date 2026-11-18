from app.es_client import get_es_client
from app.tools.search_logs import SOURCE_FIELDS
from app.tools.validators import validate_index_pattern
from app.tools.time_utils import to_wib_iso, to_wib_str

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
        
    src = hits[0]["_source"]
    if "@timestamp" in src:
        src["timestamp_wib"] = to_wib_str(src["@timestamp"])
        src["@timestamp"] = to_wib_iso(src["@timestamp"])

    return {
        "index": index,
        "found": True,
        "event": src
    }
