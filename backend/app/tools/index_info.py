from app.es_client import get_es_client
from app.tools.validators import validate_index_pattern


def get_index_info(index: str) -> dict:
    index = validate_index_pattern(index)
    es = get_es_client()

    resolved = es.indices.resolve_index(name=index)
    matching_indices = [
        item["name"]
        for item in resolved.get("indices", [])
        if item.get("name")
    ]

    count_result = es.count(index=index)

    return {
        "requested_pattern": index,
        "matching_indices": matching_indices,
        "matching_index_count": len(matching_indices),
        "document_count": count_result["count"],
    }
