from datetime import datetime



from app.config import get_settings
from app.services.openrouter_client import openrouter_chat


import json

from app.ai.system_prompt import SYSTEM_PROMPT
from app.ai.tool_definitions import OPENROUTER_TOOLS



from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from app.es_client import get_es_client
from app.models import TimeRange, ChatRequest
from app.tools.index_info import get_index_info
from app.tools.latest_event import get_latest_event
from app.tools.log_summary import get_log_summary
from app.tools.search_logs import search_logs
from app.tools.top_error_paths import get_top_error_paths
from app.tools.slow_requests import get_slow_requests
from app.tools.trace_lookup import get_trace_timeline
from app.ai.tool_executor import execute_tool
from app.ai.orchestrator import run_ai_chat
from app.api.reports import router as report_router

app = FastAPI(
    title="AI Log Observability Backend",
    version="0.1.0",
)

app.include_router(report_router)


@app.get("/")
def root():
    return {
        "service": "AI Log Observability Backend",
        "phase": 5,
        "status": "running",
    }


@app.get("/api/system/health")
def system_health():
    es = get_es_client()

    try:
        info = es.info()
        return {
            "backend": "ok",
            "elasticsearch": "ok",
            "cluster_name": info.get("cluster_name"),
            "elasticsearch_version": info.get("version", {}).get("number"),
        }
    except Exception as exc:
        return {
            "backend": "ok",
            "elasticsearch": "unavailable",
            "detail": str(exc),
        }


@app.get("/api/tools/index-info")
def index_info(index: str = "app-logs-*"):
    try:
        return get_index_info(index)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/tools/latest-event")
def latest_event(index: str = "app-logs-*"):
    try:
        return get_latest_event(index)
    except HTTPException:
        raise
    except Exception as exc:
        return HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.get("/api/tools/search-logs")
def search_logs_endpoint(
    start: datetime,
    end: datetime,
    index: str = "app-logs-*",
    status_code: int | None = None,
    path: str | None = None,
    keyword: str | None = None,
    trace_id: str | None = None,
    service_name: str | None = None,
    step_name: str | None = None,
    log_level: str | None = None,
    limit: int = 20,
    offset: int = 0,
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
            trace_id=trace_id,
            service_name=service_name,
            step_name=step_name,
            log_level=log_level,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.get("/api/tools/trace-lookup")
def trace_lookup_endpoint(
    trace_id: str,
    index: str = "app-logs-*",
    limit: int = 100,
):
    try:
        return get_trace_timeline(
            trace_id=trace_id,
            index=index,
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


@app.get("/api/tools/log-summary")
def log_summary_endpoint(
    start: datetime,
    end: datetime,
    index: str = "app-logs-*",
):
    try:
        time_range = TimeRange(
            start=start,
            end=end
        )
        return get_log_summary(
            index=index,
            time_range=time_range
        )
    except HTTPException:
        raise
    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )
    except Exception as exc:
        return HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.get("/api/tools/top-error-paths")
def top_error_paths_endpoint(
    start: datetime,
    end: datetime,
    index: str = "app-logs-*",
    error_class: str = "all",
    limit: int = 10,
):
    try:
        time_range = TimeRange(
            start=start,
            end=end
        )
        return get_top_error_paths(
            index=index,
            time_range=time_range,
            error_class=error_class,
            limit=limit,
        )
    except HTTPException:
        raise
    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.get("/api/tools/slow-requests")
def slow_requests_endpoint(
    start: datetime,
    end: datetime,
    index: str = "app-logs-*",
    min_response_time: float | None = None,
    limit: int = 10,
    offset: int = 0,
):
    try:

        time_range = TimeRange(
            start=start,
            end=end
        )

        return get_slow_requests(
            index=index,
            time_range=time_range,
            min_response_time=min_response_time,
            limit=limit,
            offset=offset,
        )

    except HTTPException:
        raise

    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.get("/api/ai/test")
def ai_connection_test():

    try:

        settings = get_settings()

        result = openrouter_chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a connectivity test. "
                        "Reply exactly with OPENROUTER_OK."
                    ),
                },
                {
                    "role": "user",
                    "content": "Test connection.",
                },
            ]
        )

        message = (
            result["choices"][0]
            ["message"]
            ["content"]
        )

        return {
            "status": "ok",
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "response": message,
        }

    except Exception as exc:

        raise HTTPException(
            status_code=502,
            detail=str(exc)
        )


@app.get("/api/ai/tool-choice-test")
def tool_choice_test(
    question: str
):
    try:

        result = openrouter_chat(
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": question,
                },
            ],

            tools=OPENROUTER_TOOLS,

            tool_choice="auto",
        )

        message = (
            result["choices"][0]
            ["message"]
        )

        tool_calls = message.get(
            "tool_calls",
            []
        )

        parsed_tool_calls = []

        for tool_call in tool_calls:

            function = tool_call["function"]

            arguments = json.loads(
                function["arguments"]
            )

            parsed_tool_calls.append(
                {
                    "tool_name": function["name"],
                    "arguments": arguments,
                }
            )

        return {
            "message_content": message.get(
                "content"
            ),

            "tool_calls": parsed_tool_calls,
        }

    except Exception as exc:

        raise HTTPException(
            status_code=502,
            detail=str(exc)
        )
@app.get("/api/ai/tool-execute-test")
def tool_execute_test(question: str):
    try:
        result = openrouter_chat(
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": question,
                },
            ],
            tools=OPENROUTER_TOOLS,
            tool_choice="auto",
        )

        message = result["choices"][0]["message"]
        tool_calls = message.get("tool_calls", [])

        if not tool_calls:
            return {
                "tool_selected": False,
                "tool_count": 0,
                "message_content": message.get("content"),
                "evidence": [],
            }

        evidence_results = []
        for tool_call in tool_calls:
            function = tool_call["function"]
            tool_name = function["name"]
            import json
            arguments = json.loads(function["arguments"])

            evidence = execute_tool(
                tool_name=tool_name,
                arguments=arguments,
            )

            evidence_results.append(
                {
                    "tool_call_id": tool_call.get("id"),
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "evidence": evidence,
                }
            )

        return {
            "tool_selected": True,
            "tool_count": len(evidence_results),
            "results": evidence_results,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc)
        )


@app.post("/api/ai/chat")
def ai_chat(
    request: ChatRequest
):
    try:
        return run_ai_chat(
            user_message=request.message,
            index_context=request.index,
        )
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )

