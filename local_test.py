import requests
import json
import os

# --- Configuration for Local Test ---

# The URL where Uvicorn is running
LOCAL_URL = "http://127.0.0.1:8000/api-endpoint"

# NOTE: Set your GITHUB_PAT here for local testing only! 
# Remember to delete this line or comment it out before moving the file.
# os.environ["GITHUB_PAT"] = "ghp_5oN1V..." 

# Your modified payload that passes validation (including 'secret' and 'signature')
TEST_PAYLOAD = {
    "email": "local@test.com",
    "secret": "Hris@tds_proj1_term3",
    "task": "LOCAL-TEST-001",
    "round": 1,
    "nonce": "LOCAL-NONCE-456",
    "brief": "Generate a simple HTML file with the text 'Local Test Success'.",
    "checks": ["Local check for text"],
    "evaluation_url": "http://127.0.0.1:8000/dummy-eval", # Use a dummy URL
    "attachments": [],
    "signature": "PLACEHOLDER_FOR_TESTING" 
}
# --- End Configuration ---

def run_local_test():
    """Sends the POST request to the local FastAPI server."""
    print(f"--- Sending POST request to {LOCAL_URL} ---")
    
    # 1. Start Uvicorn separately in your terminal: `uvicorn main:app --reload`
    
    try:
        response = requests.post(
            LOCAL_URL,
            json=TEST_PAYLOAD,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"\n✅ Server Status: {response.status_code} {response.reason}")
        
        # FastAPI is designed to return 200 even on failure with a custom JSON message
        if response.status_code == 200:
            print("Response Body (Success/Failure Message):")
            print(json.dumps(response.json(), indent=4))
        else:
            print("Response Body (Error Details):")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("\n🛑 ERROR: Could not connect to the server.")
        print("Please ensure Uvicorn is running in another terminal:")
        print("uvicorn main:app --reload")
    except Exception as e:
        print(f"\n🛑 An unexpected error occurred: {e}")

if __name__ == "__main__":
    run_local_test()