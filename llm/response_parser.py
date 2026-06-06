import json
import re
import logging

logger = logging.getLogger(__name__)


class ResponseParser:

    @staticmethod
    def parse_json(text: str) -> dict:
        """Extract JSON from LLM response using 3 strategies."""
        # Strategy 1: direct parse
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Strategy 2: extract from ```json ... ```
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Strategy 3: find first { ... }
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning(f"Failed to parse JSON from LLM response: {text[:200]}")
        return {"raw_response": text, "parse_error": True}

    @staticmethod
    def safe_text(text: str) -> str:
        return text.strip() if text else ""
