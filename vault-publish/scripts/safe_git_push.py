# -*- coding: utf-8 -*-
"""
Windows環境下で堅牢にGit pushを実行するためのリトライ付きユーティリティスクリプト。
接続リセットや一時的なネットワーク瞬断時に指数バックオフで自動再試行する。
"""
import subprocess
import time
import sys
from pathlib import Path

def run_git_push(repo_path: str, max_retries: int = 8, delay: float = 4.0) -> bool:
    repo = Path(repo_path)
    if not repo.exists():
        print(f"Error: Repository path '{repo_path}' does not exist.", file=sys.stderr)
        return False
    
    # Check if any remote is configured
    remote_res = subprocess.run(["git", "-C", str(repo), "remote"], capture_output=True, text=True)
    remotes = remote_res.stdout.split()
    if not remotes:
        print(f"Info: No remote repository configured for '{repo}'. Skipping push (local-only repository).")
        return True

    target_remote = "origin" if "origin" in remotes else remotes[0]

    # Detect current branch dynamically
    branch_res = subprocess.run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    branch = branch_res.stdout.strip() if branch_res.returncode == 0 and branch_res.stdout.strip() else "main"
    
    cmd = ["git", "-C", str(repo), "push", target_remote, branch]
    
    for attempt in range(1, max_retries + 1):
        print(f"--- Git Push Attempt {attempt}/{max_retries} ---")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.stdout:
            print(res.stdout.strip())
        if res.stderr:
            print(res.stderr.strip())
            
        if res.returncode == 0:
            print("Git push succeeded successfully!")
            return True
            
        if attempt < max_retries:
            wait_time = delay * attempt
            print(f"Push failed (code {res.returncode}). Retrying in {wait_time}s...")
            time.sleep(wait_time)
            
    print("Git push failed after all retry attempts.", file=sys.stderr)
    return False

if __name__ == "__main__":
    target_repo = sys.argv[1] if len(sys.argv) > 1 else "."
    success = run_git_push(target_repo)
    sys.exit(0 if success else 1)
