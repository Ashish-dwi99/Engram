from dhee.simple import Engram


def test_enrich_pending_fills_missing_scene_summary(tmp_path):
    memory = Engram(provider="mock", in_memory=True, data_dir=str(tmp_path))
    try:
        memory.add(
            "Dhee should summarize scenes during lifecycle maintenance.",
            user_id="default",
            infer=False,
        )
        scenes = memory.memory.db.get_scenes(user_id="default", limit=10)
        assert len(scenes) == 1
        assert not scenes[0].get("summary")

        result = memory.enrich_pending(user_id="default", batch_size=5, max_batches=1)

        assert result["scene_summaries"]["summarized_count"] == 1
        summarized = memory.memory.db.get_scene(scenes[0]["id"])
        assert "Dhee should summarize scenes" in summarized["summary"]
        assert summarized["title"].startswith("Dhee should summarize scenes")
    finally:
        memory.close()


def test_repair_memory_quality_tombstones_operational_scene_noise(tmp_path):
    memory = Engram(provider="mock", in_memory=True, data_dir=str(tmp_path))
    try:
        memory.memory.db.add_scene(
            {
                "id": "scene-edited-file",
                "user_id": "default",
                "title": "Edited /tmp/project/app.py",
                "summary": None,
                "topic": "Edited /tmp/project/app.py",
                "start_time": "2026-01-01T00:00:00+00:00",
                "end_time": "2026-01-01T00:01:00+00:00",
                "memory_ids": [],
                "participants": [],
                "strength": 1.0,
            }
        )

        before = memory.audit_memory_quality(
            user_id="default",
            require_personal_model=False,
        )
        assert before["ready"] is False
        assert before["counts"]["scene_noise"] == 1
        assert before["counts"]["operational_scene_noise"] == 1

        repair = memory.repair_memory_quality(user_id="default", dry_run=False)

        assert repair["scene_noise_tombstoned"] == 1
        assert repair["operational_scenes_tombstoned"] == 1
        assert repair["scene_noise_events_written"] == 1
        assert repair["scene_noise_backup"]
        assert memory.memory.db.get_scene("scene-edited-file") is None

        events = memory.memory.db.get_episodic_events(user_id="default", limit=10)
        assert any(
            event["memory_id"] == "scene:scene-edited-file"
            and event["event_type"] == "operational_event"
            for event in events
        )
        after = memory.audit_memory_quality(
            user_id="default",
            require_personal_model=False,
        )
        assert after["ready"] is True
        assert after["counts"]["scene_noise"] == 0
    finally:
        memory.close()
