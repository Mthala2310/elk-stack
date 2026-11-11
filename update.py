import os

latest_event_code = '''from app.es_client import get_es_client
from app.tools.validators import validate_index_pattern

SOURCE_FIELDS = [
    "@timestamp",
    "ip_addr",
    "http_method",
    "request_path",
    "http_version",
    "status_code",
    "request_size",
    "referrer",
    "user_agent",
    "response_time",
    "message",
]

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
'''

with open("backend/app/tools/latest_event.py", "w", encoding="utf-8") as f:
    f.write(latest_event_code)

main_py_path = "backend/app/main.py"
with open(main_py_path, "r", encoding="utf-8") as f:
    main_content = f.read()

# Add import
import_to_add = "from app.tools.latest_event import get_latest_event"
if import_to_add not in main_content:
    main_content = main_content.replace("from app.tools.index_info import get_index_info", "from app.tools.index_info import get_index_info\\n" + import_to_add)

# Add endpoint
endpoint_code = '''
@app.get("/api/tools/latest-event")
def latest_event(index: str = "app-logs-*"):
    try:
        return get_latest_event(index)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )
'''
if "/api/tools/latest-event" not in main_content:
    main_content += "\\n" + endpoint_code

with open(main_py_path, "w", encoding="utf-8") as f:
    f.write(main_content)

print("SUCCESS")