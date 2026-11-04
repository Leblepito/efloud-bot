"""Guards for the shared multi-model workspace (collab/).

The repo is PUBLIC and three models (claude-code, hermes, abacus) write here
concurrently, so the protocol in collab/README.md is checked mechanically:
required files exist, task headers follow the lifecycle, log VPS lines use the
fixed vocabulary, and no raw data lands in git. Skill quarantine is covered by
test_skills_incubator.py.
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COLLAB = ROOT / "collab"
TASKS_DIR = COLLAB / "tasks"
MODELS = {"claude-code", "hermes", "abacus"}
ACTORS = MODELS | {"operator", "any"}
TASK_STATUSES = {"open", "claimed", "in-review", "blocked", "done", "dropped"}
TASK_PATH_RE = re.compile(r"^(open|done)/T-\d{8}-\d{2}-[a-z0-9-]+\.md$")
TASK_ID_RE = re.compile(r"^T-\d{8}-\d{2}$")
VPS_LINE_RE = re.compile(r"^- VPS: (DEPLOYED [0-9a-f]{7,40}|NOT-DEPLOYED: DEMO|N/A)$")
MAX_FILE_BYTES = 150_000
RAW_DATA_SUFFIXES = {".jsonl", ".csv", ".parquet", ".html", ".zip"}


def _front(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} must start with YAML frontmatter"
    _, fm, _ = text.split("---\n", 2)
    data = yaml.safe_load(fm)
    assert isinstance(data, dict), f"{path} frontmatter must be a mapping"
    return data


REQUIRED = [
    "README.md",
    "MODELS.md",
    "STATUS.md",
    "tasks/_TEMPLATE.md",
    "mcp/README.md",
    "prompts/hermes-onboarding.md",
    "prompts/abacus-onboarding.md",
    *[f"log/{m}.md" for m in sorted(MODELS)],
    *[f"outputs/{m}/README.md" for m in sorted(MODELS)],
]


@pytest.mark.parametrize("rel", REQUIRED)
def test_required_file_exists(rel):
    assert (COLLAB / rel).is_file(), f"collab/{rel} missing"


def test_every_file_under_tasks_is_template_or_named_task():
    bad = [
        rel
        for p in TASKS_DIR.rglob("*")
        if p.is_file()
        and (rel := p.relative_to(TASKS_DIR).as_posix()) != "_TEMPLATE.md"
        and not TASK_PATH_RE.match(rel)
    ]
    assert not bad, f"tasks must be (open|done)/T-YYYYMMDD-NN-slug.md: {bad}"


TASKS = sorted(TASKS_DIR.glob("*/T-*.md"))


def test_there_are_tasks():
    assert TASKS, "collab/tasks/{open,done}/ should hold at least one task"


def test_task_ids_unique():
    ids = [_front(p)["id"] for p in TASKS]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"duplicate task ids: {dupes}"


@pytest.mark.parametrize("path", TASKS, ids=lambda p: p.name)
def test_task_header(path):
    fm = _front(path)
    for key in ("id", "from", "to", "status", "created", "claimed_by", "reviewer"):
        assert key in fm, f"{path.name}: missing '{key}'"
    assert TASK_ID_RE.match(str(fm["id"])), f"{path.name}: bad id {fm['id']!r}"
    assert path.name.startswith(f"{fm['id']}-"), f"{path.name}: file name must start with id"
    assert fm["from"] in ACTORS, f"{path.name}: unknown from={fm['from']}"
    assert fm["to"] in ACTORS, f"{path.name}: unknown to={fm['to']}"
    assert fm["status"] in TASK_STATUSES, f"{path.name}: bad status={fm['status']}"
    assert (fm["status"] in {"done", "dropped"}) == (path.parent.name == "done"), (
        f"{path.name}: status {fm['status']} does not match folder {path.parent.name}/"
    )
    if fm["status"] in {"claimed", "in-review"}:
        assert fm["claimed_by"] in MODELS, f"{path.name}: {fm['status']} needs claimed_by"
    if fm["reviewer"] is not None:
        assert fm["reviewer"] in MODELS, f"{path.name}: unknown reviewer={fm['reviewer']}"
    if fm["claimed_by"] is not None:
        assert fm["claimed_by"] in MODELS, f"{path.name}: unknown claimed_by"
        assert fm["reviewer"] != fm["claimed_by"], f"{path.name}: self-review is not allowed"


@pytest.mark.parametrize("model", sorted(MODELS))
def test_log_vps_lines_use_fixed_vocabulary(model):
    lines = (COLLAB / "log" / f"{model}.md").read_text(encoding="utf-8").splitlines()
    bad = [ln for ln in lines if ln.startswith("- VPS:") and not VPS_LINE_RE.match(ln)]
    assert not bad, f"log/{model}.md: VPS line must be DEPLOYED <sha> | NOT-DEPLOYED: DEMO | N/A: {bad}"


def test_no_large_or_raw_data_files_in_collab():
    offenders = [
        str(p.relative_to(ROOT))
        for p in COLLAB.rglob("*")
        if p.is_file()
        and (p.stat().st_size > MAX_FILE_BYTES or p.suffix.lower() in RAW_DATA_SUFFIXES)
    ]
    assert not offenders, f"raw/large data belongs in the private store, not the public repo: {offenders}"
