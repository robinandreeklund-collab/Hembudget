"""Arbetsförmedlingen · Sprint 6 · A1-A5.

Spec: dev/game-motor/05-arbetsformedlingen.md

Komponenter:
  A1+A2 · matching.py        match_score per (elev, jobb)
  A3    · pool.py            jobs-listing baserat på yrkespoolen + stad
  A4    · interview_flow.py  5-rond state-machine med Mats-feedback
  A5    · api.py             /v2/arbetsformedlingen/*-endpoints
"""
from .matching import (
    JobOpening,
    MATS_OPENING_MESSAGE,
    available_jobs_for_student,
    calculate_match_score,
)
from .interview_flow import (
    Round1Input,
    Round2Input,
    Round3Input,
    Round4Input,
    Round5Decision,
    RoundResult,
    abandon_application,
    accept_offer,
    apply_to_job,
    decline_offer,
    submit_round_response,
)

__all__ = [
    "JobOpening",
    "MATS_OPENING_MESSAGE",
    "available_jobs_for_student",
    "calculate_match_score",
    "Round1Input",
    "Round2Input",
    "Round3Input",
    "Round4Input",
    "Round5Decision",
    "RoundResult",
    "abandon_application",
    "accept_offer",
    "apply_to_job",
    "decline_offer",
    "submit_round_response",
]
