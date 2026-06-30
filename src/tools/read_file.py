from langchain.tools import tool

@tool
def read_file(file_path: str) -> str:
    """주어진 경로의 파일을 읽어 내용을 반환합니다."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            res = file.read()
            print(res)
            return res
    except Exception as error:
        return f"파일을 읽는 중 오류가 발생했습니다: {error}"