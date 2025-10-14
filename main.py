import os
import shutil
import subprocess
import json
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv
import os.path
import sys

# --- Configuration & Secrets ---
load_dotenv()  # Load from .env if present (for local testing)
STUDENT_SECRET = os.environ.get("STUDENT_SECRET", "Hris@tds_proj1_term3")
GITHUB_PAT = os.environ.get("GITHUB_PAT")
GITHUB_USERNAME = "Hrishikesh-200" # Your GitHub username
# --- End Configuration ---

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
    signature: Optional[str] = None 

# --- Verification & Helper Functions ---

def verify_signature(request: TaskRequest) -> bool:
    """
    Step 2: Verifies the cryptographic signature of the request.
    """
    
    # ----------------------------------------------------------------------
    # TODO: IMPLEMENT CRYPTOGRAPHIC VERIFICATION HERE
    # ----------------------------------------------------------------------
    
    # Placeholder: Return True only if actual verification passes
    return True 
    # ----------------------------------------------------------------------


def _safe_decode(output):
    """Safely decodes subprocess output, ignoring errors if output is None or not bytes."""
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode('utf-8', errors='ignore')
    return str(output)


def run_git_command(command: List[str], cwd: str):
    """
    Wrapper to run git commands safely across Windows and Linux.
    """
    try:
        # Use subprocess.run with capture_output=True for better error handling
        result = subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)
        return result
    except FileNotFoundError:
        # Fallback for Windows PATH issues
        if sys.platform.startswith('win'):
            # Re-run with shell=True on Windows if initial check failed
            result = subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True, shell=True)
            return result
        else:
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

def generate_content(request: TaskRequest) -> dict:
    # --- TODO: IMPLEMENT LLM CALL and ATTACHMENT PARSING ---
    print(f"Calling LLM to generate code for brief: {request.brief}")
    
    return {
        "index.html": f"<html><body><h1>API Test Successful for task: {request.brief}</h1></body></html>",
        "README.md": f"# {request.task}\n\nApp generated based on brief: {request.brief}", 
        "LICENSE": "MIT License content here...", 
        "usercode": "TDS-HRIS-200"
    }
    # --- END TODO ---

def create_github_repo(request: TaskRequest, generated_files: dict) -> dict:
    
    if not GITHUB_PAT:
        raise ValueError("GITHUB_PAT secret is missing or invalid.")

    repo_name = request.task 
    repo_path = os.path.join(os.getcwd(), f"{repo_name}_local_repo") 
    
    cleanup_repo(repo_path)
    
    try:
        # --- TODO: IMPLEMENT FULL GITHUB FLOW (Steps 5 & 6) ---
        
        # 1. Create Repository (via GitHub API using PAT)
        print(f"Attempting to create GitHub repo: {repo_name} for {GITHUB_USERNAME}")
        
        # 2. Clone the new repository (using HTTPS/PAT for stability on server)
        # FIX: Using GITHUB_USERNAME as the username for authentication is more reliable
        # than 'oauth2' or 'x-token-auth' for a classic PAT.
        repo_https_url_with_pat = f"https://{GITHUB_USERNAME}:{GITHUB_PAT}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
        
        # NOTE: This command is what is failing locally due to the SSH prompt/non-interactive issue.
        run_git_command(["git", "clone", repo_https_url_with_pat, repo_path], cwd=os.getcwd())
        
        # 3. Create Files 
        os.makedirs(repo_path, exist_ok=True) 
        
        for filename, content in generated_files.items():
            if filename not in ["usercode"]:
                 with open(os.path.join(repo_path, filename), "w") as f:
                    f.write(content)
            
        # 4. Commit and Push
        run_git_command(["git", "add", "."], cwd=repo_path)
        run_git_command(["git", "commit", "-m", f"Round {request.round} commit"], cwd=repo_path)
        run_git_command(["git", "push", "origin", "main"], cwd=repo_path) 

        # Get actual commit SHA for the evaluation POST
        commit_sha_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True, check=True)
        commit_sha = commit_sha_result.stdout.strip()

        # 5. Enable GitHub Pages (This is a separate GitHub API call)
        
        # 6. Construct final URLs 
        repo_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}" 
        pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/" 

        # --- END TODO ---

        return {
            "repo_url": repo_url, 
            "commit_sha": commit_sha, 
            "pages_url": pages_url,
            "usercode": generated_files["usercode"]
        }
        
    except subprocess.CalledProcessError as e:
        # Handles errors where the git command runs but returns a non-zero exit code
        error_detail = f"Git command failed. STDOUT: {_safe_decode(e.stdout)} STDERR: {_safe_decode(e.stderr)}"
        print(f"CRITICAL: {error_detail}")
        cleanup_repo(repo_path)
        raise ValueError(error_detail)
    except Exception as e:
        cleanup_repo(repo_path)
        # Catches other unexpected errors
        raise ValueError(f"An internal error occurred during GitHub operations. Error: {str(e)}")
    
    finally:
        cleanup_repo(repo_path)

# --- Main API Endpoints ---

@app.get("/")
def read_root():
    """Provides a simple status check for the root URL."""
    return {"status": "ok", "message": "API is running. POST to /api-endpoint for task processing."}

@app.post("/api-endpoint")
def handle_task_request(request: TaskRequest):
    print(f"Request accepted for task: {request.task}, round: {request.round}")

    if request.secret != STUDENT_SECRET:
        raise HTTPException(status_code=403, detail="Invalid student secret.")
    
    if not verify_signature(request):
        raise HTTPException(status_code=403, detail="Invalid signature. Request rejected.")
    
    try:
        generated_files = generate_content(request)
        repo_details = create_github_repo(request, generated_files)
        
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
        
        return {"status": "accepted", "message": f"Processing task {request.task} in background.", "usercode": repo_details['usercode']}

    except ValueError as e:
        # Catches errors raised by the GitHub function
        print(f"CRITICAL: {e}")
        # Returns 200 with the error message, as required for failure reporting
        return {"status": "accepted", "message": f"Processing failed: {str(e)}", "usercode": "Error"}
    except Exception as e:
        # Final catch for any truly unexpected internal server errors
        print(f"CRITICAL: An unexpected internal error occurred: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during processing.")