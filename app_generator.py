import requests
import json
import logging
from typing import List, Dict, Any, Optional

# --- Configuration ---
# NOTE: Replace "YOUR_AIPipe_TOKEN" with your actual token from https://aipipe.org
API_PIPE_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6IjIyZjEwMDE0MzhAZHMuc3R1ZHkuaWl0bS5hYy5pbiJ9.KF_SIjaxP9x77fgehKqOKTP1vax4steV1U3V5gzS4BY" 
AIPipe_ENDPOINT = "https://api.aipipe.org/v1/generate" # Example endpoint based on instructor's reference
LLM_MODEL = "gpt-4-turbo" # Assuming a high-capability model for code generation

# --- Logging ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Type Definitions (Assuming main.py's IncomingTask structure is available) ---
# We define a minimal Attachment model here to avoid circular dependency
class Attachment(Dict):
    name: str
    url: str

# --- Core LLM Generation Logic ---

def _construct_aipipe_prompt(brief: str, round_num: int, attachments: Optional[List[Attachment]]) -> str:
    """
    Constructs a detailed prompt for the LLM based on the task round.
    """
    context = ""
    
    if round_num == 1:
        # Round 1: New Application Creation
        system_prompt = (
            "You are a world-class web application developer. Your task is to generate a complete, single-file HTML application "
            "that fulfills the user's brief. The HTML file must be fully self-contained (CSS in <style>, JS in <script>). "
            "You MUST also generate a comprehensive README.md. The output MUST be a JSON list of files."
        )
        context = "Generate the complete, runnable HTML application and necessary supporting files (README.md, LICENSE)."
    
    elif round_num == 2:
        # Round 2: Application Revision/Update
        system_prompt = (
            "You are a master refactorer. The user has provided a brief to update the existing application. "
            "You MUST only generate the files that need to be changed (e.g., just the updated index.html) to fulfill the new brief. "
            "The output MUST be a JSON list of files."
        )
        # In a real system, we'd pass the old index.html content here. 
        # For simplicity, we assume the LLM knows the context of the previous task.
        context = (
            "Update the existing web application to incorporate the following new requirements. "
            "Focus only on modifying and returning the file(s) that need changes (e.g., 'index.html')."
        )
    
    # Format attachments for the prompt
    attachments_list = "\n".join([f"- Name: {a.get('name')}, URL: {a.get('url')}" for a in attachments]) if attachments else "None"

    # Combine all parts into the final user query structure
    full_prompt = f"""
SYSTEM INSTRUCTION: {system_prompt}

TASK ROUND: {round_num}
BRIEF: {brief}
ATTACHMENTS:
{attachments_list}

{context}
Your output MUST be a valid JSON array of objects, where each object has 'path' and 'content' keys.
Example output format:
[
    {{"path": "index.html", "content": "<!-- ... HTML code ... -->"}},
    {{"path": "README.md", "content": "# Project"}},
    {{"path": "data.csv", "content": "col1,col2\\n1,2"}}
]
"""
    return full_prompt.strip()

def _call_aipipe_service(prompt: str) -> str:
    """
    Handles the actual API call to AIPipe, including authentication and response handling.
    
    Returns the raw JSON string response from the LLM.
    """
    if API_PIPE_TOKEN == "YOUR_AIPipe_TOKEN":
        logger.critical("API_PIPE_TOKEN not set. Running MOCK instead.")
        return "" # Will trigger the mock fallback in call_llm_api

    headers = {
        "Authorization": f"Bearer {API_PIPE_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        # Instruct the model to return JSON (or another necessary config for AIPipe)
        "response_format": {"type": "json_object"} 
    }
    
    try:
        response = requests.post(AIPipe_ENDPOINT, headers=headers, json=payload, timeout=60)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        
        # AIPipe's response structure might need parsing to extract the LLM's text output
        response_data = response.json()
        
        # Example: Assuming the LLM's JSON text is inside 'generated_text'
        llm_output_json_string = response_data.get('generated_text', response.text)
        
        return llm_output_json_string
        
    except requests.exceptions.RequestException as e:
        logger.error(f"AIPipe API call failed: {e}")
        raise RuntimeError(f"AIPipe API communication error: {e}")

def call_llm_api(brief: str, round_num: int, attachments: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    """
    Main function to orchestrate the generation, calling AIPipe or the mock.
    """
    prompt = _construct_aipipe_prompt(brief, round_num, attachments)
    
    try:
        # Attempt to call the real service
        raw_json_output = _call_aipipe_service(prompt)
        if raw_json_output:
            # Attempt to parse the LLM's JSON output
            files = json.loads(raw_json_output)
            if not isinstance(files, list):
                 raise ValueError("LLM response was valid JSON but not a list of files.")
            logger.info(f"Successfully parsed {len(files)} files from AIPipe response.")
            return files
        
    except Exception as e:
        logger.warning(f"Failed to use real AIPipe service or parse response: {e}. Falling back to mock.")
        # Fall-through to the mock if the real call fails or returns empty

    # --- MOCK IMPLEMENTATION (Fallback) ---

    if round_num == 1:
        # Mock Round 1: Full creation
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.tailwindcss.com"></script>
    <title>LLM Task: {brief[:40]}...</title>
</head>
<body class="bg-gray-100 min-h-screen flex items-center justify-center">
    <div class="bg-white p-8 rounded-xl shadow-2xl max-w-lg w-full text-center border-t-4 border-green-500">
        <h1 class="text-3xl font-extrabold text-green-700 mb-4">Round 1 Generation Success!</h1>
        <p class="text-gray-600 mb-6">This is the complete application generated for your initial brief:</p>
        <div class="p-4 bg-gray-50 border border-gray-200 rounded-lg text-left">
            <strong class="block text-lg text-gray-800">Brief:</strong>
            <p class="text-sm italic text-gray-500 mt-1">"{brief}"</p>
        </div>
        <p class="mt-6 text-sm text-gray-500">LLM Generation simulated. Ready for Round 2.</p>
    </div>
</body>
</html>
        """
        return [
            {"path": "index.html", "content": html_content},
            {"path": "README.md", "content": f"# Project Generated in Round 1\n\nTask: {brief}"},
            {"path": "LICENSE", "content": "Generated MIT License Placeholder"}
        ]
        
    elif round_num == 2:
        # Mock Round 2: Revision (only return the file that changes)
        updated_html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.tailwindcss.com"></script>
    <title>LLM Task: REVISED - {brief[:30]}...</title>
</head>
<body class="bg-yellow-100 min-h-screen flex items-center justify-center">
    <div class="bg-white p-8 rounded-xl shadow-2xl max-w-lg w-full text-center border-t-4 border-yellow-500">
        <h1 class="text-3xl font-extrabold text-yellow-700 mb-4">Round 2 Revision Applied!</h1>
        <p class="text-gray-600 mb-6">The application has been successfully updated according to the new brief:</p>
        <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg text-left">
            <strong class="block text-lg text-gray-800">New Brief:</strong>
            <p class="text-sm italic text-gray-500 mt-1">"{brief}"</p>
        </div>
        <p class="mt-6 text-sm text-gray-500">LLM Revision simulated. The border color is yellow to confirm the update.</p>
    </div>
</body>
</html>
        """
        return [
            {"path": "index.html", "content": updated_html_content}
        ]
    
    raise ValueError(f"Unsupported task round: {round_num}")

