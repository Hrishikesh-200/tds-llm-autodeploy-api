from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import threading
from typing import List, Optional, Dict, Any

# Import the core task processing engine
from app_generator import process_task

# --- FastAPI App Initialization ---
app = FastAPI()

# --- Pydantic Schema for Incoming Request ---
# Represents the detailed JSON payload received from the instructor.
class Attachment(BaseModel):
    name: str
    url: str

class TaskRequest(BaseModel):
    email: str
    secret: str
    task: str
    round: int
    nonce: str
    brief: str
    checks: List[str]
    evaluation_url: str
    attachments: List[Attachment]

# --- Environment Configuration ---
# NOTE: The GITHUB_PAT is set by the environment (locally or on Hugging Face)
# We read it once when the app starts.
GITHUB_PAT = os.environ.get("GITHUB_PAT")
EXPECTED_SECRET = "Hris@tds_proj1_term3" # The secret required for verification

# --- Endpoint ---
@app.post("/api-endpoint")
def api_endpoint(request: TaskRequest):
    """
    Receives the task request, verifies the secret, and starts background processing.
    """
    # 1. Verification of Secret
    if request.secret != EXPECTED_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret provided.")

    # Check for PAT (CRITICAL for deployment)
    if not GITHUB_PAT:
        raise HTTPException(status_code=500, detail="Server misconfigured: GITHUB_PAT not set.")

    # 2. Start Task Processing in a Background Thread
    # The full process (LLM, Git, Push, Notification) runs here, 
    # allowing the endpoint to return immediately.
    task_args = request.model_dump() # Convert Pydantic model to dictionary
    
    # We pass the task parameters and the PAT to the worker function
    thread = threading.Thread(target=process_task, args=(task_args, GITHUB_PAT))
    thread.start()

    # 3. Send Immediate 200 OK Response
    # This is the required behavior: accept the request instantly.
    return {
        "status": "accepted",
        "message": f"Task '{request.task}', Round {request.round} accepted and processing started in background."
    }

# Health check endpoint
@app.get("/")
def read_root():
    return {"status": "ok", "service": "LLM Task Processor"}