from abc import abstractmethod
from abc import ABCMeta

class Agent(metaclass=ABCMeta):
    def __init__(self, model, temperature, max_output_tokens, api_key=None, base_url=None):
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    def get_llm(self):
        pass