import pandas as pd 
import os
import seaborn as sns
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from backend.graph.state import AgentState
from backend.graph.nodes.clean_agent import load_dataframe
import math

def compute_summary_stats(df):
    stats = df.describe()
    stats_dict = stats.to_dict()
    return stats_dict    #these return values as np.float

def compute_correlation(df):
    numeric = df.select_dtypes(include="number")
    if len(numeric.columns) >= 2:
        return numeric.corr().to_dict()
    return {}            # return values as np.float

def compute_value_counts(df,top_n =5):  #only 5 bec of colms like names
    categorical_colm = df.select_dtypes(include="object")
    value_counts = {}

    for column in categorical_colm.columns:
        counts = df[column].value_counts().head(top_n)
        value_counts[column] = counts.to_dict()

    return value_counts

def generate_charts(df,output_dir):
    os.makedirs(output_dir,exist_ok=True)
    chart_path = []

    numeric = df.select_dtypes(include="number")
    categorical_colm = df.select_dtypes(include="object")

    # histogram for numeric colms 
    n = len(numeric.columns)
    cols = 3 
    rows = math.ceil(n/cols)
    plt.figure(figsize=(5*cols,4*rows))

    for i , col in enumerate(numeric.columns,start=1):
        plt.subplot(rows,cols,i)
        df[col].dropna().hist(bins=20)
        plt.title(f"Distribution of {col}")
        plt.xlabel(col)
        plt.ylabel('Frequency')

    plt.tight_layout()
    path = os.path.join(output_dir,f"{col}_distribution.png")
    plt.savefig(path,bbox_inches="tight")
    plt.close()                                  #prevents memory leak matters once we're generating many charts across many user sessions.
    chart_path.append(path)

    # Correlation heatmap(only if 2+ numeric col)
    if n>=2:
        plt.figure(figsize=(6,5))
        corr = numeric.corr()
        sns.heatmap(corr,annot=True,cmap="coolwarm")
        plt.title("Correaltion Heatmap")
        path = os.path.join(output_dir,"correalation_heatmap.png")
        plt.savefig(path, bbox_inches="tight")
        plt.close()
        chart_path.append(path)

    # Bar charts for top categorical columns (cap at first 3)
    for col in categorical_colm.columns[:3]:
        plt.figure(figsize=(6,5))
        df[col].value_counts().head(5).plot(kind='bar')
        plt.title(f'Top Values in {col}')
        plt.xlabel(col)
        plt.ylabel('Count')

        path = os.path.join(output_dir,f"{col}_top_values.png")
        plt.savefig(path,bbox_inches='tight')
        plt.close()
        chart_path.append(path)

    return chart_path

def build_eda_report(stats,corr,value_counts,chart_paths):
    return {
        "summary_stats":stats,
        "correlations":corr,
        "value_counts":value_counts,
        "chart_paths":chart_paths
    }



# ----------------

def eda_agent_node(state:AgentState):
    file_path = state.get("cleaned_file_path") or state["file_path"]
    df = load_dataframe(file_path)

    stats = compute_summary_stats(df)
    corr = compute_correlation(df)
    value_counts = compute_value_counts(df)

    op_dir = os.path.join(os.path.dirname(file_path),"charts")
    chart_path = generate_charts(df,op_dir)

    eda_result = build_eda_report(stats,corr,value_counts,chart_path)

    return {'eda_results':eda_result,"eda_generated":True}



