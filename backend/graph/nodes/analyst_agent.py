from tools.sql_analyst_tool import run_sql_tool , built_sql_promt , multistep_reasoning_tool ,clean_sql_response
from graph.state import AgentState
from graph.nodes.clean_agent import load_dataframe

# -------------------------------------------
from dotenv import load_dotenv
load_dotenv()
from langchain_groq import ChatGroq

# LLM ---
model = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)

def llm_call(prompt):
    response = model.invoke(prompt)
    return response.content

# -------------------------------------------

def generate_final_answer(question,result):
        prompt = f"""Question: {question}
                    Data result: {result['result']}

                    Answer this in one or two plain sentences for someone with non technical background.
                    Reference the actual numbers from the result.
                """

        return llm_call(prompt)


def classify_question_type(question):
    prompt = f"""Question: "{question}"
Is this a direct data lookup (answerable with one SQL query) or does it need
investigation/reasoning across multiple angles? Reply with exactly one word:
"direct" or "investigative"
"""
    return llm_call(prompt).strip().lower()



#NODESSSSSSSSSSSSSSSSSSSSSSSSS------------------------------
def analyst_agent_node(state:AgentState):
    file_path = state.get("cleaned_file_path") or state["file_path"]
    is_cleaned = state.get("cleaning_completed", False)
    df = load_dataframe(file_path)
    
    question = state['user_question']

    question_type = classify_question_type(question)

    if question_type == "direct":
        prompt = built_sql_promt(question,df)
        raw_sql = llm_call(prompt)
        sql_query = clean_sql_response(raw_sql)
        result = run_sql_tool(df,sql_query)
        final_answer = generate_final_answer(question, result) if result["success"] else None
        output = {"mode": "direct", "sql_used": sql_query, "table_result": result, "final_answer": final_answer}

    else:
        reasoning_result = multistep_reasoning_tool(question,df)
        output = {"mode": "investigative", **reasoning_result}

    if not is_cleaned and output.get("final_answer"):
        output["final_answer"] = (
            "⚠️ Note: this dataset hasn't been cleaned yet, so this answer may be affected "
            "by missing values, duplicates, or formatting issues.\n\n" + output["final_answer"]
        )

    return {"analyst_output": {"question": question, **output}}


def show_answer_node(state:AgentState):
    output = state['analyst_output']
    verdict = state.get("validator_verdict",{"approved": True})


    display = {
        "question": output["question"],
        "answer": output.get("final_answer"),
        "verified": verdict["approved"],
        "supporting_data": output.get("table_result") or output.get("sub_results"),
        "sql_used": output.get("sql_used")
    }

    return {"display_output":display}
    

# df = load_dataframe("sample_dirty_dataset_cleaned.csv")
# promt = built_sql_promt("How many active users we have in our data?",df)

# raw_sql = llm_call(promt)
# sql_query = clean_sql_response(raw_sql)

# res = run_sql_tool(df,sql_query)
# final = genertate_final_answer("How many active users we have in our data?",res)
# print(raw_sql)
# print("\n -------------------------")
# print(sql_query)
# print("\n -------------------------")
# print(res)
# print("\n -------------------------")
# print(final)
