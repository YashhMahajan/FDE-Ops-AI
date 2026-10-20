"""Each technical noun and verb in the glossary is in the checker allowlist, and the reverse for
glossary entries. Thus the glossary and the STE checker cannot drift apart."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]


def _allowlist() -> set[str]:
    text = (ROOT / "src/fdeops/devtools/data/technical_words.txt").read_text(encoding="utf-8")
    return {ln.strip().lower() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")}


def _glossary_terms() -> set[str]:
    text = (ROOT / "docs/glossary.md").read_text(encoding="utf-8")
    nouns = re.findall(r"^\| ([^|]+?) \| [A-Z]", text, flags=re.M)
    verbs_block = text.split("## Technical verbs", 1)[1]
    verbs = [
        w.strip()
        for line in verbs_block.splitlines()
        if line.startswith("- ")
        for w in re.sub(r"\([^)]*\)", "", line[2:]).split(",")
    ]
    terms = set()
    for n in nouns:
        if n.strip().lower() == "term":
            continue
        terms.add(re.sub(r"\s*\([^)]*\)", "", n).strip().lower())
    return terms | {v.lower() for v in verbs if v}


def test_glossary_terms_are_in_the_allowlist() -> None:
    allow = _allowlist()
    assert len(_glossary_terms()) > 60  # the parser found the glossary entries
    missing = sorted(t for t in _glossary_terms() if t not in allow and t.split()[0] not in allow)
    assert missing == [], f"add these glossary terms to technical_words.txt: {missing}"
