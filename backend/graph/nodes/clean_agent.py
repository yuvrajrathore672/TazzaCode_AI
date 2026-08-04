import os
import pandas as pd

from langgraph.types import interrupt
from backend.graph.state import AgentState



def load_dataframe(filepath:str) -> pd.DataFrame:
    path = os.path.splitext(filepath)[1].lower()     #split file name in two parts "name",".extension" then we take [1]ext
    if path == ".csv":
        df = pd.read_csv(filepath)
    elif path in ('.xlsx','.xls'):
        df = pd.read_excel(filepath)
    else:
        raise ValueError(f'Unsupported file type : {path}')
    return df


def detect_missing_values(dataframe):
    missing_vlaues = dataframe.isnull().sum()
    issues = []

    for colm , count in missing_vlaues.items():
        if count>0:
            is_numeric = pd.api.types.is_numeric_dtype(dataframe[colm])  #return T/F for colm is numeric or not(py check internaly)
            defualt_action = 'fill_mean' if is_numeric else "drop_rows"
            issues.append({
                "id":f"missing_values_{colm}",
                "issue_type":"missing_values",
                "column":colm,
                "description":f"{colm} has {count} missing values ({round(count/len(dataframe)*100,1)}%)",
                "suggested_action": defualt_action
            })
    return issues



def detect_duplicates(dataframe):
    duplicates = dataframe.duplicated().sum()
    if duplicates==0:
        return []
    return [{
        "id":f"duplicate_rows_None",
        "issue_type":"duplicate_rows",
        "column":None,
        "description":f"Found {duplicates} duplicate rows",
        "suggested_action":"drop_duplicates"
    }]

def detect_invalid_values(df):
    issues = []
    
    for col in df.columns:
        coerced= pd.to_numeric(df[col],errors='coerce')     #error-coerce means it will turn invalid val to Nan (abc-nan)
        if coerced.notna().mean() < 0.5:                    #notna check real values and return T if NaN then F ex-- [1,1,0,1,1] -mean
            continue

        series = coerced.dropna()

        if len(series) == 0:
            continue

        negative_rate = (series<0).mean()            #[f,f,t,f,f] -- mean == [0,0,1,0,0] --- mean
        negative_count = (series<0).sum()
        if negative_count > 0 and (negative_rate <= 0.1 or negative_count <= 2):
            issues.append({
                "id": f"invalid_values_{col}",
                "issue_type": "invalid_values",
                "column": col,
                "description": f"{col} is mostly non-negative, but {(series < 0).sum()} value(s) are negative — likely data entry errors",
                "suggested_action": "absolute_value" if col.lower() in ("age", "salary", "price", "quantity") else "clip_to_zero"
            })

    return issues


def detect_type_mismatches(df):
    issues = []

    for column in df.columns:
        series = df[column].dropna()
        if (pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series)):
            continue

        # Try numeric conversion
        numeric = pd.to_numeric(series, errors="coerce")
        numeric_rate = numeric.notna().mean()              #here internally it uses np so thats why we get np.float

        # Try datetime conversion
        date_time = pd.to_datetime(series, errors="coerce")
        datetime_rate = date_time.notna().mean()

        if numeric_rate >=0.7:
            issues.append({
                "id": f"type_mismatch_{column}",
                "issue_type": "type_mismatch",
                "column":column,
                "description": f"{column} looks numeric but is stored as {series.dtype} ({round(float(numeric_rate)*100,1)}% convertible)",
                "suggested_action": "convert_to_numeric",                
                "confidence": round(float(numeric_rate), 2)
            })

        elif datetime_rate >=0.7:
            issues.append({
                "id": f"type_mismatch_{column}",
                "issue_type": "type_mismatch",
                "column": column,
                "description": f"{column} looks like a date but is stored as {series.dtype} ({round(float(datetime_rate)*100,1)}% convertible)",
                "suggested_action": "convert_to_datetime"
            })

        #float (num_rate) bec langchain/grph serializer doesn't know how to store np data like np.float

    return issues


COMMON_SYNONYMS = {
    "y": "yes", "n": "no",
    "m": "male", "f": "female",
    "true": "yes", "false": "no",
    "1": "yes", "0": "no"
}

def normalize_categorical(series):
    return series.str.strip().str.lower().replace(COMMON_SYNONYMS)

def detect_categorical_inconsistencies(df,max_unique=10):
    issues = []
    categorical = df.select_dtypes(include='object')

    for col in categorical.columns:
        original_unique = df[col].dropna().unique()
        if len(original_unique) > max_unique:
            continue            # skip -- colm - name, id ,etccc

        normalize = normalize_categorical(df[col].dropna())
        normalized_unique = normalize.unique()

        if len(normalized_unique) < len(original_unique):
            issues.append({
                "id": f"categorical_inconsistency_{col}",
                "issue_type": "categorical_inconsistency",
                "column": col,
                "description": f"{col} has inconsistent values {list(original_unique)} that normalize to {list(normalized_unique)}",
                "suggested_action": "normalize"
            })

    return issues



def build_issue_reporter(missing,invalid_values,duplicates,mismatches,normalize):
    issues = []
    issues.extend(missing)
    issues.extend(invalid_values)
    issues.extend(duplicates)
    issues.extend(mismatches)
    issues.extend(normalize)
    return issues



# NODESSSS- --------------------------------------------
def initial_choice_node(state: AgentState):
    response = interrupt({
        "type": "initial_choice",
        "cleaning_issues": state["cleaning_issues"],
        "instruction": "Data is uploaded. Choose: 'clean' (review cleaning issues), "
                        "'skip_to_eda' (skip cleaning, go straight to EDA), or "
                        "'ask_question' (ask about the data now, cleaned or not)."
    })
    return {
        "initial_action": response.get("action", "clean"),
        "user_question": response.get("question")
    }




def clean_agent_node(state:AgentState):
    file_path =  state.get('cleaned_file_path') or state["file_path"]
    df = load_dataframe(file_path)
    missing = detect_missing_values(df)
    duplicates = detect_duplicates(df)
    mismatch = detect_type_mismatches(df)
    invalid_values = detect_invalid_values(df)
    normalize = detect_categorical_inconsistencies(df)

    issues = build_issue_reporter(missing,invalid_values,duplicates,mismatch,normalize)
    df_schema =  {col:str(dtype) for col , dtype in df.dtypes.items()}

    return {
        'cleaning_issues':issues,
        'df_schema': df_schema}



def human_review_node(state:AgentState):
    print(">>> HITL node was called")
    response = interrupt({
        "type":"approval",
        "reason":"Review detected cleaning issues before applying fixes",
        "cleaning_issues": state["cleaning_issues"],
        "instruction" : "Choose how each issue should be fixed."
    })

    return {
        "cleaning_decisions": response.get("decisions", {})}




# APPLY FNXXXX -------------------------------------------------------------------------

def apply_duplicates(df):
    return df.drop_duplicates()

def apply_type_conversion(df,column,action):
    if action== "convert_to_numeric":
        df[column] = pd.to_numeric(df[column],errors='coerce')

    elif action == 'convert_to_datetime':
        df[column] = pd.to_datetime(df[column],errors='coerce')
    return df


def fill_missing_values(df, column, action):
    if action == "fill_mean":
        df[column] = pd.to_numeric(df[column], errors="coerce")
        df[column] = df[column].fillna(df[column].mean())
    elif action == "fill_median":
        df[column] = pd.to_numeric(df[column], errors="coerce")
        df[column] = df[column].fillna(df[column].median())
    elif action == "fill_mode":
        df[column] = df[column].fillna(df[column].mode()[0])
    elif action == "drop_rows":
        df = df.dropna(subset=[column])
    return df

def apply_invalid_values(df,colm,action):
    numeric_col = pd.to_numeric(df[colm], errors="coerce")
    if action == 'drop_rows':
        df =  df[(numeric_col>=0) | numeric_col.isna()]
    elif action == 'set_null':
        df.loc[numeric_col<0,colm] = None
    elif action == 'fill_median':
        valid_median = numeric_col[numeric_col >= 0].median()
        df[colm] = numeric_col.where(numeric_col >= 0, valid_median)
    elif action == 'clip_to_zero':
        df[colm] = numeric_col.clip(lower=0)
    elif action == 'absolute_value':
        df[colm] = numeric_col.abs()
    return df


def apply_categorical_inconsistency(df,colm,action):
    if action == 'normalize':
        df[colm] = normalize_categorical(df[colm])
    return df

#useful when we do 2-3 times cleaning so instead of cleaned_cleaned.csv -- cleaned.csv
def get_cleaned_output_path(file_path):
    base, ext = os.path.splitext(file_path)
    if base.endswith("_cleaned"):
        return f"{base}{ext}"  # already has suffix, just reuse the same name
    return f"{base}_cleaned{ext}"

# APPLY NODEEEEEEEE
def apply_cleaning_node(state:AgentState):
    file_path = state.get("cleaned_file_path") or state["file_path"]
    df = load_dataframe(file_path)

    issues = state['cleaning_issues']
    decisions = state['cleaning_decisions']

    for issue in issues:
        decision = decisions.get(issue['id'],"skip")
        if decision == "skip":
            continue

        if issue['issue_type'] == 'missing_values':
            df = fill_missing_values(df,issue['column'],action=decision)

        elif issue['issue_type'] == 'duplicate_rows':
            df = apply_duplicates(df)

        elif issue['issue_type'] == 'type_mismatch':
            df = apply_type_conversion(df,column=issue['column'],action=decision)

        elif issue['issue_type'] == 'invalid_values':
            df = apply_invalid_values(df,issue['column'],decision)

        elif issue['issue_type'] == "categorical_inconsistency":
            df = apply_categorical_inconsistency(df,issue['column'],action=decision)

    
    
    path = os.path.splitext(file_path)[1].lower()
    if path == '.csv':
        cleaned_path = get_cleaned_output_path(file_path)
        df.to_csv(cleaned_path,index=False)
    elif path == '.xls':
        cleaned_path = get_cleaned_output_path(file_path)
        df.to_excel(cleaned_path,index=False)

    elif path == '.xlsx':
        cleaned_path = get_cleaned_output_path(file_path)
        df.to_excel(cleaned_path,index=False)
    
    return {'cleaned_file_path': cleaned_path,'cleaning_completed':True}
    
