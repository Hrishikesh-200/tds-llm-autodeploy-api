import os
import shutil
import subprocess
import json
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os.path

# --- Configuration & Secrets ---
# Use os.environ.get to safely retrieve secrets from Hugging Face environment variables
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

# --- Helper Functions ---

def cleanup_repo(repo_path: str):
    """Uses Python's shutil module for safe, cross-platform directory removal (rm -rf)."""
    if os.path.exists(repo_path):
        print(f"Cleaning up directory: {repo_path}")
        try:
            # This works on Windows, Linux (HF), and macOS.
            shutil.rmtree(repo_path) 
        except Exception as e:
            # Log a warning but don't crash the main API process
            print(f"WARNING: Could not remove directory {repo_path}: {e}")
    else:
        print(f"Cleanup skipped: Directory not found: {repo_path}")

def generate_content(brief: str) -> str:
    # --- TODO: IMPLEMENT LLM CALL ---
    print(f"Calling LLM to generate code for brief: {brief}")
    
    # Placeholder response to allow API to run
    if "HTML" in brief.upper():
        return f"<html><body><h1>API Test Successful for task: {brief}</h1></body></html>"
    return f"Response to brief: {brief}"
    # --- END TODO ---

def create_github_repo(request: TaskRequest, file_content: str) -> dict:
    
    if not GITHUB_PAT:
        raise ValueError("GITHUB_PAT secret is missing or invalid.")

    repo_name = request.task
    repo_path = os.path.join(os.getcwd(), f"{repo_name}_local_repo") 
    
    # 1. Cleanup old repo directory if it exists (Fixes local compatibility)
    cleanup_repo(repo_path)
    
    try:
        # --- TODO: IMPLEMENT FULL GITHUB FLOW ---

        # 1. Create Repository (via GitHub API)
        # e.g., using 'requests' to hit the GitHub /user/repos endpoint
        print(f"Attempting to create GitHub repo: {repo_name}")
        
        # 2. Clone the new repository (Using Hrishikesh-200)
        # NOTE: This line requires the repo to be created first via API/CLI
        subprocess.run(["git", "clone", f"https://github.com/{GITHUB_USERNAME}/{repo_name}.git", repo_path], check=True)
        
        # 3. Create Files (LICENSE, README.md, index.html from file_content)
        # Using os.makedirs with exist_ok=True is cross-platform safe
        os.makedirs(repo_path, exist_ok=True) 
        
        # Example: Simple file creation
        with open(os.path.join(repo_path, "index.html"), "w") as f:
            f.write(file_content)
            
        # 4. Commit and Push
        # Use HTTPS URL with PAT for authentication
        # remote_url = f"https://oauth2:{GITHUB_PAT}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
        # subprocess.run(["git", "remote", "set-url", "origin", remote_url], cwd=repo_path, check=True)
        # subprocess.run(["git", "push", "origin", "main", "-f"], cwd=repo_path, check=True)
        
        # Get actual commit SHA for the evaluation POST
        commit_sha_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True, check=True)
        commit_sha = commit_sha_result.stdout.strip()

        # 5. Enable GitHub Pages (via GitHub API or by pushing to 'gh-pages' branch)
        
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
        # Ensure cleanup even on Git failure
        cleanup_repo(repo_path)
        raise ValueError(error_detail)
    except Exception as e:
        # Ensure cleanup on other failures
        cleanup_repo(repo_path)
        raise ValueError(f"An internal error occurred during GitHub operations. Error: {str(e)}")
    
    finally:
        # 5. Final cleanup of the local working directory (Always runs)
        # This is where the local compatibility fix truly shines.
        cleanup_repo(repo_path)


# --- Main API Endpoint ---

@app.post("/api-endpoint")
def handle_task_request(request: TaskRequest):
    print(f"Request accepted for task: {request.task}, round: {request.round}")

    # 1. Secret/Authentication Check
    if request.secret != STUDENT_SECRET:
        raise HTTPException(status_code=403, detail="Invalid student secret.")
    
    # 2. Signature Verification (Required by Project)
    # ### TODO: IMPLEMENT SIGNATURE VERIFICATION HERE ###
    # If signature verification fails, raise HTTPException(status_code=403, detail="Invalid signature.")
    
    try:
        # 3. Content Generation
        generated_content = generate_content(request.brief)

        # 4. GitHub Operations (Create Repo, Commit, Push, Enable Pages)
        repo_details = create_github_repo(request, generated_content)
        
        # 5. POST to evaluation_url (Required by Project)
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
        # Example using requests:
        # response = requests.post(request.evaluation_url, json=evaluation_payload, headers={"Content-Type": "application/json"})
        # response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        # --- END TODO ---
        
        return {"status": "accepted", "message": f"Processing task {request.task} in background."}

    except ValueError as e:
        # Catch errors from the GitHub function
        print(f"CRITICAL: {e}")
        # Send a 200 OK but with a message indicating failure
        return {"status": "accepted", "message": f"Processing failed: {str(e)}"}
    except Exception as e:
        # Catch any other unexpected errors
        print(f"CRITICAL: An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during processing.")
   
    
        
