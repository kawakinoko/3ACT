from llm.abstract_agent import Agent
from langchain_openai import ChatOpenAI

class SelfManagedAgent(Agent):
    def __init__(self, model="qwen3.5:9b", temperature=0.1, max_output_tokens=2048, api_key="not-needed", base_url=None):
        super.__init__(model, temperature, max_output_tokens, api_key, base_url)

    def get_llm(self):
        """
        Returns an instance of ChatOpenAI configured with OpenAI.
        """
        
        return ChatOpenAI(
            model=self.model,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            base_url=self.base_url,
            api_key=self.api_key
        )