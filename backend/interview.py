"""
interview.py — Session state machine
Controls the flow: question → answer → evaluate → follow-up or next skill → end
"""

from . import store, llm

MAX_FOLLOWUPS = 1      # max follow-up questions per skill
PASS_SCORE = 6         # score threshold to move to next skill


def start_interview(role: str, skills: list[str]) -> tuple[str, str]:
    """
    Create a new session and generate the first question.
    Returns (session_id, first_question_text).
    """
    session_id = store.create_session(role, skills)
    question = _ask_question(session_id)
    return session_id, question


def _ask_question(session_id: str) -> str:
    """
    Generate a question for the current skill and store it in the session.
    """
    session = store.get_session(session_id)
    role = session["role"]
    skills = session["skills"]
    skill_index = session["skill_index"]
    current_skill = skills[skill_index]
    history = session["history"]

    question = llm.generate_question(role, current_skill, history)
    store.update_session(session_id, {"current_question": question})
    return question


def process_answer(session_id: str, answer_text: str) -> dict:
    """
    Process a candidate's answer.
    Returns a result dict:
    {
        "transcript": str,
        "question": str,
        "score": int,
        "feedback": str,
        "next_question": str | None,   # None means interview is done
        "is_followup": bool,
        "is_complete": bool,
        "skill": str,
        "summary": str | None,         # filled when complete
    }
    """
    session = store.get_session(session_id)
    if not session or session["status"] == "complete":
        raise ValueError("Session is complete or does not exist.")

    role = session["role"]
    skills = session["skills"]
    skill_index = session["skill_index"]
    current_skill = skills[skill_index]
    question = session["current_question"]
    follow_up_count = session["follow_up_count"]

    # Evaluate the answer
    eval_result = llm.evaluate_answer(role, current_skill, question, answer_text)
    score = eval_result.get("score", 5)
    feedback = eval_result.get("feedback", "")

    # Record this Q&A in history
    store.append_history(session_id, {
        "skill": current_skill,
        "question": question,
        "answer": answer_text,
        "score": score,
        "feedback": feedback,
        "is_followup": follow_up_count > 0,
    })

    # Decide next step
    weak = score < PASS_SCORE
    can_followup = follow_up_count < MAX_FOLLOWUPS

    if weak and can_followup:
        # Ask a follow-up for the same skill
        followup_q = llm.generate_followup(role, current_skill, question, answer_text)
        store.update_session(session_id, {
            "current_question": followup_q,
            "follow_up_count": follow_up_count + 1,
        })
        return {
            "transcript": answer_text,
            "question": question,
            "score": score,
            "feedback": feedback,
            "next_question": followup_q,
            "is_followup": True,
            "is_complete": False,
            "skill": current_skill,
            "summary": None,
        }
    else:
        # Move to next skill
        next_skill_index = skill_index + 1
        if next_skill_index >= len(skills):
            # All skills exhausted — end interview
            store.update_session(session_id, {"status": "complete"})
            summary = llm.generate_summary(role, session["history"] + [{
                "skill": current_skill,
                "question": question,
                "answer": answer_text,
                "score": score,
                "feedback": feedback,
            }])
            return {
                "transcript": answer_text,
                "question": question,
                "score": score,
                "feedback": feedback,
                "next_question": None,
                "is_followup": False,
                "is_complete": True,
                "skill": current_skill,
                "summary": summary,
            }
        else:
            # Next skill
            store.update_session(session_id, {
                "skill_index": next_skill_index,
                "follow_up_count": 0,
            })
            next_q = _ask_question(session_id)
            return {
                "transcript": answer_text,
                "question": question,
                "score": score,
                "feedback": feedback,
                "next_question": next_q,
                "is_followup": False,
                "is_complete": False,
                "skill": current_skill,
                "summary": None,
            }


def get_status(session_id: str) -> dict:
    session = store.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    return {
        "session_id": session_id,
        "role": session["role"],
        "skills": session["skills"],
        "skill_index": session["skill_index"],
        "status": session["status"],
        "history_count": len(session["history"]),
    }
