from fastapi import FastAPI, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from langgraph.types import Command
import uuid, os
from graph.graph_builder import workflow
from tools.email_tool import send_email

app = FastAPI(title="TazzaCode AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"]
)


def get_pending_interrupt(config):
    snapshot = workflow.get_state(config)
    if snapshot.tasks:
        for task in snapshot.tasks:
            if task.interrupts:
                return [i.value for i in task.interrupts]
    return None


@app.post("/upload")
def upload_file(file: UploadFile):
    session_id = str(uuid.uuid4())
    os.makedirs(f"uploads/{session_id}", exist_ok=True)
    ext = os.path.splitext(file.filename)[1].lower()

    if ext not in (".csv", ".xlsx", ".xls"):
        return {"error": f"Unsupported file type: {ext}"}

    file_path = f'uploads/{session_id}/original{ext}'
    with open(file_path, "wb") as f:
        f.write(file.file.read())

    config = {'configurable': {'thread_id': session_id}}
    # workflow.invoke({'file_path': file_path}, config=config)

    workflow.invoke({"action": "init","session_id": session_id,"file_path": file_path,"initial_popup_shown": False},config=config)

    interrupt_data = get_pending_interrupt(config)

    return {"session_id": session_id, "interrupt": interrupt_data,'popup':True}


@app.post("/chat/{session_id}")
def chat(session_id:str,payload:dict):
    config = {'configurable': {'thread_id': session_id}}
    result = workflow.invoke({"action": "question","user_question": payload["question"]},config=config)
    return result


@app.post("/clean/{session_id}")
def clean_dataset(session_id: str):
    config = {'configurable': {'thread_id': session_id}}
    workflow.invoke({'action':'clean'},config=config)

    return {"interrupt": get_pending_interrupt(config)}



# @app.post("/resume/{session_id}")
# def resume(session_id: str, payload: dict):              #payload be like -- decisions,axn,procdeed_to_eda etc
#     config = {"configurable": {"thread_id": session_id}}
#     result = workflow.invoke(Command(resume=payload), config=config)

#     interrupt_data = get_pending_interrupt(config)

#     return {'interrupt': interrupt_data, "state": result}    

@app.post("/clean/review/{session_id}")
def clean_review(session_id: str, payload: dict):
    config = {'configurable': {'thread_id': session_id}}
    result = workflow.invoke(Command(resume=payload),config=config)
    interrupt_data = get_pending_interrupt(config)
    return {'interrupt': interrupt_data, "state": result}  
  

@app.post("/generate-report/{session_id}")
def generate_report(session_id: str):
    config = {"configurable": {"thread_id": session_id}}
    result = workflow.invoke({"action": "report"},config=config)

    return result




@app.get("/download/{session_id}/{file_type}")
def download_file(session_id:str,file_type:str):
    config = {'configurable':{'thread_id':session_id}}
    state = workflow.get_state(config).values

    if file_type == 'cleaned':
        path = state.get("cleaned_file_path")
    elif file_type == "report":
        path = state.get("report_file_path")
    else:
        return {"error": "Invalid file_type, use 'cleaned' or 'report'"}

    if not path or not os.path.exists(path):
        return {"error": "File not found or not ready yet"}

    return FileResponse(path,filename=os.path.basename(path))


@app.post('/email/{session_id}')
def email_report(session_id:str,payload:dict):
    config = {'configurable':{'thread_id':session_id}}
    # state = workflow.get_state(config).values
    result = workflow.invoke({"action": "email"}, config=config)
    email_content = result.get('email_content')
    if not email_content:
        return {'error':"Report not ready yet"}

    recipient = payload.get('email_id')
    result = send_email(email_content,recipient)
    return result