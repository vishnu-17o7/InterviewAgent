"""
interview.py — Adaptive session state machine

Handles:
- Deep probing on strong answers (score >= 8)
- Silence detection and re-asking
- Off-topic redirection
- Clarification rephrasing (without coaching)
- Structured evaluation report with cited evidence
"""

from . import store, llm

TOTAL_QUESTIONS = 10
PASS_SCORE = 6
DEEP_PROBE_THRESHOLD = 8


def start_interview(candidate_id: int, role: str, skills: list[str],
                    job_description: str = "", candidate_profile: str = "") -> tuple[str, str]:
    """Create session. Generate/load questions. Return first question."""
    jt_id = store.find_or_create_job_template(role, skills)

    if not store.job_template_has_questions(jt_id):
        questions = llm.generate_all_questions(role, skills, job_description, candidate_profile)
        store.insert_questions(jt_id, questions)

    all_qs = store.get_questions_for_job(jt_id)
    first_q = _pick_question(all_qs, skills, 0)

    session_id = store.create_session(candidate_id, jt_id, skills, first_q,
                                      job_description, candidate_profile)
    return session_id, first_q


def _pick_question(all_qs: list[dict], skills: list[str], question_index: int) -> str:
    num_skills = len(skills)
    skill_idx = question_index % num_skills
    skill = skills[skill_idx]
    full_rounds = question_index // num_skills
    visits = full_rounds + (1 if question_index % num_skills >= skill_idx else 0)
    skill_qs = [q for q in all_qs if q["skill"] == skill]
    skill_qs.sort(key=lambda q: q.get("sort_order", 0))
    if skill_qs:
        pool_idx = visits % len(skill_qs)
        return skill_qs[pool_idx]["question_text"]
    return f"Tell me about your experience with {skill}."


def _current_skill(skills: list[str], question_index: int) -> str:
    return skills[question_index % len(skills)]


def process_answer_audio(session_id: str, audio_b64: str, audio_format: str = "wav") -> dict:
    session = store.get_session(session_id)
    if not session or session["status"] == "complete":
        raise ValueError("Session is complete or does not exist.")

    role = session["role"]
    skills = session["skills"]
    question_index = session["question_index"]
    current_skill = _current_skill(skills, question_index)
    question = session["current_question"]

    eval_result = llm.evaluate_answer_with_audio(
        role, current_skill, question, audio_b64, audio_format
    )
    transcript = eval_result.get("transcript", "[no speech detected]")
    score = eval_result.get("score", 5)
    feedback = eval_result.get("feedback", "")

    return _handle_response(
        session, role, skills, question_index, current_skill,
        question, transcript, score, feedback,
    )


def process_answer(session_id: str, answer_text: str) -> dict:
    session = store.get_session(session_id)
    if not session or session["status"] == "complete":
        raise ValueError("Session is complete or does not exist.")

    role = session["role"]
    skills = session["skills"]
    question_index = session["question_index"]
    current_skill = _current_skill(skills, question_index)
    question = session["current_question"]

    eval_result = llm.evaluate_answer(role, current_skill, question, answer_text)
    score = eval_result.get("score", 5)
    feedback = eval_result.get("feedback", "")

    return _handle_response(
        session, role, skills, question_index, current_skill,
        question, answer_text, score, feedback,
    )


def _handle_response(
    session, role, skills, question_index, current_skill,
    question, transcript, score, feedback,
) -> dict:
    session_id = session["session_id"]
    next_index = question_index + 1

    # ── Answer Type Detection ──────────────────────────────────────────
    answer_type = llm.detect_answer_type(transcript)

    if answer_type == "silence":
        return _handle_silence(session_id, role, current_skill, question, transcript, question_index)

    if answer_type == "clarification":
        return _handle_clarification(session_id, question, question_index)

    if answer_type == "off_topic":
        return _handle_off_topic(session_id, current_skill, question, transcript, question_index)

    # ── Normal answer — record and decide next step ────────────────────
    is_followup = _is_current_followup(session_id, question_index)

    store.append_history(session_id, {
        "skill": current_skill,
        "question": question,
        "answer": transcript,
        "score": score,
        "feedback": feedback,
        "is_followup": is_followup,
    })

    # Deep probe on strong answers
    if score >= DEEP_PROBE_THRESHOLD and next_index < TOTAL_QUESTIONS:
        deeper_q = llm.generate_deeper_probe(role, current_skill, question, transcript)
        store.update_session(session_id, {
            "current_question": deeper_q,
            "question_index": next_index,
        })
        return {
            "transcript": transcript,
            "question": question,
            "score": score,
            "feedback": feedback,
            "next_question": deeper_q,
            "is_followup": is_followup,
            "is_complete": False,
            "skill": current_skill,
            "summary": None,
        }

    # Follow-up on weak answers
    if score < PASS_SCORE and next_index < TOTAL_QUESTIONS:
        followup_q = llm.generate_followup(role, current_skill, question, transcript)
        store.update_session(session_id, {
            "current_question": followup_q,
            "question_index": next_index,
        })
        return {
            "transcript": transcript,
            "question": question,
            "score": score,
            "feedback": feedback,
            "next_question": followup_q,
            "is_followup": is_followup,
            "is_complete": False,
            "skill": current_skill,
            "summary": None,
        }

    # Interview complete
    if next_index >= TOTAL_QUESTIONS:
        store.update_session(session_id, {"status": "complete", "question_index": next_index})
        all_history = store.get_session(session_id)["history"]
        report = llm.generate_structured_report(
            role, all_history,
            session.get("job_description", ""),
            session.get("candidate_profile", ""),
        )
        return {
            "transcript": transcript,
            "question": question,
            "score": score,
            "feedback": feedback,
            "next_question": None,
            "is_followup": is_followup,
            "is_complete": True,
            "skill": current_skill,
            "summary": report,
        }

    # Next regular question
    next_skill = _current_skill(skills, next_index)
    all_qs = store.get_questions_for_job(session["job_template_id"])
    next_q = _pick_question(all_qs, skills, next_index)

    store.update_session(session_id, {
        "current_question": next_q,
        "question_index": next_index,
    })

    return {
        "transcript": transcript,
        "question": question,
        "score": score,
        "feedback": feedback,
        "next_question": next_q,
        "is_followup": is_followup,
        "is_complete": False,
        "skill": current_skill,
        "summary": None,
    }


def _handle_silence(session_id, role, skill, question, transcript, question_index):
    """Silence or very short answer — re-ask the question once."""
    store.append_history(session_id, {
        "skill": skill,
        "question": question,
        "answer": transcript or "[silence]",
        "score": 0,
        "feedback": "Candidate did not provide an answer.",
        "is_followup": False,
    })

    retry_q = f"Take your time — let me ask again: {question}"

    store.update_session(session_id, {
        "current_question": retry_q,
    })
    return {
        "transcript": transcript or "[silence]",
        "question": question,
        "score": 0,
        "feedback": "",
        "next_question": retry_q,
        "is_followup": False,
        "is_complete": False,
        "skill": skill,
        "summary": None,
    }


def _handle_clarification(session_id, question, question_index):
    """Candidate asks for clarification — rephrase without coaching."""
    rephrased = llm.rephrase_question(question)

    store.update_session(session_id, {
        "current_question": rephrased,
    })
    return {
        "transcript": "[candidate asked for clarification]",
        "question": question,
        "score": 0,
        "feedback": "",
        "next_question": rephrased,
        "is_followup": False,
        "is_complete": False,
        "skill": "",
        "summary": None,
    }


def _handle_off_topic(session_id, skill, question, transcript, question_index):
    """Off-topic answer — redirect back to the question."""
    redirect_q = f"That's interesting, but let me ask again: {question}"

    store.update_session(session_id, {
        "current_question": redirect_q,
    })
    return {
        "transcript": transcript,
        "question": question,
        "score": 0,
        "feedback": "Answer was off-topic — redirecting.",
        "next_question": redirect_q,
        "is_followup": False,
        "is_complete": False,
        "skill": skill,
        "summary": None,
    }


def _is_current_followup(session_id: str, question_index: int) -> bool:
    session = store.get_session(session_id)
    history = session.get("history", [])
    if not history:
        return False
    last = history[-1]
    return last.get("score", 10) < PASS_SCORE and not last.get("is_followup", False)


def get_status(session_id: str) -> dict:
    session = store.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    return {
        "session_id": session_id,
        "role": session["role"],
        "skills": session["skills"],
        "question_index": session["question_index"],
        "status": session["status"],
        "history_count": len(session.get("history", [])),
    }
