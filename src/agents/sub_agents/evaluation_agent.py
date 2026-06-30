from langchain.agents import create_agent
from llm.factory import get_llm
from global_config import *

EVALUATION_PROMPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "prompts", "evaluation_system.md"
)

class EvaluationAgent:
    def __init__(self):
        try:
            with open(EVALUATION_PROMPT_PATH, "r", encoding="utf-8") as f:
                prompt_content = f.read()
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
        except FileNotFoundError as e:
            raise e

    def invoke(self, prompt):
        message = {"role": "user", "content": prompt}
        return self.agent.invoke({"messages": [message]})
