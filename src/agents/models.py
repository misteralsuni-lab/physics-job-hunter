from pydantic import BaseModel, Field, field_validator
from typing import Literal


class TutoringBrief(BaseModel):
    """Structured brief produced by the Tutoring Parser (private-tutoring branch).

    Distinct from :class:`StrategicBrief`. Used by the tutoring proposal
    generator to anchor outreach to the individual student / parent context.

    See ``docs/dual-pathway.md`` §4.
    """

    student_pain_points: list[str] = Field(
        ...,
        min_length=1,
        max_length=4,
        description="Specific difficulties the student mentions (topics, exam timing, confidence).",
    )
    parent_signals: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="Parent-side signals: urgency, prior tutors, budget hints, language tone.",
    )
    subject_alignment: str = Field(
        ...,
        min_length=10,
        max_length=400,
        description="Which of Mahmoud's IGCSE/A-Level topics and concepts the request maps to.",
    )
    recommended_first_session_focus: str = Field(
        ...,
        min_length=10,
        max_length=300,
        description="What we should cover in the free 30-min intro session.",
    )
    voice_warmth_target: int = Field(
        ...,
        ge=1,
        le=5,
        description="1=formal/academic, 5=warm/parental. Drives tone of the proposal copy.",
    )
    red_flags: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="Concerns to surface: homework-completion requests, grade guarantees, etc.",
    )

    @field_validator("student_pain_points")
    @classmethod
    def _pain_points_non_empty(cls, v: list[str]) -> list[str]:
        cleaned = [s.strip() for s in v if s.strip()]
        if not cleaned:
            raise ValueError("student_pain_points must contain at least one non-empty item")
        return cleaned

    @classmethod
    def fallback(cls, raw_excerpt: str = "") -> "TutoringBrief":
        """Graceful fallback when the parser fails or times out.

        ``raw_excerpt`` is a short slice of the original raw_message so the
        subject_alignment is at least tied to something concrete even with
        no LLM output.
        """
        excerpt = raw_excerpt.strip().splitlines()[0][:160] if raw_excerpt.strip() else "the request"
        return cls(
            student_pain_points=[excerpt or "the request as described"],
            parent_signals=[],
            subject_alignment=(
                "General IGCSE/A-Level Physics and Mathematics support; "
                "specific topics to be confirmed in the introductory session."
            ),
            recommended_first_session_focus=(
                "Map the syllabus, identify the highest-leverage topic gaps, "
                "and agree a starting plan for the first paid block."
            ),
            voice_warmth_target=3,
            red_flags=[],
        )


class StrategicBrief(BaseModel):
    """Structured strategic brief produced by the Research Agent.

    The brief guides the cover-letter generator by anchoring it to
    institution-specific facts and the strongest alignment with the
    candidate's profile.
    """

    institution_facts: list[str] = Field(
        ...,
        min_length=2,
        max_length=3,
        description="2-3 highly specific, unique facts about the school.",
    )
    strategic_alignment: str = Field(
        ...,
        min_length=20,
        max_length=800,
        description="Short paragraph deciding which part of Mahmoud's expertise best matches the school's goals.",
    )
    recommended_angle: str = Field(
        ...,
        min_length=10,
        max_length=400,
        description="Directive for the cover letter opening hook.",
    )

    school_profile: str = ""
    recruitment_analysis: str = ""
    candidate_match: str = ""
    contact_strategy: str = ""

    @field_validator("institution_facts")
    @classmethod
    def _facts_must_be_non_empty(cls, v: list[str]) -> list[str]:
        cleaned = [fact.strip() for fact in v if fact.strip()]
        if len(cleaned) < 2:
            raise ValueError("institution_facts must contain at least 2 non-empty facts")
        return cleaned

    @classmethod
    def fallback(cls, school_name: str = "the school") -> "StrategicBrief":
        """Return a graceful fallback brief when research data is unavailable."""
        return cls(
            institution_facts=[
                f"{school_name} is recruiting a Physics specialist for an international programme.",
                "The role targets IGCSE or A-Level delivery within a STEM department.",
            ],
            strategic_alignment=(
                "Mahmoud's four years of IGCSE and A-Level Physics and Mathematics teaching, "
                "combined with his B.Sc. Engineering background and current PGCEi studies, "
                "provide a direct match for the advertised STEM role. In the absence of deeper "
                "institutional detail, the strongest emphasis should be on his curriculum "
                "expertise and applied, engineering-informed pedagogy."
            ),
            recommended_angle=(
                f"Open the letter by connecting {school_name}'s advertised Physics programme "
                "to Mahmoud's hands-on IGCSE and A-Level classroom experience, then introduce "
                "his engineering 'Applied Mastery' approach as the natural fit for the role."
            ),
            school_profile="",
            recruitment_analysis="",
            candidate_match="",
            contact_strategy="",
        )
