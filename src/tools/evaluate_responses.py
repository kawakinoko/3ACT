import json
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from agents.sub_agents.evaluation_agent import EvaluationAgent

class EvaluateResponsesInput(BaseModel):
    """Schema for evaluate_responses tool input"""
    runs_json: str = Field(description="JSON string representing the run results returned by run_usecases tool")

@tool(args_schema=EvaluateResponsesInput)
def evaluate_responses(runs_json: str) -> str:
    """
    Evaluates each run result in the JSON by comparing the actual chatbot response
    with the expected response using the Evaluation Agent.
    """
    try:
        runs = json.loads(runs_json)
    except Exception as e:
        return f"Error: Invalid JSON payload provided: {str(e)}"
        
    eval_agent = EvaluationAgent()
    evaluated_results = []
    
    print("\n🔍 Evaluating chatbot responses with the Evaluation Agent...")
    for idx, run in enumerate(runs):
        query = run.get("query", "")
        expected = run.get("expected_response", "")
        actual = run.get("actual_response", "")
        status = run.get("status", "")
        
        # If the automation failed, score 0.0 directly
        if status == "failed" or not actual or actual.startswith("Error running automation"):
            run["evaluation"] = {
                "overall_score": 0.0,
                "correctness_score": 0.0,
                "relevance_score": 0.0,
                "completeness_score": 0.0,
                "clarity_score": 0.0,
                "groundedness_score": 0.0,
                "reason": "Execution failed or chatbot did not return any answer.",
                "fix_suggestion": "Check the automation run logs and browser screenshots.",
                "flags": ["evaluation_failed"]
            }
            evaluated_results.append(run)
            continue
            
        eval_prompt = f"""
Evaluate the following chatbot QA response:
- User Question: {query}
- Expected Reference Response: {expected}
- Actual Chatbot Response: {actual}
        """
        
        try:
            print(f"📊 Evaluating case {idx + 1}/{len(runs)}: '{query[:50]}'")
            agent_result = eval_agent.invoke(eval_prompt)
            output_content = agent_result["messages"][-1].content
            
            # Clean JSON markdown formatting if present
            clean_content = output_content.strip()
            if clean_content.startswith("```"):
                lines = clean_content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                clean_content = "\n".join(lines).strip()
                
            eval_data = json.loads(clean_content)
            run["evaluation"] = eval_data
        except Exception as e:
            run["evaluation"] = {
                "overall_score": 0.0,
                "correctness_score": 0.0,
                "relevance_score": 0.0,
                "completeness_score": 0.0,
                "clarity_score": 0.0,
                "groundedness_score": 0.0,
                "reason": f"Evaluation error: {str(e)}",
                "fix_suggestion": "Check LLM API connectivity or prompt format.",
                "flags": ["evaluation_failed"]
            }
            
        evaluated_results.append(run)
        
    return json.dumps(evaluated_results, ensure_ascii=False, indent=2)
