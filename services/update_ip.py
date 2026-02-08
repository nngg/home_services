import os
import requests
import json
import time
import shutil
import stat
from git import Repo, GitCommandError

# --- Configuration ---
# It's highly recommended to use environment variables for sensitive data.
GITHUB_TOKEN = os.environ.get("GITHUB_PAT")
# e.g., "your_username/your_repository"
REPO_FULL_NAME = os.environ.get("GITHUB_REPO_FULL_NAME")

# Local path to clone the repository
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_REPO_PATH = os.path.join(SCRIPT_DIR, "repo_clone")
CONFIG_FILE_PATH = os.path.join(LOCAL_REPO_PATH, "web_page/config.json")
CHECK_INTERVAL_SECONDS = 300  # 10 minutes

def get_public_ip():
    """Fetches the public IP address from an external service."""
    try:
        print("Fetching public IP address...")
        response = requests.get("https://api.ipify.org?format=json", timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        ip_data = response.json()
        print(f"Successfully fetched public IP: {ip_data['ip']}")
        return ip_data["ip"]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching public IP: {e}")
        return None

def update_github_config(new_ip, force_update=False):
    """Clones/pulls a repo, updates a JSON file with the new IP, and pushes the change."""
    repo_url = f"https://{GITHUB_TOKEN}@github.com/{REPO_FULL_NAME}.git"
    repo = None  # Initialize repo to None
    
    try:
        # Clone the repo if it doesn't exist locally, otherwise pull changes
        if not os.path.exists(LOCAL_REPO_PATH):
            print(f"Cloning repository {REPO_FULL_NAME}...")
            repo = Repo.clone_from(repo_url, LOCAL_REPO_PATH)
        else:
            repo = Repo(LOCAL_REPO_PATH)
            
        # Configure git identity to prevent "Please tell me who you are" errors
        with repo.config_writer() as git_config:
            git_config.set_value("user", "email", "update-bot@example.com")
            git_config.set_value("user", "name", "IP Update Bot")

        print("Pulling latest changes from the repository...")
        origin = repo.remote(name="origin")
        origin.set_url(repo_url)
        origin.pull()

        # Read the current config file
        try:
            with open(CONFIG_FILE_PATH, "r") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # If file doesn't exist or is invalid, create a new structure
            print(f"'{os.path.basename(CONFIG_FILE_PATH)}' not found or invalid. Creating a new one.")
            config = {}

        # Check if the IP needs updating to avoid unnecessary commits
        if not force_update and config.get("public_ip") == new_ip:
            print("IP address is already up-to-date. No changes needed.")
            return
        
        if force_update and config.get("public_ip") == new_ip:
            print("Force update enabled: Proceeding with update check even if IP hasn't changed.")

        # Update the IP and write back to the file
        if config.get("public_ip") != new_ip:
            print(f"IP has changed. Updating config from '{config.get('public_ip')}' to '{new_ip}'.")
        else:
            print(f"IP {new_ip} is unchanged, but force update is active. Updating config file.")

        config["public_ip"] = new_ip
        config["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
        with open(CONFIG_FILE_PATH, "w") as f:
            json.dump(config, f, indent=4)

        # Commit and push the changes
        repo.index.add([CONFIG_FILE_PATH])
        commit_message = f"feat: Update public IP to {new_ip}"
        repo.index.commit(commit_message)
        
        print("Pushing changes to GitHub...")
        origin.push()
        repo.close()
        print("Successfully pushed IP update to GitHub.")

    except GitCommandError as e:
        if "nothing to commit" in str(e).lower():
            print("Git reported nothing to commit (files identical).")
        else:
            print(f"An error occurred with Git: {e}")
            print("Error 128 often indicates authentication failure or a corrupt repository lock.")
            print("Attempting to remove the local repository clone to force a fresh start...")
            try:
                # ** THE FIX **: Explicitly close the repo object to release file handles before deletion.
                if repo:
                    repo.close()

                if os.path.exists(LOCAL_REPO_PATH):
                    def remove_readonly(func, path, _):
                        os.chmod(path, stat.S_IWRITE)
                        func(path)
                    shutil.rmtree(LOCAL_REPO_PATH, onerror=remove_readonly)
                    print("Repository removed. The next run will re-clone it.")
            except Exception as cleanup_error:
                print(f"Failed to remove repository automatically: {cleanup_error}")
                print(f"Please manually delete the folder: {LOCAL_REPO_PATH}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def main():
    """Main loop to periodically check and update the IP address."""
    if not GITHUB_TOKEN or not REPO_FULL_NAME:
        print("Error: GITHUB_PAT and GITHUB_REPO_FULL_NAME environment variables must be set.")
        print("Please set them before running the script.")
        return

    first_run = True
    while True:
        print("\n--- Starting IP Check ---")
        current_ip = get_public_ip()
        if current_ip:
            update_github_config(current_ip, force_update=first_run)
            first_run = False
        
        print(f"--- Check complete. Waiting for {CHECK_INTERVAL_SECONDS / 60:.0f} minutes... ---")
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
