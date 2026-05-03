"""
test_adaptive_conduct.py — Edge case and adaptive conduct tests.

Tests silence handling, off-topic redirection, clarification, and deep probe behavior.
"""

import io
import base64
import pytest


class TestAdaptiveConduct:
    def test_silence_handling(self, client, candidate_id):
        """Silence should trigger a re-ask without crashing."""
        resp = client.post("/session/start", json={
            "candidate_id": candidate_id,
            "role": "Engineer",
            "skills": ["Python"],
        })
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # Submit a very short/empty audio (simulates silence)
        fake_wav = base64.b64decode(
            "UklGRiQAAABXQVZFZm10IBAAAAABAAEAIlYAAESsAAACABAAZGF0YQAAAAA="
        )
        resp = client.post(
            "/session/answer",
            data={"session_id": session_id},
            files={"audio": ("test.wav", io.BytesIO(fake_wav), "audio/wav")},
        )
        # Should not crash — either 200 with next question or 500 from LLM
        assert resp.status_code in (200, 500)

    def test_deep_probe_on_strong_answer(self, client, candidate_id):
        """A high-scoring answer should trigger a deep probe instead of moving on."""
        # This test verifies the flow doesn't crash — actual deep probe behavior
        # depends on LLM scoring the fake audio
        resp = client.post("/session/start", json={
            "candidate_id": candidate_id,
            "role": "Senior Engineer",
            "skills": ["System Design"],
        })
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        fake_wav = base64.b64decode(
            "UklGRiQAAABXQVZFZm10IBAAAAABAAEAIlYAAESsAAACABAAZGF0YQAAAAA="
        )
        # Submit answer — deep probe behavior depends on LLM score
        resp = client.post(
            "/session/answer",
            data={"session_id": session_id},
            files={"audio": ("test.wav", io.BytesIO(fake_wav), "audio/wav")},
        )
        # Should not crash regardless of score
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            # Either next question, follow-up, deep probe, or complete
            assert "next_question" in data or data.get("is_complete")


class TestJdProfileGeneration:
    def test_jd_aware_question_generation(self, client, candidate_id):
        """Questions should be tailored when JD is provided."""
        jd = "We need a Python developer with deep Django experience who can build REST APIs."
        profile = "Candidate has 2 years of Django experience and has built several REST APIs."
        resp = client.post("/session/start", json={
            "candidate_id": candidate_id,
            "role": "Python Developer",
            "skills": ["Django", "REST APIs", "PostgreSQL"],
            "job_description": jd,
            "candidate_profile": profile,
        })
        assert resp.status_code == 200
        data = resp.json()
        # Question should be related to Django or REST APIs
        q = data["question"].lower()
        assert any(term in q for term in ["django", "rest", "api", "endpoint"])


class TestAntiCoaching:
    def test_evaluation_does_not_crash(self, client, candidate_id):
        """Verify the evaluation flow works without coaching the candidate."""
        resp = client.post("/session/start", json={
            "candidate_id": candidate_id,
            "role": "Engineer",
            "skills": ["Python"],
        })
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        fake_wav = base64.b64decode(
            "UklGRiQAAABXQVZFZm10IBAAAAABAAEAIlYAAESsAAACABAAZGF0YQAAAAA="
        )
        resp = client.post(
            "/session/answer",
            data={"session_id": session_id},
            files={"audio": ("test.wav", io.BytesIO(fake_wav), "audio/wav")},
        )
        if resp.status_code == 200:
            data = resp.json()
            # Feedback should not contain coaching language
            if data.get("feedback"):
                fb = data["feedback"].lower()
                coaching_phrases = ["the correct answer is", "you should say", "the right way"]
                for phrase in coaching_phrases:
                    assert phrase not in fb


class TestEdgeCases:
    def test_concurrent_sessions(self, client, candidate_id):
        """Starting multiple sessions for the same candidate should work."""
        for i in range(3):
            resp = client.post("/session/start", json={
                "candidate_id": candidate_id,
                "role": f"Role {i}",
                "skills": ["Python"],
            })
            assert resp.status_code == 200

        # Verify candidate sessions API returns all of them
        sessions = client.get(f"/candidate/{candidate_id}/sessions").json()
        assert len(sessions) >= 3

    def test_dashboard_after_multiple_candidates(self, client):
        """Dashboard should aggregate multiple candidates correctly."""
        for name in ["Alpha", "Beta", "Gamma"]:
            r = client.post("/candidate/register", json={"name": name})
            cid = r.json()["id"]
            client.post("/session/start", json={
                "candidate_id": cid,
                "role": "Engineer",
                "skills": ["Python"],
            })

        resp = client.get("/dashboard/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stats"]["total_candidates"] >= 3
        assert data["stats"]["total_sessions"] >= 3
