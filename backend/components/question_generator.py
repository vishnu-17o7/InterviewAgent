"""
Component 1: Question Generation

Interface:
  generate(role, skills, jd, profile) -> list[{"skill", "question_text"}]
  suggest_skills(role) -> list[str]

Responsibilities:
- Accepts job description and candidate profile to tailor questions
- Generates 5 questions per skill
- Skips generation if questions already cached in DB for this role+skills combo
- Does NOT depend on interview conduct or evaluation logic
"""

from .. import llm
from .. import store

QUESTIONS_PER_SKILL = 5


def generate(role: str, skills: list[str], job_description: str = "",
             candidate_profile: str = "") -> list[dict]:
    """
    Generate or retrieve cached questions for a role+skills combo.
    Returns [{"skill": str, "question_text": str}, ...]
    """
    jt_id = store.find_or_create_job_template(role, skills)

    if not store.job_template_has_questions(jt_id):
        questions = llm.generate_all_questions(role, skills, job_description, candidate_profile)
        store.insert_questions(jt_id, questions)

    return store.get_questions_for_job(jt_id)


def suggest_skills(role: str) -> list[str]:
    """Ask the LLM for 5 relevant technical interview skills."""
    return llm.suggest_skills(role)
