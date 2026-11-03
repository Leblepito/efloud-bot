#!/usr/bin/env python3
"""
Efloud-bot Git Hook Setup Script

Installs the post-commit hook that keeps the Graphify AST knowledge graph
current — but ONLY when Graphify is actually installed.

Graphify is an OPTIONAL local tool (not a bot dependency, not in
requirements.txt/constraints.txt, cloned under external_repos/). The hook must
therefore degrade cleanly: skipping is fine, claiming success for work that never
ran is not. The previous version printed "Graphify update successfully completed!"
unconditionally — on a machine without the module it reported success on every
commit while doing nothing.
"""

import os
import sys

HOOK_CONTENT = """#!/bin/sh
# Efloud-bot post-commit hook: auto-updates the Graphify AST knowledge graph.
# Graphify is OPTIONAL (not a bot dependency). A missing module or a failed run
# must never look like success, and must never affect the commit.

PY=""
if [ -x ".venv/Scripts/python" ]; then
    PY=".venv/Scripts/python"
elif [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
fi

if [ -z "$PY" ]; then
    echo "[graphify] skip: no python interpreter found"
    exit 0
fi

if ! "$PY" -c "import graphify" >/dev/null 2>&1; then
    echo "[graphify] skip: module not installed ($PY -m pip install -e external_repos/graphify)"
    exit 0
fi

echo "==> Updating Graphify AST knowledge graph..."
"$PY" -m graphify update . --no-cluster
rc=$?
if [ "$rc" -ne 0 ]; then
    echo "[graphify] update failed (exit $rc) — commit kept, knowledge graph may be stale" >&2
else
    echo "==> Graphify update completed."
fi
exit 0
"""


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

    print(f"==> Writing hook to {post_commit_path}...")
    with open(post_commit_path, "w", newline="\n") as f:
        f.write(HOOK_CONTENT)
        
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

    print("\n[SUCCESS] Git hook setup is complete. Commits update the graphify")
    print("          knowledge graph when Graphify is installed, and skip cleanly otherwise.")

if __name__ == "__main__":
    main()
