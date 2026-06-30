"""Scenario metadata enrichment through the category sub-agent."""
from __future__ import annotations

import json
import global_config
from dataclasses import replace
from functools import lru_cache

from app.models import TestCase

DEFAULT_CATEGORY_RESULT = {
    "scenario_type": "spec",
    "product_family": "unknown",
    "released_override": False,
    "policy_tags": []
}

VALID_SCENARIO_TYPES = {"spec", "comparison", "policy_sensitive", "noise_sensitive"}

def _has_middle_agent_key() -> bool:
    return bool(global_config.API_KEY_MIDDLE)


def _extract_json_object(text: str) -> dict:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise

def _normalize_category_payload(payload: dict) -> dict:
    scenario_type = str(payload.get("scenario_type") or "spec").strip()
    if scenario_type not in VALID_SCENARIO_TYPES:
        scenario_type = "spec"

    product_family = str(payload.get("product_family") or "unknown").strip() or "unknown"
    policy_tags = payload.get("policy_tags") or []
    if not isinstance(policy_tags, list):
        policy_tags = []

    return {
        "scenario_type": scenario_type,
        "product_family": product_family,
        "released_override": bool(payload.get("released_override", False)),
        "policy_tags": [str(tag).strip() for tag in policy_tags if str(tag.strip())]
    }

@lru_cache(maxsize=512)
def classify_scenario_text(category: str, question: str, expected_keywords: tuple[str, ...]=()):
    """Classify scenario metadata with the dedicated category sub-agent."""
    if not _has_middle_agent_key():
        return dict(DEFAULT_CATEGORY_RESULT)

    try:
        from agents.sub_agents.category_agent import CategoryAgent

        agent = CategoryAgent()
        result = agent.invoke(
            json.dumps(
                {
                    "category": category,
                    "question": question,
                    "expected_keywords": list(expected_keywords)
                },
                ensure_ascii=False
            )
        )
        content = result["messages"][-1].content
        return _normalize_category_payload(_extract_json_object(content))
    except Exception:
        return dict(DEFAULT_CATEGORY_RESULT)

def enrich_test_case_metadata(test_case: TestCase) -> TestCase:
    metadata = classify_scenario_text(
        test_case.category,
        test_case.question,
        tuple(test_case.expected_keywords)
    )
    return replace(
        test_case,
        scenario_type=metadata["scenario_type"],
        product_family=metadata["product_family"],
        released_override=metadata["released_override"],
        policy_tags=metadata["policy_tags"],
    )