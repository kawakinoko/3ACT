from agents.abstract_agent import AbstractAgent
from global_config import *

CATEGORY_PROMPT_PATH = PROJECT_ROOT / "prompts" / "category_system.md"

class CategoryAgent(AbstractAgent):
    def __init__(self):
        try:
            with open(CATEGORY_PROMPT_PATH, "r", encoding="utf-8") as handle:
                prompt_content = handle.read()
            
            self.agent = self.create_agent(
                llm=LLM_MIDDLE,
                model=MODEL_MIDDLE,
                temperature=0.1,
                max_output_tokens=4096,
                api_key=API_KEY_MIDDLE,
                base_url=BASE_URL_MIDDLE,
                system_prompt=prompt_content,
                tools=[]
            )
        except FileNotFoundError as e:
            raise e
