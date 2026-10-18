"""A checker for ASD-STE100 Simplified Technical English in Markdown files.

The checker finds the rules that a program can find with high precision:

- Rule 1.1: words that the STE dictionary does not approve. The finding gives the approved
  alternative.
- Rule 4.2: contractions.
- Rule 5.1: more than 20 words in an instruction (a numbered step).
- Rule 6.3: more than 25 words in a descriptive sentence.
- Rule 6.6: more than six sentences in a paragraph.
- Rule 8.1: semicolons.

Word counts obey rules 8.5 to 8.7. Text in parentheses, numbers, identifiers, code and hyphenated
words count as one word. The checker ignores code blocks, inline code, URLs and front matter.
A human must still do a review for the other rules, for example rule 3.6 (active voice).
"""

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

DATA = resources.files("fdeops.devtools") / "data"
CONTRACTION = re.compile(
    r"\b\w+(n't|'re|'ve|'ll|'d|'m)\b|\b(it|that|there|what|here|let)'s\b", re.IGNORECASE
)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9`\"(\[])|(?<=:)\s*$")
WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
NUMBERED = re.compile(r"^\s*\d+\.\s+")
BULLET = re.compile(r"^\s*[-*+]\s+")


@dataclass(frozen=True)
class Rules:
    not_approved: dict[str, str]
    approved: frozenset[str]
    allowed: frozenset[str]
    phrases: tuple[str, ...] = ()
    """Multi-word proper nouns and technical nouns, matched exactly (for example GitHub Actions)."""


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: STE {self.rule}: {self.message}"


def load_rules(extra_allow: Path | None = None) -> Rules:
    data = json.loads((DATA / "ste100.json").read_text(encoding="utf-8"))
    entries = _words_file((DATA / "technical_words.txt").read_text(encoding="utf-8"))
    if extra_allow is not None and extra_allow.exists():
        entries += _words_file(extra_allow.read_text(encoding="utf-8"))
    words = {e.lower() for e in entries if " " not in e}
    phrases = tuple(sorted((e for e in entries if " " in e), key=len, reverse=True))
    return Rules(
        not_approved=data["not_approved"],
        approved=frozenset(data["approved"]),
        allowed=frozenset(words),
        phrases=phrases,
    )


def _words_file(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def _clean(line: str) -> str:
    line = re.sub(r"`[^`]*`", " CODE ", line)
    line = re.sub(r'"[^"]{1,80}"', " QUOTE ", line)  # rule 8.6: quoted text is one word
    line = re.sub(r"\{[A-Za-z_][A-Za-z0-9_]*\}", " CODE ", line)  # template placeholders
    line = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", line)
    line = re.sub(r"https?://\S+", " URL ", line)
    line = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", line)
    return line


def count_words(sentence: str) -> int:
    """Count words as rules 8.5 to 8.7 tell: parenthesized text is one word."""
    s = re.sub(r"\([^()]*\)", " P ", _clean(sentence))
    return len([t for t in s.split() if re.search(r"[A-Za-z0-9]", t)])


def _lemmas(word: str) -> list[str]:
    w = word.lower().strip("'-")
    forms = [w]
    for suffix, repl in (
        ("ies", "y"),
        ("es", ""),
        ("s", ""),
        ("ied", "y"),
        ("ed", ""),
        ("ed", "e"),
        ("ing", ""),
        ("ing", "e"),
        ("d", ""),
    ):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            forms.append(w[: -len(suffix)] + repl)
    return forms


def _word_findings(text: str, rules: Rules, path: str, lineno: int) -> list[Finding]:
    for phrase in rules.phrases:
        text = text.replace(phrase, " ")
    out = []
    for m in WORD.finditer(text):
        word = m.group(0)
        if word.isupper() and len(word) > 1:  # abbreviations and identifiers
            continue
        forms = _lemmas(word)
        if any(f in rules.allowed or f in rules.approved for f in forms):
            continue
        hit = next((f for f in forms if f in rules.not_approved), None)
        if hit is not None:
            out.append(
                Finding(
                    path, lineno, "1.1", f"'{word}' is not approved; use {rules.not_approved[hit]}"
                )
            )
    return out


def _blocks(text: str) -> list[tuple[int, str, str]]:
    """Split Markdown into (first line number, kind, text) blocks."""
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
        start = end + 1
    blocks: list[tuple[int, str, str]] = []
    para: list[str] = []
    para_line = 0
    in_code = False

    def flush() -> None:
        nonlocal para
        if para:
            blocks.append((para_line, "para", " ".join(para)))
            para = []

    for i in range(start, len(lines)):
        raw = lines[i]
        stripped = raw.strip()
        if stripped.startswith("```"):
            flush()
            in_code = not in_code
            continue
        if in_code:
            continue
        if not stripped or stripped.startswith(("<!--", "<?")):
            flush()
            continue
        if stripped.startswith("|"):
            flush()
            blocks.append((i + 1, "table", stripped.replace("|", " ")))
        elif stripped.startswith("#"):
            flush()
            blocks.append((i + 1, "heading", stripped.lstrip("#")))
        elif NUMBERED.match(raw):
            flush()
            para, para_line = [NUMBERED.sub("", raw)], i + 1
            blocks.append((para_line, "step", para[0]))
            para = []
        elif BULLET.match(raw):
            flush()
            para, para_line = [BULLET.sub("", raw)], i + 1
        elif stripped.startswith(">"):
            flush()
            para, para_line = [stripped.lstrip("> ")], i + 1
        elif para:
            para.append(stripped)
        else:
            para, para_line = [stripped], i + 1
    flush()
    return blocks


def check_text(text: str, rules: Rules, path: str = "<text>") -> list[Finding]:
    findings: list[Finding] = []
    for lineno, kind, block in _blocks(text):
        clean = _clean(block)
        findings += _word_findings(clean, rules, path, lineno)
        if kind in ("table", "heading"):
            continue
        if ";" in clean:
            findings.append(Finding(path, lineno, "8.1", "do not use semicolons"))
        for m in CONTRACTION.finditer(clean):
            findings.append(
                Finding(path, lineno, "4.2", f"do not use contractions ('{m.group(0)}')")
            )
        sentences = [s for s in SENTENCE_END.split(block) if s and s.strip()]
        limit, rule = (20, "5.1") if kind == "step" else (25, "6.3")
        for s in sentences:
            n = count_words(s)
            if n > limit:
                findings.append(
                    Finding(
                        path, lineno, rule, f"sentence has {n} words (maximum {limit}): {s[:60]}..."
                    )
                )
        if kind == "para" and len(sentences) > 6:
            findings.append(
                Finding(
                    path, lineno, "6.6", f"paragraph has {len(sentences)} sentences (maximum 6)"
                )
            )
    return findings


def check_paths(paths: list[Path], rules: Rules) -> list[Finding]:
    out: list[Finding] = []
    for p in paths:
        files = sorted(p.rglob("*.md")) if p.is_dir() else [p]
        for f in files:
            out += check_text(f.read_text(encoding="utf-8"), rules, str(f))
    return out
