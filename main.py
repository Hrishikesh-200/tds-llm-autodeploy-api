import os
import shutil
import subprocess
import json
import logging
import requests
import base64
import threading
import time 
from typing import Dict, Any, List, Optional

# --- Import the real LLM generation function ---
from app_generator import call_llm_api 
# ---------------------------------------------------

# FastAPI and Pydantic Imports
from fastapi import FastAPI, BackgroundTasks, Response, status, HTTPException
from pydantic import BaseModel, Field

# --- Configuration & Setup ---

# Set your GitHub details here
GITHUB_USERNAME = "Hrishikesh-200"
REPO_NAME = "tds-llm-autodeploy-api" # The central repository name

# Path is relative to where the server (main.py) is executed
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configure logging for the worker process
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Pydantic Data Models (Based on your cURL payload) ---
class TaskRequest(BaseModel):
    """Defines the structure of the incoming API request payload."""
    email: str
    secret: str = Field(..., description="The shared secret key for authentication.")
    task: str
    round: int = 1
    nonce: str
    brief: str = Field(..., description="The prompt for the LLM.")
    checks: List[str]
    evaluation_url: str = Field(..., description="URL to notify after processing.")
    attachments: List[Dict[str, str]] = []

class TaskResponse(BaseModel):
    """Defines the structure of the successful API response."""
    status: str
    message: str
    uuid: str # Assuming a unique task ID is generated

# --- Core Processing Logic (Run in Background) ---

# Helper Functions 

def run_git_command(command: List[str], path: str, pat: str) -> str:
    """Runs a Git command, capturing output and providing better error context."""
    logger.debug(f"Executing Git command in {path}: {' '.join(command)}")
    
    try:
        # Use a longer timeout for potential slow remote operations
        result = subprocess.run(
            command, 
            cwd=path, 
            check=True,  # Raises exception on non-zero exit code
            capture_output=True, 
            text=True,
            timeout=120 
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        error_message = f"Git command failed. STDOUT: {e.stdout} STDERR: {e.stderr}"
        logger.critical(error_message)
        raise Exception(error_message)


def cleanup(path: str):
    """Safely removes the local repository folder, retrying for Windows file locks."""
    if os.path.exists(path):
        max_retries = 3
        wait_time = 0.5
        for i in range(max_retries):
            try:
                shutil.rmtree(path)
                logger.info(f"Successfully cleaned up directory: {path}")
                return
            except Exception as e:
                if i < max_retries - 1:
                    logger.warning(f"Cleanup attempt {i+1} failed for {path} (WinError 5 likely). Retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    logger.critical(f"Failed to remove directory after {max_retries} retries: {e}")
                    raise e # Re-raise the exception after exhausting retries
            
def notify_evaluator(eval_url: str, response_payload: Dict[str, Any]) -> bool:
    """Sends the final result JSON to the instructor's evaluation URL."""
    logger.info(f"Notifying evaluator at: {eval_url}")
    try:
        response = requests.post(eval_url, json=response_payload, timeout=30)
        response.raise_for_status() 
        logger.info(f"Evaluator notified successfully. Status: {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to notify evaluation URL {eval_url}: {e}")
        return False


# Main Logic
def process_task(task_params: Dict[str, Any], pat: str):
    """
    Manages the full LLM code generation and Git deployment lifecycle.
    """
    
    # 0. Initial Setup & Validation
    task_name = task_params.get("task")
    round_num = task_params.get("round", 1)
    
    local_repo_path = os.path.join(BASE_DIR, REPO_NAME) 
    
    logger.info(f"Starting task: {task_name}, Round: {round_num}")
    
    # URL Construction (Corrected to avoid double 'https://')
    repo_url_host_path = f"github.com/{GITHUB_USERNAME}/{REPO_NAME}"
    authenticated_repo_url = f"https://{pat}@{repo_url_host_path}.git" 
    repo_url_base = f"https://{repo_url_host_path}" 
    
    # Define a default failure response structure
    failure_response = {
        "email": task_params["email"],
        "task": task_params["task"],
        "round": task_params["round"],
        "nonce": task_params["nonce"],
        "repo_url": repo_url_base,
        "commit_sha": "ERROR",
        "pages_url": f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}/",
    }
    
    # --- 1. Cleanup & Clone ---
    try:
        cleanup(local_repo_path)
        logger.info(f"Cloning '{REPO_NAME}'...")
        run_git_command(["git", "clone", authenticated_repo_url, local_repo_path], BASE_DIR, pat)
    except Exception as e:
        logger.error(f"Failed during initial clone: {e}")
        failure_response["commit_sha"] = "GIT_CLONE_FAILED"
        notify_evaluator(task_params["evaluation_url"], failure_response)
        return

    # --- 2. LLM Generation and File Content Preparation ---
    try:
        # 🟢 CALLING THE REAL LLM LOGIC FROM app_generator.py
        llm_output = call_llm_api(
            task_params["brief"], 
            task_params["attachments"], 
            task_name
        )
        main_file_name = llm_output["filename"]
    except Exception as e:
        logger.error(f"LLM/File preparation failed: {e}")
        cleanup(local_repo_path)
        failure_response["commit_sha"] = "LLM_GEN_FAILED"
        notify_evaluator(task_params["evaluation_url"], failure_response)
        return

    # --- 3. Branching (Multi-Round Logic) ---
    target_branch = "main" if round_num == 1 else f"round-{round_num}"
    try:
        # FIX: Handle branch switching vs. branch creation
        if round_num == 1:
            # Switch to the existing 'main' branch (Round 1)
            run_git_command(["git", "checkout", "main"], local_repo_path, pat)
        else:
            # Create and switch to a new branch (Subsequent Rounds)
            run_git_command(["git", "checkout", "-b", target_branch], local_repo_path, pat)

        # Configure identity (needed before commit)
        run_git_command(["git", "config", "user.name", GITHUB_USERNAME], local_repo_path, pat)
        run_git_command(["git", "config", "user.email", task_params.get("email")], local_repo_path, pat)

    except Exception as e:
        logger.error(f"Branching/Config failed: {e}")
        cleanup(local_repo_path)
        failure_response["commit_sha"] = "GIT_BRANCH_FAILED"
        notify_evaluator(task_params["evaluation_url"], failure_response)
        return


    # --- 4. Write Files (The Generalized I/O) ---
    try:
        # Write the main LLM output file
        with open(os.path.join(local_repo_path, main_file_name), "w") as f:
            f.write(llm_output["code_content"]) 

        # Write/Overwrite boilerplate files
        with open(os.path.join(local_repo_path, "README.md"), "w") as f:
            f.write(llm_output["readme_content"]) 
        with open(os.path.join(local_repo_path, "LICENSE"), "w") as f:
            f.write(llm_output.get("license_content", "MIT License...")) 

        # Attachment Handling (Decoding data URIs)
        for attachment in task_params.get("attachments", []):
            if attachment["url"].startswith("data:"):
                try:
                    base64_data = attachment["url"].split(',')[1] 
                    binary_data = base64.b64decode(base64_data)
                    attachment_path = os.path.join(local_repo_path, attachment["name"])
                    with open(attachment_path, "wb") as f:
                        f.write(binary_data)
                    logger.info(f"Saved attachment: {attachment['name']}")
                except Exception as e:
                    logger.error(f"Failed to decode/save attachment {attachment['name']}: {e}")

    except Exception as e:
        logger.error(f"File writing failed: {e}")
        cleanup(local_repo_path)
        failure_response["commit_sha"] = "FILE_WRITE_FAILED"
        notify_evaluator(task_params["evaluation_url"], failure_response)
        return

    # --- 5. Commit and Push ---
    try:
        run_git_command(["git", "add", "."], local_repo_path, pat)
        run_git_command(["git", "commit", "-m", f"Submission for Round {round_num} - {task_name}"], local_repo_path, pat)
        
        # Push to the remote target branch
        run_git_command(["git", "push", "-f", "origin", target_branch], local_repo_path, pat)
        
        # Get the final commit SHA for the notification payload
        commit_sha = run_git_command(["git", "rev-parse", "HEAD"], local_repo_path, pat).strip()
        
    except Exception as e:
        logger.error(f"Deployment Push failed: {e}")
        cleanup(local_repo_path)
        failure_response["commit_sha"] = "GIT_PUSH_FAILED"
        notify_evaluator(task_params["evaluation_url"], failure_response)
        return
        
    # --- 6. Final Notification and Cleanup ---
    success_payload = {
        "email": task_params["email"],
        "task": task_params["task"],
        "round": task_params["round"],
        "nonce": task_params["nonce"],
        "repo_url": repo_url_base,
        "commit_sha": commit_sha,
        "pages_url": f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}/",
    }
    
    notify_evaluator(task_params["evaluation_url"], success_payload)
    cleanup(local_repo_path)
    logger.info(f"Task {task_name}, Round {round_num} successfully processed and deployed.")


# --- FastAPI Application ---

app = FastAPI(title="LLM Autodeploy Task Processor", version="1.0")
# ⚠️ REMEMBER TO REPLACE THIS WITH YOUR ACTUAL PAT
GITHUB_PAT_PLACEHOLDER = "YOUR_SECURE_GITHUB_PAT_HERE" 

@app.post("/api-endpoint", response_model=TaskResponse, status_code=202)
async def api_endpoint(request: TaskRequest, background_tasks: BackgroundTasks):
    
    expected_secret = "Hris@tds_proj1_term3"
    if request.secret != expected_secret:
        raise HTTPException(status_code=401, detail="Invalid secret key provided.")

    pat = GITHUB_PAT_PLACEHOLDER
    if pat == "YOUR_SECURE_GITHUB_PAT_HERE":
        logger.critical("GITHUB_PAT_PLACEHOLDER is not set. Cannot run git commands.")
        raise HTTPException(status_code=500, detail="Server misconfigured: GITHUB_PAT not set.")

    # We use a separate thread to process the task and prevent blocking the API request
    task_thread = threading.Thread(target=process_task, args=(request.model_dump(), pat))
    task_thread.start()
    
    return {
        "status": "accepted",
        "message": f"Task '{request.task}', Round {request.round} accepted and processing started in background.",
        "uuid": "d01ceb1f-8ea3-4a04-a8aa-673aaf52eb4c"
    }

@app.post("/eval")
def handle_evaluation(response: Response):
    """Placeholder endpoint to prevent 404 errors during evaluation notification."""
    response.status_code = status.HTTP_200_OK
    return {"status": "ok", "message": "Evaluation notification received locally."}

@app.get("/")
def read_root():
    return {"status": "ok", "message": "LLM Autodeploy API is running."}
