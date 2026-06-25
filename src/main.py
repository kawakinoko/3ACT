import sys
import os
from agents.orchestrator import OrchestratorAgent

# Ensure the src folder is in the python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def run_agent(query_prompt):
    print("🤖 Initializing Orchestrator Agent...")
    agent = OrchestratorAgent()
    result = agent.invoke(query_prompt)
    
    print("\n================== ORCHESTRATION RESULT ==================")
    print(result["messages"][-1].content)
    print("==========================================================")

if __name__ == '__main__':
    # Default query pointing to the usecases text file
    query = """
    Please run the usecases from the filepath: /home/kawakinoko/Documents/GitHub/3ACT/usecases.txt
    Then evaluate the responses and output a summary report.
    """
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if os.path.exists(arg):
            query = f"Please run the usecases from the filepath: {os.path.abspath(arg)}\nThen evaluate the responses and output a summary report."
        else:
            query = arg

    run_agent(query)
