import subprocess
import time
import shutil
import os
import requests
import json
import logging
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List, Optional

# --- Configuration ---
# Your GitHub Personal Access Token (PAT) - REQUIRED FOR GIT PUSH
# REPLACE THIS PLACEHOLDER WITH YOUR ACTUAL TOKEN
GITHUB_PAT_PLACEHOLDER = "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" 

# Your GitHub username and the name of the repository you created for this project
GITHUB_USERNAME = "Hrishikesh-200" # Replace with your GitHub username
REPO_NAME = "tds-llm-autodeploy-api"
student_secret = "Hris@tds_proj1_term3"
BASE_URL = f"https://github.com/{GITHUB_USERNAME}/{REPO_NAME}"
LOCAL_REPO_PATH = os.path.join(os.getcwd(), REPO_NAME)

# --- Logging Setup ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# Configure a stream handler for console output
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# --- Pydantic Models for API ---
class Attachment(BaseModel):
    name: str
    url: str

class IncomingTask(BaseModel):
    email: str
    task: str
    round: int
    nonce: str
    brief: str
    checks: List[str]
    evaluation_url: str
    attachments: Optional[List[Attachment]] = []
    student_secret: str  # Student secret for authentication/evaluation
    # signature field is included in the project spec but omitted here for simplicity
    # signature: str

class TaskStatus(BaseModel):
    status: str
    message: str
    uuid: str

class EvaluationPayload(BaseModel):
    email: str
    task: str
    round: int
    nonce: str
    repo_url: str
    commit_sha: str
    pages_url: str
    student_secret: str # Student secret for the final payload

app = FastAPI()

# --- Helper Functions ---

def run_git_command(command: List[str], cwd: str) -> str:
    """Executes a git command and returns its stdout or raises an error on failure."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8'
        )
        # Log command output for successful pushes/commits
        if "push" in command or "commit" in command:
            logger.info(f"Git command succeeded. STDOUT: {result.stdout.strip()}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        # Log detailed error information from Git
        error_message = f"Git command failed: {' '.join(command)}\nSTDERR: {e.stderr.strip()}\nSTDOUT: {e.stdout.strip()}"
        logger.critical(error_message)
        raise RuntimeError(f"Git command failed: {e.stderr.strip()}")
    except FileNotFoundError:
        logger.critical("Git command not found. Ensure Git is installed and in your PATH.")
        raise

def safe_rmtree(path: str, max_attempts=5, delay=0.5):
    """Safely removes a directory, handling Windows file locks."""
    if not os.path.exists(path):
        return

    for attempt in range(max_attempts):
        try:
            # On Windows, try to make files writable first if deletion fails
            if os.name == 'nt':
                 for root, dirs, files in os.walk(path, topdown=False):
                    for name in files:
                        filepath = os.path.join(root, name)
                        os.chmod(filepath, 0o777) # Change permissions to read/write/execute

            shutil.rmtree(path)
            logger.info(f"Successfully cleaned up directory: {path}")
            return
        except OSError as e:
            # WinError 5 is Access Denied, a common Windows lock issue
            if "WinError 5" in str(e) or "Access is denied" in str(e):
                logger.warning(f"Cleanup attempt {attempt + 1} failed for {path} (WinError 5 likely). Retrying in {delay}s: {e}")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                logger.critical(f"Failed to remove directory due to unhandled error: {e}")
                raise

    logger.critical(f"Failed to remove directory after {max_attempts} retries: {path}")
    raise RuntimeError(f"Could not clean up directory: {path}")


# --- Core Task Processing ---

def process_task(request: IncomingTask):
    """Handles the full task pipeline: generate, clone, write, commit, push, notify."""
    from app_generator import call_llm_api, mock_signature_verification # Dynamic import

    logger.info(f"Starting task: {request.task}, Round: {request.round}")
    logger.info(f"Received Student Secret: {request.student_secret[:4]}...")

    pat = GITHUB_PAT_PLACEHOLDER
    # Check if the PAT has been replaced
    if pat == "github_pat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx":
        logger.critical("GITHUB_PAT_PLACEHOLDER is not set. Cannot run git commands.")
        return # Exit the background task

    # 1. Cleanup before clone (essential for Windows)
    try:
        # Aggressive cleanup at the start
        safe_rmtree(LOCAL_REPO_PATH)
    except Exception as e:
        logger.error(f"Failed during cleanup: {e}")
        return # Exit the background task

    # 2. Mock Signature Verification (as per project spec)
    # The actual implementation would involve a public key and hashing
    if not mock_signature_verification(request):
        logger.error(f"Signature verification failed for task {request.task}")
        # In a real app, this would raise an HTTP 401/403
        return

    # 3. Clone Repository
    # Note: We don't put the PAT here directly for cloning to let git credential helper work, 
    # but we explicitly set the remote later for the push command.
    CLONE_URL_NO_AUTH = BASE_URL # Use the simple HTTPS URL for cloning
    try:
        logger.info(f"Cloning '{REPO_NAME}' from {CLONE_URL_NO_AUTH}...")
        run_git_command(["git", "clone", CLONE_URL_NO_AUTH, LOCAL_REPO_PATH], cwd=os.getcwd())
    except Exception as e:
        logger.error(f"Failed during initial clone. Ensure the repo exists and is accessible: {e}")
        return

    # 4. Generate App Content
    try:
        generated_files = call_llm_api(request.brief, request.round, request.attachments)
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        return

    # 5. Write Files and Get Commit SHA
    try:
        logger.info(f"Writing {len(generated_files)} files to local repository...")
        for file in generated_files:
            filepath = os.path.join(LOCAL_REPO_PATH, file['path'])
            # Ensure subdirectory exists for the file
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding='utf-8') as f:
                f.write(file['content'])
        
        # 6. Git Commit
        run_git_command(["git", "add", "."], cwd=LOCAL_REPO_PATH)
        commit_message = f"Round {request.round}: {request.task} - {request.brief[:50]}..."
        run_git_command(["git", "commit", "-m", commit_message], cwd=LOCAL_REPO_PATH)

        # Get the new commit SHA
        commit_sha = run_git_command(["git", "rev-parse", "HEAD"], cwd=LOCAL_REPO_PATH)
        logger.info(f"New commit SHA: {commit_sha}")

        # 7. Git Push (Using the token in the remote URL for robustness)
        # We explicitly set the remote URL with the token before pushing
        AUTHENTICATED_REMOTE_URL = f"https://{pat}@{BASE_URL.replace('https://', '')}.git"
        
        # Configure the remote URL to include the PAT for authentication
        run_git_command(["git", "remote", "set-url", "origin", AUTHENTICATED_REMOTE_URL], cwd=LOCAL_REPO_PATH)
        
        # Force push to main branch
        run_git_command(["git", "push", "origin", "main"], cwd=LOCAL_REPO_PATH)
        
        # Restore the remote URL to the clean version after push
        run_git_command(["git", "remote", "set-url", "origin", BASE_URL], cwd=LOCAL_REPO_PATH)
        
    except Exception as e:
        logger.error(f"Git or File operation failed: {e}")
        return
        
    # 8. Notify Evaluator
    payload = EvaluationPayload(
        email=request.email,
        task=request.task,
        round=request.round,
        nonce=request.nonce,
        repo_url=BASE_URL,
        commit_sha=commit_sha,
        pages_url=f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}/",
        student_secret=request.student_secret
    )

    try:
        logger.info(f"Notifying evaluator at: {request.evaluation_url}")
        # Implement exponential backoff for real submission
        max_retries = 3
        delay = 1
        response = None

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    request.evaluation_url,
                    json=payload.model_dump(),
                    headers={"Content-Type": "application/json"},
                    timeout=10 # Increased timeout for network operation
                )
                if response.status_code == 200:
                    logger.info(f"Evaluator notified successfully. Status: {response.status_code}")
                    break
                else:
                    logger.warning(f"Evaluator notification failed (Attempt {attempt + 1}). Status: {response.status_code}, Response: {response.text}")

            except requests.RequestException as e:
                logger.warning(f"Failed to connect to evaluator URL (Attempt {attempt + 1}): {e}")

            if attempt < max_retries - 1:
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2 # Exponential backoff

        if response is None or response.status_code != 200:
             logger.critical(f"Final submission to evaluator failed after {max_retries} attempts.")


    except Exception as e:
        logger.error(f"An unexpected error occurred during evaluation submission: {e}")

    finally:
        # 10. Final Cleanup
        try:
            safe_rmtree(LOCAL_REPO_PATH)
        except Exception as e:
            logger.critical(f"Final cleanup failed: {e}. Directory may be locked.")


# --- API Endpoints ---

@app.post("/api-endpoint", response_model=TaskStatus, status_code=202)
async def handle_task_request(request: IncomingTask, background_tasks: BackgroundTasks):
    """Receives the LLM deployment task and starts processing in the background."""
    
    # Use a fixed UUID for assignment simplicity
    task_uuid = "d01ceb1f-8ea3-4a04-a8aa-673aaf52eb4c"
    
    # Run the heavy-lifting task processing in a background thread
    background_tasks.add_task(process_task, request)
    
    # Immediate response to the client
    return TaskStatus(
        status="accepted",
        message=f"Task '{request.task}', Round {request.round} accepted and processing started in background.",
        uuid=task_uuid
    )

# Mock endpoint for the background task to call (your local endpoint)
@app.post("/eval")
async def mock_eval_endpoint(payload: EvaluationPayload):
    """Mocks the evaluation API endpoint."""
    logger.info(f"Received Evaluation Payload for {payload.task}, Round {payload.round}")
    logger.info(f"Repo URL: {payload.repo_url}, Commit: {payload.commit_sha}")
    logger.info(f"Student Secret in Payload: {payload.student_secret[:4]}...")
    return {"status": "ok", "message": "Evaluation request recorded."}

@app.on_event("startup")
async def startup_event():
    logger.info("Application starting up...")
    pat = GITHUB_PAT_PLACEHOLDER
    if pat == "github_pat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx":
         logger.critical("!!! WARNING: GITHUB_PAT IS NOT SET. GIT COMMANDS WILL FAIL !!!")
    if GITHUB_USERNAME == "YourGitHubUsername":
         logger.critical("!!! WARNING: GITHUB_USERNAME IS NOT SET. REPO URLS WILL BE INCORRECT !!!")

    # Clean up any leftover folder from a previous crash
    try:
        safe_rmtree(LOCAL_REPO_PATH)
    except Exception as e:
        logger.error(f"Startup cleanup failed: {e}")
