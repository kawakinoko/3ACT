import os
from langchain.agents import create_agent
from factory import get_llm
from tools.run_usecases import run_usecases
from tools.evaluate_responses import evaluate_responses

ORCHESTRATOR_PROMPT_PATH = "../prompts/orchestrator_system.md"

class OrchestratorAgent:
    def __init__(self):
        try:
            with open(ORCHESTRATOR_PROMPT_PATH, "r", encoding="utf-8") as f:
                prompt_content = f.read()
            self.agent = create_agent(
                model=get_llm(
                    model_name="gemini-2.5-flash",
                    temperature=0.1,
                    max_tokens=4096
                ),
                tools=[
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
