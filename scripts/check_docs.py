"""Make sure that the documents tell the truth. CI runs it.

1. Each relative link in a Markdown file points to a file or folder that exists.
2. Each `fdeops ...` command that a document names exists (its `--help` exits with 0).
3. Each complete `uv run fdeops ...` command in a bash block of the README and the guides runs
   and exits with 0. Commands with placeholders (<...>, "...") or that need a key are skipped.

Usage: uv run python scripts/check_docs.py [--no-run]
"""

import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = [
    ROOT / "README.md",
    ROOT / "SECURITY.md",
    ROOT / "CODE_OF_CONDUCT.md",
    ROOT / "CONTRIBUTING.md",
    *sorted((ROOT / "docs").rglob("*.md")),
]
RUN_FROM = [ROOT / "README.md", *sorted((ROOT / "docs" / "guides").glob("*.md"))]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"```bash\n(.*?)```", re.S)
COMMAND = re.compile(r"`(?:uv run )?fdeops ((?:[a-z][a-z-]*)(?: [a-z][a-z-]*)?)")
SKIP = ("<", "...", "OPENROUTER", "MODEL=", "your-key")


def check_links() -> list[str]:
    problems = []
    for doc in DOCS:
        if not doc.exists():
            problems.append(f"{doc.relative_to(ROOT)}: the file does not exist")
            continue
        text = re.sub(r"```.*?```", "", doc.read_text(encoding="utf-8"), flags=re.S)
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path = (doc.parent / target.split("#", 1)[0]).resolve()
            if not path.exists():
                problems.append(f"{doc.relative_to(ROOT)}: broken link {target}")
    return problems


def _help_ok(words: list[str]) -> bool:
    r = subprocess.run(
        ["uv", "run", "fdeops", *words, "--help"], cwd=ROOT, capture_output=True, text=True
    )
    return r.returncode == 0


def check_commands() -> list[str]:
    problems = []
    seen: set[str] = set()
    for doc in DOCS:
        if not doc.exists():
            continue
        for match in COMMAND.findall(doc.read_text(encoding="utf-8")):
            words = match.split()
            if match in seen:
                continue
            seen.add(match)
            # "fdeops release propose" is a subcommand. "fdeops run --x" gives one word.
            if not _help_ok(words) and not _help_ok(words[:1]):
                problems.append(f"{doc.relative_to(ROOT)}: the command `fdeops {match}` does not exist")
    return problems


def runnable_commands() -> list[tuple[Path, str]]:
    out = []
    for doc in RUN_FROM:
        for block in FENCE.findall(doc.read_text(encoding="utf-8")):
            joined = re.sub(r"\\\n\s*", " ", block)
            for line in joined.splitlines():
                if "needs a recording" in line:
                    continue
                cmd = line.split("  #", 1)[0].strip()
                if cmd.startswith("uv run fdeops") and not any(s in cmd for s in SKIP):
                    out.append((doc, cmd))
    return out


def run_commands() -> list[str]:
    problems = []
    for doc, cmd in runnable_commands():
        print(f"$ {cmd}", flush=True)
        r = subprocess.run(shlex.split(cmd), cwd=ROOT, capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
            problems.append(f"{doc.relative_to(ROOT)}: `{cmd}` exited {r.returncode}: {tail}")
    return problems


def main() -> int:
    problems = check_links() + check_commands()
    if "--no-run" not in sys.argv:
        problems += run_commands()
    for p in problems:
        print(f"FAIL {p}", file=sys.stderr)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
