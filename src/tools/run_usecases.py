import sys
import os
import json
from pathlib import Path
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from app.browser import BrowserManager
from app.config import load_config
from app.logger import create_logger
from app.samsung_rubicon import configure_runtime, run_single_case
from app.models import TestCase

class RunUsecasesInput(BaseModel):
    """Schema for run_usecases tool input"""
    usecases_input: str = Field(description="Plain text or filepath containing one or more usecases formatted with 'Query: <query>' and 'Expected response: <expected_response>'")

def parse_usecases(input_str: str) -> list[dict]:
    content = input_str
    # Check if it's a file path
    if len(input_str.strip()) < 500 and os.path.exists(input_str.strip()):
        try:
            with open(input_str.strip(), "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            pass

    usecases = []
    current_usecase = {}
    
    for line in content.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        
        lower_line = line_str.lower()
        if lower_line.startswith("query:") or lower_line.startswith("prompt:"):
            if "query" in current_usecase:
                usecases.append(current_usecase)
                current_usecase = {}
            parts = line_str.split(":", 1)
            current_usecase["query"] = parts[1].strip()
        elif lower_line.startswith("expected response:"):
            parts = line_str.split(":", 1)
            current_usecase["expected_response"] = parts[1].strip()
            
    if current_usecase:
        usecases.append(current_usecase)
        
    valid_usecases = []
    for uc in usecases:
        if "query" in uc:
            if "expected_response" not in uc:
                uc["expected_response"] = ""
            valid_usecases.append(uc)
    return valid_usecases

@tool(args_schema=RunUsecasesInput)
def run_usecases(usecases_input: str) -> str:
    """
    Runs one or more usecases on the Samsung.com AI chatbot by loading the session storage state, 
    navigating, inputting the query, and extracting the response text and taking screenshots.
    """
    usecases = parse_usecases(usecases_input)
    if not usecases:
        return "Error: No valid usecases parsed. Make sure they are formatted with 'Query: <query>' and 'Expected response: <expected_response>'."

    project_root = Path("../../")
    config = load_config(project_root)
    logger = create_logger(config.runtime_log_path)
    
    # Run headlessly by default for background execution if not specified in env
    if os.getenv("HEADLESS") is None:
        config.headless = True
    else:
        config.headless = os.getenv("HEADLESS").lower() in ("true", "1", "yes")

    print(f"\n🤖 Starting Browser Automation on samsung.com (Headless={config.headless})...")
    browser_manager = BrowserManager(config=config, logger=logger)
    browser_manager.start()
    configure_runtime(config, logger)
    
    results = []
    try:
        for idx, uc in enumerate(usecases):
            test_case = TestCase(
                id=f"orchestrated_case_{idx + 1}",
                category="orchestrated",
                locale=config.default_locale,
                page_url=config.samsung_base_url,
                question=uc["query"],
                expected_keywords=[],
                forbidden_keywords=[],
                expected_response=uc["expected_response"]
            )
            
            print(f"📝 Usecase {idx + 1}/{len(usecases)}: {test_case.question}")
            session = browser_manager.new_case_session(test_case.id)
            try:
                pair = run_single_case(session.page, test_case)
                actual_answer = pair.answer_raw or ""
                results.append({
                    "id": test_case.id,
                    "query": uc["query"],
                    "expected_response": uc["expected_response"],
                    "actual_response": actual_answer,
                    "status": pair.status,
                    "screenshots": {
                        "full_screenshot": str(pair.full_screenshot_path) if pair.full_screenshot_path else "",
                        "chat_screenshot": str(pair.chat_screenshot_path) if pair.chat_screenshot_path else ""
                    }
                })
                print(f"🤖 Response: {actual_answer[:100]}...\n")
            except Exception as e:
                logger.exception("Error running single case: %s", e)
                results.append({
                    "id": test_case.id,
                    "query": uc["query"],
                    "expected_response": uc["expected_response"],
                    "actual_response": f"Error running automation: {str(e)}",
                    "status": "failed",
                    "screenshots": {}
                })
                print(f"❌ Automation Error: {str(e)}\n")
            finally:
                session.close()
    finally:
        browser_manager.stop()
        
    return json.dumps(results, ensure_ascii=False, indent=2)
