"""CI-resident runner for the Claude Code review subagents.

Mirrors `.claude/agents/{smc-strategy-reviewer,risk-safety-auditor}.md`
(interactive Claude Code subagents) so the same review runs headlessly on
PRs that touch risk-critical or SMC-strategy paths. Read-only: posts a
review comment on the PR, never writes code or auto-merges.

Usage:
    python scripts/ci/claude_review.py <agent-name> <pr-number>

Requires: ANTHROPIC_API_KEY, GH_TOKEN env vars.
"""
from __future__ import annotations

import os
import subprocess
import sys

import anthropic

AGENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", ".claude", "agents")

# Cap the diff sent to the model — large PRs get truncated rather than
# failing outright or blowing the context budget.
MAX_DIFF_CHARS = 60_000


def load_agent_prompt(agent_name: str) -> str:
    path = os.path.join(AGENTS_DIR, f"{agent_name}.md")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def get_pr_diff(base_ref: str) -> str:
    subprocess.run(["git", "fetch", "origin", base_ref], check=True)
    merge_base = subprocess.run(
        ["git", "merge-base", f"origin/{base_ref}", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "diff", merge_base, "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n... [diff truncated for length] ..."
    return diff


def run_review(agent_name: str, diff: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    system_prompt = load_agent_prompt(agent_name)
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": (
                "Review the following PR diff per your instructions above. "
                "Use the exact output format specified in your agent definition.\n\n"
                f"```diff\n{diff}\n```"
            ),
        }],
    )
    return "".join(block.text for block in message.content if block.type == "text")


def post_pr_comment(pr_number: str, agent_name: str, body: str) -> None:
    comment = f"## 🤖 Claude Code — `{agent_name}` (automated review)\n\n{body}"
    subprocess.run(
        ["gh", "pr", "comment", pr_number, "--body", comment],
        check=True,
    )


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: claude_review.py <agent-name> <pr-number>", file=sys.stderr)
        return 2
    agent_name, pr_number = sys.argv[1], sys.argv[2]
    base_ref = os.environ.get("GITHUB_BASE_REF", "master")

    diff = get_pr_diff(base_ref)
    if not diff.strip():
        print("No diff to review — skipping.")
        return 0

    review = run_review(agent_name, diff)
    post_pr_comment(pr_number, agent_name, review)
    print(review)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
