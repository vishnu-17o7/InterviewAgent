"""
components — Separable interview pipeline modules.

Each component has a clear, independent interface:
- QuestionGenerator: Generate tailored question sets
- InterviewConductor: Adaptive interview state machine
- Evaluator: Score answers & produce structured reports

They communicate through shared data models (dicts), not direct imports.
Changing one component does not require rewriting the others.
"""
