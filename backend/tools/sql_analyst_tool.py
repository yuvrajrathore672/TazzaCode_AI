import duckdb
import json
import numpy as np

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

# we can use @tool but they dont automatically have access of our df

def run_sql_tool(df,sql_query):
    try:
        result = duckdb.query(sql_query).to_df()      #converting duckdb result to pd.DF   
        result = result.replace([np.nan, np.inf, -np.inf], None)    #NaN isn't valid JSON,it's a np-specific float value, not something the JSON spec recognizes. # query may return nan (ex-groupby and pd represent that as nan)
        return {
            "success":True,
            "result":result.to_dict(orient='records'),    #turn result to list of dict
            "row_count":len(result)
        }
    except Exception as e:
        return {
            "success":False,
            "error":str(e)
        }
# LLMs wraps code in ```sql fences 



def build_schema_context(df,max_samples=5):
    lines = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        if dtype == "object" or df[col].nunique()<=10:
            samples = df[col].dropna().unique()[:max_samples].tolist()
            lines.append(f"{col}({dtype}) - example values : {samples}")
        else:
            lines.append(f"{col} ({dtype})")
    return "\n".join(lines)

#this is for colms like -- yes,no but our sql can't see whole data so we are giving some samples for these type of colms so that when llm generate sql_query it can see and dont make mistake



# user ques to sql_query using LLM
def built_sql_promt(question,df):
    schema_context = build_schema_context(df)
    return f"""You are a data analyst. Given this table schema, write a single SQL query
        to answer the user's question. The table is named 'df'. Only return the raw SQL query,
        nothing else — no explanation, no markdown formatting.

        Schema: {schema_context}

        Question: {question}
        """




#  we have to need to strip markdown fences bec , they can break duckdb.query() if passed in directly 
def clean_sql_response(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").replace("sql", "", 1).strip()
    return text


# --------------------------------------------------------------------------------------------------------------
def plan_sub_questions(ques,df):
    schema_context = build_schema_context(df)
    prompt = f"""A user asked: "{ques}"
                This requires investigation, not a single lookup. Given this schema, propose 2-4 SQL
                queries that would help answer it. Return ONLY a JSON list of objects like:
                [{{"purpose": "check by region", "sql": "SELECT ..."}}]
                Table is named 'df'. No markdown, just raw JSON.

                Schema:
                {schema_context}
                """

    raw = llm_call(prompt)
    return json.loads(clean_sql_response(raw))


def multistep_reasoning_tool(ques,df):
    sub_queries = plan_sub_questions(ques,df)

    sub_results = []
    for sq in sub_queries:
        result = run_sql_tool(df,sql_query=sq['sql'])
        sub_results.append({
            "purpose":sq['purpose'],
            "sql":sq['sql'] ,
            "result":result})

    synthesis_prompt = f"""Question: {ques}
                            Here are results from several sub-investigations:
                            {sub_results}
                            Write a formal analytical answer (3-5 sentences) synthesizing these findings.
                            Only reference numbers actually present above.
                            """
    final_answer = llm_call(synthesis_prompt)
    
    return {
        "sub_results":sub_results,
        "final_answer":final_answer
    }

