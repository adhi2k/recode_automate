import json
import time
import base64
import re
import os
from github import Github, InputGitTreeElement

CONFIG_FILE = "config.json"

def load_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def modify_readme(content, name, register_number, image_filename):
    # Decode if needed (PyGithub might return string if it's text, or base64)
    # The content passed here will be a string
    
    # Replace Name
    content = re.sub(r'###\s*Name:\s*.*', f'### Name: {name}', content, flags=re.IGNORECASE)
    # Replace Register Number
    content = re.sub(r'###\s*Register Number:\s*.*', f'### Register Number: {register_number}', content, flags=re.IGNORECASE)
    
    # Add Image at the end for PDF print
    image_tag = f"\n\n---\n\n## Print Output\n![Print Output]({image_filename})\n"
    if image_filename not in content:
        content += image_tag
        
    return content

def get_all_files(repo, branch="main"):
    """Recursively fetch all files from a repository."""
    contents = repo.get_contents("", ref=branch)
    files = []
    while contents:
        file_content = contents.pop(0)
        if file_content.type == "dir":
            contents.extend(repo.get_contents(file_content.path, ref=branch))
        else:
            files.append(file_content)
    return files

def process_repository(g, repo_config, config):
    college_repo_name = repo_config.get("college_repo")
    completed_repo_name = repo_config["completed_repo"]
    
    user = g.get_user()
    print(f"\n--- Processing: {completed_repo_name} ---")
    
    target_repo = None
    
    # Step 1: Fork college repo if provided
    if college_repo_name:
        print(f"Forking {college_repo_name}...")
        college_repo = g.get_repo(college_repo_name)
        target_repo = user.create_fork(college_repo)
        print("Waiting for fork to complete...")
        time.sleep(10) # Give GitHub some time to create the fork
    else:
        # If no college repo, assume the user already has a repo with the same name
        repo_name = completed_repo_name.split('/')[-1]
        target_repo = user.get_repo(repo_name)
    
    print(f"Target repository: {target_repo.full_name}")
    
    # Step 2: Fetch files from completed repository
    print(f"Fetching files from completed repo: {completed_repo_name}")
    completed_repo = g.get_repo(completed_repo_name)
    completed_branch = completed_repo.default_branch
    target_branch = target_repo.default_branch
    
    files = get_all_files(completed_repo, branch=completed_branch)
    
    # Prepare tree elements
    tree_elements = []
    
    for file_content in files:
        # Handle README.md specifically
        if file_content.name.lower() == "readme.md":
            print(f"Modifying {file_content.path}...")
            # Get decoded content
            raw_content = file_content.decoded_content.decode('utf-8')
            modified_content = modify_readme(
                raw_content, 
                config["name"], 
                config["register_number"], 
                os.path.basename(config["image_file_path"])
            )
            blob = target_repo.create_git_blob(modified_content, "utf-8")
            tree_elements.append(InputGitTreeElement(path=file_content.path, mode="100644", type="blob", sha=blob.sha))
        else:
            # For other files, we can just copy them over by creating a new blob with their content
            # (or if they are large, we might need a different approach, but this works for most assignments)
            try:
                content = file_content.decoded_content
                # If it's binary or text, create blob in base64
                encoded_content = base64.b64encode(content).decode('utf-8')
                blob = target_repo.create_git_blob(encoded_content, "base64")
                tree_elements.append(InputGitTreeElement(path=file_content.path, mode="100644", type="blob", sha=blob.sha))
            except Exception as e:
                print(f"Skipping {file_content.path} due to error: {e}")
                
    # Step 3: Add the image file
    image_path = config["image_file_path"]
    if os.path.exists(image_path):
        print(f"Adding image: {image_path}")
        with open(image_path, "rb") as img_file:
            img_content = img_file.read()
            encoded_img = base64.b64encode(img_content).decode('utf-8')
            blob = target_repo.create_git_blob(encoded_img, "base64")
            # We put the image at the root
            tree_elements.append(InputGitTreeElement(path=os.path.basename(image_path), mode="100644", type="blob", sha=blob.sha))
    else:
        print(f"WARNING: Image file '{image_path}' not found locally!")
        
    # Step 4: Create Tree and Commit
    print("Creating commit...")
    # Get the latest commit on the target branch
    ref = target_repo.get_git_ref(f"heads/{target_branch}")
    base_commit = target_repo.get_git_commit(ref.object.sha)
    base_tree = base_commit.tree
    
    # Create new tree with all elements
    new_tree = target_repo.create_git_tree(tree_elements, base_tree)
    
    # Create commit
    commit_message = "Automated upload of completed assignment"
    new_commit = target_repo.create_git_commit(commit_message, new_tree, [base_commit])
    
    # Update reference
    ref.edit(new_commit.sha)
    
    print("Commit pushed successfully!")
    print(f"Repository URL: {target_repo.html_url}")
    
    # Try to find GitHub Pages URL
    # GitHub pages usually follow username.github.io/repo_name
    pages_url = f"https://{user.login}.github.io/{target_repo.name}"
    print(f"Possible GitHub Pages URL: {pages_url}")
    

def main():
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: {CONFIG_FILE} not found!")
        return
        
    config = load_config()
    
    token = config.get("github_token")
    if not token or token == "YOUR_GITHUB_PERSONAL_ACCESS_TOKEN":
        print("Error: Please set your 'github_token' in config.json")
        print("You can generate one at: https://github.com/settings/tokens (Needs 'repo' scope)")
        return
        
    g = Github(token)
    
    try:
        user = g.get_user()
        print(f"Authenticated as: {user.login}")
    except Exception as e:
        print(f"Authentication failed: {e}")
        return
        
    for repo_config in config.get("repositories", []):
        try:
            process_repository(g, repo_config, config)
        except Exception as e:
            print(f"Error processing repository: {e}")

if __name__ == "__main__":
    main()
