import httpx
from app.core.config import settings


class SnwolleyConfigurationError(RuntimeError):
    pass


class SnwolleyResponseError(RuntimeError):
    pass


class SnwolleyRateLimitError(RuntimeError):
    def __init__(self, retry_after: str):
        super().__init__(f"Snwolley rate limit reached; retry after {retry_after} seconds")
        self.retry_after = retry_after


async def ask_snwolley(message: str, chat_id: str | None = None) -> dict:
    """Send bounded, application-generated business context to Snwolley.

    The API key is read only by the backend. We deliberately do not retry 429s
    automatically because the provider specifies a five-request-per-minute cap.
    """
    if not settings.snwolley_api_key:
        raise SnwolleyConfigurationError("SNWOLLEY_API_KEY is not configured")

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": settings.snwolley_api_key,
    }
    payload = {"message": message[:12000], "stream": False}
    if chat_id:
        payload["chat_id"] = chat_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(settings.snwolley_api_url, headers=headers, json=payload)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "unknown")
            raise SnwolleyRateLimitError(retry_after)
        if response.status_code == 401:
            raise SnwolleyConfigurationError("Snwolley API key was rejected")
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise SnwolleyResponseError("Snwolley returned a non-JSON response") from exc
        if not isinstance(payload, dict):
            raise SnwolleyResponseError("Snwolley returned an unexpected response format")
        return payload
