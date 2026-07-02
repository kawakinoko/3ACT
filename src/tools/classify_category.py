import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.scenario_tags import classify_scenario_text

class ClassifyQuestionCategoryInput(BaseModel):
    """Schema for classify_question_category tool input."""

    text: str = Field(description="User question to classify")

@tool(args_schema=ClassifyQuestionCategoryInput)
def classify_text_category(text: str) -> str:
    """
    Classify a Samsung QA question through the dedicated Category Agent.

    Output will be in this format:
    {
        "product_family": <product_family>,
        "scenario_type": <scenario_type>
    }
    1. product_family: a category of a product or a model name or a service
    2. scenario_type: an intention of the given question or answer or an exect target that the user wants to know/chatbot answered
    """

    result = classify_scenario_text(text)
    return json.dumps(result, ensure_ascii=False)
