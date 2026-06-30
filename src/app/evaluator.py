"""OpenAI-based structured evaluation for extracted QA pairs."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any

from openai import OpenAI
from llm.factory import get_llm

from app.config import AppConfig
from app.dom_extractor import (
    _detect_topic_family as _dom_detect_topic_family,
    _is_question_repetition as _dom_is_question_repetition,
    _looks_truncated as _dom_looks_truncated,
)
from app.error_taxonomy import (
    CARRYOVER_CONTAMINATION,
    INVALID_ANSWER,
    LOW_CONFIDENCE_EXTRACTION,
    PROMO_OR_REVIEW_LEAK,
    QUESTION_REPETITION,
    SPECULATIVE_UNVERIFIED,
    TOPIC_MISMATCH,
    TRUNCATED_ANSWER,
    normalize_error_flag,
)
from app.models import EvalResult, ExtractedPair, TestCase
from agents.sub_agents.evaluation_agent import EvaluationAgent

ALLOWED_FLAGS = {
    QUESTION_REPETITION,
    CARRYOVER_CONTAMINATION,
    SPECULATIVE_UNVERIFIED,
    TRUNCATED_ANSWER,
    PROMO_OR_REVIEW_LEAK,
    TOPIC_MISMATCH,
    INVALID_ANSWER,
    LOW_CONFIDENCE_EXTRACTION,
    "weak_keyword_alignment",
    "too_short",
    "timestamp_like",
    "input_not_verified",
    "evaluation_failed",
}

EVALUATOR_VERSION = "evaluator-v3.0"

EVALUATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "score_scale": {"type": "string", "enum": ["0-10"]},
        "evaluation_language": {"type": "string", "enum": ["en"]},
        "overall_score": {"type": "number", "minimum": 0, "maximum": 10},
        "correctness_score": {"type": "number", "minimum": 0, "maximum": 4},
        "relevance_score": {"type": "number", "minimum": 0, "maximum": 2},
        "completeness_score": {"type": "number", "minimum": 0, "maximum": 2},
        "clarity_score": {"type": "number", "minimum": 0, "maximum": 1},
        "groundedness_score": {"type": "number", "minimum": 0, "maximum": 1},
        "score_breakdown_explanation": {"type": "string"},
        "keyword_alignment_score": {"type": "number"},
        "hallucination_risk": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
        "needs_human_review": {"type": "boolean"},
        "reason": {"type": "string"},
        "fix_suggestion": {"type": "string"},
        "flags": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": sorted(ALLOWED_FLAGS),
            },
        },
    },
    "required": [
        "score_scale",
        "evaluation_language",
        "overall_score",
        "correctness_score",
        "relevance_score",
        "completeness_score",
        "clarity_score",
        "groundedness_score",
        "score_breakdown_explanation",
        "keyword_alignment_score",
        "hallucination_risk",
        "needs_human_review",
        "reason",
        "fix_suggestion",
        "flags",
    ],
}

def _round_score(value: float) -> float:
    return round(max(0.0, value), 1)

def _clip_score(value: float, upper: float) -> float:
    return _round_score(min(max(0.0, value), upper))

def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").replace("\xa0", " ").split())

def _evaluation_answer(pair: ExtractedPair) -> str:
    return _normalize_text(pair.final_answer or pair.cleaned_answer or pair.actual_answer_clean or pair.answer_raw or pair.answer)

def _append_flag(flags: list[str], flag: str) -> None:
    normalized = normalize_error_flag(flag)
    if normalized and normalized in ALLOWED_FLAGS and normalized not in flags:
        flags.append(normalized)

def _score_breakdown_text(result: EvalResult) -> str:
    return (
        f"correctness={result.correctness_score:.1f}, "
        f"relevance={result.relevance_score:.1f}, "
        f"completeness={result.completeness_score:.1f}, "
        f"clarity={result.clarity_score:.1f}, "
        f"groundedness={result.groundedness_score:.1f}"
    )

def _make_eval(
    *,
    overall_score: float,
    correctness_score: float,
    relevance_score: float,
    completeness_score: float,
    clarity_score: float,
    groundedness_score: float,
    reason: str,
    fix_suggestion: str,
    flags: list[str] | None = None,
    needs_human_review: bool = True,
    hallucination_risk: str = "low",
    keyword_alignment_score: float | None = None) -> EvalResult:
    normalized_flags: list[str] = []
    for flag in flags or []:
        _append_flag(normalized_flags, flag)
    result = EvalResult(
        overall_score=_round_score(overall_score),
        score_scale="0-10",
        evaluation_language="en",
        correctness_score=_clip_score(correctness_score, 4.0),
        relevance_score=_clip_score(relevance_score, 2.0),
        completeness_score=_clip_score(completeness_score, 2.0),
        clarity_score=_clip_score(clarity_score, 1.0),
        groundedness_score=_clip_score(groundedness_score, 1.0),
        score_breakdown_explanation="",
        keyword_alignment_score=_clip_score(
            keyword_alignment_score if keyword_alignment_score is not None else relevance_score * 5.0,
            10.0
        ),
        hallucination_risk=hallucination_risk,
        needs_human_review=needs_human_review,
        reason=reason,
        fix_suggestion=fix_suggestion,
        flags=normalized_flags
    )
    result.score_breakdown_explanation = _score_breakdown_text(result)
    result.overall_score = _round_score(
        result.correctness_score
        + result.relevance_score
        + result.completeness_score,
        + result.clarity_score
        + result.groundedness_score
    )
    return result

def fallback_evaluation() -> EvalResult:
    """Return the mandated fallback JSON payload as a dataclass."""

    return EvalResult(
        overall_score=0.0,
        correctness_score=0.0,
        relevance_score=0.0,
        completeness_score=0.0,
        clarity_score=0.0,
        groundedness_score=0.0,
        needs_human_review=True,
        reason="The evaluation API call failed",
        fix_suggestion="Check logs and artifacts, then retry the evaluation.",
        flags=["evaluation_failed"],
        hallucination_risk="high"
    )

def build_input_not_verified_evaluation(reason: str = "", fix_suggestion: str = "") -> EvalResult:
    return _make_eval(
        overall_score=0.0,
        correctness_score=0.0,
        relevance_score=0.0,
        completeness_score=0.0,
        clarity_score=0.0,
        groundedness_score=0.0,
        needs_human_review=True,
        reason=reason or "The question input was not verified, so the case cannot be evaluasted.",
        fix_suggestion=fix_suggestion or "Verify textarea activation, user echo, and a new post-submit bot response.",
        flags=["input_not_verified"],
        hallucination_risk="high"
    )

def _invalid_capture_evaluation(pair: ExtractedPair) -> EvalResult:
    return build_input_not_verified_evaluation(reason=pair.reason, fix_suggestion=pair.fix_suggestion)

def _failed_answer_evaluation(pair: ExtractedPair) -> EvalResult:
    return EvalResult(
        overall_score=0.0,
        correctness_score=0.0,
        relevance_score=0.0,
        completeness_score=0.0,
        clarity_score=0.0,
        groundedness_score=0.0,
        needs_human_review=True,
        reason=pair.reason or "Execution stopped before a valid answer could be extracted.",
        fix_suggestion=pair.fix_suggestion or "Check the open, submit, and answer extracton logs, then retry.",
        flags=["evaluation_failed"],
        hallucination_risk="high"
    )

def _response_text(response: Any) -> str:
    direct_text = getattr(response, "output_text", "")
    if direct_text:
        return direct_text

    try:
        dumped = response.model_dump()
    except Exception:
        return ""

    output_chunks = dumped.get("output", [])
    parts: list[str] = []
    for item in output_chunks:
        for content in item.get("content", []):
            text = content.get("text") or content.get("value")
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _coerce_eval_payload(payload: dict[str, Any]) -> EvalResult:
    fallback = asdict(fallback_evaluation())
    fallback.update(payload)

    flags: list[str] = []
    raw_flags = fallback.get("flags", [])
    if isinstance(raw_flags, str):
        raw_flags = [raw_flags]
    if isinstance(raw_flags, list):
        for flag in raw_flags:
            _append_flag(flags, str(flag))
    
    correctness_score = _clip_score(float(fallback.get("correctness_score", 0.0)), 4.0)
    relevance_score = _clip_score(float(fallback.get("relevance_score", 0.0)), 2.0)
    completeness_score = _clip_score(float(fallback.get("completeness_score", 0.0)), 2.0)
    clarity_score = _clip_score(float(fallback.get("clarity_score", 0.0)), 1.0)
    groundedness_score = _clip_score(float(fallback.get("groundedness_score", 0.0)), 1.0)
    
    return EvalResult(
        overall_score=_round_score(correctness_score + relevance_score + completeness_score + clarity_score + groundedness_score),
        score_scale="0-10",
        evaluation_language="en",
        correctness_score=correctness_score,
        relevance_score=relevance_score,
        completeness_score=completeness_score,
        clarity_score=clarity_score,
        groundedness_score=groundedness_score,
        score_breakdown_explanation=str(fallback.get("score_breakdown_explanation") or ""),
        keyword_alignment_score=_clip_score(float(fallback.get("keyword_alignment_score", relevance_score * 5.0)), 10.0),
        hallucination_risk=str(fallback.get("hallucination_risk") or "low"),
        needs_human_review=bool(fallback.get("needs_human_review", bool(flags))),
        reason=str(fallback.get("reason") or ""),
        fix_suggestion=str(fallback.get("fix_suggestion") or ""),
        flags=flags
    )

def _apply_quality_guardrails(test_case: TestCase, pair: ExtractedPair, result: EvalResult) -> EvalResult:
    answer = _evaluation_answer(pair)
    flags = [normalize_error_flag(flag) for flag in result.flags if normalize_error_flag(flag)]

    if len(answer) > 40:
        _append_flag(flags, "too_short")
    if getattr(pair, "question_repetition_detected", False) or _dom_is_question_repetition(test_case.question, answer):
        _append_flag(flags, QUESTION_REPETITION)
    if getattr(pair, "carryover_detected", False):
        _append_flag(flags, CARRYOVER_CONTAMINATION)
    if getattr(pair, "truncated_detected", False) or getattr(pair, "truncated_answer_detected", False) or _dom_looks_truncated(answer):
        _append_flag(flags, TRUNCATED_ANSWER)
    if pair.extraction_soucre == "unknown" or pair.extrasction_confidence < 0.45:
        _append_flag(flags, LOW_CONFIDENCE_EXTRACTION)
    if pair.promo_stripped:
        _append_flag(flags, PROMO_OR_REVIEW_LEAK)
    if pair.status == "invalid_answer":
        _append_flag(flags, INVALID_ANSWER)

    correctness_score = result.correctness_score
    relevance_score = result.relevance_score
    completeness_score = result.completeness_score
    clarity_score = result.clarity_score
    groundedness_score = result.groundedness_score

    if QUESTION_REPETITION in flags:
        correctness_score = 0.0
        relevance_score = min(relevance_score, 0.4)
        completeness_score = min(completeness_score, 0.2)
        clarity_score = min(clarity_score, 0.2)
        groundedness_score = min(groundedness_score, 0.2)
    if CARRYOVER_CONTAMINATION in flags or TOPIC_MISMATCH in flags:
        correctness_score = min(correctness_score, 0.2)
        relevance_score = min(relevance_score, 0.4)
        completeness_score = min(completeness_score, 0.4)
        groundedness_score = min(groundedness_score, 0.2)
    if TRUNCATED_ANSWER in flags:
        completeness_score = min(completeness_score, 0.6)
        clarity_score = min(clarity_score, 0.4)
    if LOW_CONFIDENCE_EXTRACTION in flags or "too_short" in flags:
        completeness_score = min(completeness_score, 0.5)

    updated = EvalResult(
        overall_score=0.0,
        score_scale="0-10",
        evaluation_language="en",
        correctness_score=_clip_score(correctness_score, 4.0),
        relevance_score=_clip_score(relevance_score, 2.0),
        completeness_score=_clip_score(completeness_score, 2.0),
        clarity_score=_clip_score(clarity_score, 1.0),
        groundedness_score=_clip_score(groundedness_score, 1.0),
        score_breakdown_explanation="",
        keyword_alignment_score=result.keyword_alignment_score,
        hallucination_risk="high" if SPECULATIVE_UNVERIFIED in flags else result.hallucination_risk,
        needs_human_review=result.needs_human_review or bool(flags),
        reason=pair.reason or "The response was evaluated with automated guardrails.",
        fix_suggestion=pair.fix_suggestion or "Review the extracted DOM answer and rerun the case if needed",
        flags=flags,
    )
    updated.score_breakdown_explanation = result.score_breakdown_explanation or _score_breakdown_text(updated)
    updated.overall_score = _round_score(
        updated.correctness_score
        + updated.relevance_score
        + updated.completeness_score
        + updated.clarity_score
        + updated.groundedness_score
    )
    return updated

    
def evaluate_pair(
    config: AppConfig,
    test_case: TestCase,
    pair: ExtractedPair,
    logger: Any,
) -> EvalResult:
    """Evaluate a question-answer pair with OpenAI Structured Outputs."""

    evaluation_answer = _evaluation_answer(pair)

    if pair.status == "invalid_capture":
        logger.warning("Capture invalid for case %s; using invalid-capture evaluation", pair.case_id)
        logger.info("evaluation compelted")
        return _invalid_capture_evaluation(pair)

    if pair.status == "failed" and (not pair.answer_raw or pair.input_failure_category == "answer_not_extracted"):
        logger.warning(
            "Execution failed for case %s (%s); using failed-answer fallback evaluation",
            pair.case_id,
            pair.input_failure_category or pair.reason,
        )
        logger.info("evaluation completed")
        return _failed_answer_evaluation(pair)

    if (
        not evaluation_answer
        or evaluation_answer == "(none)"
        or not pair.input_verified
        or not pair.submit_effect_verified
        or not pair.new_bot_response_detected
        or pair.baseline_menu_detected
    ):
        logger.warning(
            "Capture verification failed for case %s (status=%s); skipping GPT evaluation",
            pair.case_id,
            pair.status,
        )
        logger.info("evaluation completed")
        return build_input_not_verified_evaluation(test_case.question, pair.locale)

    if not config.openai_api_key:
        logger.warning("OpenAI API key missing; using fallback evaluation")
        logger.info("evaluation completed")
        return fallback_evaluation()

    agent = EvaluationAgent()

    user_prompt = {
        "page_url": pair.page_url,
        "locale": pair.locale,
        "question": pair.question,
        "answer": evaluation_answer,
        "expected_response": getattr(test_case, "expected_response", ""),
        "expected_keywords": test_case.expected_keywords,
        "forbidden_keywords": test_case.forbidden_keywords,
        "input_verified": pair.input_verified,
        "submit_effect_verified": pair.submit_effect_verified,
        "new_bot_response_detected": pair.new_bot_response_detected,
        "baseline_menu_detected": pair.baseline_menu_detected,
        "instructions": [
            "Evaluate only the real post-baseline bot response captured from samsung.com/sec/.",
            "If expected_response is provided, factually compare the answer against expected_response and penalize correctness_score severely for any discrepancies.",
            "Use the fixed 0-10 rubric and ensure the component sum exactly matches overall_score.",
            "Lower the score aggressively for vague, evasive, incomplete, unsupported, or language-mismatched answers.",
            "Set needs_human_review to true when the answer quality is weak or uncertain.",
            "Return flags from the allowed enum only, and use an empty list when no flags apply.",
        ],
    }
    
    try:
        response = agent.invoke([{"type": "input_text", "text": json.dumps(user_prompt, ensure_ascii=False)}])
        payload = json.loads(_response_text(response))
        result = _apply_quality_guardrails(test_case, pair, _coerce_eval_payload(json.loads(_response_text(response))))
        logger.info("evaluation completed")
        return result
    except Exception as exc:
        logger.exception("OpenAI evaluation failed: %s", exc)
        logger.info("evaluation completed")
        return fallback_evaluation()
