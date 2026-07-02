from tools.classify_category import classify_text_category
from agents.abstract_agent import AbstractAgent
from global_config import *

EVALUATION_PROMPT_PATH = PROJECT_ROOT / "prompts" / "evaluation_system.md"

class EvaluationAgent(AbstractAgent):
    def __init__(self):
        try:
            with open(EVALUATION_PROMPT_PATH, "r", encoding="utf-8") as f:
                prompt_content = f.read()

            self.agent = self.create_agent(
                llm=LLM_MIDDLE,
                model=MODEL_MIDDLE,
                temperature=0.1,
                max_output_tokens=4096,
                api_key=API_KEY_MIDDLE,
                base_url=BASE_URL_MIDDLE,
                system_prompt=prompt_content,
                tools=[classify_text_category]
            )
        except FileNotFoundError as e:
            raise e
