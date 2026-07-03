from abc import abstractmethod
from abc import ABCMeta

from langchain.agents import create_agent as create_langchain_agent
from llm.factory import get_llm

class AbstractAgent(metaclass=ABCMeta):
    def __init__(self):
        self.agent = None

    def _response_text(self, response) -> str:
        output_content = response["messages"][-1].content
        print("===============================output===============================")
        print(output_content)
        if isinstance(output_content, list):
            output_content = output_content[-1]["text"]
        # Clean JSON markdown formatting if present
        clean_content = output_content.strip()
        if clean_content.startswith("```"):
            lines = clean_content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_content = "\n".join(lines).strip()
        return clean_content

    def invoke(self, prompt):
        if self.agent is None:
            raise RuntimeError("agent is not initialized")
        message = {"role": "user", "content": prompt}
        print(f"{type(self).__name__}: {message}")
        response = self.agent.invoke({"messages": [message]})
        print(f"{type(self).__name__}: {response}")
        return self._response_text(response)

    @classmethod
    def create_agent(cls, llm, model, temperature, max_output_tokens, api_key, base_url, system_prompt, tools=[]):
        if api_key is None or len(api_key.strip()) == 0:
            print(f"Warning: API key is not set. Skipping agent creation.")
            return None
        return create_langchain_agent(
                model=get_llm(
                    llm=llm,
                    model=model,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    api_key=api_key,
                    base_url=base_url
                ),
                tools=tools,
                system_prompt=system_prompt
            )

    def get_agent(self):
        return self.agent