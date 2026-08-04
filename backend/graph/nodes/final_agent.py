from graph.state import AgentState


def build_email_content(state: AgentState):
    attachments = [state["report_file_path"]] if state.get("report_file_path") else []
    if state.get("cleaned_file_path"):
        attachments.append(state["cleaned_file_path"])
    elif state.get("file_path"):
        attachments.append(state["file_path"])  # raw file if cleaning was skipped

    subject = "Your TazzaCode AI Data Report"
    body = f"""Hello,

            Attached: {'your cleaned dataset and ' if state.get('cleaned_file_path') else ''}your EDA report.

            Thanks for using TazzaCode AI.
            """
    
    return {"subject": subject, "body": body, "attachments": attachments}



def final_agent_node(state:AgentState):
    email_content = build_email_content(state)
    return {"email_content":email_content}
