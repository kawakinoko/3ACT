import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

def get_llm(model_name="gemini-1.5-flash", temperature=0.1, max_tokens=2048, base_url=None, api_key: str = None):
    """
    Returns an instance of ChatGoogleGenerativeAI configured with Gemini.
    Checks GEMINI_API_KEY or GOOGLE_API_KEY by default.
    """
    raw_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=temperature,
        max_output_tokens=max_tokens,
        google_api_key=raw_key
    )
