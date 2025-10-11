from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import subprocess
import os
import json
import time
from app_generator import generate_application # Assuming this is your LLM core

# --- 1. CONFIGURATION ---
# IMPORTANT: This secret MUST MATCH the value you submit in the Google Form.
STUDENT_SECRET = "Hris@tds_proj1_term3" 
# GitHub Personal Access Token (PAT) should be set as an Environment Variable in Hugging Face Space Secrets
GITHUB_PAT = os.environ.get("GITHUB_PAT") 
GITHUB_USERNAME = "Hrishikesh-200" # Replace with your actual GitHub username

app = FastAPI()

# Pydantic model to parse the incoming JSON request from the instructor
class TaskRequest(BaseModel):
    email: str
    secret: str
    task: str
    round: int
    nonce: str
    brief: str
    checks: list[str]
    evaluation_url: str
    attachments: list # simplified structure

# Pydantic model for the outgoing JSON evaluation ping
class EvaluationPing(BaseModel):
    email: str
    task: str
    round: int
    nonce: str
    repo_url: str
    commit_sha: str
    pages_url: str

# --- 2. GITHUB & DEPLOYMENT HELPER ---

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

# --- 3. MAIN API ENDPOINT (The required /api-endpoint) ---

@app.post("/api-endpoint")
def handle_task_request(request: TaskRequest):
    # 1. Check if the secret matches
    if request.secret != STUDENT_SECRET:
        raise HTTPException(status_code=403, detail="Secret verification failed.")

    # 2. Immediately send HTTP 200 response
    print(f"Request accepted for task: {request.task}, round: {request.round}")
    
    # --- ASYNCHRONOUS BACKGROUND WORK (The core Build/Revise logic) ---
    # In a production system, this would be a background task (e.g., using Celery), 
    # but for a simple demonstration, we run the logic and immediately return 200.
    
    try:
        # Define the new repo name
        repo_name = request.task 
        repo_path = os.path.join("/tmp", repo_name)
        
        # --- BUILD / REVISE LOGIC ---
        if request.round == 1:
            # A. Clone/Create the Repo (Round 1 only)
            if os.path.exists(repo_path):
                 run_git_command(f"rm -rf {repo_path}", "/tmp")
            
            # Create a new public repo via GitHub API (not shown, but required)
            # For simplicity, we assume the repo is created and we push to it.
            
            # B. LLM Generate App & Files
            html_content, readme_content, license_content = generate_application(request.brief, request.checks, request.attachments)
            
            # C. Create Local Repo Structure
            os.makedirs(repo_path, exist_ok=True)
            with open(os.path.join(repo_path, "index.html"), "w") as f:
                f.write(html_content)
            with open(os.path.join(repo_path, "README.md"), "w") as f:
                f.write(readme_content)
            with open(os.path.join(repo_path, "LICENSE"), "w") as f:
                f.write(license_content)
                
            # D. Git Setup and Initial Commit
            github_url = f"https://{GITHUB_USERNAME}:{GITHUB_PAT}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
            
            run_git_command(f"git init", repo_path)
            run_git_command(f"git remote add origin {github_url}", repo_path)
            run_git_command(f"git add .", repo_path)
            run_git_command(f'git commit -m "Initial commit for task {request.task}"', repo_path)
            
            # E. Push (Deploys to GitHub Pages via default settings/Action)
            run_git_command(f"git push -u origin main", repo_path)
            
            # F. Get Commit SHA and URLs
            commit_sha = run_git_command("git rev-parse HEAD", repo_path)
            repo_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}"
            # This PAGES URL structure is standard for GitHub Pages.
            pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/" 

        elif request.round == 2:
            # --- REVISE LOGIC (Similar structure but modify existing code) ---
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
            
        # --- 4. POST TO EVALUATION URL (Required within 10 minutes) ---
        
        ping_data = EvaluationPing(
            email=request.email,
            task=request.task,
            round=request.round,
            nonce=request.nonce,
            repo_url=repo_url,
            commit_sha=commit_sha,
            pages_url=pages_url,
        )

        # Implement the exponential backoff loop for re-submission
        delay = 1
        max_retries = 5
        for i in range(max_retries):
            try:
                response = requests.post(
                    request.evaluation_url, 
                    headers={"Content-Type": "application/json"},
                    json=ping_data.dict(),
                    timeout=5 # Set a reasonable timeout
                )
                if response.status_code == 200:
                    print(f"Successfully pinged evaluation API for round {request.round}.")
                    break
                else:
                    print(f"Ping failed (Status: {response.status_code}). Retrying in {delay}s...")
            except requests.exceptions.RequestException as e:
                print(f"Ping failed (Exception: {e}). Retrying in {delay}s...")
            
            time.sleep(delay)
            delay *= 2 # 1, 2, 4, 8, 16... seconds delay
        else:
            print("Failed to notify evaluation API after multiple retries.")
            # Final failure should be logged/reported internally
            
    except Exception as e:
        # Catch and log any errors during the build/deploy process
        print(f"An error occurred during build/deploy: {e}")
        # Even if the build fails, the API returns 200 to the instructor immediately
        
    return {"status": "accepted", "message": f"Processing task {request.task} in background."}