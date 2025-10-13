import os
import shutil
import subprocess
import json
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os.path
import sys

# --- Configuration & Secrets ---
STUDENT_SECRET = os.environ.get("STUDENT_SECRET", "Hris@tds_proj1_term3")
GITHUB_PAT = os.environ.get("GITHUB_PAT")
GITHUB_USERNAME = "Hrishikesh-200" # Your GitHub username

app = FastAPI()

# Pydantic model for the incoming JSON request
class TaskRequest(BaseModel):
    email: str
    secret: str
    task: str
    round: int
    nonce: str
    brief: str
    checks: List[str]
    evaluation_url: str
    attachments: List[dict] = []

# --- Helper Functions ---

def run_git_command(command: List[str], cwd: str):
    """
    Wrapper to run git commands, attempting to use the Windows shell if necessary.
    This resolves the issue where commands like 'git' are not found in the path.
    """
    try:
        # Try running without shell=True first (safer)
        subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)
    except FileNotFoundError:
        # If the command is not found (common on Windows without a proper PATH setup), 
        # try running it through the system shell.
        if sys.platform.startswith('win'):
            # On Windows, explicitly use shell=True
            subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True, shell=True)
        else:
            # Re-raise the error if it's not a Windows PATH issue
            raise

def cleanup_repo(repo_path: str):
    """Uses Python's shutil module for safe, cross-platform directory removal (rm -rf)."""
    if os.path.exists(repo_path):
        print(f"Cleaning up directory: {repo_path}")
        try:
            shutil.rmtree(repo_path) 
        except Exception as e:
            print(f"WARNING: Could not remove directory {repo_path}: {e}")
    else:
        print(f"Cleanup skipped: Directory not found: {repo_path}")

def generate_content(brief: str) -> str:
    # --- TODO: IMPLEMENT LLM CALL ---
    print(f"Calling LLM to generate code for brief: {brief}")
    
    if "HTML" in brief.upper():
        return f"<html><body><h1>API Test Successful for task: {brief}</h1></body></html>"
    return f"Response to brief: {brief}"
    # --- END TODO ---

def create_github_repo(request: TaskRequest, file_content: str) -> dict:
    
    if not GITHUB_PAT:
        raise ValueError("GITHUB_PAT secret is missing or invalid.")

    repo_name = request.task
    repo_path = os.path.join(os.getcwd(), f"{repo_name}_local_repo") 
    
    # 1. Cleanup old repo directory if it exists (Fixes local compatibility for the repo folder)
    cleanup_repo(repo_path)
    
    try:
        # --- TODO: IMPLEMENT FULL GITHUB FLOW ---

        # 1. Create Repository (via GitHub API)
        print(f"Attempting to create GitHub repo: {repo_name}")
        
        # 2. Clone the new repository (Using Hrishikesh-200)
        # We use the run_git_command helper to deal with Windows compatibility
        run_git_command(["git", "clone", f"https://github.com/{GITHUB_USERNAME}/{repo_name}.git", repo_path], cwd=os.getcwd())
        
        # 3. Create Files 
        os.makedirs(repo_path, exist_ok=True) 
        
        with open(os.path.join(repo_path, "index.html"), "w") as f:
            f.write(file_content)
            
        # 4. Commit and Push
        # Example using the helper function:
        # run_git_command(["git", "add", "."], cwd=repo_path)
        # run_git_command(["git", "commit", "-m", "Initial commit from API"], cwd=repo_path)

        # Get actual commit SHA for the evaluation POST
        commit_sha_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True, check=True)
        commit_sha = commit_sha_result.stdout.strip()

        # 5. Enable GitHub Pages 
        
        # 6. Construct final URLs (Using Hrishikesh-200)
        repo_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}" 
        pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/" 

        # --- END TODO ---

        return {
            "repo_url": repo_url, 
            "commit_sha": commit_sha, 
            "pages_url": pages_url
        }
        
    except subprocess.CalledProcessError as e:
        error_detail = f"Git command failed. STDOUT: {e.stdout.decode()} STDERR: {e.stderr.decode()}"
        print(f"CRITICAL: {error_detail}")
        cleanup_repo(repo_path)
        raise ValueError(error_detail)
    except Exception as e:
        cleanup_repo(repo_path)
        raise ValueError(f"An internal error occurred during GitHub operations. Error: {str(e)}")
    
    finally:
        # 5. Final cleanup of the local working directory (Always runs)
        cleanup_repo(repo_path)


# --- Main API Endpoint ---

@app.post("/api-endpoint")
def handle_task_request(request: TaskRequest):
    print(f"Request accepted for task: {request.task}, round: {request.round}")

    if request.secret != STUDENT_SECRET:
        raise HTTPException(status_code=403, detail="Invalid student secret.")
    
    # ### TODO: IMPLEMENT SIGNATURE VERIFICATION HERE ###
    
    try:
        generated_content = generate_content(request.brief)
        repo_details = create_github_repo(request, generated_content)
        
        evaluation_payload = {
            "email": request.email,
            "task": request.task,
            "round": request.round,
            "nonce": request.nonce,
            "repo_url": repo_details['repo_url'],
            "commit_sha": repo_details['commit_sha'],
            "pages_url": repo_details['pages_url']
        }
        
        # --- TODO: IMPLEMENT EVALUATION POST ---
        print(f"POSTing final details to evaluation URL: {request.evaluation_url}")
        # --- END TODO ---
        
        return {"status": "accepted", "message": f"Processing task {request.task} in background."}

    except ValueError as e:
        print(f"CRITICAL: {e}")
        return {"status": "accepted", "message": f"Processing failed: {str(e)}"}
    except Exception as e:
        print(f"CRITICAL: An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during processing.")
          
