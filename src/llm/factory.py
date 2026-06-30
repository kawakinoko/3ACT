from llm.gemini import GeminiAgent
from llm.openai import OpenAIAgent
from llm.self_managed import SelfManagedAgent
from llm.abstract_agent import Agent

MAP_LLM = {
    "gemini": GeminiAgent,
    "openai": OpenAIAgent,
    "self_managed": SelfManagedAgent
}
def get_llm(llm="gemini", model="gemini-1.5-flash", temperature=0.1, max_output_tokens=2048, api_key="not-needed", base_url=None) -> Agent:
    """
    Returns an corresponding llm agent based on the provided llm type:
    Supported type:
    gemini
    openai
    self_managed
    """

    if llm not in MAP_LLM:
        raise RuntimeError("""
            Supported type:
            gemini
            openai
            self_managed
        """)

    return MAP_LLM[llm](
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        api_key=api_key,
        base_url=base_url
    )
