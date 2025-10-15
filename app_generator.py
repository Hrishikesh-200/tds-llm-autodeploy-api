import logging
import requests
import json
import os
import time
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# --- Configuration for LLM API ---
# IMPORTANT: In a production environment, use environment variables for keys.
# Since the environment variable system is not available here, we leave it blank 
# as per instruction, relying on the runtime to provide it.
API_KEY = "" 
API_URL_BASE = "https://generativelanguage.googleapis.com/v1beta/models/"
MODEL_NAME = "gemini-2.5-flash-preview-05-20"


def call_llm_api(brief: str, attachments: List[Dict[str, str]], task_name: str) -> Dict[str, str]:
    """
    Implements the real logic to call the Gemini API and generate structured code.
    
    Returns a dictionary containing required keys: 'filename', 'code_content', 
    'readme_content', and 'license_content'.
    """
    logger.info(f"LLM: Calling model for brief: {brief[:50]}...")
    
    # 1. Define the desired structured output (Schema)
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "filename": {"type": "STRING", "description": "The primary file name (e.g., index.html)."},
            "code_content": {"type": "STRING", "description": "The complete, self-contained code content for the primary file."},
            "readme_content": {"type": "STRING", "description": "Markdown content for the README.md file."},
            "license_content": {"type": "STRING", "description": "Content for a simple MIT License file."}
        },
        "required": ["filename", "code_content", "readme_content"]
    }

    # 2. Define the System Prompt
    system_prompt = (
        "You are a world-class code generation assistant. "
        "Your task is to generate a single, complete web application (HTML, CSS, JS in one file) "
        "or a Python script based on the user's request. "
        "The output MUST strictly follow the provided JSON schema. "
        "Ensure the generated code is fully functional and adheres to best practices. "
        "Do not include any placeholders like '...' in the code_content."
    )
    
    # 3. Construct the API Payload
    user_parts = [{"text": brief}]
    
    # NOTE: Attachment handling logic for LLM vision/context would go here, 
    # but for simplicity, we assume the model handles text prompts first.
    
    payload = {
        "contents": [{"role": "user", "parts": user_parts}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": response_schema
        },
        # Assuming we don't need real-time search for code generation:
        # "tools": [{"google_search": {}}] 
    }

    # 4. Execute the API Call with Exponential Backoff
    url = f"{API_URL_BASE}{MODEL_NAME}:generateContent?key={API_KEY}"
    max_retries = 5
    delay = 1
    
    for i in range(max_retries):
        try:
            response = requests.post(url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload), timeout=60)
            response.raise_for_status()
            
            result = response.json()
            candidate = result.get('candidates', [{}])[0]
            
            if candidate and candidate.get('content') and candidate['content'].get('parts'):
                json_text = candidate['content']['parts'][0].get('text', '{}')
                
                # 5. Parse and Return the Structured Content
                try:
                    llm_data = json.loads(json_text)
                    # Ensure all required keys are present before returning
                    if all(key in llm_data for key in ["filename", "code_content", "readme_content"]):
                        return llm_data
                    else:
                        raise ValueError("LLM returned incomplete JSON data.")

                except json.JSONDecodeError:
                    logger.error(f"Failed to decode JSON from LLM: {json_text}")
                    raise Exception("LLM response was not valid JSON.")
            
            raise Exception("LLM returned empty or malformed response.")

        except requests.exceptions.RequestException as e:
            logger.error(f"API Request failed (Attempt {i+1}): {e}")
            if i < max_retries - 1:
                time.sleep(delay)
                delay *= 2
            else:
                raise Exception(f"Failed to call Gemini API after {max_retries} retries.")
        except Exception as e:
            # Catch exceptions from parsing or incomplete data
            raise e

    # This line should ideally not be reached
    raise Exception("An unexpected error occurred in LLM generation loop.")

    
    
