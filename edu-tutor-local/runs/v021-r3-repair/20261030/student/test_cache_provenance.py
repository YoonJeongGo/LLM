"""File-only synthetic cache provenance tests; no model/API/database calls."""
import copy
import unittest
import collect_journeys as collector


class FirstPlayCacheTest(unittest.TestCase):
    def fixture(self):
        clip = {"audio_id": "a", "step_id": "s1", "cache_hit": False, "elapsed_seconds": 1.2}
        job = {"id": "j", "kind": "speech", "state": "succeeded", "updated_at": "2026-10-30T00:00:01Z",
               "result": {"lesson_id": "l", "steps": [clip]}}
        entry = {"lesson_id": "l", "step_id": "s1", "audio_id": "a", "event_index": 2,
                 "event": {"at_iso": "2026-10-30T00:00:02Z"}, "tts_clip_cache_hit": True,
                 "tts_generation_snapshot": {"provider": "windows_sapi_local"}}
        return {"owned_jobs": [job], "responses": []}, [entry]

    def test_new_synthesis_overrides_later_cache_observation(self):
        record, played = self.fixture()
        record["responses"].append({"at": "2026-10-30T00:00:01.5Z", "path": "/api/lessons/l/cache",
            "value": {"clips": [{"step_id": "s1", "audio_id": "a", "cache_hit": True}]}})
        collector.bind_first_play_cache_provenance(record, played)
        self.assertIs(played[0]["tts_clip_cache_hit"], False)
        self.assertEqual(played[0]["cache_provenance"]["binding"]["job_id"], "j")
        self.assertIs(played[0]["tts_generation_metadata_is_historical_when_cached"], False)

    def test_exact_cache_response_remains_a_hit(self):
        record, played = self.fixture(); record["owned_jobs"] = []
        record["responses"].append({"at": "2026-10-30T00:00:01Z", "path": "/api/lessons/l/cache",
            "value": {"clips": [{"step_id": "s1", "audio_id": "a", "cache_hit": True}]}})
        collector.bind_first_play_cache_provenance(record, played)
        self.assertIs(played[0]["tts_clip_cache_hit"], True)

    def test_same_audio_other_lesson_is_not_current_synthesis(self):
        record, played = self.fixture(); record["owned_jobs"][0]["result"]["lesson_id"] = "previous"
        collector.bind_first_play_cache_provenance(record, played)
        self.assertIsNone(played[0]["tts_clip_cache_hit"])

    def test_wrong_step_or_audio_not_used(self):
        for key in ["step_id", "audio_id"]:
            with self.subTest(key=key):
                record, played = self.fixture(); record["owned_jobs"][0]["result"]["steps"][0][key] = "wrong"
                collector.bind_first_play_cache_provenance(record, played)
                self.assertIsNone(played[0]["tts_clip_cache_hit"])

    def test_future_job_or_response_not_used(self):
        record, played = self.fixture(); record["owned_jobs"][0]["updated_at"] = "2026-10-30T00:00:03Z"
        record["responses"].append({"at": "2026-10-30T00:00:03Z", "path": "/api/lessons/l/cache",
            "value": {"clips": [{"step_id": "s1", "audio_id": "a", "cache_hit": True}]}})
        collector.bind_first_play_cache_provenance(record, played)
        self.assertIsNone(played[0]["tts_clip_cache_hit"])

    def test_cancelled_job_is_not_completed_synthesis(self):
        record, played = self.fixture(); record["owned_jobs"][0]["state"] = "cancelled"
        collector.bind_first_play_cache_provenance(record, played)
        self.assertIsNone(played[0]["tts_clip_cache_hit"])

    def test_missing_time_is_unknown_not_false(self):
        record, played = self.fixture(); played[0]["event"] = {}
        collector.bind_first_play_cache_provenance(record, played)
        self.assertIsNone(played[0]["tts_clip_cache_hit"])

    def test_resume_uses_first_play_cutoff(self):
        record, played = self.fixture()
        played.append(copy.deepcopy(played[0])); played[-1].update(event_index=8, event={"at_iso": "2026-10-30T00:00:08Z"})
        later = copy.deepcopy(record["owned_jobs"][0]); later.update(id="later", updated_at="2026-10-30T00:00:06Z")
        later["result"]["steps"][0]["cache_hit"] = True; record["owned_jobs"].append(later)
        collector.bind_first_play_cache_provenance(record, played)
        self.assertEqual([p["tts_clip_cache_hit"] for p in played], [False, False])
        self.assertEqual(played[1]["cache_provenance"]["first_play_at_iso"], "2026-10-30T00:00:02Z")


if __name__ == "__main__":
    unittest.main()
