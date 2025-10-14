import os
import requests
from dotenv import load_dotenv

# --- Optional: load from .env if you're testing locally ---
# (Hugging Face automatically injects secrets, so this is only needed for local runs)
load_dotenv()

# --- Read environment variables ---
GITHUB_PAT = os.getenv("GITHUB_PAT")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")

print("=== GitHub Environment Test ===")
print(f"GITHUB_USERNAME: {GITHUB_USERNAME}")
print(f"GITHUB_PAT Found: {bool(GITHUB_PAT)}")

# --- Basic checks ---
if not GITHUB_PAT:
    print("\n❌ ERROR: GITHUB_PAT is missing! Make sure it's set in environment or .env file.")
    exit(1)

if not GITHUB_USERNAME:
    print("\n⚠️  WARNING: GITHUB_USERNAME not found. Set it to your GitHub username.")
    exit(1)

# --- Test API authentication with GitHub ---
print("\nTesting GitHub API connection...")

headers = {
    "Authorization": f"token {GITHUB_PAT}",
    "Accept": "application/vnd.github.v3+json"
}

response = requests.get("https://api.github.com/user", headers=headers)

if response.status_code == 200:
    data = response.json()
    print(f"✅ GitHub authentication successful! Logged in as: {data['login']}")
    print(f"Public repos: {data['public_repos']}")
else:
    print(f"❌ GitHub authentication failed: {response.status_code}")
    print(response.text)
