from __future__ import annotations

import json
import re
from statistics import fmean
from typing import TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from agent.logging import EVENT_NODE_ENTER, EVENT_NODE_EXIT, write_event
from agent.state import AgentState, CitationVerdict
from tools import make_chat
from tools.searcher import domain_of

_FORCE_WEAK_RE = re.compile(r"FORCE_WEAK", re.IGNORECASE)
_FORCE_RETRY_RE = re.compile(r"FORCE_RETRY", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"[.;\n]+")
_TOKEN_RE = re.compile(r"\b[a-z0-9]{2,}\b")
_STATUS_RE = re.compile(r"^\s*(Yes|Partial|No)\b[:\-]?\s*(.*)$", re.IGNORECASE | re.DOTALL)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
}


class CitationVerifierOutput(TypedDict):
    citation_verdict: CitationVerdict
    confidence: float
    _verifier_claims: list[str] | None
    _verifier_claim_citations: list[list[int]] | None
    _verifier_scores: list[float] | None
    _verifier_notes: list[str] | None


def _log_enter(state: AgentState, node_name: str, *, state_diff: dict[str, object] | None = None) -> None:
    write_event(
        state["thread_id"],
        state["attempt"],
        node_name,
        EVENT_NODE_ENTER,
        state["mode"],
        state_diff=state_diff or {},
    )



def _log_exit(state: AgentState, node_name: str, *, state_diff: dict[str, object] | None = None) -> None:
    write_event(
        state["thread_id"],
        state["attempt"],
        node_name,
        EVENT_NODE_EXIT,
        state["mode"],
        state_diff=state_diff or {},
    )



def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()



def _split_claims_offline(draft_answer: str) -> list[str]:
    if not draft_answer.strip():
        return []

    return [
        fragment
        for fragment in (_normalize_whitespace(part) for part in _SENTENCE_SPLIT_RE.split(draft_answer))
        if fragment
    ]



def _coerce_claims(payload: object) -> list[str] | None:
    if isinstance(payload, list):
        claims = [_normalize_whitespace(str(item)) for item in payload]
        return [claim for claim in claims if claim]

    if isinstance(payload, dict):
        raw_claims = payload.get("claims")
        if isinstance(raw_claims, list):
            claims = [_normalize_whitespace(str(item)) for item in raw_claims]
            return [claim for claim in claims if claim]

    return None



def _parse_claim_list(raw: str) -> list[str] | None:
    candidates = [raw.strip()]
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        candidates.append(cleaned.strip())

    array_match = re.search(r"\[[\s\S]*\]", raw)
    if array_match:
        candidates.append(array_match.group(0))

    dict_match = re.search(r"\{[\s\S]*\}", raw)
    if dict_match:
        candidates.append(dict_match.group(0))

    for candidate in candidates:
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        claims = _coerce_claims(payload)
        if claims is not None:
            return claims

    return None



def _tokenize(text: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS}



def _offline_alignment(claims: list[str], sources: list[dict[str, str]]) -> tuple[list[float], list[str]]:
    if not claims:
        return [], ["No factual claims extracted from draft answer."]

    if not sources:
        return [0.0 for _ in claims], ["supported by 0 source(s)" for _ in claims]

    source_words = _tokenize(" ".join(source["snippet"] for source in sources))
    scores: list[float] = []
    notes: list[str] = []
    for claim in claims:
        claim_words = _tokenize(claim)
        if not claim_words:
            score = 0.0
        else:
            score = round(len(claim_words & source_words) / len(claim_words), 2)
        supporting_sources = sum(1 for source in sources if claim_words & _tokenize(source["snippet"]))
        scores.append(score)
        notes.append(f"supported by {supporting_sources} source(s)")
    return scores, notes



def _parse_alignment_response(raw: str) -> tuple[float, str]:
    match = _STATUS_RE.match(raw.strip())
    if not match:
        return 0.0, "unable to verify"

    label = match.group(1).lower()
    reason = _normalize_whitespace(match.group(2))
    if label == "yes":
        return 1.0, reason or "supported by provided snippets"
    if label == "partial":
        return 0.5, reason or "partially supported by provided snippets"
    return 0.0, reason or "not supported by provided snippets"



def _forced_verdict(state: AgentState) -> CitationVerdict | None:
    if _FORCE_WEAK_RE.search(state["question"]):
        return {
            "status": "weak",
            "confidence": 0.30,
            "notes": ["Forced weak citation verdict for retry-loop testing."],
        }

    if _FORCE_RETRY_RE.search(state["question"]):
        if state["attempt"] == 1:
            return {
                "status": "weak",
                "confidence": 0.30,
                "notes": ["Forced weak citation verdict on the first attempt."],
            }
        return {
            "status": "grounded",
            "confidence": 0.85,
            "notes": ["Forced grounded citation verdict on the retry attempt."],
        }

    return None



def _research_key_facts(state: AgentState) -> list[dict[str, object]]:
    report = state.get("research_report")
    if not report:
        return []
    return [
        fact
        for fact in report.get("key_facts", [])
        if isinstance(fact, dict) and _normalize_whitespace(str(fact.get("claim") or ""))
    ]



def _score_key_fact_alignment(
    claim: str,
    cited_indices: list[int],
    *,
    synthesized: bool,
    sources: list[dict[str, str]],
) -> tuple[float, str]:
    if synthesized:
        return 0.0, "synthesized claim is unsupported"

    unique_indices: list[int] = []
    for index in cited_indices:
        if index not in unique_indices:
            unique_indices.append(index)

    if not unique_indices:
        return 0.0, "supported by 0 cited source(s)"
    if any(index < 0 or index >= len(sources) for index in unique_indices):
        return 0.0, "contains invalid cited source index"

    claim_words = _tokenize(claim)
    cited_sources = [sources[index] for index in unique_indices]
    cited_words = _tokenize(" ".join(source["snippet"] for source in cited_sources))
    score = 1.0 if claim_words & cited_words else 0.5

    domains = {domain_of(source["url"]) for source in cited_sources if domain_of(source["url"])}
    if len(domains) >= 2:
        score = min(1.0, round(score * 1.15, 4))

    return score, f"checked against {len(unique_indices)} cited source(s)"



def _blind_synthesis_detected(state: AgentState) -> bool:
    for fact in _research_key_facts(state):
        if bool(fact.get("synthesized")) and not list(fact.get("citations") or []):
            return True
    return False



def extract_claims(state: AgentState) -> dict[str, object]:
    node_name = "citation_verifier.extract_claims"
    key_facts = _research_key_facts(state)
    _log_enter(
        state,
        node_name,
        state_diff={"draft_answer": bool(state["draft_answer"]), "key_facts": len(key_facts)},
    )

    if key_facts:
        claims = [_normalize_whitespace(str(fact.get("claim") or "")) for fact in key_facts]
        claim_citations = [list(fact.get("citations") or []) for fact in key_facts]
    elif state["mode"] == "live":
        prompt = (
            "Extract the atomic factual claims from the draft answer below. "
            "Return JSON only as an array of strings.\n\n"
            f"Draft answer:\n{state['draft_answer']}"
        )
        raw = make_chat("live").complete(
            prompt,
            system="You extract atomic factual claims into a JSON list.",
            max_tokens=256,
        )
        claims = _parse_claim_list(raw) or _split_claims_offline(state["draft_answer"])
        claim_citations = None
    else:
        claims = _split_claims_offline(state["draft_answer"])
        claim_citations = None

    update = {"_verifier_claims": claims, "_verifier_claim_citations": claim_citations}
    _log_exit(state, node_name, state_diff={"claims": len(claims)})
    return update



def check_alignment(state: AgentState) -> dict[str, object]:
    node_name = "citation_verifier.check_alignment"
    claims = list(state["_verifier_claims"] or [])
    key_facts = _research_key_facts(state)
    using_key_facts = bool(key_facts and state.get("_verifier_claim_citations") is not None)
    _log_enter(
        state,
        node_name,
        state_diff={"claims": len(claims), "sources": len(state["sources"]), "key_facts": using_key_facts},
    )

    if using_key_facts:
        claim_citations = cast(list[list[int]], state.get("_verifier_claim_citations") or [])
        scores = []
        notes = []
        for index, claim in enumerate(claims):
            fact = key_facts[index] if index < len(key_facts) else {"citations": [], "synthesized": False}
            score, note = _score_key_fact_alignment(
                claim,
                claim_citations[index] if index < len(claim_citations) else [],
                synthesized=bool(fact.get("synthesized", False)),
                sources=state["sources"],
            )
            scores.append(score)
            notes.append(note)
    elif state["mode"] == "live" and claims:
        if not state["sources"]:
            scores = [0.0 for _ in claims]
            notes = ["supported by 0 source(s)" for _ in claims]
        else:
            chat = make_chat("live")
            snippets = "\n\n".join(
                f"[{index}] {source['snippet']}" for index, source in enumerate(state["sources"], start=1)
            )
            scores = []
            notes = []
            for claim in claims:
                prompt = (
                    "Does the following claim find support in these snippets? "
                    "Reply with Yes, Partial, or No followed by a brief reason.\n\n"
                    f"Claim: {claim}\n\n"
                    f"Snippets:\n{snippets}"
                )
                raw = chat.complete(
                    prompt,
                    system="You verify whether claims are grounded in the provided snippets.",
                    max_tokens=128,
                )
                score, note = _parse_alignment_response(raw)
                scores.append(score)
                notes.append(note)
    else:
        scores, notes = _offline_alignment(claims, state["sources"])

    mean_score = float(fmean(scores)) if scores else 0.0
    update = {"_verifier_scores": scores, "_verifier_notes": notes}
    _log_exit(state, node_name, state_diff={"scores": scores, "mean_score": mean_score})
    return update



def emit_verdict(state: AgentState) -> dict[str, object]:
    node_name = "citation_verifier.emit_verdict"
    claims = list(state["_verifier_claims"] or [])
    scores = list(state["_verifier_scores"] or [])
    notes = list(state["_verifier_notes"] or [])
    blind_synthesis = _blind_synthesis_detected(state)
    _log_enter(
        state,
        node_name,
        state_diff={"claims": len(claims), "scores": scores, "sources": len(state["sources"])},
    )

    verdict = _forced_verdict(state)
    if verdict is None:
        if not state["sources"]:
            verdict = {
                "status": "not_applicable",
                "confidence": 1.0,
                "notes": ["No sources available for citation verification."],
            }
        elif not claims:
            verdict = {
                "status": "not_applicable",
                "confidence": 1.0,
                "notes": notes or ["No factual claims extracted from draft answer."],
            }
        else:
            confidence = float(fmean(scores)) if scores else 0.0
            status = "grounded" if confidence >= 0.70 else "weak"
            if blind_synthesis:
                status = "weak"
                notes = [*notes, "Blind synthesis detected: at least one key fact lacked citation support."]
            verdict = {
                "status": cast(str, status),
                "confidence": confidence,
                "notes": notes,
            }

    update = {
        "citation_verdict": verdict,
        "confidence": verdict["confidence"],
        "_verifier_claims": None,
        "_verifier_claim_citations": None,
        "_verifier_scores": None,
        "_verifier_notes": None,
    }
    _log_exit(state, node_name, state_diff={"citation_verdict": verdict, "confidence": verdict["confidence"]})
    return update



def build_citation_verifier_subgraph():
    graph = StateGraph(AgentState, output=CitationVerifierOutput)
    retry_policy = RetryPolicy(max_attempts=2)
    graph.add_node("extract_claims", extract_claims, retry=retry_policy)
    graph.add_node("check_alignment", check_alignment, retry=retry_policy)
    graph.add_node("emit_verdict", emit_verdict)
    graph.add_edge(START, "extract_claims")
    graph.add_edge("extract_claims", "check_alignment")
    graph.add_edge("check_alignment", "emit_verdict")
    graph.add_edge("emit_verdict", END)
    return graph.compile()


citation_verifier = build_citation_verifier_subgraph()



def citation_verifier_node(state: AgentState) -> dict[str, object]:
    return cast(dict[str, object], citation_verifier.invoke(state))


__all__ = [
    "build_citation_verifier_subgraph",
    "check_alignment",
    "citation_verifier",
    "citation_verifier_node",
    "emit_verdict",
    "extract_claims",
]
