from agents.abstract_agent import AbstractAgent
from pathlib  import Path
from llm.factory import get_llm
from tools.classify_question_category import classify_question_category
from tools.run_usecases import run_usecases
from tools.evaluate_responses import evaluate_responses
from tools.read_file import read_file
from global_config import *

ORCHESTRATOR_PROMPT_PATH = PROJECT_ROOT / "prompts" / "orchestrator_system.md"

class OrchestratorAgent(AbstractAgent):
    def __init__(self):
        try:
            with open(ORCHESTRATOR_PROMPT_PATH, "r", encoding="utf-8") as f:
                prompt_content = f.read()
            self.agent = self.create_agent(
                llm=LLM_SMALL,
                model=MODEL_SMALL,
                temperature=0.1,
                max_output_tokens=4096,
                api_key=API_KEY_SMALL,
                base_url=BASE_URL_SMALL,
                system_prompt=prompt_content,
                tools=[
                    read_file,
                    classify_question_category,
                    run_usecases,
                    evaluate_responses
                ]
            )
        except FileNotFoundError as e:
            raise e
