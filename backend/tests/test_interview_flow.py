"""
test_interview_flow.py — Full end-to-end interview flow tests.

Simulates an entire interview from start to completion with real LLM calls.
"""

import io
import base64
import pytest


@pytest.mark.slow
class TestFullInterviewFlow:
    def test_complete_interview(self, client, candidate_id):
        """Run a full 10-question interview with fake audio answers."""
        # Start interview
        role = "Junior Developer"
        skills = ["JavaScript"]
        resp = client.post("/session/start", json={
            "candidate_id": candidate_id,
            "role": role,
            "skills": skills,
        })
        assert resp.status_code == 200
        data = resp.json()
        session_id = data["session_id"]
        assert len(data["question"]) > 10

        # Submit 10 fake audio answers
        fake_wav = base64.b64decode(
            "UklGRiQAAABXQVZFZm10IBAAAAABAAEAIlYAAESsAAACABAAZGF0YQAAAAA="
        )

        question_count = 0
        for _ in range(15):  # Up to 15 in case of follow-ups/silence
            resp = client.post(
                "/session/answer",
                data={"session_id": session_id},
                files={"audio": ("test.wav", io.BytesIO(fake_wav), "audio/wav")},
            )
            if resp.status_code not in (200, 500):
                break

            if resp.status_code == 200:
                data = resp.json()
                question_count += 1
                if data.get("is_complete"):
                    break

        # Should have completed
        status = client.get(f"/session/status/{session_id}").json()
        assert status["status"] == "complete"
        assert question_count >= 10

    def test_end_early(self, client, candidate_id):
        """End an interview early after a few answers."""
        resp = client.post("/session/start", json={
            "candidate_id": candidate_id,
            "role": "Tester",
            "skills": ["QA"],
        })
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # Submit one answer
        fake_wav = base64.b64decode(
            "UklGRiQAAABXQVZFZm10IBAAAAABAAEAIlYAAESsAAACABAAZGF0YQAAAAA="
        )
        resp = client.post(
            "/session/answer",
            data={"session_id": session_id},
            files={"audio": ("test.wav", io.BytesIO(fake_wav), "audio/wav")},
        )

        # End early
        resp = client.post(f"/session/end/{session_id}")
        assert resp.status_code == 200
        assert "history" in resp.json()


class TestTwoRoles:
    def test_different_roles_different_questions(self, client):
        """Verify two different roles produce different questions."""
        # Role 1
        r = client.post("/candidate/register", json={"name": "Role1 Test"})
        cid1 = r.json()["id"]
        r = client.post("/session/start", json={
            "candidate_id": cid1,
            "role": "Backend Engineer",
            "skills": ["Python", "PostgreSQL"],
        })
        q1 = r.json()["question"]

        # Role 2
        r = client.post("/candidate/register", json={"name": "Role2 Test"})
        cid2 = r.json()["id"]
        r = client.post("/session/start", json={
            "candidate_id": cid2,
            "role": "Frontend Engineer",
            "skills": ["React", "CSS"],
        })
        q2 = r.json()["question"]

        # Different roles should generate different questions
        assert q1 != q2
