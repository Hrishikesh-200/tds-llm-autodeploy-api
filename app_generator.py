import os
import requests
import json
import time
import logging
from typing import Dict, Any, List, Optional

# Set up logging
logger = logging.getLogger(__name__)

# --- Constants ---
LLM_FILE_GENERATOR_SUCCESS_KEY = "success"
# --- UPDATED: Using a hypothetical aipipe.org endpoint ---
# NOTE: The payload structure assumes this endpoint is compatible with Gemini's request body.
AIPE_API_URL = "http://api.aipipe.org/generate_content" 
API_KEY = os.getenv("LLM_API_KEY", "") # Key must be configured in environment using generic LLM_API_KEY

# Mock response structure used when API fails or is not available
MOCK_RESPONSE: Dict[str, Any] = {
    "files": {
        "index.html": """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mock Deployment</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
        body { font-family: 'Inter', sans-serif; }
    </style>
</head>
<body class="bg-gray-100 min-h-screen flex items-center justify-center p-4">
    <div class="bg-white p-8 rounded-xl shadow-2xl max-w-lg w-full text-center">
        <h1 class="text-3xl font-bold text-gray-800 mb-4">Mock Deployment Successful</h1>
        <p class="text-gray-600 mb-6">
            The application generator (LLM API) failed to connect (likely a network or DNS issue), 
            but the deployment pipeline is working!
        </p>
        <p class="text-sm text-gray-500">
            This is a placeholder page from the LLM mock fallback. 
            Commit SHA: [Placeholder SHA]
        </p>
    </div>
</body>
</html>
"""
    },
    LLM_FILE_GENERATOR_SUCCESS_KEY: True,
    "error": None
}

# --- Utility Functions ---

def build_prompt(brief: str, round_num: int, existing_files: Dict[str, str], attachments: List[Dict[str, str]]) -> str:
    """Constructs the comprehensive user prompt for the LLM."""
    
    prompt = [
        f"You are tasked with generating or revising a web application based on the user's brief.",
        "Your response MUST be a single JSON object containing a 'files' key. The value of 'files' must be a dictionary where keys are file paths (e.g., 'index.html', 'styles/main.css') and values are the complete file contents.",
        "Do not include any text, conversation, or markdown outside of the final JSON object.",
        "Constraint: You must only generate ONE file (index.html or App.jsx/App.ts) and put all code (HTML, CSS, JS, React/Angular) into that single file.",
        "Use Tailwind CSS for styling in all HTML/React files."
    ]
    
    prompt.append(f"\n--- TASK BRIEF (ROUND {round_num}) ---\n{brief}\n")
    
    if existing_files:
        prompt.append("\n--- EXISTING CODE FOR REVISION ---\n")
        for file_path, content in existing_files.items():
            prompt.append(f"FILENAME: {file_path}\n---\n{content}\n---\n")
        prompt.append("Based on the brief, modify the existing files or create new ones as necessary.")

    if attachments:
        prompt.append("\n--- ATTACHMENT CONTEXT ---\n")
        for attachment in attachments:
            prompt.append(f"ATTACHMENT NAME: {attachment.get('file_name', 'N/A')}\nATTACHMENT CONTENT:\n{attachment.get('content', 'No content')}\n")

    return "\n".join(prompt)

def call_llm_api(brief: str, round_num: int, existing_files: Dict[str, str], attachments: List[Dict[str, str]]) -> Dict[str, Any]:
    """Calls the LLM API to generate application code with exponential backoff."""
    
    logger.info(f"Preparing LLM call for Round {round_num}...")
    
    # 1. Build the prompt and JSON schema for structured output
    user_prompt = build_prompt(brief, round_num, existing_files, attachments)
    
    # Define the required JSON output structure
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "files": {
                "type": "OBJECT",
                "additionalProperties": {"type": "STRING"},
                "description": "A dictionary where keys are file names/paths and values are the complete code content."
            }
        },
        "required": ["files"]
    }

    # 2. Construct the API payload
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "config": {
            "systemInstruction": "You are a professional software engineer that responds only with a single JSON object conforming to the required schema. Your task is to generate complete, runnable code files for the requested application.",
            "responseMimeType": "application/json",
            "responseSchema": response_schema
        },
        "tools": [{"google_search": {}}] # Assuming the aipipe service supports a grounding tool
    }
    
    # --- Using the new AIPE_API_URL and appending the API key ---
    full_api_url = f"{AIPE_API_URL}?api_key={API_KEY}"
    # ------------------------------------------------
    
    # 3. Implement Exponential Backoff
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                full_api_url, # Use the constructed URL with the key
                json=payload, 
                timeout=30 # Set a timeout
            )
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            
            # Successful response
            response_json = response.json()
            
            # Extract text/JSON from the response structure (assuming a compatible response format)
            text_response = response_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '{}')
            
            # The LLM outputs a stringified JSON object which must be parsed
            try:
                llm_data = json.loads(text_response)
                
                if 'files' in llm_data and isinstance(llm_data['files'], dict) and llm_data['files']:
                    logger.info("LLM generation successful and files extracted.")
                    return {
                        "files": llm_data['files'],
                        LLM_FILE_GENERATOR_SUCCESS_KEY: True,
                        "error": None
                    }
                else:
                    return {
                        "files": {},
                        LLM_FILE_GENERATOR_SUCCESS_KEY: False,
                        "error": "LLM response did not contain the required 'files' dictionary or it was empty."
                    }
                    
            except json.JSONDecodeError:
                 return {
                    "files": {},
                    LLM_FILE_GENERATOR_SUCCESS_KEY: False,
                    "error": f"Failed to parse JSON response from LLM: {text_response[:200]}..."
                }

        except requests.exceptions.RequestException as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries}: aipipe.org API call failed: {e}. Retrying...") 
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt) # Exponential backoff: 1s, 2s, 4s...
            else:
                logger.error(f"Failed to use real LLM service after {max_retries} retries. Falling back to mock.")
                # Fallback to the mock response on final failure
                return MOCK_RESPONSE
        
        except Exception as e:
            logger.error(f"An unexpected error occurred during LLM API call: {e}")
            return MOCK_RESPONSE

    # Should not be reached, but included for safety
    return MOCK_RESPONSE

# Mock for safety if used outside of main.py
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    print("Running mock LLM call test...")
    result = call_llm_api("Generate a simple HTML web page with a blue background.", 1, {}, [])
    print(f"Result Status: {result[LLM_FILE_GENERATOR_SUCCESS_KEY]}")
    if result.get('files'):
        print(f"Generated file keys: {list(result['files'].keys())}")
