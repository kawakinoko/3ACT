from langchain.tools import tool
from pydantic import BaseModel, Field

class ReadFileInput(BaseModel):
    """Schema for read file tool input"""
    file_path: str = Field(description="File path of the file to read")

@tool(args_schema=ReadFileInput)
def read_file(file_path: str) -> str:
    """
    Read a file from a given path.
    Returns a file content with a concatenated string form.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            res = file.read()
            return res
    except Exception as error:
        return f"파일을 읽는 중 오류가 발생했습니다: {error}"