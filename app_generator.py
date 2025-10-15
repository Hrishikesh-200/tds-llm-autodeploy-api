import logging
from typing import Dict, Any, List

# WARNING: This entire file now contains MOCK logic to avoid external API calls (and billing issues).
# This is for testing the deployment pipeline only.

def call_llm_api(brief: str, attachments: List[Dict[str, str]], task_name: str) -> Dict[str, str]:
    """
    MOCK function: Simulates the LLM's structured output.
    It returns different code based on keywords in the brief to make testing realistic.
    """
    logging.info(f"MOCK LLM: Simulating model response for brief: {brief[:80]}...")
    
    brief_lower = brief.lower()
    
    # ⚠️ MOCK Logic 
    if "image" in brief_lower or "picture" in brief_lower:
        filename = "index.html"
        code_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>LLM Generated Image Placeholder</title>
</head>
<body>
    <div style="text-align: center; padding: 50px; border: 2px dashed #007BFF; margin: 20px;">
        <h2>LLM Task: {task_name}</h2>
        <p>Image generation simulated. This HTML file acts as the output placeholder.</p>
        <p>Prompt: <strong>{brief}</strong></p>
    </div>
</body>
</html>
"""
    elif "calculator" in brief_lower or "script" in brief_lower or "python" in brief_lower:
        filename = "solution.py"
        code_content = f"""
# MOCK Python Solution for {task_name}
# Task Brief: {brief}

def solve_mock_problem(a: int, b: int) -> int:
    # This simulates a computation that the LLM would write.
    return a + b + 42 

if __name__ == "__main__":
    result = solve_mock_problem(10, 5)
    print(f"Mock result: {{result}}")
"""
    else: # Default HTML file
        filename = "index.html"
        code_content = f"<html><body><h1>MOCK LLM Solution for: {task_name}</h1><p>Prompt: {brief}</p><p>Deployment successful!</p></body></html>"

    # Common boilerplate files
    readme_content = f"# Solution for {task_name}\n\n## Task Brief\n{brief}\n\n## Files\nPrimary file generated: {filename}\n\n**NOTE: This is a MOCK response to test the deployment pipeline.**"
    license_content = "MIT License\n(MOCK Content)"
    
    # Return the structured dictionary that process_task expects
    return {
        "filename": filename,
        "code_content": code_content,
        "readme_content": readme_content,
        "license_content": license_content
    }


