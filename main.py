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
[cite_start]# [cite: 1] STUDENT_SECRET is used for verification logic beyond signature
STUDENT_SECRET = os.environ.get("STUDENT_SECRET", "Hris@tds_proj1_term3")
GITHUB_PAT = os.environ.get("GITHUB_PAT")
[cite_start]GITHUB_USERNAME = "Hrishikesh-200" # Your GitHub username [cite: 1]
# --- End Configuration ---

app = FastAPI()

# Pydantic model for the incoming JSON request
class TaskRequest(BaseModel):
    [cite_start]email: str # [cite: 1]
    secret: str
    [cite_start]task: str # [cite: 1]
    [cite_start]round: int # [cite: 1]
    [cite_start]nonce: str # [cite: 1]
    [cite_start]brief: str # [cite: 1]
    [cite_start]checks: List[str] # [cite: 1]
    [cite_start]evaluation_url: str # [cite: 1]
    [cite_start]attachments: List[dict] = [] # [cite: 1]
    [cite_start]signature: str # [cite: 1]
    # [cite_start]usercode: Optional[str] = "" # Field mentioned in response [cite: 1]

# --- Helper Functions ---

def run_git_command(command: List[str], cwd: str):
    """
    Wrapper to run git commands safely across Windows and Linux.
    """
    try:
        # Try running without shell=True first (safer)
        result = subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)
        return result
    except FileNotFoundError:
        # If the command is not found (common on Windows without a proper PATH setup), 
        # try running it through the system shell.
        if sys.platform.startswith('win'):
            result = subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True, shell=True)
            return result
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

def generate_content(request: TaskRequest) -> dict:
    # --- TODO: IMPLEMENT LLM CALL and ATTACHMENT PARSING ---
    # [cite_start]1. Decode and save files from request.attachments (data URIs)[cite: 1].
    # [cite_start]2. Call your LLM-assisted generator using request.brief[cite: 1].
    # [cite_start]3. Generate all required files: index.html, LICENSE, README.md, etc.[cite: 1].
    print(f"Calling LLM to generate code for brief: {request.brief}")
    
    # Placeholder for generated files and required content
    return {
        "index.html": f"<html><body><h1>API Test Successful for task: {request.brief}</h1></body></html>",
        [cite_start]"README.md": f"# {request.task}\n\nApp generated based on brief: {request.brief}", # [cite: 1]
        [cite_start]"LICENSE": "MIT License content here...", # [cite: 1]
        [cite_start]"usercode": "TDS-HRIS-200" # Unique user code for response [cite: 1]
    }
    # --- END TODO ---

def create_github_repo(request: TaskRequest, generated_files: dict) -> dict:
    
    if not GITHUB_PAT:
        raise ValueError("GITHUB_PAT secret is missing or invalid.")

    [cite_start]repo_name = request.task # Use unique repo name based on .task [cite: 1]
    repo_path = os.path.join(os.getcwd(), f"{repo_name}_local_repo") 
    
    cleanup_repo(repo_path)
    
    try:
        # --- TODO: IMPLEMENT FULL GITHUB FLOW ---
        
        # [cite_start]1. Create Repository (via GitHub API) and ensure it's public [cite: 1]
        print(f"Attempting to create GitHub repo: {repo_name} for {GITHUB_USERNAME}")
        
        # 2. Clone the new repository 
        repo_ssh_url = f"git@github.com:{GITHUB_USERNAME}/{repo_name}.git"
        # Using HTTPS with PAT is also a common method: 
        # repo_https_url = f"https://oauth2:{GITHUB_PAT}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
        
        run_git_command(["git", "clone", repo_ssh_url, repo_path], cwd=os.getcwd())
        
        # 3. Create Files (LICENSE, README.md, index.html)
        os.makedirs(repo_path, exist_ok=True) 
        for filename, content in generated_files.items():
            if filename not in ["usercode"]:
                 with open(os.path.join(repo_path, filename), "w") as f:
                    f.write(content)
            
        # 4. Commit and Push
        run_git_command(["git", "add", "."], cwd=repo_path)
        run_git_command(["git", "commit", "-m", f"Round {request.round} commit"], cwd=repo_path)
        # Configure remote URL with PAT for push authentication if using HTTPS
        # run_git_command(["git", "remote", "set-url", "origin", repo_https_url], cwd=repo_path)
        run_git_command(["git", "push", "origin", "main"], cwd=repo_path) 

        # Get actual commit SHA for the evaluation POST
        commit_sha_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True, check=True)
        commit_sha = commit_sha_result.stdout.strip()

        # [cite_start]5. Enable GitHub Pages [cite: 1] (This is usually a separate GitHub API call)
        
        # 6. Construct final URLs (Based on Hrishikesh-200)
        [cite_start]repo_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}" # [cite: 1]
        [cite_start]pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/" # [cite: 1]

        # --- END TODO ---

        return {
            "repo_url": repo_url, 
            "commit_sha": commit_sha, 
            "pages_url": pages_url,
            "usercode": generated_files["usercode"]
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
        cleanup_repo(repo_path)

# --- Main API Endpoint ---

@app.post("/api-endpoint")
def handle_task_request(request: TaskRequest):
    print(f"Request accepted for task: {request.task}, round: {request.round}")

    # 1. Student Secret Check (Secondary check, not required by PDF but good practice)
    if request.secret != STUDENT_SECRET:
        raise HTTPException(status_code=403, detail="Invalid student secret.")
    
    # [cite_start]2. Signature Verification [cite: 1]
    ### TODO: IMPLEMENT SIGNATURE VERIFICATION HERE ###
    # if not verify_signature(request):
    #     raise HTTPException(status_code=403, detail="Invalid signature.")
    
    try:
        # 3. Content Generation
        generated_files = generate_content(request)

        # 4. GitHub Operations 
        repo_details = create_github_repo(request, generated_files)
        
        # [cite_start]5. POST to evaluation_url [cite: 1]
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
        # [cite_start]response = requests.post(request.evaluation_url, json=evaluation_payload, headers={"Content-Type": "application/json"}) [cite: 1]
        # [cite_start]response.raise_for_status() # Must ensure a HTTP 200 response. [cite: 1]
        # --- END TODO ---
        
        # [cite_start]6. Final API Response [cite: 1]
        return {"status": "accepted", "message": f"Processing task {request.task} in background.", "usercode": repo_details['usercode']}

    except ValueError as e:
        # Catch errors from the GitHub function
        print(f"CRITICAL: {e}")
        return {"status": "accepted", "message": f"Processing failed: {str(e)}", "usercode": "Error"}
    except Exception as e:
        # Catch any other unexpected errors
        print(f"CRITICAL: An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during processing.")
