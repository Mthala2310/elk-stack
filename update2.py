import os

# 1. Create models.py
models_code = '''from datetime import datetime
from pydantic import BaseModel, model_validator
from app.config import get_settings

class TimeRange(BaseModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError(
                "start dan end wajib memiliki timezone."
            )
        if self.start >= self.end:
            raise ValueError(
                "start harus lebih kecil dari end."
            )
        
        max_hours = get_settings().tool_max_lookback_hours
        duration_hours = (
            self.end - self.start
        ).total_seconds() / 3600
        
        if duration_hours > max_hours:
            raise ValueError(
                f"Time range maksimal {max_hours} jam."
            )
        return self
'''
with open("backend/app/models.py", "w", encoding="utf-8") as f:
    f.write(models_code)

# 2. Update validators.py
validate_limit_code = '''
def validate_limit(limit: int) -> int:
    max_results = get_settings().tool_max_results
    if limit < 1:
        raise HTTPException(
            status_code=400,
            detail="limit minimal 1"
        )
    if limit > max_results:
        raise HTTPException(
            status_code=400,
            detail=f"limit maksimal {max_results}"
        )
    return limit
'''
with open("backend/app/tools/validators.py", "a", encoding="utf-8") as f:
    f.write(validate_limit_code)

# 3. Create search_logs.py
search_logs_code = '''from app.es_client import get_es_client
from app.models import TimeRange
from app.tools.validators import (
    validate_index_pattern,
    validate_limit,
)

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

def search_logs(
    index: str,
    time_range: TimeRange,
    status_code: int | None = None,
    path: str | None = None,
    keyword: str | None = None,
    limit: int = 20,
) -> dict:
    index = validate_index_pattern(index)
    limit = validate_limit(limit)
    es = get_es_client()
    
    filters = [
        {
            "range": {
                "@timestamp": {
                    "gte": time_range.start.isoformat(),
                    "lte": time_range.end.isoformat(),
                }
            }
        }
    ]
    
    must = []
    
    if status_code is not None:
        filters.append(
            {"term": {"status_code": status_code}}
        )
        
    if path is not None:
        filters.append(
            {"term": {"request_path.keyword": path}} # usually it's exact match, we can use match as well, but term is better for path if it's keyword
        ) # Actually, the user's snippet cut off. Let's use match for path as requested or just standard match
        
    if keyword is not None:
        must.append(
            {"match": {"message": keyword}}
        )

    # Let's adjust path to match if user wanted match
    if path is not None:
        filters[-1] = {"match": {"request_path": path}}

    query = {"bool": {"filter": filters}}
    if must:
        query["bool"]["must"] = must

    result = es.search(
        index=index,
        size=limit,
        query=query,
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
    
    return {
        "index": index,
        "count": len(hits),
        "total": result["hits"]["total"]["value"] if isinstance(result["hits"]["total"], dict) else result["hits"]["total"],
        "events": [hit["_source"] for hit in hits]
    }
'''
with open("backend/app/tools/search_logs.py", "w", encoding="utf-8") as f:
    f.write(search_logs_code)

# 4. Update main.py
with open("backend/app/main.py", "r", encoding="utf-8") as f:
    main_content = f.read()

import_code = '''
from datetime import datetime
from app.models import TimeRange
from app.tools.search_logs import search_logs
'''
if "from app.models import TimeRange" not in main_content:
    # insert after the last import
    main_content = main_content.replace("from app.tools.latest_event import get_latest_event", "from app.tools.latest_event import get_latest_event" + import_code)

endpoint_code = '''
@app.get("/api/tools/search-logs")
def search_logs_endpoint(
    start: datetime,
    end: datetime,
    index: str = "app-logs-*",
    status_code: int | None = None,
    path: str | None = None,
    keyword: str | None = None,
    limit: int = 20,
):
    try:
        time_range = TimeRange(
            start=start,
            end=end
        )
        return search_logs(
            index=index,
            time_range=time_range,
            status_code=status_code,
            path=path,
            keyword=keyword,
            limit=limit,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )
'''
if "/api/tools/search-logs" not in main_content:
    main_content += "\n" + endpoint_code

with open("backend/app/main.py", "w", encoding="utf-8") as f:
    f.write(main_content)

print("SUCCESS")