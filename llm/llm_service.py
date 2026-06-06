import httpx
import asyncio
import logging
from typing import Optional
from configs.base import settings

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self):
        self.base_url  = settings.LLM_BASE_URL
        self.model     = settings.LLM_MODEL
        self.timeout   = settings.LLM_TIMEOUT
        self.max_retry = settings.LLM_MAX_RETRY

    async def complete(
        self,
        prompt: str,
        context: Optional[list] = None,
        stream: bool = False,
    ) -> dict:
        """
        Call local Mistral LLM.
        Returns {"response": "...", "context": [...], "done": True}
        """
        payload = {
            "model":   self.model,
            "prompt":  prompt,
            "stream":  stream,
        }
        if context:
            payload["context"] = context

        for attempt in range(1, self.max_retry + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(self.base_url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    logger.info(f"LLM call succeeded on attempt {attempt}")
                    return {
                        "response": data.get("response", ""),
                        "context":  data.get("context", []),
                        "done":     data.get("done", True),
                    }
            except httpx.TimeoutException:
                logger.warning(f"LLM timeout on attempt {attempt}/{self.max_retry}")
                if attempt == self.max_retry:
                    raise RuntimeError("LLM service timed out after max retries")
                await asyncio.sleep(2 ** attempt)
            except httpx.HTTPStatusError as e:
                logger.error(f"LLM HTTP error {e.response.status_code}: {e}")
                raise RuntimeError(f"LLM HTTP error: {e.response.status_code}")
            except Exception as e:
                logger.error(f"LLM unexpected error on attempt {attempt}: {e}")
                if attempt == self.max_retry:
                    raise
                await asyncio.sleep(2 ** attempt)
        raise RuntimeError("LLM failed after all retries")

    async def complete_text(self, prompt: str, context: Optional[list] = None) -> str:
        result = await self.complete(prompt, context)
        return result["response"]
