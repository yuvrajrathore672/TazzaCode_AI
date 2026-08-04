# check whatever analyst_output contains against the real data, before showing it to the user — this is our rejection-loop.

from graph.state import AgentState

# -------------------------------------------
from dotenv import load_dotenv
load_dotenv()
from langchain_groq import ChatGroq

# LLM ---
model = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)

def llm_call(promt):
    response = model.invoke(promt)
    return response.content

# -------------------------------------------


def validator_agent_node(state:AgentState):
    output = state['analyst_output']

    prompt = f"""Question: {output['question']}
                Answer given: {output.get('final_answer')}
                Supporting data: {output.get('table_result') or output.get('sub_results')}

                Does the answer accurately reflect the supporting data, with no invented numbers?
                Reply with exactly one word first: "approved" or "rejected".
                Then on a new line, briefly explain why.
            """

    verdict_text = llm_call(prompt)
    verdict = verdict_text.strip().lower().startswith("approved")

    return {
        "validator_verdict" : {
            "approved":verdict,
            "reasoning":verdict_text
        },
        "retry_count": state.get("retry_count", 0) + 1
    }

