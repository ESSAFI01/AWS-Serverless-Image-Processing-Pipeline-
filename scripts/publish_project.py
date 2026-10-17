"""Publish the explicit source-file list to the user's empty public repository.

Run manually in normal PowerShell after local verification. No AWS calls.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REMOTE = "https://github.com/ESSAFI01/AWS-Serverless-Image-Processing-Pipeline-.git"


def git(*args, capture=False, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, check=check,
                          capture_output=capture, text=True)


def main():
    if (ROOT / ".git").exists():
        raise SystemExit("This folder already has Git history. Stop and use its existing workflow; nothing was changed.")
    paths = (ROOT / "scripts/repository-files.txt").read_text().splitlines()
    for name in paths:
        target = (ROOT / name).resolve()
        if not target.is_relative_to(ROOT) or not target.is_file():
            raise SystemExit("Missing or unsafe publication path: " + name)
    if not git("config", "user.name", capture=True, check=False).stdout.strip() or not git(
        "config", "user.email", capture=True, check=False
    ).stdout.strip():
        raise SystemExit("Configure your own Git author name and email first, then rerun. No files were uploaded.")
    refs = git("ls-remote", REMOTE, capture=True).stdout.strip()
    if refs:
        raise SystemExit("The remote is no longer empty. Stop to reconcile its history; nothing was changed.")
    git("init", "-b", "main")
    git("remote", "add", "origin", REMOTE)
    git("add", "--", *paths)
    staged = git("diff", "--cached", "--name-only", "-z", capture=True).stdout
    if set(staged.rstrip("\0").split("\0")) != set(paths):
        raise SystemExit("Unexpected staged-file list; inspect Git status before committing.")
    git("commit", "-m", "Implement Project 2 serverless image processing pipeline")
    git("push", "-u", "origin", "main")
    print("Published the selected source files. No AWS resources were created.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit("Git command failed. Inspect the message and local Git status; no force-push was attempted.")
    except FileNotFoundError:
        raise SystemExit("Git is not available in this PowerShell session.")
