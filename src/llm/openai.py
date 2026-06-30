from llm.abstract_agent import Agent
from langchain_openai import ChatOpenAI

class OpenAIAgent(Agent):
    def __init__(self, model="gpt-4o", temperature=0.1, max_output_tokens=2048, api_key=None, base_url=None):
        super.__init__(model, temperature, max_output_tokens, api_key)

    def get_llm(self):
        """
        Returns an instance of ChatOpenAI configured with OpenAI.
        """
        
        return ChatOpenAI(
            model=self.model,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            api_key=self.api_key
        )