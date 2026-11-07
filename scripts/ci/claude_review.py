"""CI-resident runner for the Claude Code review subagents.

Agent prompts live in `scripts/ci/agents/{smc-strategy-reviewer,risk-safety-auditor}.md`
(tracked in git; `.claude/` is gitignored, so it is absent on the CI runner) so the review runs headlessly on
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

AGENTS_DIR = os.path.join(os.path.dirname(__file__), "agents")

# Cap the diff sent to the model — large PRs get truncated rather than
# failing outright or blowing the context budget.
MAX_DIFF_CHARS = 60_000


def load_agent_prompt(agent_name: str) -> str:
    path = os.path.join(AGENTS_DIR, f"{agent_name}.md")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def get_pr_diff(pr_number: str) -> str:
    # Read the PR diff as data through the API — the workflow runs on
    # pull_request_target with the base branch checked out, and PR code must
    # never be checked out or executed next to ANTHROPIC_API_KEY (T-20261107-08).
    diff = subprocess.run(
        ["gh", "pr", "diff", pr_number],
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

    try:
        diff = get_pr_diff(pr_number)
    except subprocess.CalledProcessError as exc:
        # The API refuses very large diffs (HTTP 406) — say so instead of failing.
        reason = (exc.stderr or "").strip()[:200] or f"exit {exc.returncode}"
        post_pr_comment(pr_number, agent_name,
                        f"⚠️ Could not fetch the PR diff (`gh pr diff`: {reason}). "
                        "The diff is likely too large for automated review — manual review required.")
        return 0
    if not diff.strip():
        print("No diff to review — skipping.")
        return 0

    review = run_review(agent_name, diff)
    post_pr_comment(pr_number, agent_name, review)
    print(review)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
