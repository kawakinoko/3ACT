import json
import os
from pathlib import Path
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from app.browser import BrowserManager
from app.config import load_config
from app.logger import create_logger
from app.models import TestCase
from app.samsung_rubicon import configure_runtime, run_single_case
from global_config import PROJECT_ROOT

class RunUsecasesInput(BaseModel):
    """Schema for run_usecases tool input"""

    usecases_input: str = Field(
        description=(
            "Plain text or filepath containing one or more usecases formatted "
            "with 'Query: <query>' and 'Expected response: <expected_response>'"
        )
    )

def parse_usecases(input_str: str) -> list[dict]:
    content = input_str
    candidate_path = input_str.strip()
    if len(candidate_path) < 500 and os.path.exists(candidate_path):
        try:
            with open(candidate_path, "r", encoding="utf-8") as handle:
                content = handle.read()
        except Exception:
            pass

    usecases = []
    current_usecase: dict[str, str] = {}
    for line in content.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        
        lower_line = line_str.lower()
        parts = line_str.split(":", 1)
        if lower_line.startswith("query:", "prompt:"):
            if "query" in current_usecase:
                usecases.append(current_usecase)
                current_usecase = {}
            current_usecase["query"] = parts[1].strip()
        elif lower_line.startswith("expected response:"):
            current_usecase["expected_response"] = parts[1].strip()
            
    if current_usecase:
        usecases.append(current_usecase)
        
    valid_usecases = []
    for usecase in usecases:
        if "query" not in usecase:
            continue
        usecase.setdefault("expected_response", "")
        valid_usecases.append(usecase)
    return valid_usecases

@tool(args_schema=RunUsecasesInput)
def run_usecases(usecases_input: str) -> str:
    """
    Runs one or more usecases on the Samsung.com AI chatbot and extract responses.
    Browser execution is headed by default so the user can watch the flow.
    """
    usecases = parse_usecases(usecases_input)
    if not usecases:
        return (
            "Error: No valid usecases parsed. Make sure they are formatted with "
            "'Query: <query>' and 'Expected response: <expected_response>'."
        )

    config = load_config(PROJECT_ROOT)
    config.ensure_directories()
    logger = create_logger(config.runtime_log_path)
    
    # Run headlessly by default for background execution if not specified in env
    if os.getenv("HEADLESS") is None:
        config.headless = True
    else:
        config.headless = os.getenv("HEADLESS").lower() in ("true", "1", "yes")

    print(f"\n🤖 Starting browser automation on samsung.com (Headless={config.headless})...")
    browser_manager = BrowserManager(config=config, logger=logger)
    browser_manager.start()
    configure_runtime(config, logger)
    
    results = []
    try:
        for index, usecase in enumerate(usecases):
            test_case = TestCase(
                id=f"orchestrated_case_{index + 1}",
                category="orchestrated",
                locale=config.default_locale,
                page_url=config.samsung_base_url,
                question=usecase["query"],
                expected_keywords=[],
                forbidden_keywords=[],
                expected_response=usecase["expected_response"]
            )
            
            print(f"Usecase {index + 1}/{len(usecases)}: {test_case.question}")
            session = browser_manager.new_case_session(test_case.id)
            try:
                pair = run_single_case(session.page, test_case)
                actual_answer = pair.answer_raw or ""
                results.append({
                    "id": test_case.id,
                    "query": usecase["query"],
                    "expected_response": usecase["expected_response"],
                    "actual_response": actual_answer,
                    "status": pair.status,
                    "screenshots": {
                        "full_screenshot": str(pair.full_screenshot_path) if pair.full_screenshot_path else "",
                        "chat_screenshot": str(pair.chat_screenshot_path) if pair.chat_screenshot_path else ""
                    }
                })
                print(f"Response: {actual_answer[:100]}...\n")
            except Exception as error:
                logger.exception("Error running single case: %s", error)
                results.append({
                    "id": test_case.id,
                    "query": usecase["query"],
                    "expected_response": usecase["expected_response"],
                    "actual_response": f"Error running automation: {str(error)}",
                    "status": "failed",
                    "screenshots": {}
                })
                print(f"Automation Error: {str(error)}\n")
            finally:
                session.close()
    finally:
        browser_manager.stop()
        
    return json.dumps(results, ensure_ascii=False, indent=2)
