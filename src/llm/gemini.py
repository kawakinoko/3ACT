from llm.abstract_client import Client
from langchain_google_genai import ChatGoogleGenerativeAI

class GeminiClient(Client):
    def __init__(self, model="gemini-1.5-flash", temperature=0.1, max_output_tokens=2048, api_key=None, base_url=None):
        super(GeminiClient, self).__init__(model, temperature, max_output_tokens, api_key)

    def get_llm(self):
        """
        Returns an instance of ChatGoogleGenerativeAI configured with Gemini.
        """
        
        return ChatGoogleGenerativeAI(
            model=self.model,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            google_api_key=self.api_key
        )