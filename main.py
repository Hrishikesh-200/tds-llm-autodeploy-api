import os
import shutil
import subprocess
import threading
import time
from typing import List, Dict, Any, Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
import logging

# Load environment variables from .env file
load_dotenv()

# --- Configuration & Constants ---
# --- IMPORTANT: Configure these using your .env file ---
PAT = os.getenv('GITHUB_PAT')
USERNAME = os.getenv('GITHUB_USERNAME')
REPO_NAME = os.getenv('REPO_NAME') or "tds-llm-autodeploy-api"

# Basic validation and fallback
if not USERNAME or not PAT:
    # Use placeholder for safety if running outside of a properly configured environment
    USERNAME = os.getenv('GITHUB_USERNAME') or "YourGitHubUsername"
    PAT = os.getenv('GITHUB_PAT') or "github_pat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    logging.critical("!!! WARNING: GITHUB_USERNAME or GITHUB_PAT is not fully set. Git commands might fail. Check your .env file. !!!")

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants based on configuration
BASE_URL = f"https://github.com/{USERNAME}/{REPO_NAME}"
REPO_URL = f"https://github.com/{USERNAME}/{REPO_NAME}"
PAGES_URL = f"https://{USERNAME}.github.io/{REPO_NAME}/"
LOCAL_REPO_PATH = REPO_NAME

# Import the generator module (it must be in the same directory)
try:
    from app_generator import call_llm_api, LLM_FILE_GENERATOR_SUCCESS_KEY
except ImportError:
    logger.error("Could not import app_generator.py. Make sure it is in the same directory.")
    # Define a mock to prevent immediate crash if the file is missing
    def call_llm_api(brief: str, round_num: int, existing_files: Dict[str, str], attachments: List[Dict[str, str]]) -> Dict[str, Any]:
        return {LLM_FILE_GENERATOR_SUCCESS_KEY: False, 'error': 'app_generator.py missing'}
    LLM_FILE_GENERATOR_SUCCESS_KEY = "success" # Mock key

# --- FastAPI App Setup ---
app = FastAPI(title="LLM Autodeploy API")

# Add CORS middleware for local testing flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Models ---

# Incoming payload from the evaluator
class IncomingTask(BaseModel):
    email: str
    task: str
    round: int
    nonce: str
    brief: str
    checks: List[str]
    evaluation_url: str
    attachments: List[Dict[str, str]]
    student_secret: str  # Added as per project spec


# Outgoing payload to the evaluation URL
class EvaluationPayload(BaseModel):
    email: str
    task: str
    round: int
    nonce: str
    repo_url: str
    commit_sha: str
    pages_url: str
    student_secret: str


# --- Utility Functions ---

def safe_rmtree(path: str):
    """Safely remove a directory, handling potential file lock issues."""
    if os.path.exists(path):
        logger.info(f"Cleaning up local repository folder: {path}")
        # On Windows, rmtree can fail due to file locks. Retry with a small delay.
        for _ in range(5):
            try:
                shutil.rmtree(path)
                return
            except Exception as e:
                logger.warning(f"Failed to remove {path}: {e}. Retrying in 1 second.")
                time.sleep(1)
        logger.error(f"Failed to remove repository directory {path} after multiple retries.")


def run_git_command(command: List[str], cwd: str) -> Optional[str]:
    """Execute a git command and return the output or log the error."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Git command failed: {' '.join(command)}")
        logger.error(f"Error output: {e.stderr.strip()}")
        return None
    except FileNotFoundError:
        logger.error("Git command not found. Ensure Git is installed and in your PATH.")
        return None


def get_existing_files(path: str) -> Dict[str, str]:
    """Reads all existing files in the repo path (for Round 2 revision)."""
    if not os.path.isdir(path):
        return {}
    
    existing_files = {}
    
    # Simple recursive walker to find all relevant files, ignoring .git and logs
    for root, _, files in os.walk(path):
        if '.git' in root or 'logs' in root:
            continue
            
        for file_name in files:
            # Construct the relative path
            relative_path = os.path.relpath(os.path.join(root, file_name), path)
            
            # Skip files that should not be edited or read by the LLM
            if relative_path in ['.env', 'main.py', 'app_generator.py', 'requirements.txt', 'LICENSE', 'README.md', 'main.yml']:
                continue
                
            try:
                with open(os.path.join(root, file_name), 'r', encoding='utf-8') as f:
                    existing_files[relative_path] = f.read()
            except Exception as e:
                logger.warning(f"Could not read file {relative_path} for LLM context: {e}")
                
    return existing_files


# --- Core Task Processing Logic ---

def process_task(request: IncomingTask):
    """Handles the main logic flow: LLM call, Git deployment, and evaluation ping."""
    
    logger.info(f"Starting task {request.task}, Round {request.round} for {request.email}")
    logger.info(f"Student Secret Received: {request.student_secret[:4]}...") # Log first few chars for confirmation

    # --- 1. LLM Generation Phase ---
    try:
        # For Round 2, we need the existing code for the LLM to revise
        existing_files = {}
        if request.round == 2:
            # Clone is done first to get the existing files
            if not run_git_command(["git", "clone", BASE_URL, LOCAL_REPO_PATH], cwd="."):
                raise Exception("Failed to clone repository for Round 2.")
            
            existing_files = get_existing_files(LOCAL_REPO_PATH)
            logger.info(f"Round 2: Read {len(existing_files)} files for revision context.")

        
        # Call the LLM generator (in app_generator.py)
        llm_result = call_llm_api(
            request.brief,
            request.round,
            existing_files,
            request.attachments
        )

        if not llm_result.get(LLM_FILE_GENERATOR_SUCCESS_KEY):
            error_msg = llm_result.get('error', 'Unknown LLM generation error.')
            raise Exception(f"LLM Generation Failed: {error_msg}")

        generated_files: Dict[str, str] = llm_result['files']
        if not generated_files:
            raise Exception("LLM Generation succeeded but returned no files to deploy.")
        
        logger.info(f"LLM generated/revised {len(generated_files)} files.")

    except Exception as e:
        logger.error(f"Generation phase error: {e}")
        safe_rmtree(LOCAL_REPO_PATH)
        # Note: In a real system, you might ping the evaluator about the failure here.
        return

    # --- 2. Git Deployment Phase ---
    commit_sha = "unknown"
    
    try:
        # Cleanup any pre-existing local repository clone
        if request.round == 1:
            safe_rmtree(LOCAL_REPO_PATH)
            
            # Clone the repository (Round 1 only, Round 2 cloned it earlier)
            clone_output = run_git_command(["git", "clone", BASE_URL, LOCAL_REPO_PATH], cwd=".")
            if not clone_output:
                raise Exception("Failed to clone repository.")
            logger.info("Repository cloned successfully.")
            
            # Configure committer identity required for commits inside the container
            run_git_command(["git", "config", "user.email", f"{USERNAME}@users.noreply.github.com"], cwd=LOCAL_REPO_PATH)
            run_git_command(["git", "config", "user.name", USERNAME], cwd=LOCAL_REPO_PATH)
        
        # --- Write/Update Files ---
        for path, content in generated_files.items():
            full_path = os.path.join(LOCAL_REPO_PATH, path)
            
            # Ensure directory exists for files in subfolders
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            logger.info(f"File written/updated: {path}")

        # --- Git Commit ---
        run_git_command(["git", "add", "."], cwd=LOCAL_REPO_PATH)
        
        commit_message = f"Round {request.round} Task {request.task} - LLM Autodeployer"
        if not run_git_command(["git", "commit", "-m", commit_message], cwd=LOCAL_REPO_PATH):
            # If commit fails (e.g., nothing changed), we still try to push if Round 2
            if request.round == 1:
                 raise Exception("Git commit failed (perhaps no changes were made).")
            # If round 2, and nothing changed, just move to push step

        # Get the commit SHA (used for the evaluation payload)
        commit_sha = run_git_command(["git", "rev-parse", "HEAD"], cwd=LOCAL_REPO_PATH) or "unknown"
        logger.info(f"New commit SHA: {commit_sha}")
        
        # --- Git Push (Authenticated) ---
        # Format the remote URL with the PAT for authentication
        pat = os.getenv('GITHUB_PAT') # Reload PAT for safety, although loaded at start
        if not pat:
             raise Exception("GITHUB_PAT is missing from environment variables.")
             
        AUTHENTICATED_REMOTE_URL = f"https://{pat}@{BASE_URL.replace('https://', '').replace('.git', '')}.git"
        
        # Set the remote URL to use the PAT for this push
        run_git_command(["git", "remote", "set-url", "origin", AUTHENTICATED_REMOTE_URL], cwd=LOCAL_REPO_PATH)
        
        # Push the changes
        if not run_git_command(["git", "push", "origin", "main"], cwd=LOCAL_REPO_PATH):
            raise Exception("Git push failed.")
            
        logger.info("Repository successfully pushed to GitHub.")

    except Exception as e:
        logger.error(f"Deployment phase error: {e}")
        # Final cleanup regardless of success/failure
        safe_rmtree(LOCAL_REPO_PATH)
        return
    
    # --- Final Cleanup ---
    safe_rmtree(LOCAL_REPO_PATH)
    logger.info("Local repository cleanup successful.")


    # --- 3. Ping Evaluation API ---
    try:
        payload = EvaluationPayload(
            email=request.email,
            task=request.task,
            round=request.round,
            nonce=request.nonce,
            repo_url=REPO_URL,
            commit_sha=commit_sha,
            pages_url=PAGES_URL,
            student_secret=request.student_secret,
        )

        logger.info(f"Pinging evaluator at {request.evaluation_url}...")
        
        # Use exponential backoff for resilience (not fully implemented, but shown as structure)
        response = requests.post(request.evaluation_url, json=payload.model_dump())
        
        response.raise_for_status() # Raise an exception for HTTP error codes
        
        logger.info(f"Evaluator ping successful! Status: {response.status_code}")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to ping evaluator at {request.evaluation_url}. Error: {e}")
        # Note: The task still completed, but the notification failed.


# --- API Endpoint ---

@app.post("/api-endpoint", status_code=202)
async def handle_task_request(request: IncomingTask, background_tasks: BackgroundTasks):
    """
    Receives a task request and schedules the long-running process in a background thread.
    Returns 202 Accepted immediately.
    """
    
    # 1. Basic validation (e.g., confirming the correct secret header is present if required, though here we use the JSON body)
    if not request.student_secret or len(request.student_secret) < 10:
         logger.warning(f"Task {request.task} received with invalid or short student secret.")
         # Optional: raise HTTPException(status_code=401, detail="Invalid Student Secret")
         
    # 2. Add the core logic to the background task queue
    background_tasks.add_task(process_task, request)
    
    logger.info(f"Task {request.task}, Round {request.round} accepted and scheduled for background processing.")
    
    # 3. Return immediate acceptance
    return {"message": "Task accepted and processing in the background."}

# Mock endpoint for testing the local evaluation ping
@app.post("/eval")
async def mock_evaluator(payload: EvaluationPayload):
    logger.info("--- MOCK EVALUATOR RECEIVED PAYLOAD ---")
    logger.info(f"Task: {payload.task}, Round: {payload.round}")
    logger.info(f"Commit SHA: {payload.commit_sha}")
    logger.info(f"Pages URL: {payload.pages_url}")
    logger.info(f"Secret verified: {payload.student_secret[:4]}...")
    logger.info("---------------------------------------")
    return {"status": "success", "message": "Payload received by mock evaluator"}
