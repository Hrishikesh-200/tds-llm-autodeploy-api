<<<<<<< HEAD
import os
import shutil
import subprocess
import json
import logging
import requests
import base64
from typing import Dict, Any, List

# --- Configuration & Setup ---
# Set your GitHub details here
GITHUB_USERNAME = "Hrishikesh-200"
REPO_NAME = "tds-llm-autodeploy-api" # The central repository name
REPO_BASE_URL = f"https://github.com/{GITHUB_USERNAME}/"

# Path is relative to where the server (main.py) is executed
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configure logging for the worker process
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions ---

def run_git_command(command: List[str], path: str, pat: str) -> str:
    """Runs a Git command, capturing output and providing better error context."""
    logging.debug(f"Executing Git command in {path}: {' '.join(command)}")
=======
#app_generator.py
def generate_application(brief, checks, attachments, is_revision=False):
    """
    This function contains the core logic to call your chosen LLM.
>>>>>>> 6fd7a63d88d24532ab83208d3d5c438aeb46b6af
    
    # Use PAT only if cloning/pushing via HTTPS requires it
    # Note: On some systems, PAT in the URL is handled by 'git clone'.
    # For 'push', it relies on the config set previously.

    try:
        # Use a longer timeout for potential slow remote operations
        result = subprocess.run(
            command, 
            cwd=path, 
            check=True,  # CRITICAL: Raises exception on non-zero exit code
            capture_output=True, 
            text=True,
            timeout=120 
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        error_message = f"Git command failed. STDOUT: {e.stdout} STDERR: {e.stderr}"
        
        # 🚨 Enhanced logging for common PAT/Auth errors
        if any(keyword in e.stderr for keyword in ["Authentication failed", "fatal: repository", "403 Forbidden"]):
            error_message += "\n(CRITICAL HINT: GITHUB_PAT is likely invalid, expired, or lacking 'repo' scope.)"
        
        logging.critical(error_message)
        raise Exception(error_message)


def cleanup(path: str):
    """Safely removes the local repository folder."""
    if os.path.exists(path):
        try:
            shutil.rmtree(path)
            logging.info(f"Successfully cleaned up directory: {path}")
        except Exception as e:
            # Attempt a second time to handle potential file lock issues on Windows
            logging.warning(f"Initial cleanup failed for {path}. Attempting second pass: {e}")
            try:
                shutil.rmtree(path)
            except Exception as e2:
                logging.critical(f"Failed to remove directory after retry: {e2}")

def notify_evaluator(eval_url: str, response_payload: Dict[str, Any]) -> bool:
    """Sends the final result JSON to the instructor's evaluation URL."""
    logging.info(f"Notifying evaluator at: {eval_url}")
    try:
        # Required to use the same round/nonce/task from the request
        response = requests.post(eval_url, json=response_payload, timeout=30)
        response.raise_for_status() # Raise HTTP error for bad responses (4xx or 5xx)
        logging.info(f"Evaluator notified successfully. Status: {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to notify evaluation URL {eval_url}: {e}")
        return False

# --- LLM and GitHub API Mock/Placeholder Functions ---

def create_github_repo(repo_name: str, pat: str):
    """
    Placeholder: Must be replaced with actual GitHub API call (POST /user/repos).
    Your system is likely set up to clone the existing REPO_NAME, so this might be redundant.
    For this specific evaluation, we assume the base repository already exists.
    """
    logging.info(f"Skipping remote repo creation. Assuming '{repo_name}' already exists.")


def call_llm_api(brief: str, attachments: List[Dict[str, str]], task_name: str) -> Dict[str, str]:
    """
    Placeholder: Must be replaced with actual LLM API call (e.g., Gemini API).
    The prompt MUST instruct the LLM to provide a structured JSON response.
    """
    logging.info(f"LLM: Calling model for brief: {brief[:80]}...")
    
    # ⚠️ LLM Response Mock (Simulates structured output)
    if "game" in brief.lower():
        filename = "index.html"
        code_content = "<html><head><title>LLM Game</title></head><body><h1>A Game Placeholder</h1><script>// Game logic here</script></body></html>"
    elif "calculator" in brief.lower() or "sum" in brief.lower() or "csv" in brief.lower():
        filename = "solution.py"
        code_content = f"# Python script for {task_name}\n\ndef solve(): return 'Result'"
    else: # Default web page for visual check
        filename = "index.html"
        code_content = f"<html><body><h1>LLM Solution for: {task_name}</h1><p>{brief}</p></body></html>"

    readme_content = f"# Solution for {task_name}\n\n## Task Brief\n{brief}\n\n## Files\nPrimary file generated: {filename}"
    
    return {
        "filename": filename,
        "code_content": code_content,
        "readme_content": readme_content,
        "license_content": "MIT License\n..." # Actual MIT license boilerplate
    }

# --- Main Logic ---

def process_task(task_params: Dict[str, Any], pat: str):
    """
    Manages the full LLM code generation and Git deployment lifecycle.
    Runs in a background thread initiated by main.py.
    """
    
    # 0. Initial Setup & Validation
    task_name = task_params.get("task")
    round_num = task_params.get("round", 1)
    
    local_repo_path = os.path.join(BASE_DIR, REPO_NAME) # Clone to a fixed path
    
    logging.info(f"Starting task: {task_name}, Round: {round_num}")
    
    repo_url_base = f"{REPO_BASE_URL}{REPO_NAME}"
    authenticated_repo_url = f"https://{pat}@{repo_url_base}.git"
    
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
        # Clone the existing base repository
        logging.info(f"Cloning '{REPO_NAME}'...")
        run_git_command(["git", "clone", authenticated_repo_url, local_repo_path], BASE_DIR, pat)
    except Exception as e:
        logging.error(f"Failed during initial clone: {e}")
        failure_response["commit_sha"] = "GIT_CLONE_FAILED"
        notify_evaluator(task_params["evaluation_url"], failure_response)
        return

    # --- 2. LLM Generation and File Content Preparation ---
    try:
        llm_output = call_llm_api(
            task_params["brief"], 
            task_params["attachments"], 
            task_name
        )
        # Extract content using the generalized keys
        main_file_name = llm_output["filename"]
        
    except Exception as e:
        logging.error(f"LLM/File preparation failed: {e}")
        cleanup(local_repo_path)
        failure_response["commit_sha"] = "LLM_GEN_FAILED"
        notify_evaluator(task_params["evaluation_url"], failure_response)
        return

    # --- 3. Branching (Multi-Round Logic) ---
    target_branch = "main" if round_num == 1 else f"round-{round_num}"
    try:
        # Create or switch to the target branch
        run_git_command(["git", "checkout", "-b", target_branch], local_repo_path, pat)
        
        # Configure identity (needed before commit)
        run_git_command(["git", "config", "user.name", GITHUB_USERNAME], local_repo_path, pat)
        run_git_command(["git", "config", "user.email", task_params.get("email")], local_repo_path, pat)

    except Exception as e:
        logging.error(f"Branching/Config failed: {e}")
        cleanup(local_repo_path)
        failure_response["commit_sha"] = "GIT_BRANCH_FAILED"
        notify_evaluator(task_params["evaluation_url"], failure_response)
        return


<<<<<<< HEAD
    # --- 4. Write Files (The Generalized I/O) ---
    try:
        # Clear existing files to ensure only new content is present (optional, but clean)
        # shutil.rmtree(os.path.join(local_repo_path, "*")) 
        
        # Write the main LLM output file
        with open(os.path.join(local_repo_path, main_file_name), "w") as f:
            f.write(llm_output["code_content"]) 

        # Write/Overwrite boilerplate files
        with open(os.path.join(local_repo_path, "README.md"), "w") as f:
            f.write(llm_output["readme_content"]) 
        with open(os.path.join(local_repo_path, "LICENSE"), "w") as f:
            f.write(llm_output.get("license_content", "MIT License...")) 

        # 🚀 Attachment Handling (Decoding data URIs)
        for attachment in task_params.get("attachments", []):
            if attachment["url"].startswith("data:"):
                # Format: data:<mime-type>;base64,<data>
                try:
                    # Isolate the base64 data string
                    base64_data = attachment["url"].split(',')[1] 
                    binary_data = base64.b64decode(base64_data)
                    
                    attachment_path = os.path.join(local_repo_path, attachment["name"])
                    with open(attachment_path, "wb") as f:
                        f.write(binary_data)
                    logging.info(f"Saved attachment: {attachment['name']}")
                except Exception as e:
                    logging.error(f"Failed to decode/save attachment {attachment['name']}: {e}")

    except Exception as e:
        logging.error(f"File writing failed: {e}")
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
        logging.error(f"Deployment Push failed: {e}")
        cleanup(local_repo_path)
        failure_response["commit_sha"] = "GIT_PUSH_FAILED"
        notify_evaluator(task_params["evaluation_url"], failure_response)
        return
        
    # --- 6. Final Notification and Cleanup ---
    
    # Construct the FINAL required successful response payload
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
    logging.info(f"Task {task_name}, Round {round_num} successfully processed and deployed.")
=======
    return html_content, readme_content, license_content
>>>>>>> 6fd7a63d88d24532ab83208d3d5c438aeb46b6af
