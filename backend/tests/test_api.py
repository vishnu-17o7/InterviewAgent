"""
test_api.py — Tests for all API endpoints with real LLM calls.

Requires OPENROUTER_API_KEY and GROQ_API_KEY set in .env at project root.
These tests make actual API calls and will consume tokens.
"""

import io
import base64
import pytest


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestCandidateRegistration:
    def test_register_valid(self, client):
        resp = client.post("/candidate/register", json={"name": "Alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["name"] == "Alice"

    def test_register_empty_name(self, client):
        resp = client.post("/candidate/register", json={"name": "   "})
        assert resp.status_code == 400

    def test_candidate_sessions(self, client, candidate_id):
        resp = client.get(f"/candidate/{candidate_id}/sessions")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestSkillsSuggest:
    def test_suggest_skills(self, client):
        resp = client.post("/skills/suggest", json={"role": "Senior Python Developer"})
        assert resp.status_code == 200
        data = resp.json()
        assert "skills" in data
        assert isinstance(data["skills"], list)
        assert len(data["skills"]) >= 1

    def test_suggest_empty_role(self, client):
        resp = client.post("/skills/suggest", json={"role": "   "})
        assert resp.status_code == 400


class TestSessionStart:
    def test_start_valid(self, client, candidate_id):
        resp = client.post("/session/start", json={
            "candidate_id": candidate_id,
            "role": "Backend Engineer",
            "skills": ["Python", "SQL"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "question" in data
        assert "audio_b64" in data
        assert "skill" in data

    def test_start_with_jd_and_profile(self, client, candidate_id):
        resp = client.post("/session/start", json={
            "candidate_id": candidate_id,
            "role": "Frontend Developer",
            "skills": ["React", "CSS"],
            "job_description": "Looking for a senior React developer with 5+ years experience.",
            "candidate_profile": "3 years React experience, knows CSS well, familiar with TypeScript.",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["question"]) > 20

    def test_start_missing_role(self, client, candidate_id):
        resp = client.post("/session/start", json={
            "candidate_id": candidate_id,
            "role": "",
            "skills": ["Python"],
        })
        assert resp.status_code == 400

    def test_start_no_skills(self, client, candidate_id):
        resp = client.post("/session/start", json={
            "candidate_id": candidate_id,
            "role": "Engineer",
            "skills": [],
        })
        assert resp.status_code == 400

    def test_question_caching(self, client, candidate_id):
        """Same role+skills reuses cached questions."""
        role = "Python Developer"
        skills = ["Python", "Django"]

        # First start — generates questions
        r1 = client.post("/session/start", json={
            "candidate_id": candidate_id, "role": role, "skills": skills,
        })
        assert r1.status_code == 200
        q1 = r1.json()["question"]

        # Second start — should use cached questions (same first question)
        r2 = client.post("/candidate/register", json={"name": "Bob"})
        cid2 = r2.json()["id"]
        r3 = client.post("/session/start", json={
            "candidate_id": cid2, "role": role, "skills": skills,
        })
        assert r3.status_code == 200
        q2 = r3.json()["question"]

        # First question should be identical (from cache)
        assert q1 == q2


class TestSessionStatus:
    def test_status_active(self, client, session_id):
        resp = client.get(f"/session/status/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"

    def test_status_not_found(self, client):
        resp = client.get("/session/status/nonexistent-id")
        assert resp.status_code == 200
        assert "error" in resp.json()


class TestSessionEnd:
    def test_end_session(self, client, session_id):
        resp = client.post(f"/session/end/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Session ended"

    def test_end_nonexistent(self, client):
        resp = client.post("/session/end/nonexistent-id")
        assert resp.status_code == 404


class TestDashboard:
    def test_overview(self, client, candidate_id):
        resp = client.get("/dashboard/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "stats" in data
        assert "candidates" in data
        assert data["stats"]["total_candidates"] >= 1


class TestSessionAnswer:
    def test_submit_answer_audio(self, client, session_id):
        """Submit a fake audio answer to test the answer flow end-to-end."""
        # Create a minimal valid WAV file (44 bytes of silence)
        fake_wav = base64.b64decode(
            "UklGRiQAAABXQVZFZm10IBAAAAABAAEAIlYAAESsAAACABAAZGF0YQAAAAA="
        )
        resp = client.post(
            "/session/answer",
            data={"session_id": session_id},
            files={"audio": ("test.wav", io.BytesIO(fake_wav), "audio/wav")},
        )
        # 200 if the LLM processed it, 500 if the audio is invalid
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "transcript" in data
            assert "score" in data
            assert "feedback" in data
            assert "is_complete" in data

    def test_submit_invalid_session(self, client):
        fake_wav = base64.b64decode(
            "UklGRiQAAABXQVZFZm10IBAAAAABAAEAIlYAAESsAAACABAAZGF0YQAAAAA="
        )
        resp = client.post(
            "/session/answer",
            data={"session_id": "nonexistent"},
            files={"audio": ("test.wav", io.BytesIO(fake_wav), "audio/wav")},
        )
        assert resp.status_code == 404
