import os
import json
import time
import requests # Needed for GitHub API call and Evaluation ping
import subprocess
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app_generator import generate_application # Assuming this is your LLM core

# --- 1. CONFIGURATION (MUST BE UPDATED) ---
# IMPORTANT: This secret MUST MATCH the value you submit in the Google Form.
STUDENT_SECRET = "Hris@tds_proj1_term3" # REPLACE with your actual secret
# GITHUB_PAT is read from the Hugging Face Space Secrets
GITHUB_PAT = os.environ.get("GITHUB_PAT") 
GITHUB_USERNAME = "Hrishikesh-200" # CONFIRM: Your actual GitHub username

app = FastAPI()

# Pydantic models (as previously defined)
class TaskRequest(BaseModel):
    email: str
    secret: str
    task: str
    round: int
    nonce: str
    brief: str
    checks: list[str]
    evaluation_url: str
    attachments: list 

class EvaluationPing(BaseModel):
    email: str
    task: str
    round: int
    nonce: str
    repo_url: str
    commit_sha: str
    pages_url: str

# --- 2. GITHUB & DEPLOYMENT HELPERS ---

def run_git_command(command, repo_path):
    """Executes a git command in the context of the repository."""
    result = subprocess.run(
        command,
        cwd=repo_path,
        capture_output=True,
        text=True,
        shell=True,
        env={"GIT_TERMINAL_PROMPT": "0"}
    )
    if result.returncode != 0:
        print(f"Error running command: {command}")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        raise RuntimeError(f"Git command failed: {result.stderr}")
    return result.stdout.strip()

def create_github_repo(repo_name, username, pat):
    """Creates a new public repository on GitHub via the REST API."""
    api_url = f"https://api.github.com/user/repos"
    headers = {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {
        "name": repo_name,
        "private": False,
        "auto_init": False
    }
    response = requests.post(api_url, headers=headers, json=data)
    
    if response.status_code == 201:
        print(f"Successfully created remote repo: {repo_name}")
        return True
    elif response.status_code == 422 and "already exists" in response.text:
        print(f"Remote repo {repo_name} already exists (Continuing).")
        return True
    else:
        print(f"Failed to create repo. Status: {response.status_code}, Response: {response.text}")
        raise RuntimeError("GitHub repo creation failed.")

# --- 3. STATUS ENDPOINT (Optional, for easy browser check) ---

@app.get("/")
def read_root():
    """A simple endpoint to confirm the API is running."""
    return {"status": "ok", "message": "Student LLM Deployment API is operational. Send POST to /api-endpoint."}

# --- 4. MAIN API ENDPOINT (The required /api-endpoint) ---

@app.post("/api-endpoint")
def handle_task_request(request: TaskRequest):
    # 1. Check if the secret matches
    if request.secret != STUDENT_SECRET:
        raise HTTPException(status_code=403, detail="Secret verification failed.")

    # 2. Immediately send HTTP 200 response
    print(f"Request accepted for task: {request.task}, round: {request.round}")
    
    # --- ASYNCHRONOUS BACKGROUND WORK (The core Build/Revise logic) ---
    
    # Check for PAT before proceeding with Git/GitHub operations
    if not GITHUB_PAT:
         print("CRITICAL: GITHUB_PAT secret is missing or invalid.")
         # You still return 200, but log the internal failure
         return {"status": "accepted", "message": "Processing failed: Missing GITHUB_PAT."}
        
    try:
        # Define the new repo name
        repo_name = request.task 
        repo_path = os.path.join("/tmp", repo_name)
        
        # --- BUILD LOGIC (Round 1) ---
        if request.round == 1:
            
            # A. Prepare Local Directory
            if os.path.exists(repo_path):
                 run_git_command(f"rm -rf {repo_path}", "/tmp")
            os.makedirs(repo_path, exist_ok=True)
            
            # B. CREATE REMOTE REPO VIA API (CRITICAL NEW STEP)
            create_github_repo(repo_name, GITHUB_USERNAME, GITHUB_PAT)
            
            # C. LLM Generate App & Files
            html_content, readme_content, license_content = generate_application(request.brief, request.checks, request.attachments)
            
            # D. Create Local Files
            with open(os.path.join(repo_path, "index.html"), "w") as f:
                f.write(html_content)
            with open(os.path.join(repo_path, "README.md"), "w") as f:
                f.write(readme_content)
            with open(os.path.join(repo_path, "LICENSE"), "w") as f:
                f.write(license_content)
                
            # E. Git Setup, Commit, and Push
            github_url = f"https://{GITHUB_USERNAME}:{GITHUB_PAT}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
            
            run_git_command(f"git init", repo_path)
            run_git_command(f"git remote add origin {github_url}", repo_path)
            run_git_command(f"git add .", repo_path)
            run_git_command(f'git commit -m "Initial commit for task {request.task}"', repo_path)
            
            # F. Push (Deploys to GitHub Pages via default settings/Action)
            run_git_command(f"git push -u origin main", repo_path)
            
            # G. Get Commit SHA and URLs
            commit_sha = run_git_command("git rev-parse HEAD", repo_path)
            repo_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}"
            pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/" 

        # --- REVISE LOGIC (Round 2) ---
        elif request.round == 2:
            # A. Clone Existing Repo
            github_url = f"https://{GITHUB_USERNAME}:{GITHUB_PAT}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
            run_git_command(f"git clone {github_url} {repo_path}", "/tmp")
            
            # B. LLM Revise App & Files
            html_content, readme_content = generate_application(request.brief, request.checks, request.attachments, is_revision=True)
            
            # C. Overwrite/Modify Files
            with open(os.path.join(repo_path, "index.html"), "w") as f:
                f.write(html_content)
            with open(os.path.join(repo_path, "README.md"), "w") as f:
                f.write(readme_content)
            
            # D. Git Commit and Push
            run_git_command(f"git add .", repo_path)
            run_git_command(f'git commit -m "Revision for round {request.round}: {request.brief[:30]}..."', repo_path)
            run_git_command(f"git push", repo_path)
            
            # E. Get Commit SHA and URLs
            commit_sha = run_git_command("git rev-parse HEAD", repo_path)
            repo_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}"
            pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/" 
            
        # --- 5. POST TO EVALUATION URL ---
        
        ping_data = EvaluationPing(
            email=request.email,
            task=request.task,
            round=request.round,
            nonce=request.nonce,
            repo_url=repo_url,
            commit_sha=commit_sha,
            pages_url=pages_url,
        )

        # Implementation of exponential backoff loop for re-submission
        delay = 1
        max_retries = 5
        for i in range(max_retries):
            try:
                response = requests.post(
                    request.evaluation_url, 
                    headers={"Content-Type": "application/json"},
                    json=ping_data.dict(),
                    timeout=5 
                )
                if response.status_code == 200:
                    print(f"Successfully pinged evaluation API for round {request.round}.")
                    break
                else:
                    print(f"Ping failed (Status: {response.status_code}). Retrying in {delay}s...")
            except requests.exceptions.RequestException as e:
                print(f"Ping failed (Exception: {e}). Retrying in {delay}s...")
            
            time.sleep(delay)
            delay *= 2 
        else:
            print("Failed to notify evaluation API after multiple retries.")
            
    except Exception as e:
        print(f"An internal error occurred during build/deploy: {e}")
        
    return {"status": "accepted", "message": f"Processing task {request.task} in background."}
