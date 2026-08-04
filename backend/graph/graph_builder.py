import os
import uuid

from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph , END , START
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from graph.state import AgentState

from graph.nodes.clean_agent import clean_agent_node, human_review_node , apply_cleaning_node , initial_choice_node
from graph.nodes.eda_agent import eda_agent_node
from graph.nodes.report_generation_agent import report_generation_node
from graph.nodes.analyst_agent import analyst_agent_node , show_answer_node
from graph.nodes.validator_agent import validator_agent_node 
from graph.nodes.final_agent import final_agent_node 

from PIL import Image
import io



DATABASE_URL = os.getenv("DATABASE_URL")

graph = StateGraph(AgentState)

# ROUTERS --------------------------------------
def dispatcher_node(state: AgentState):
    """
    Does nothing except forward the action.
    """
    return {
        "action": state["action"]
    }

def route_action(state: AgentState):
    action = state["action"]
    if action == "init":
        return END
    if action == "clean":
        return "clean"
    if action == "question":
        return "question"
    if action == "report":
        return "report"
    if action == "email":
        return "email"
    return END

def route_after_cleaning(state:AgentState):
    """
    After the user reviews cleaning suggestions.
    Cleaning happens only ONCE.
    """
    return END

def route_after_validation(state: AgentState):

    verdict = state.get("validator_verdict", {})

    if verdict.get("approved"):
        return "approved"

    retry = state.get("retry_count", 0)

    if retry >= 2:
        return "approved"

    return "retry"

# -------------------------------------------------


#adding nodes -- 
graph.add_node('dispatcher', dispatcher_node)
graph.add_node('cleaning_agent', clean_agent_node)
graph.add_node('HITL', human_review_node)
graph.add_node('apply_clean_agent', apply_cleaning_node)
graph.add_node('eda_agent', eda_agent_node)
graph.add_node('report_gen_node', report_generation_node)
graph.add_node('analyst_agent', analyst_agent_node)
graph.add_node('validator_agent', validator_agent_node)
graph.add_node('show_answer', show_answer_node)
graph.add_node('final_agent', final_agent_node)



graph.add_edge(START, 'dispatcher')
graph.add_conditional_edges("dispatcher",route_action,{"clean": "cleaning_agent","question": "analyst_agent","report": "eda_agent","email": "final_agent",END: END},)

graph.add_edge('cleaning_agent','HITL')
graph.add_edge('HITL', 'apply_clean_agent')
graph.add_edge('apply_clean_agent',END)

graph.add_edge('eda_agent', 'report_gen_node')
graph.add_edge('report_gen_node',END)

graph.add_edge('analyst_agent', 'validator_agent')
graph.add_conditional_edges('validator_agent', route_after_validation, {"approved":"show_answer","retry":"analyst_agent"})
graph.add_edge('show_answer', END)

graph.add_edge('final_agent', END)



pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=10, kwargs={"autocommit": True})
checkpointer = PostgresSaver(pool)
checkpointer.setup()



config = {'configurable':{'thread_id':str(uuid.uuid4())}}

# compile -- 
workflow = graph.compile(checkpointer=checkpointer)



# img_bytes = workflow.get_graph().draw_mermaid_png()
# img = Image.open(io.BytesIO(img_bytes))
# img.show()

