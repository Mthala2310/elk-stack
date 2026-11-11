import time
from typing import Any
import httpx

from app.config import get_settings


def _extract_error_message(response: httpx.Response) -> str | None:
    try:
        data = response.json()
        if isinstance(data, dict):
            error = data.get("error", {})
            if isinstance(error, dict):
                return error.get("message")
            return str(error)
    except Exception:
        pass
    return response.text.strip() or None


def _retry_delay(
    response: httpx.Response | None,
    attempt: int,
    base_seconds: float,
) -> float:
    if response is not None and response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
    # Exponential backoff: base_seconds * (2 ** attempt)
    return base_seconds * (2 ** attempt)


def openrouter_chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
) -> dict:
    settings = get_settings()

    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY belum dikonfigurasi."
        )

    url = f"{settings.openrouter_base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "X-Title": "AI Log Observability Platform",
    }

    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0.1,
        "stream": False,
    }

    if tools is not None:
        payload["tools"] = tools

    if tool_choice is not None:
        payload["tool_choice"] = tool_choice

    max_attempts = 1 + max(0, settings.llm_max_retries)

    for attempt in range(max_attempts):
        try:
            with httpx.Client(
                timeout=settings.llm_timeout_seconds
            ) as client:
                response = client.post(
                    url,
                    headers=headers,
                    json=payload,
                )

            # =============================
            # RETRYABLE HTTP STATUS (429, 500, 502, 503, 504)
            # =============================
            if response.status_code in {429, 500, 502, 503, 504}:
                if attempt < max_attempts - 1:
                    delay = _retry_delay(
                        response=response,
                        attempt=attempt,
                        base_seconds=settings.llm_retry_base_seconds,
                    )
                    time.sleep(delay)
                    continue

                message = _extract_error_message(response)
                raise RuntimeError(
                    f"OpenRouter gagal setelah {max_attempts} percobaan "
                    f"(HTTP {response.status_code})"
                    + (f": {message}" if message else ".")
                )

            # Non-retryable HTTP status error (400, 401, 403, etc.)
            response.raise_for_status()

            data = response.json()

            if not isinstance(data, dict):
                raise RuntimeError(
                    "Response OpenRouter bukan JSON object yang valid."
                )

            if "error" in data:
                error_data = data["error"]
                error_message = (
                    error_data.get("message", "Unknown OpenRouter error")
                    if isinstance(error_data, dict)
                    else str(error_data)
                )
                raise RuntimeError(
                    f"OpenRouter API error: {error_message}"
                )

            if "choices" not in data or not data["choices"]:
                raise RuntimeError(
                    "Response OpenRouter tidak memiliki 'choices' yang valid."
                )

            return data

        # =============================
        # TIMEOUT
        # =============================
        except httpx.TimeoutException as exc:
            if attempt < max_attempts - 1:
                delay = _retry_delay(
                    response=None,
                    attempt=attempt,
                    base_seconds=settings.llm_retry_base_seconds,
                )
                time.sleep(delay)
                continue

            raise RuntimeError(
                "OpenRouter timeout setelah "
                f"{max_attempts} percobaan."
            ) from exc

        # =============================
        # NETWORK / CONNECTION
        # =============================
        except httpx.RequestError as exc:
            if attempt < max_attempts - 1:
                delay = _retry_delay(
                    response=None,
                    attempt=attempt,
                    base_seconds=settings.llm_retry_base_seconds,
                )
                time.sleep(delay)
                continue

            raise RuntimeError(
                "OpenRouter tidak dapat "
                "dihubungi setelah "
                f"{max_attempts} percobaan. "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        # =============================
        # NON-RETRYABLE HTTP STATUS
        # =============================
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            message = _extract_error_message(exc.response)
            raise RuntimeError(
                f"OpenRouter menolak request "
                f"(HTTP {status_code})"
                + (f": {message}" if message else ".")
            ) from exc

    raise RuntimeError("OpenRouter request gagal.")
