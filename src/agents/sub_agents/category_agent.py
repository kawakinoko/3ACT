from global_config import *
from langchain.agents import create_agent
from llm.factory import get_llm

CATEGORY_PROMPT_PATH = PROJECT_ROOT / "prompts" / "category_system.md"

class CategoryAgent:
    def __init__(self):
        with open(CATEGORY_PROMPT_PATH, "r", encoding="utf-8") as handle:
            prompt_content = handle.read()
        
        self.agent = create_agent(
            model=get_llm(
                llm=LLM_MIDDLE,
                model=MODEL_MIDDLE,
                temperature=0.1,
                max_output_tokens=4096,
                api_key=API_KEY_MIDDLE,
                base_url=BASE_URL_MIDDLE
            ),
            tools=[],
            system_prompt=prompt_content
        )

    def invoke(self, prompt):
        message = {"role": "user", "content": prompt}
        return self.agent.invoke({"messages": [message]})

