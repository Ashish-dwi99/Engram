"""Tests for LongMemEval benchmark runner helpers."""

import json
from argparse import Namespace

from engram.benchmarks import longmemeval


def test_extract_user_only_text_filters_non_user_roles():
    turns = [
        {"role": "system", "content": "ignore"},
        {"role": "user", "content": "first user fact"},
        {"role": "assistant", "content": "ignore"},
        {"role": "user", "content": "second user fact"},
    ]
    text = longmemeval.extract_user_only_text(turns)
    assert text == "first user fact\nsecond user fact"


def test_parse_session_id_from_result_prefers_metadata():
    row = {
        "metadata": {"session_id": "sid_meta"},
        "memory": "Session ID: sid_text",
    }
    assert longmemeval.parse_session_id_from_result(row) == "sid_meta"


def test_compute_session_metrics_hits_expected_scores():
    metrics = longmemeval.compute_session_metrics(
        retrieved_session_ids=["s1", "s2", "s3"],
        answer_session_ids=["s2", "s3"],
    )
    assert metrics["recall_any@1"] == 0.0
    assert metrics["recall_any@3"] == 1.0
    assert metrics["recall_all@1"] == 0.0
    assert metrics["recall_all@3"] == 1.0


def test_build_output_row_excludes_debug_fields_by_default():
    row = longmemeval.build_output_row(
        question_id="q1",
        hypothesis="answer",
        retrieved_session_ids=["s1"],
        retrieval_metrics={"recall_any@1": 1.0},
        include_debug_fields=False,
    )
    assert row == {"question_id": "q1", "hypothesis": "answer"}


def test_build_memory_full_potential_enables_echo_category_graph(tmp_path):
    memory = longmemeval.build_memory(
        llm_provider="mock",
        embedder_provider="simple",
        vector_store_provider="memory",
        embedding_dims=64,
        history_db_path=str(tmp_path / "h.db"),
        full_potential=True,
    )
    assert memory.config.echo.enable_echo is True
    assert memory.config.category.enable_categories is True
    assert memory.config.graph.enable_graph is True


def test_build_memory_minimal_disables_echo_category_graph(tmp_path):
    memory = longmemeval.build_memory(
        llm_provider="mock",
        embedder_provider="simple",
        vector_store_provider="memory",
        embedding_dims=64,
        history_db_path=str(tmp_path / "h.db"),
        full_potential=False,
    )
    assert memory.config.echo.enable_echo is False
    assert memory.config.category.use_llm_categorization is False
    assert memory.config.graph.enable_graph is False


class _StubLLM:
    def generate(self, prompt: str) -> str:
        _ = prompt
        return "stub hypothesis"


class _StubMemory:
    def __init__(self):
        self.llm = _StubLLM()
        self.deleted = []
        self.added = []

    def delete_all(self, user_id: str):
        self.deleted.append(user_id)
        return {"deleted_count": 0}

    def add(self, **kwargs):
        self.added.append(kwargs)
        return {"id": f"mem_{len(self.added)}"}

    def search_with_context(self, **kwargs):
        _ = kwargs
        return {
            "results": [
                {
                    "metadata": {"session_id": "session_1"},
                    "memory": "Session ID: session_1\nUser Transcript:\nalpha",
                },
                {
                    "metadata": {"session_id": "session_2"},
                    "memory": "Session ID: session_2\nUser Transcript:\nbeta",
                },
            ]
        }


def test_run_longmemeval_writes_eval_compatible_jsonl(monkeypatch, tmp_path):
    dataset = [
        {
            "question_id": "q_001",
            "question": "Where did I have dinner last week?",
            "answer_session_ids": ["session_1"],
            "haystack_session_ids": ["session_1", "session_2"],
            "haystack_dates": ["2026-01-01", "2026-01-02"],
            "haystack_sessions": [
                [{"role": "user", "content": "I had dinner at Juniper Lane."}],
                [{"role": "user", "content": "I bought a notebook."}],
            ],
        }
    ]
    dataset_path = tmp_path / "longmemeval_small.json"
    dataset_path.write_text(json.dumps(dataset), encoding="utf-8")

    output_path = tmp_path / "hypotheses.jsonl"
    retrieval_path = tmp_path / "retrieval.jsonl"

    stub_memory = _StubMemory()
    monkeypatch.setattr(longmemeval, "build_memory", lambda **_: stub_memory)

    args = Namespace(
        dataset_path=str(dataset_path),
        output_jsonl=str(output_path),
        retrieval_jsonl=str(retrieval_path),
        include_debug_fields=False,
        full_potential=True,
        user_id="u_test",
        start_index=0,
        end_index=-1,
        max_questions=-1,
        skip_abstention=False,
        top_k=3,
        max_context_chars=2048,
        print_every=0,
        answer_backend="engram-llm",
        hf_model="Qwen/Qwen2.5-1.5B-Instruct",
        hf_max_new_tokens=64,
        llm_provider="mock",
        llm_model=None,
        embedder_provider="simple",
        embedder_model=None,
        vector_store_provider="memory",
        embedding_dims=384,
        history_db_path=str(tmp_path / "history.db"),
        qdrant_path=None,
    )

    summary = longmemeval.run_longmemeval(args)
    assert summary["processed"] == 1
    assert len(stub_memory.added) == 2
    assert stub_memory.deleted == ["u_test"]

    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"question_id": "q_001", "hypothesis": "stub hypothesis"}]

    retrieval_rows = [json.loads(line) for line in retrieval_path.read_text(encoding="utf-8").splitlines()]
    assert retrieval_rows[0]["question_id"] == "q_001"
    assert retrieval_rows[0]["retrieved_session_ids"] == ["session_1", "session_2"]
    assert retrieval_rows[0]["metrics"]["recall_any@1"] == 1.0
