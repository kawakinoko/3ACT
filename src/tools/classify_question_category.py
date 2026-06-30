import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.scenario_tags import classify_scenario_text

class ClassifyQuestionCategoryInput(BaseModel):
    """Schema for classify_question_category tool input."""

    category: str = Field(default="", description="Existing testcase category label, if any")
    question: str = Field(description="User question to classify")
    expected_keywords: list[str] = Field(default_factory=list, description="Optional expected keywords")

@tool(args_schema=ClassifyQuestionCategoryInput)
def classify_question_category(category: str, question: str, expected_keywords: list[str] | None = None) -> str:
    """Classify a Samsung QA question through the dedicated Category Agent."""

    result = classify_scenario_text(category, question, tuple(expected_keywords or []))
    return json.dumps(result, ensure_ascii=False)
