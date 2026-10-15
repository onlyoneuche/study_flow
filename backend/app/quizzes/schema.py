import re
import string
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.core.study import normalise
from app.models.enums import Difficulty, EducationLevel

# Small, local filter required by §7.3. Word boundaries avoid matches inside curriculum terms.
BLOCKLIST = re.compile(r"\b(?:fuck|fucking|shit|porn|pornography|xxx|nude|nudes)\b", re.I)
BANNED_OPTIONS = re.compile(r"\b(?:all|none) of the above\b|\bboth\b.+\band\b", re.I)


def normalise_text(value: str):
    return normalise(value).rstrip(string.punctuation + "’” ")


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=10, max_length=300)
    options: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        min_length=4, max_length=4
    )
    correct_index: Annotated[StrictInt, Field(ge=0, le=3)]
    explanation: str = Field(max_length=200)
    difficulty: Difficulty

    @field_validator("options")
    @classmethod
    def valid_options(cls, options):
        normalised = [normalise_text(option) for option in options]
        if any(not option for option in normalised) or len(set(normalised)) != 4:
            raise ValueError("Options must be distinct and non-empty after normalisation")
        if any(BANNED_OPTIONS.search(option) for option in normalised):
            raise ValueError("All/none of the above and both-and options are not allowed")
        return options

    @model_validator(mode="after")
    def suitable_content(self) -> Self:
        if BLOCKLIST.search(" ".join([self.question, self.explanation, *self.options])):
            raise ValueError("Content filter rejected this question")
        return self


class QuizDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[Question] = Field(min_length=15, max_length=15)

    @model_validator(mode="after")
    def unique_questions(self) -> Self:
        if len({normalise_text(q.question) for q in self.questions}) != 15:
            raise ValueError("Questions must not be duplicates after normalisation")
        counts = {
            difficulty: sum(q.difficulty == difficulty for q in self.questions)
            for difficulty in Difficulty
        }
        if counts != {Difficulty.EASY: 5, Difficulty.MEDIUM: 6, Difficulty.HARD: 4}:
            raise ValueError("Use exactly 5 easy, 6 medium and 4 hard questions")
        return self


def level_descriptor(level: EducationLevel):
    if level.value.startswith("JSS"):
        return (
            f"Nigerian junior secondary year {level.value[-1]} (about age 10 to 14), "
            "NERDC curriculum / BECE style"
        )
    if level.value.startswith("SS"):
        return f"Nigerian senior secondary year {level.value[-1]}, WAEC/NECO/JAMB UTME style"
    if level.value.startswith("UG_"):
        year = int(level.value[3:]) // 100
        return f"University undergraduate, year {year} ({level.value[3:]}L)"
    return (
        "Postgraduate (Masters/PhD)"
        if level == EducationLevel.POSTGRAD
        else "General adult learner, intermediate difficulty"
    )


SYSTEM_PROMPT = """You are an experienced examiner writing multiple-choice questions for students.
Output only JSON that matches the provided schema. No commentary."""
USER_PROMPT = """Write exactly 15 multiple-choice questions.
Subject: {subject}
Topic: {topic}
Learner level: {level_descriptor}

Rules:
- Every question must test the topic above at the stated level.
- Mix difficulty: 5 easy (recall), 6 medium (understanding), 4 hard (application).
- Each question has exactly 4 options, all different, all plausible.
- Exactly one option is correct; give its index (0 to 3) as correct_index.
- Do not use "all of the above", "none of the above" or "both A and B".
- Keep each question under 300 characters and each option under 120 characters.
- Add a one-sentence explanation (under 200 characters) of the correct answer.
- Use British English and examples familiar to Nigerian students where natural.
- Content must be suitable for school-age learners.
{retry_feedback}"""
