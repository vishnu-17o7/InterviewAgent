"""
Component 2: Interview Conduct (State Machine)

Interface:
  next_action(session, answer, eval_result) -> Action

Responsibilities:
- Controls question flow (round-robin across skills, up to 10 questions)
- Handles adaptive scenarios: silence, off-topic, clarification, deep probe
- Does NOT generate questions or evaluate answers directly
- Returns structured actions the API layer renders

An Action is a dict:
  {
    "type": "ask" | "follow_up" | "deep_probe" | "rephrase" | "redirect" | "end",
    "question": str,          # the next question to ask
    "skill": str,             # which skill this relates to
    "is_complete": bool,      # is the interview over?
    "next_question_index": int,
  }
"""

from .. import store, llm

TOTAL_QUESTIONS = 10
PASS_SCORE = 6
DEEP_PROBE_THRESHOLD = 8


def next_action(session: dict, transcript: str, score: int) -> dict:
    """
    Determine what to do next based on the candidate's answer.

    Returns an Action dict that the API layer uses to update the session
    and return the next question to the frontend.
    """
    skills = session["skills"]
    question_index = session["question_index"]
    current_skill = _current_skill(skills, question_index)
    question = session["current_question"]
    role = session["role"]
    session_id = session["session_id"]
    next_index = question_index + 1

    # ── Detect answer type ────────────────────────────────────────────
    answer_type = llm.detect_answer_type(transcript)

    if answer_type == "silence":
        return _silence_action(session_id, current_skill, question, question_index)

    if answer_type == "clarification":
        return _clarification_action(session_id, question, question_index)

    if answer_type == "off_topic":
        return _off_topic_action(session_id, current_skill, question, question_index)

    # ── Deep probe on strong answers ──────────────────────────────────
    if score >= DEEP_PROBE_THRESHOLD and next_index < TOTAL_QUESTIONS:
        deeper_q = llm.generate_deeper_probe(role, current_skill, question, transcript)
        return _action("deep_probe", deeper_q, current_skill, next_index, False)

    # ── Follow-up on weak answers ─────────────────────────────────────
    if score < PASS_SCORE and next_index < TOTAL_QUESTIONS:
        followup_q = llm.generate_followup(role, current_skill, question, transcript)
        return _action("follow_up", followup_q, current_skill, next_index, False)

    # ── Interview complete ────────────────────────────────────────────
    if next_index >= TOTAL_QUESTIONS:
        return _action("end", None, current_skill, next_index, True)

    # ── Next regular question ─────────────────────────────────────────
    next_skill = _current_skill(skills, next_index)
    all_qs = store.get_questions_for_job(session["job_template_id"])
    next_q = _pick_question(all_qs, skills, next_index)
    return _action("ask", next_q, next_skill, next_index, False)


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


def _action(action_type: str, question: str, skill: str, question_index: int, is_complete: bool) -> dict:
    return {
        "type": action_type,
        "question": question,
        "skill": skill,
        "is_complete": is_complete,
        "next_question_index": question_index,
    }


def _silence_action(session_id, skill, question, question_index):
    retry_q = f"Take your time — let me ask again: {question}"
    store.update_session(session_id, {"current_question": retry_q})
    return _action("ask", retry_q, skill, question_index, False)


def _clarification_action(session_id, question, question_index):
    rephrased = llm.rephrase_question(question)
    store.update_session(session_id, {"current_question": rephrased})
    return _action("rephrase", rephrased, "", question_index, False)


def _off_topic_action(session_id, skill, question, question_index):
    redirect_q = f"That's interesting, but let me ask again: {question}"
    store.update_session(session_id, {"current_question": redirect_q})
    return _action("redirect", redirect_q, skill, question_index, False)
