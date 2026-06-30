from tools import classify_question_category
from pathlib  import Path
from langchain.agents import create_agent
from llm.factory import get_llm
from tools.classify_question_category import classify_question_category
from tools.run_usecases import run_usecases
from tools.evaluate_responses import evaluate_responses
from global_config import *

ORCHESTRATOR_PROMPT_PATH = "../prompts/orchestrator_system.md"

class OrchestratorAgent:
    def __init__(self):
        try:
            with open(ORCHESTRATOR_PROMPT_PATH, "r", encoding="utf-8") as f:
                prompt_content = f.read()
            self.agent = create_agent(
                model=get_llm(
                    llm=LLM_SMALL,
                    model=MODEL_SMALL,
                    temperature=0.1,
                    max_output_tokens=4096,
                    api_key=API_KEY_SMALL,
                    base_url=BASE_URL_SMALL
                ),
                tools=[
                    classify_question_category,
                    run_usecases,
                    evaluate_responses
                ],
                system_prompt=prompt_content
            )
        except FileNotFoundError as e:
            raise e

    def invoke(self, prompt):
        message = {"role": "user", "content": prompt}
        return self.agent.invoke({"messages": [message]})
