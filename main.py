import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from agents.orchestrator import OrchestratorAgent

# Ensure the src folder is in the python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def run_agent(query_prompt):
    print("🤖 Initializing Orchestrator Agent...")
    agent = OrchestratorAgent()
    print("\n================== ORCHESTRATION QUERY ==================")
    print(query_prompt)
    print("==========================================================")
    result = agent.invoke(query_prompt)
    print("\n================== ORCHESTRATION RESULT ==================")
    print(result)
    print("==========================================================")

if __name__ == '__main__':
    # Default query pointing to the usecases text file
    query = """
    Please run the usecases from the filepath: /home/kawakinoko/Documents/GitHub/3ACT/usecases.txt
    Read the usecase from the given filepath.
    Then evaluate the responses and output a summary report.
    """
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if os.path.exists(arg):
            query = f"Please run the usecases from the filepath: {os.path.abspath(arg)}\nThen evaluate the responses and output a summary report."
        else:
            query = arg

    run_agent(query)
