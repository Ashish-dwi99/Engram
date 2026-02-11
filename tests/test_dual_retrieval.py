"""Tests for dual retrieval and intersection promotion."""

import pytest

from engram import Engram
from engram.retrieval.reranker import intersection_promote


@pytest.fixture
def memory():
    eng = Engram(in_memory=True, provider="mock")
    return eng._memory


def _stage_and_approve(memory, *, content, token, user_id="u-dual", agent_id="reader"):
    proposal = memory.propose_write(
        content=content,
        user_id=user_id,
        agent_id=agent_id,
        token=token,
        mode="staging",
        infer=False,
        scope="work",
    )
    memory.approve_commit(proposal["commit_id"])


def test_dual_retrieval_intersection_promotion(memory):
    session = memory.create_session(
        user_id="u-dual",
        agent_id="reader",
        allowed_confidentiality_scopes=["work"],
    )

    _stage_and_approve(
        memory,
        token=session["token"],
        content="On 8 May at dance studio, Gina's team performed Finding Freedom and won first place.",
    )
    _stage_and_approve(
        memory,
        token=session["token"],
        content="Gina likes contemporary dance in general.",
    )

    payload = memory.search_with_context(
        query="What piece did Gina perform when her team won first place?",
        user_id="u-dual",
        agent_id="reader",
        token=session["token"],
        limit=5,
    )

    assert payload["results"]
    assert payload["scene_hits"]
    assert payload["results"][0].get("episodic_match") is True

    context_packet = payload["context_packet"]
    assert context_packet["snippets"]
    # Scene citations are emitted in context packet.
    assert context_packet["snippets"][0]["citations"]["scene_ids"]

    trace = payload["retrieval_trace"]
    assert trace["strategy"] == "semantic_plus_episodic_intersection"
    assert trace["intersection_candidates"] >= 1
    assert "boost_weight" in trace
    assert "boost_cap" in trace

    scores = [float(item.get("composite_score", 0.0)) for item in payload["results"]]
    assert scores == sorted(scores, reverse=True)

    first = payload["results"][0]
    assert "base_composite_score" in first
    assert "intersection_boost" in first
    assert float(first["composite_score"]) >= float(first["base_composite_score"])


def test_intersection_promote_applies_calibrated_boost_deterministically():
    semantic_results = [
        {"id": "m1", "composite_score": 0.75, "score": 0.75},
        {"id": "m2", "composite_score": 0.80, "score": 0.80},
        {"id": "m3", "composite_score": 0.65, "score": 0.65},
    ]
    episodic_scenes = [
        {"id": "s1", "memory_ids": ["m1"], "search_score": 0.95},
    ]

    ranked = intersection_promote(
        semantic_results,
        episodic_scenes,
        boost_weight=0.35,
        max_boost=0.35,
    )
    by_id = {item["id"]: item for item in ranked}

    assert ranked[0]["id"] == "m1"
    assert by_id["m1"]["episodic_match"] is True
    assert float(by_id["m1"]["intersection_boost"]) > 0.0
    assert float(by_id["m1"]["composite_score"]) > float(by_id["m1"]["base_composite_score"])
    assert by_id["m2"]["episodic_match"] is False
    assert float(by_id["m2"]["intersection_boost"]) == 0.0
