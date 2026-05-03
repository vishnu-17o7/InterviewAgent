"""
interview.py — Session state machine
10-question flat loop with round-robin skill selection.
Questions are cached per job template in SQLite.
"""

from . import store, llm

TOTAL_QUESTIONS = 10
PASS_SCORE = 6


def start_interview(candidate_id: int, role: str, skills: list[str]) -> tuple[str, str]:
    """Create session. Generate/load questions. Return first question."""
    jt_id = store.find_or_create_job_template(role, skills)

    if not store.job_template_has_questions(jt_id):
        questions = llm.generate_all_questions(role, skills)
        store.insert_questions(jt_id, questions)

    all_qs = store.get_questions_for_job(jt_id)
    first_q = _pick_question(all_qs, skills, 0)

    session_id = store.create_session(candidate_id, jt_id, skills, first_q)
    return session_id, first_q


def _pick_question(all_qs: list[dict], skills: list[str], question_index: int) -> str:
    """
    Round-robin: current skill = skills[question_index % len(skills)].
    Pool index = how many times this skill has been visited so far
    (which is question_index // len(skills), plus 1 if the remainder
    covers this skill's position).
    """
    num_skills = len(skills)
    skill_idx = question_index % num_skills
    skill = skills[skill_idx]

    # How many times has this skill been visited up to and including this question_index?
    # Every full round contributes 1 visit per skill.
    full_rounds = question_index // num_skills
    visits = full_rounds + (1 if question_index % num_skills >= skill_idx else 0)

    # Gather all cached questions for this skill
    skill_qs = [q for q in all_qs if q["skill"] == skill]
    skill_qs.sort(key=lambda q: q.get("sort_order", 0))

    if skill_qs:
        pool_idx = visits % len(skill_qs)
        return skill_qs[pool_idx]["question_text"]

    # Fallback
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

    return _finish_answer(
        session_id, session, role, skills, question_index,
        current_skill, question, transcript, score, feedback,
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

    return _finish_answer(
        session_id, session, role, skills, question_index,
        current_skill, question, answer_text, score, feedback,
    )


def _finish_answer(
    session_id, session, role, skills, question_index,
    current_skill, question, transcript, score, feedback,
) -> dict:
    is_followup = _is_current_followup(session_id, question_index)

    store.append_history(session_id, {
        "skill": current_skill,
        "question": question,
        "answer": transcript,
        "score": score,
        "feedback": feedback,
        "is_followup": is_followup,
    })

    weak = score < PASS_SCORE
    next_index = question_index + 1

    # Follow-up: if score is weak AND we haven't asked 10 yet, ask a follow-up
    if weak and next_index < TOTAL_QUESTIONS:
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

    # Interview complete after 10 questions
    if next_index >= TOTAL_QUESTIONS:
        store.update_session(session_id, {"status": "complete", "question_index": next_index, "completed_at": None})
        all_history = store.get_session(session_id)["history"]
        summary = llm.generate_summary(role, all_history)
        return {
            "transcript": transcript,
            "question": question,
            "score": score,
            "feedback": feedback,
            "next_question": None,
            "is_followup": is_followup,
            "is_complete": True,
            "skill": current_skill,
            "summary": summary,
        }

    # Next regular question from pool
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


def _is_current_followup(session_id: str, question_index: int) -> bool:
    """
    A question is a follow-up if the previous answer was weak (score < PASS_SCORE).
    We detect this by checking the last history entry's score.
    """
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
