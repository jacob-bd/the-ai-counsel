"""Council lineup normalization and validation."""

from __future__ import annotations

from typing import List, Optional, Tuple

from .settings import normalize_model_ids


def requires_chairman(execution_mode: str, *, critique_mode: str = "freeform") -> bool:
    """Return whether a chairman model is required for the given run mode."""
    if critique_mode == "audit":
        return True
    return execution_mode == "full"


def validate_council_lineup(
    council_models: Optional[List[str]],
    chairman_model: Optional[str],
    *,
    execution_mode: str,
    critique_mode: str = "freeform",
    fallback_council: Optional[List[str]] = None,
    fallback_chairman: Optional[str] = None,
) -> Tuple[List[str], str]:
    """
    Normalize and validate a council lineup.

    Raises:
        ValueError: When council models are empty or chairman is required but missing.
    """
    source = council_models if council_models is not None else fallback_council
    models = normalize_model_ids(source)
    if not models:
        raise ValueError("At least one council model is required")

    chairman_source = chairman_model if chairman_model is not None else fallback_chairman
    chairman = str(chairman_source or "").strip()
    if requires_chairman(execution_mode, critique_mode=critique_mode) and not chairman:
        raise ValueError("A chairman model is required for this execution mode")

    return models, chairman
