#!/usr/bin/env python3
"""
Efloud-bot Git Hook Setup Script
Automatically installs the post-commit git hook to auto-update the Graphify knowledge graph.
"""

import os
import sys

def main():
    print("==> Checking repository structure...")
    git_dir = os.path.join(os.getcwd(), ".git")
    
    if not os.path.exists(git_dir):
        print("ERROR: Not in a git repository root. Please run this script from the project root.")
        sys.exit(1)
        
    hooks_dir = os.path.join(git_dir, "hooks")
    if not os.path.exists(hooks_dir):
        os.makedirs(hooks_dir)
        
    post_commit_path = os.path.join(hooks_dir, "post-commit")
    
    # post-commit bash script structure
    hook_content = """#!/bin/sh
# Efloud-bot post-commit hook: Auto-updates Graphify AST knowledge graph
echo "=========================================================="
echo "==> Auto-updating Graphify AST Knowledge Graph..."
echo "=========================================================="

if [ -f ".venv/Scripts/python" ]; then
    .venv/Scripts/python -m graphify update . --no-cluster
elif [ -f ".venv/bin/python" ]; then
    .venv/bin/python -m graphify update . --no-cluster
else
    python3 -m graphify update . --no-cluster
fi

echo "==> Graphify update successfully completed!"
echo "=========================================================="
"""

    print(f"==> Writing hook to {post_commit_path}...")
    with open(post_commit_path, "w", newline="\n") as f:
        f.write(hook_content)
        
    # On Unix/Linux/macOS (and under Git Bash on Windows), make it executable
    if sys.platform != "win32":
        try:
            os.chmod(post_commit_path, 0o755)
            print("==> Successfully marked hook as executable (chmod +x)")
        except Exception as e:
            print(f"Warning: Failed to chmod +x hook script: {e}")
    else:
        # On Windows, Git uses standard sh.exe, so having the shebang #!/bin/sh is sufficient.
        print("==> Registered hook on Windows system.")

    print("\n[SUCCESS] Git hook setup is complete. Every commit will now auto-update the graphify knowledge graph.")

if __name__ == "__main__":
    main()
