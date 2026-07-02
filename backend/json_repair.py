"""JSON extraction and repair for LLM structured output."""
import json
import re
from typing import Any, Optional


_FENCED_JSON_RE = re.compile(
    r"```(?:json|text)?[ \t]*\r?\n(.*?)\r?\n[ \t]*```",
    re.DOTALL | re.IGNORECASE,
)


def _iter_balanced_json_candidates(text: str):
    """Yield balanced object/array candidates while ignoring delimiters in strings."""
    matching = {"{": "}", "[": "]"}
    closing = set(matching.values())

    for start, opening in enumerate(text):
        if opening not in matching:
            continue

        stack = []
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char in matching:
                stack.append(char)
            elif char in closing:
                if not stack or matching[stack[-1]] != char:
                    break
                stack.pop()
                if not stack:
                    yield text[start:index + 1]
                    break


def extract_json_block(text: str) -> Optional[Any]:
    """Extract the first repairable JSON value from fenced or surrounding text."""
    if not text:
        return None

    for fenced_content in _FENCED_JSON_RE.findall(text):
        result = repair_json(fenced_content.strip())
        if result is not None:
            return result

    for candidate in _iter_balanced_json_candidates(text):
        result = repair_json(candidate)
        if result is not None:
            return result

    return None


def repair_json(text: str) -> Optional[Any]:
    """Attempt to parse JSON with common LLM error repairs."""
    if not text:
        return None

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fix trailing commas
    fixed = re.sub(r',\s*([}\]])', r'\1', text)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Fix single quotes
    fixed2 = fixed.replace("'", '"')
    try:
        return json.loads(fixed2)
    except json.JSONDecodeError:
        pass

    return None
