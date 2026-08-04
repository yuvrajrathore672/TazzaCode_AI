from typing import TypedDict


class AgentState(TypedDict):
    session_id            : str 
    file_path             : str 
    cleaned_file_path     : str

    df_schema             : dict           # column names, types
    cleaning_issues       : list           # detected problems
    cleaning_decisions    : dict           # user's HITL choices

    cleaning_completed    : bool
    eda_generated         : bool
    report_generated      : bool

    eda_results           : dict           # stats, correlations, chart paths
    report_sections       : dict
    report_file_path      : str

    chat_history          : list[dict]     # question/answer pairs
    user_question         : str | None

    analyst_output        : dict           # answer + supporting data/query used
    validator_verdict     : dict           # {approved: bool}
    retry_count           : int

    display_output        : dict

    email_content         : dict
    initial_popup_shown   : bool
    action                : str