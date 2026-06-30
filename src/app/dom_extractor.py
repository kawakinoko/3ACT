"""DOM-first, baseline-aware extraction helpers for Sprinklr chat responses."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.models import CandidateAnswer, ResolvedChatContext, TestCase
from utils.utils import build_locator, ensure_parent


MESSAGE_LIKE_SELECTORS = [
    "[data-message-author]",
    "[data-author]",
    "[role='log'] article",
    "[role='log'] li",
    "[role='list'] article",
    "[role='list'] li",
    "[aria-live] article",
    "[aria-live] li",
    "article[class*='message' i]",
    "div[class*='message' i]",
    "div[class*='chat' i]",
    "div[class*='bubble' i]",
    "div[class*='assistant' i]",
    "div[class*='agent' i]",
    "section[class*='message' i]",
]

USER_MESSAGE_SELECTORS = [
    ".user-message",
    "[data-message-author='user']",
    "[data-author='user']",
    "[data-author='customer']",
    "[class*='user' i][class*='message' i]",
    "[class*='customer' i][class*='message' i]",
    "[class*='outgoing' i]",
    "[class*='sent' i]",
]

MIN_CLEAN_ANSWER_LEN = 6
EXTRACTOR_VERSION = "dom-extractor-v3.0"


def normalize_text_for_diff(text: str) -> str:
    sanitized = re.sub(r"[\u200e\u200f\u202a-\u202e\ufeff]", "", str(text or ""))
    return " ".join(sanitized.replace("\xa0", " ").split())


def _normalize_text(text: str) -> str:
    return normalize_text_for_diff(text).lower()


def _is_question_repetition(question: str, answer: str) -> bool:
    nq = _normalize_text(question)
    na = _normalize_text(answer)
    if not nq or not na:
        return False
    if na == nq or na == f"{nq} , {nq}" or na == f"{nq}, {nq}":
        return True
    return nq in na and len(na) <= len(nq) * 1.4


def _detect_topic_family(text: str) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return "unknown"

    try:
        from scenario_tags import classify_scenario_text
        return str(classify_scenario_text("", normalized).get("product_family") or "unknown")
    except Exception:
        return "unknown"


def _looks_truncated(answer: str) -> bool:
    normalized = _normalize_text(answer)
    if not normalized:
        return False
    if normalized.endswith(":"):
        return True
    return bool(re.search(r"(?:sm-[a-z0-9]+|\d{2,3}(?:,\d{3})+원)$", normalized))


def _strip_ui_noise(text: str) -> tuple[str, bool]:
    return _normalize_multiline_text(text), False


def _strip_leading_ui_noise(text: str) -> str:
    return _normalize_multiline_text(text)


def _baseline_clean_answer(text: str) -> str:
    return _strip_leading_ui_noise(text)


def _is_stale_or_invalid_candidate(
    question: str,
    raw_answer: str,
    cleaned_answer: str,
    baseline_last_answer: str = "",
    baseline_topic_family: str = "unknown",
) -> bool:
    answer_text = cleaned_answer or raw_answer
    if not answer_text:
        return False

    normalized_answer = _normalize_text(answer_text)
    normalized_baseline = _normalize_text(_baseline_clean_answer(baseline_last_answer))
    if normalized_baseline and normalized_answer == normalized_baseline:
        return True

    question_family = _detect_topic_family(question)
    answer_family = _detect_topic_family(answer_text)
    baseline_family = baseline_topic_family if baseline_topic_family != "unknown" else _detect_topic_family(baseline_last_answer)
    topic_mismatch = (
        question_family != "unknown"
        and answer_family != "unknown"
        and question_family != answer_family
    )
    question_repetition = _is_question_repetition(question, raw_answer) or _is_question_repetition(question, cleaned_answer)
    baseline_family_match = (
        baseline_family != "unknown"
        and answer_family != "unknown"
        and baseline_family == answer_family
        and question_family != "unknown"
        and question_family != baseline_family
    )
    return baseline_family_match or (question_repetition and topic_mismatch)


def _extract_question_keywords(text: str) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []

    keywords: list[str] = []
    for token in re.findall(r"[a-z0-9가-힣+]{2,}", normalized):
        if token in keywords:
            continue
        keywords.append(token)
    return keywords


def _keyword_coverage(question: str, answer: str, expected_keywords: list[str]) -> float:
    normalized_answer = _normalize_text(answer)
    if not normalized_answer:
        return 0.0

    focus_keywords = [keyword.lower() for keyword in expected_keywords if keyword]
    focus_keywords.extend(_extract_question_keywords(question)[:6])

    deduped: list[str] = []
    for keyword in focus_keywords:
        if keyword and keyword not in deduped:
            deduped.append(keyword)

    if not deduped:
        return 0.0

    hits = sum(1 for keyword in deduped if keyword in normalized_answer)
    return hits / len(deduped)


def _clean_answer_candidate_details(
    text: str,
    question: str = "",
    baseline_last_answer: str = "",
    baseline_topic_family: str = "unknown",
) -> dict[str, Any]:
    raw_answer = _normalize_multiline_text(text)
    if not raw_answer:
        return {
            "raw_answer": "",
            "cleaned_answer": "",
            "question_repetition_detected": False,
            "truncated_detected": False,
            "ui_noise_stripped": False,
            "cta_stripped": False,
            "promo_stripped": False,
            "carryover_detected": False,
            "keyword_coverage_score": 0.0,
            "topic_family": "unknown",
            "topic_mismatch_detected": False,
        }

    cleaned, ui_noise_stripped = _strip_ui_noise(raw_answer)

    question_repetition_detected = _is_question_repetition(question, cleaned)
    cta_stripped = False
    promo_stripped = False
    if question_repetition_detected:
        cleaned = ""
    else:
        cleaned = " ".join(cleaned.split()).strip()

    truncated_detected = bool(cleaned) and _looks_truncated(cleaned)
    if truncated_detected:
        cleaned = ""
    elif cleaned and len(cleaned) < MIN_CLEAN_ANSWER_LEN:
        cleaned = ""

    topic_family = _detect_topic_family(cleaned or raw_answer)
    question_family = _detect_topic_family(question)
    topic_mismatch_detected = (
        question_family != "unknown"
        and topic_family != "unknown"
        and question_family != topic_family
    )
    keyword_coverage_score = _keyword_coverage(question, cleaned or raw_answer, [])
    carryover_detected = _is_stale_or_invalid_candidate(
        question,
        raw_answer,
        cleaned,
        baseline_last_answer=baseline_last_answer,
        baseline_topic_family=baseline_topic_family,
    )

    return {
        "raw_answer": raw_answer,
        "cleaned_answer": cleaned,
        "question_repetition_detected": question_repetition_detected,
        "truncated_detected": truncated_detected,
        "ui_noise_stripped": ui_noise_stripped,
        "cta_stripped": cta_stripped,
        "promo_stripped": promo_stripped,
        "carryover_detected": carryover_detected,
        "keyword_coverage_score": keyword_coverage_score,
        "topic_family": topic_family,
        "topic_mismatch_detected": topic_mismatch_detected,
    }


def _normalize_multiline_text(text: str) -> str:
    return "\n".join(line.strip() for line in str(text or "").splitlines() if line.strip())


def _strip_meta_text(text: str, question: str = "") -> str:
    return _clean_answer_candidate_details(text, question=question)["cleaned_answer"]


def is_static_ui_text(text: str) -> bool:
    normalized = normalize_text_for_diff(text)
    if not normalized:
        return True
    if len(normalized) <= 1:
        return True
    if re.fullmatch(r"[\W_]+", normalized):
        return True
    if re.fullmatch(r"[0-9]{1,2}:[0-9]{2}(?:\s?[AP]M)?", normalized, re.IGNORECASE):
        return True
    if re.fullmatch(r"[0-9]{4}[./-][0-9]{1,2}[./-][0-9]{1,2}", normalized):
        return True
    return False


def looks_like_chat_history_dump(text: str) -> bool:
    normalized = _normalize_multiline_text(text)
    if not normalized or len(normalized) < 120:
        return False

    lines = [line for line in normalized.splitlines() if line.strip()]
    question_like_count = normalized.count("?")
    if len(lines) >= 8 and question_like_count >=3:
        return True
    if len(normalized) >= 2000 and question_like_count >= 2:
        return True

    return False


def remove_static_ui_segments(segments: list[str]) -> list[str]:
    filtered: list[str] = []
    seen: set[str] = set()
    for segment in segments:
        normalized = _strip_meta_text(segment)
        if not normalized or is_static_ui_text(normalized):
            continue
        if looks_like_chat_history_dump(normalized):
            continue
        if len(normalized) < 6:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        filtered.append(_normalize_multiline_text(normalized))
    return filtered


def filter_out_static_ui_text(segments: list[str]) -> list[str]:
    return remove_static_ui_segments(segments)


def _ordered_unique_segments(segments: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for segment in segments:
        normalized = _strip_meta_text(segment)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(_normalize_multiline_text(normalized))
    return ordered


def _merge_answer_candidates(*candidate_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in candidate_groups:
        for segment in group:
            normalized = _strip_meta_text(segment)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(_normalize_multiline_text(normalized))
    return merged


def _compose_multiblock_answer_candidates(
    segments: list[str],
    question: str = "",
    baseline_last_answer: str = "",
    baseline_topic_family: str = "unknown",
) -> list[str]:
    fragments: list[str] = []
    seen: set[str] = set()
    for segment in segments:
        details = _clean_answer_candidate_details(
            segment,
            question=question,
            baseline_last_answer=baseline_last_answer,
            baseline_topic_family=baseline_topic_family,
        )
        cleaned = details.get("cleaned_answer", "")
        if not cleaned:
            continue
        if details.get("question_repetition_detected") or details.get("topic_mismatch_detected"):
            continue
        if details.get("carryover_detected") or details.get("truncated_detected"):
            continue
        if cleaned.endswith("?"):
            continue
        normalized = _normalize_text(cleaned)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        fragments.append(cleaned)

    if len(fragments) > 2:
        return []

    joined = _normalize_multiline_text(" ".join(fragments[:12]))
    joined_details = _clean_answer_candidate_details(
        joined,
        question=question,
        baseline_last_answer=baseline_last_answer,
        baseline_topic_family=baseline_topic_family
    )
    cleaned_joined = joined_details.get("cleaned_answer", "")
    if not cleaned_joined:
        return []
    if joined_details.get("question_repetition_detected") or joined_details.get("topic_mismatch_detected"):
        return []
    if joined_details.get("carryover_detected") or joined_details.get("truncated_detected"):
        return []
    if question and _keyword_coverage(question, cleaned_joined, []) <= 0:
        return []
    if len(cleaned_joined) >= max(len(fragment) for fragment in fragments) + 8:
        return []
    return [cleaned_joined]


def _remove_question_echo_segments(segments: list[str], question: str = "") -> list[str]:
    if not _strip_meta_text(question):
        return segments

    filtered: list[str] = []
    for segment in segments:
        normalized = _strip_meta_text(segment)
        if not normalized:
            continue
        if _is_question_repetition(question, normalized):
            continue
        filtered.append(segment)
    return filtered


def _candidate_snapshot_script() -> str:
    return r"""
(node) => {
  const normalize = (value) => (value || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const depthFrom = (root, el) => {
    let depth = 0;
    let cursor = el;
    while (cursor && cursor !== root) {
      depth += 1;
      cursor = cursor.parentElement;
    }
    return depth;
  };
  const directText = (el) => Array.from(el.childNodes || [])
    .filter((child) => child.nodeType === Node.TEXT_NODE)
    .map((child) => normalize(child.textContent || ''))
    .filter(Boolean)
    .join(' ');
  const ancestorMeta = (root, el) => {
    const parts = [];
    let cursor = el;
    while (cursor && cursor !== root.parentElement) {
      parts.push(
        typeof cursor.className == 'string' ? cursor.className : '',
        cursor.getAttribute('role') || '',
        cursor.getAttribute('data-testid) || '',
        cursor.getAttribute('aria-label') || '',
        cursor.getAttribute('data-message-author') || cursor.getAttribute('data-author') || ''
      );
      if (cursor === root) break;
      cursor = cursor.parentElement;
    }
    return parts.filter(Boolean).join(' ');
  };
  const rawDescendants = [node, ...node.querySelectorAll('*')]
    .filter((el) => visible(el))
    .map((el, index) => {
      const text = normalize(el.innerText || el.textContent || '');
      if (!text) return null;
      return {
        element: el,
        index,
        text,
        depth: depthFrom(node, el),
        tag: (el.tagName || '').toLowerCase(),
        className: typeof el.className === 'string' ? el.className : '',
        role: el.getAttribute('role') || '',
        testId: el.getAttribute('data-testid') || '',
        ariaLabel: el.getAttribute('aria-label') || '',
        author: el.getAttribute('data-message-author') || el.getAttribute('data-author') || '',
        directText: directText(el),
        ancestorMeta: ancestorMeta(node, el)
      };
    })
    .filter(Boolean);
  const descendants = rawDescendants.map((item) => {
    const textDescendants = rawDescendants.filter((other) =>
      other.index !== item.index && item.element.contains(other.element)
    );
    return {
      text: item.text,
      directText: item.directText,
      depth: item.depth,
      tag: item.tag,
      className: item.className,
      role: item.role,
      testId: item.testId,
      ariaLabel: item.ariaLabel,
      author: item.author,
      ancestorMeta: item.ancestorMeta,
      hasTextDescendant: textDescendants.length > 0,
      textDescendantCount: textDescendants.length,
      isLeafText: textDescendants.length === 0,
    };
  });
  return {
    wrapperText: normalize(node.innerText || node.textContent || ''),
    descendants,
    className: typeof node.className === 'string' ? node.className : '',
    role: node.getAttribute('role') || '',
    tag: (node.tagName || '').toLowerCase(),
    testId: node.getAttribute('data-testid') || '',
    ariaLabel: node.getAttribute('aria-label') || '',
  };
}
"""


def _dom_role_score(descendant: dict[str, Any]) -> int:
    metadata = " ".join(
        str(descendant.get(key, "") or "")
        for key in ("className", "role", "testId", "ariaLabel", "author", "ancestorMeta")
    ).lower()
    if re.search(r"\b(user|customer|outgoing|sent)\b", metadata):
        return -120
    if re.search(r"\b(bot|agent|assistant|incoming|answer)\b", metadata):
        return 80
    return 0


def _descendant_text_candidates(node: dict[str, Any]) -> list[dict[str, Any]]:
    descendants = node.get("descendants", []) if isinstance(node, dict) else []
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for dom_index, descendant in enumerate(descendants):
        text = normalize_text_for_diff(descendant.get("text", ""))
        if not text or text in seen:
            continue
        seen.add(text)
        candidates.append({**descendant, "text": text, "domIndex": dom_index})

    leaf_candidates = [candidate for candidate in candidates if candidate.get("isLeafText")]
    terminal_candidates = leaf_candidates or [
        candidate for candidate in candidates if not candidate.get("hasTextDescendant")
    ]
    selected = terminal_candidates or candidates
    return sorted(
        selected,
        key=lambda candidate: (
            1 if candidate.get("isLeafText") else 0,
            _dom_role_score(candidate),
            int(candidate.get("depth") or 0),
            min(len(str(candidate.get("text") or "")), 600)
        ),
        reverse=True
    )


def _compose_node_text_candidate(node: dict[str, Any]) -> dict[str, Any] | None:
    descendants = node.get("descendants", []) if isinstance(node, dict) else []
    leaf_fragments: list[str] =[]
    seen: set[str] = set()

    for descendant in descendants:
        if not descendant.get("isLeafText"):
            continue
        if _dom_role_score(descendant) < 0:
            continue
        text = normalize_text_for_diff(descendant.get("text", ""))
        if not text or is_static_ui_text(text):
            continue
        normalized = _normalize_text(text)
        if normalized in seen:
            continue
        seen.add(normalized)
        leaf_fragments.append(text)
    
    if len(leaf_fragments) < 2:
        return None

    composed = _normalize_multiline_text("\n".join(leaf_fragments))
    if not composed or looks_like_chat_history_dump(composed):
        return None

    longest_leaf = max(len(fragment) for fragment in leaf_fragments)
    if len(normalize_text_for_diff(composed)) >= longest_leaf + 8:
        return None

    return {
        "text": composed,
        "depth": 0,
        "isLeafText": False,
        "hasTextDescendant": False,
        "isCompositeText": True,
        "fragmentCount": len(leaf_fragments)
    }


def _wrapper_text_candidate(node: dict[str, Any], options: list[dict[str, Any]]) -> dict[str, Any] | None:
    wrapper_text = normalize_text_for_diff(node.get("wrapperText", "")) if isinstance(node, dict) else ""
    if not wrapper_text or looks_like_chat_history_dump(wrapper_text):
        return None
    
    longest_option = 0
    for option in options:
        longest_option = max(longest_option, len(normalize_text_for_diff(str(option.get("text") or ""))))

    if longest_option and len(wrapper_text) <= longest_option + 8:
        return None
    
    return {
        "text": wrapper_text,
        "depth": 0,
        "isLeafText": False,
        "hasTextDescendasnt": True,
        "isWRapperText": True
    }


def find_text_containing_descendants(node: dict[str, Any]) -> list[str]:
    return [candidate["text"] for candidate in _descendant_text_candidates(node)]


def extract_clean_text_from_message_node(node: dict[str, Any]) -> str:
    options = _descendant_text_candidates(node)
    if isinstance(node, dict):
        composite_candidate = _compose_node_text_candidate(node)
        if composite_candidate is not None:
            options.insert(0, composite_candidate)
        wrapper_candidate = _wrapper_text_candidate(node, options)
        if wrapper_candidate is not None:
            options.append(wrapper_candidate)
        if not options:
            wrapper_text = normalize_text_for_diff(node.get("wrapperText", ""))
            if wrapper_text and not looks_like_chat_history_dump(wrapper_text):
                options.append({
                    "text": wrapper_text,
                    "depth": 0,
                    "isLeafText": False,
                    "hasTextDescendant": True,
                    "isWrapperText": True
                })

    best_text = ""
    best_score = -10**9
    for option in options:
        option_text = str(option.get("text", "")if isinstance(option, dict) else option)
        normalized = _strip_meta_text(option_text)
        if not normalized or is_static_ui_text(normalized):
            continue
        score = min(len(normalized), 600)
        if isinstance(option, dict):
            score += int(option.get("depth") or 0) * 8
            score += _dom_role_score(option)
            if option.get("isLeafText"):
                score += 120
            if option.get("isCompositeText"):
                score += 220 + min(int(option.get("fragmentCount") or 0), 8) * 10
            if option.get("isWrapperText"):
                score += 20
            if option.get("hasTextDescendant"):
                score -= 160
        if "\n" in option_text:
            score += 12
        if len(normalized.split()) >= 5:
            score += 8
        if len(normalized) <= 8:
            score -= 12
        if best_text and normalized in normalize_text_for_diff(best_text):
            continue
        if score >= best_score:
            best_score = score
            best_text = _normalize_multiline_text(normalized)
    return best_text


def _collect_candidate_snapshots(locator: Any) -> list[dict[str, Any]]:
    try:
        return locator.evaluate_all(
            f"""
(nodes) => {{
  const collect = {_candidate_snapshot_script().strip()};
  return nodes.map((node) => collect(node));
}}
"""
        )
    except Exception:
        return []


def _collect_candidates_from_specs(chat_context: ResolvedChatContext, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for spec in specs:
        try:
            locator = build_locator(chat_context.scope, spec)
        except Exception:
            continue
        collected.extend(_collect_candidate_snapshots(locator))
    return collected


def find_message_candidate_nodes(chat_context: ResolvedChatContext) -> list[dict[str, Any]]:
    candidates = _collect_candidates_from_specs(chat_context, chat_context.bot_message_candidates)
    candidates.extend(_collect_candidates_from_specs(chat_context, chat_context.history_candidates))
    for selector in MESSAGE_LIKE_SELECTORS:
        try:
            locator = chat_context.scope.locator(selector)
        except Exception:
            continue
        candidates.extend(_collect_candidate_snapshots(locator))
    return candidates


def _visible_block_script() -> str:
    return r"""
(root) => {
  const normalize = (value) => (value || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const selectors = ['article', 'li', 'p', 'div', 'section', 'span'];
  const nodes = [root, ...root.querySelectorAll(selectors.join(','))];
  const seen = new Set();
  const blocks = [];
  for (const node of nodes) {
    if (!visible(node)) continue;
    const text = normalize(node.innerText || node.textContent || '');
    if (!text || seen.has(text)) continue;
    seen.add(text);
    blocks.push(text);
  }
  return blocks;
}
"""


def extract_visible_text_blocks(chat_context: ResolvedChatContext) -> list[str]:
    try:
        if chat_context.container_locator is not None:
            blocks = chat_context.container_locator.evaluate(_visible_block_script())
            return filter_out_static_ui_text([_normalize_multiline_text(block) for block in blocks])
    except Exception:
        pass

    return extract_message_like_blocks(chat_context)


def extract_message_like_blocks(chat_context: ResolvedChatContext) -> list[str]:
    blocks: list[str] = []
    seen: set[str] = set()
    for node in find_message_candidate_nodes(chat_context):
        text = extract_clean_text_from_message_node(node)
        normalized = normalize_text_for_diff(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        blocks.append(text)
    return blocks


def compute_new_text_segments(before: str | list[str], after: str | list[str]) -> list[str]:
    before_segments = before if isinstance(before, list) else str(before or "").splitlines()
    after_segments = after if isinstance(after, list) else str(after or "").splitlines()
    before_set = {normalize_text_for_diff(item) for item in before_segments if normalize_text_for_diff(item)}
    result: list[str] = []
    seen: set[str] = set()
    for segment in after_segments:
        normalized = normalize_text_for_diff(segment)
        if not normalized or normalized in before_set or normalized in seen:
            continue
        seen.add(normalized)
        result.append(_normalize_multiline_text(segment))
    return result


def choose_best_answer_segment(
    segments: list[str],
    question: str = "",
    baseline_last_answer: str = "",
    baseline_topic_family: str = "unknown",
) -> str:
    return choose_best_answer_candidate(
        segments,
        question=question,
        baseline_last_answer=baseline_last_answer,
        baseline_topic_family=baseline_topic_family,
    )["cleaned_answer"]


def choose_best_answer_candidate(
    segments: list[str],
    question: str = "",
    baseline_last_answer: str = "",
    baseline_topic_family: str = "unknown",
) -> dict[str, Any]:
    filtered = filter_out_static_ui_text(segments)
    if not filtered:
        return _clean_answer_candidate_details(
            "",
            question=question,
            baseline_last_answer=baseline_last_answer,
            baseline_topic_family=baseline_topic_family,
        )
    best_candidate = _clean_answer_candidate_details(
        "",
        question=question,
        baseline_last_answer=baseline_last_answer,
        baseline_topic_family=baseline_topic_family,
    )
    best_score = -10**9
    for index, segment in enumerate(filtered):
        details = _clean_answer_candidate_details(
            segment,
            question=question,
            baseline_last_answer=baseline_last_answer,
            baseline_topic_family=baseline_topic_family,
        )
        normalized = details["cleaned_answer"]
        raw_answer = details["raw_answer"]
        if not raw_answer:
            continue
        if looks_like_chat_history_dump(raw_answer) or looks_like_chat_history_dump(normalized):
            continue
        if details["carryover_detected"]:
            continue
        if details["question_repetition_detected"] or details["topic_mismatch_detected"] or not normalized:
            continue
        if details["truncated_detected"]:
            continue
        sentence_end_marker = (". ", "! ", "? ")
        sentence_like_count = sum(normalized.count(marker) for marker in sentence_end_marker)
        score = len(normalized) + (index * 2)
        question_norm = _normalize_text(question)
        normalized_for_question = _normalize_text(normalized)
        if question_norm and question_norm in normalized_for_question:
            score -= 80
            if normalized_for_question.startswith(question_norm):
                score -= 120
        if len(normalized.split()) >= 5:
            score += 8
        if "\n" in segment:
            score += 10
        if len(normalized) >= 40:
            score += 10
        if sentence_like_count >= 1:
            score += 10
        if normalized.endswith(sentence_end_marker):
            score += 4
        score += int(details["keyword_coverage_score"] * 40)
        if normalized.endswith("?"):
            score -= 30
        if len(normalized) <= 40 and normalized.endswith("?"):
            score -= 20
        if details["ui_noise_stripped"] and len(normalized) < MIN_CLEAN_ANSWER_LEN * 3:
            score -= 20
        if score >= best_score:
            best_score = score
            best_candidate = details
    return best_candidate


def collect_bot_candidates(
    chat_context: ResolvedChatContext,
    question: str = "",
    scenario_meta: TestCase | None = None,
) -> list[CandidateAnswer]:
    structured_history = extract_structured_message_history(chat_context)
    bot_texts = extract_bot_message_texts(chat_context)
    current_bot_count = len(bot_texts)
    bot_count_increased = current_bot_count > chat_context.baseline_bot_count
    new_bot_by_count = bot_texts[chat_context.baseline_bot_count:current_bot_count] if bot_count_increased else []
    new_bot_segments = compute_new_text_segments(chat_context.baseline_bot_messages, bot_texts)
    new_history_segments = compute_new_text_segments(
        chat_context.baseline_message_nodes_snapshot,
        structured_history.get("history", []),
    )
    baseline_last_answer = getattr(chat_context, "baseline_last_answer", "")
    baseline_topic_family = getattr(chat_context, "baseline_topic_family", "unknown")
    merged_segments = _merge_answer_candidates(
        _ordered_unique_segments(_remove_question_echo_segments(filter_out_static_ui_text(new_bot_by_count + new_bot_segments), question)),
        _ordered_unique_segments(_remove_question_echo_segments(filter_out_static_ui_text(new_history_segments), question)),
    )
    merged_segments = _merge_answer_candidates(
        merged_segments,
        _compose_multiblock_answer_candidates(
            merged_segments,
            question=question,
            baseline_last_answer=baseline_last_answer,
            baseline_topic_family=baseline_topic_family
        )
    )

    expected_keywords = list(getattr(scenario_meta, "expected_keywords", []) or [])
    question_family = _detect_topic_family(question)
    candidates: list[CandidateAnswer] = []
    for index, segment in enumerate(merged_segments, start=1):
        details = _clean_answer_candidate_details(
            segment,
            question=question,
            baseline_last_answer=baseline_last_answer,
            baseline_topic_family=baseline_topic_family,
        )
        cleaned = details.get("cleaned_answer", "")
        raw = details.get("raw_answer", "")
        text_for_scoring = cleaned or raw
        keyword_coverage = _keyword_coverage(question, text_for_scoring, expected_keywords)
        topic_family = details.get("topic_family", "unknown")
        topic_family_match = question_family == "unknown" or topic_family == "unknown" or question_family == topic_family
        length_score = min(len(cleaned or raw), 240) / 24.0
        completeness_score = 1.0 if cleaned and not details.get("truncated_detected", False) else 0.0
        score = length_score
        score += keyword_coverage * 10.0
        score += 1.5 if topic_family_match else -3.0
        score += completeness_score * 2.0
        if details.get("question_repetition_detected", False):
            score -= 12.0
        if details.get("carryover_detected", False):
            score -= 10.0
        if details.get("truncated_detected", False):
            score -= 8.0
        if details.get("ui_noise_stripped", False):
            score -= 1.5
        if details.get("cta_stripped", False):
            score -= 1.0
        if details.get("promo_stripped", False):
            score -= 1.0
        candidates.append(
            CandidateAnswer(
                raw_text=raw,
                cleaned_text=cleaned,
                source="dom",
                score=score,
                rank=index,
                keyword_coverage=keyword_coverage,
                is_question_repetition=bool(details.get("question_repetition_detected", False)),
                has_ui_noise=bool(details.get("ui_noise_stripped", False)),
                has_followup_cta=bool(details.get("cta_stripped", False)),
                has_promo_or_review=bool(details.get("promo_stripped", False)),
                is_truncated=bool(details.get("truncated_detected", False)),
                topic_family_match=topic_family_match,
                is_stale_vs_baseline=bool(details.get("carryover_detected", False)),
                length_score=length_score,
                completeness_score=completeness_score,
            )
        )
    candidates.sort(key=lambda item: item.score, reverse=True)
    for rank, candidate in enumerate(candidates, start=1):
        candidate.rank = rank
    return candidates


def rank_candidates(
    candidates: list[CandidateAnswer],
) -> CandidateAnswer | None:
    for candidate in candidates:
        if (
            candidate.cleaned_text
            and not candidate.is_question_repetition
            and not candidate.is_stale_vs_baseline
            and not candidate.is_truncated
            and not candidate.cleaned_text.endswith("?")
        ):
            return candidate
    return None


def _flatten_scope_text(scope_result: Any) -> str:
    return _normalize_multiline_text(str(scope_result or ""))


def extract_visible_chat_text(chat_context: ResolvedChatContext) -> str:
    text = ""
    try:
        if chat_context.container_locator is not None:
            text = chat_context.container_locator.inner_text(timeout=1500)
    except Exception:
        text = ""

    if text:
        return _flatten_scope_text(text)

    return "\n".join(extract_message_like_blocks(chat_context))


def diff_visible_text_against_baseline(chat_context: ResolvedChatContext) -> list[str]:
    current_blocks = extract_visible_text_blocks(chat_context)
    return compute_new_text_segments(chat_context.baseline_visible_blocks, current_blocks)


def build_post_baseline_answer_candidates(
    chat_context: ResolvedChatContext,
    question: str = "",
    scenario_meta: TestCase | None = None,
) -> dict[str, Any]:
    structured_history = extract_structured_message_history(chat_context)
    bot_texts = extract_bot_message_texts(chat_context)
    current_bot_count = len(bot_texts)
    bot_count_increased = current_bot_count > chat_context.baseline_bot_count
    new_bot_by_count = bot_texts[chat_context.baseline_bot_count:current_bot_count] if bot_count_increased else []
    new_bot_segments = compute_new_text_segments(chat_context.baseline_bot_messages, bot_texts)
    new_history_segments = compute_new_text_segments(
        chat_context.baseline_message_nodes_snapshot,
        structured_history.get("history", []),
    )
    diff_segments = diff_visible_text_against_baseline(chat_context)
    baseline_last_answer = getattr(chat_context, "baseline_last_answer", "")
    baseline_topic_family = getattr(chat_context, "baseline_topic_family", "unknown")
    strict_candidates = _ordered_unique_segments(
        _remove_question_echo_segments(
            filter_out_static_ui_text(new_bot_by_count + new_bot_segments),
            question,
        )
    )
    fallback_candidates = _ordered_unique_segments(
        _remove_question_echo_segments(
            filter_out_static_ui_text(new_history_segments + diff_segments),
            question,
        )
    )
    strict_candidates = _merge_answer_candidates(
        strict_candidates,
        _compose_multiblock_answer_candidates(
            strict_candidates,
            question=question,
            baseline_last_answer=baseline_last_answer,
            baseline_topic_family=baseline_topic_family
        )
    )
    fallback_candidates = _merge_answer_candidates(
        fallback_candidates,
        _compose_multiblock_answer_candidates(
            fallback_candidates,
            question=question,
            baseline_last_answer=baseline_last_answer,
            baseline_topic_family=baseline_topic_family
        )
    )
    all_candidates = _merge_answer_candidates(strict_candidates, fallback_candidates)
    raw_candidate_details = [
        _clean_answer_candidate_details(
            segment,
            question=question,
            baseline_last_answer=getattr(chat_context, "baseline_last_answer", ""),
            baseline_topic_family=getattr(chat_context, "baseline_topic_family", "unknown"),
        )
        for segment in new_bot_by_count + new_bot_segments + new_history_segments
    ]
    candidates = [
        candidate
        for candidate in collect_bot_candidates(chat_context, question=question, scenario_meta=scenario_meta)
        if (candidate.cleaned_text or candidate.raw_text) in all_candidates
    ]
    cleaned_candidates = [
        {
            "question_repetition_detected": details.get("question_repetition_detected", False),
            "truncated_detected": details.get("truncated_detected", False),
            "carryover_detected": details.get("carryover_detected", False),
            "ui_noise_stripped": details.get("ui_noise_stripped", False),
            "cta_stripped": details.get("cta_stripped", False),
            "promo_stripped": details.get("promo_stripped", False),
            "keyword_coverage_score": details.get("keyword_coverage_score", 0.0),
        }
        for details in raw_candidate_details
    ]
    any_question_repetition_detected = any(item["question_repetition_detected"] for item in cleaned_candidates)
    any_truncated_detected = any(item["truncated_detected"] for item in cleaned_candidates)
    any_carryover_detected = any(item["carryover_detected"] for item in cleaned_candidates)

    selected_candidate = _clean_answer_candidate_details("", question=question)
    selected_source = "unknown"
    selected_confidence = 0.0
    selected_rank = 0
    if candidates:
        ranked_candidate = rank_candidates(candidates)
        if ranked_candidate is not None:
            selected_rank = ranked_candidate.rank
            selected_candidate = _clean_answer_candidate_details(
                ranked_candidate.raw_text,
                question=question,
                baseline_last_answer=baseline_last_answer,
                baseline_topic_family=baseline_topic_family,
            )
    
    best_segment_candidate = choose_best_answer_candidate(
        all_candidates,
        question=question,
        baseline_last_answer=baseline_last_answer,
        baseline_topic_family=baseline_topic_family
    )
    if best_segment_candidate.get("cleaned_answer"):
        selected_clean = str(selected_candidate.get("cleaned_answer") or "")
        segment_clean = str(best_segment_candidate.get("cleaned_answer") or "")
        if not selected_clean or len(segment_clean) > len(selected_clean) + 8:
            selected_candidate = best_segment_candidate
            if selected_rank == 0:
                selected_rank = 1

    normalized_selected = _normalize_text(selected_candidate.get("cleaned_answer", "") or selected_candidate.get("raw_answer", ""))
    strict_normalized = {
        _normalize_text(candidate)
        for candidate in strict_candidates
        if _normalize_text(candidate)
    }
    fallback_normalized = {
        _normalize_text(candidate)
        for candidate in fallback_candidates
        if _normalize_text(candidate)
    }
    if normalized_selected and normalized_selected in strict_normalized:
        selected_source = "dom"
        selected_confidence = 1.0
    elif normalized_selected and normalized_selected in fallback_normalized:
        selected_source = "dom"
        selected_confidence = 0.72

    selected_question_repetition_detected = bool(selected_candidate.get("question_repetition_detected", False))
    selected_truncated_detected = bool(selected_candidate.get("truncated_detected", False))
    selected_carryover_detected = bool(selected_candidate.get("carryover_detected", False))
    if selected_candidate.get("cleaned_answer") or selected_candidate.get("raw_answer"):
        question_repetition_detected = selected_question_repetition_detected
        truncated_detected = selected_truncated_detected
        carryover_detected = selected_carryover_detected
    else:
        question_repetition_detected = any_question_repetition_detected
        truncated_detected = any_truncated_detected
        carryover_detected = any_carryover_detected

    return {
        "answer": selected_candidate["cleaned_answer"],
        "raw_answer": selected_candidate["raw_answer"],
        "cleaned_answer": selected_candidate["cleaned_answer"],
        "success": bool(selected_candidate["cleaned_answer"]),
        "extraction_source": selected_source,
        "extraction_confidence": selected_confidence,
        "question_repetition_detected": question_repetition_detected,
        "truncated_detected": truncated_detected,
        "ui_noise_stripped": any(item["ui_noise_stripped"] for item in cleaned_candidates) or bool(selected_candidate.get("ui_noise_stripped", False)),
        "cta_stripped": selected_candidate["cta_stripped"],
        "promo_stripped": selected_candidate["promo_stripped"],
        "carryover_detected": carryover_detected,
        "keyword_coverage_score": float(selected_candidate.get("keyword_coverage_score", 0.0) or 0.0),
        "history": structured_history.get("history", []),
        "structured_message_history_count": structured_history.get("count", 0),
        "fallback_diff_used": structured_history.get("fallback_diff_used", False) or bool(diff_segments),
        "visible_chat_text": extract_visible_chat_text(chat_context),
        "visible_text_blocks": extract_visible_text_blocks(chat_context),
        "bot_texts": bot_texts,
        "current_bot_count": current_bot_count,
        "bot_count_increased": bot_count_increased,
        "new_bot_segments": new_bot_segments,
        "new_history_segments": new_history_segments,
        "diff_segments": diff_segments,
        "strict_candidates": strict_candidates,
        "fallback_candidates": fallback_candidates,
        "all_candidates": all_candidates,
        "candidate_count": len(candidates),
        "selected_candidate_rank": selected_rank,
        "stale_answer_detected": carryover_detected,
    }


def extract_bot_message_texts(chat_context: ResolvedChatContext) -> list[str]:
    messages: list[str] = []
    seen: set[str] = set()
    for node in _collect_candidates_from_specs(chat_context, chat_context.bot_message_candidates):
        text = extract_clean_text_from_message_node(node)
        normalized = normalize_text_for_diff(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        messages.append(text)
    return messages


def extract_structured_message_history(chat_context: ResolvedChatContext) -> dict[str, Any]:
    messages: list[str] = []
    seen: set[str] = set()
    fallback_diff_used = False

    for spec_group in [chat_context.bot_message_candidates, chat_context.history_candidates]:
        for node in _collect_candidates_from_specs(chat_context, spec_group):
            text = extract_clean_text_from_message_node(node)
            normalized = normalize_text_for_diff(text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            messages.append(text)

    for selector in USER_MESSAGE_SELECTORS + MESSAGE_LIKE_SELECTORS:
        try:
            locator = chat_context.scope.locator(selector)
        except Exception:
            continue
        for node in _collect_candidate_snapshots(locator):
            text = extract_clean_text_from_message_node(node)
            normalized = normalize_text_for_diff(text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            messages.append(text)

    messages = filter_out_static_ui_text(messages)
    if messages:
        return {"history": messages, "count": len(messages), "fallback_diff_used": fallback_diff_used}

    blocks = extract_message_like_blocks(chat_context)
    if blocks:
        fallback_diff_used = True
        return {"history": blocks, "count": len(blocks), "fallback_diff_used": fallback_diff_used}

    return {"history": [], "count": 0, "fallback_diff_used": fallback_diff_used}


def extract_message_history_candidates(chat_context: ResolvedChatContext) -> list[str]:
    return extract_structured_message_history(chat_context).get("history", [])


def count_bot_messages(chat_context: ResolvedChatContext) -> int:
    return len(extract_bot_message_texts(chat_context))


def extract_last_bot_message_text(chat_context: ResolvedChatContext) -> str:
    bot_messages = extract_bot_message_texts(chat_context)
    return bot_messages[-1] if bot_messages else ""


def extract_message_history(chat_context: ResolvedChatContext) -> list[str]:
    return extract_structured_message_history(chat_context).get("history", [])


def save_html_fragment(chat_context: ResolvedChatContext, output_path: Path | None) -> str:
    if output_path is None:
        return ""

    html = ""
    try:
        if chat_context.container_locator is not None:
            html = chat_context.container_locator.evaluate("node => node.outerHTML")
        else:
            html = chat_context.input_locator.evaluate(
                "node => node.closest('form,section,article,aside,div')?.outerHTML || node.outerHTML"
            )
    except Exception:
        html = ""

    if not html:
        return ""

    ensure_parent(output_path)
    output_path.write_text(html, encoding="utf-8")
    return str(output_path)


def extract_dom_payload(
    chat_context: ResolvedChatContext,
    fragment_path: Path | None,
    question: str = "",
    scenario_meta: TestCase | None = None,
) -> dict[str, Any]:
    candidate_data = build_post_baseline_answer_candidates(chat_context, question=question, scenario_meta=scenario_meta)
    html_fragment_path = save_html_fragment(chat_context, fragment_path)
    return {
        "success": bool(candidate_data["cleaned_answer"]),
        "answer": candidate_data["cleaned_answer"],
        "raw_answer": candidate_data["raw_answer"],
        "cleaned_answer": candidate_data["cleaned_answer"],
        "extraction_source": candidate_data.get("extraction_source", "unknown"),
        "extraction_confidence": float(candidate_data.get("extraction_confidence", 0.0) or 0.0),
        "question_repetition_detected": candidate_data["question_repetition_detected"],
        "truncated_detected": candidate_data["truncated_detected"],
        "ui_noise_stripped": bool(candidate_data.get("ui_noise_stripped", False)),
        "cta_stripped": candidate_data["cta_stripped"],
        "promo_stripped": candidate_data["promo_stripped"],
        "carryover_detected": bool(candidate_data.get("carryover_detected", False)),
        "stale_answer_detected": bool(candidate_data.get("stale_answer_detected", False)),
        "candidate_count": int(candidate_data.get("candidate_count", 0) or 0),
        "selected_candidate_rank": int(candidate_data.get("selected_candidate_rank", 0) or 0),
        "keyword_coverage_score": float(candidate_data.get("keyword_coverage_score", 0.0) or 0.0),
        "history": candidate_data["history"],
        "structured_message_history_count": candidate_data["structured_message_history_count"],
        "fallback_diff_used": candidate_data["fallback_diff_used"],
        "visible_chat_text": candidate_data["visible_chat_text"],
        "visible_text_blocks": candidate_data["visible_text_blocks"],
        "new_bot_segments": candidate_data["new_bot_segments"],
        "new_history_segments": candidate_data["new_history_segments"],
        "diff_segments": candidate_data["diff_segments"],
        "current_bot_count": candidate_data["current_bot_count"],
        "bot_count_increased": candidate_data["bot_count_increased"],
        "strict_candidates": candidate_data["strict_candidates"],
        "fallback_candidates": candidate_data["fallback_candidates"],
        "all_candidates": candidate_data["all_candidates"],
        "html_fragment_path": html_fragment_path,
    }
