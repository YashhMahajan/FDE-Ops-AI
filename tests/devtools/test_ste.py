from pathlib import Path

from fdeops.devtools.ste import check_text, count_words, load_rules

RULES = load_rules()


def rules_hit(text: str) -> list[str]:
    return [f.rule for f in check_text(text, RULES)]


def test_count_words_follows_rule_8() -> None:
    # numbers, codes, hyphenated words and parenthesized text each count as one word (8.5-8.7)
    assert count_words("Set the limit to 20000 (the default value) for `plan_growth`.") == 8
    assert count_words("Use a well-known e-mail address.") == 5


def test_sentence_length_descriptive_25() -> None:
    long = " ".join(["word"] * 26) + "."
    assert "6.3" in rules_hit(long)
    assert "6.3" not in rules_hit(" ".join(["word"] * 25) + ".")


def test_instruction_length_20_in_numbered_steps() -> None:
    step = "1. " + " ".join(["Open"] + ["word"] * 20) + "."
    assert "5.1" in rules_hit(step)


def test_semicolon_forbidden() -> None:
    assert "8.1" in rules_hit("The agent stops; the run ends.")


def test_contractions_forbidden() -> None:
    assert "4.2" in rules_hit("Do not use it if it's broken and don't retry.")


def test_not_approved_word_with_alternative() -> None:
    found = check_text("Ensure that the value is correct.", RULES)
    hit = next(f for f in found if f.rule == "1.1")
    assert "ensure" in hit.message.lower() and "MAKE SURE" in hit.message


def test_inflected_forms_are_found() -> None:
    assert "1.1" in rules_hit("The tool provides a report.")
    assert "1.1" in rules_hit("The script verified the data.")


def test_code_urls_and_allowlist_are_ignored() -> None:
    text = "Run `ensure_ready()` first.\n\n```bash\nfoo; bar\n```\n\nSee https://x.example/ensure."
    assert rules_hit(text) == []


def test_paragraph_max_six_sentences() -> None:
    para = " ".join(["This is one."] * 7)
    assert "6.6" in rules_hit(para)


def test_frontmatter_and_tables_not_counted_as_sentences() -> None:
    text = "---\ntitle: x; y\n---\n\n| a | b |\n|---|---|\n| " + " ".join(["w"] * 30) + " | z |\n"
    assert "6.3" not in rules_hit(text) and "8.1" not in rules_hit(text)


def test_project_allowlist_file(tmp_path: Path) -> None:
    allow = tmp_path / "allow.txt"
    allow.write_text("# technical verbs\nensure\n")
    rules = load_rules(allow)
    assert "1.1" not in [f.rule for f in check_text("Ensure it works.", rules)]


def test_glossary_terms_are_in_the_allowlist() -> None:
    import re

    glossary = (Path(__file__).parents[2] / "docs" / "glossary.md").read_text()
    allowed = load_rules().allowed
    nouns = re.findall(r"^\| ([a-z][a-z \-]+?)(?: \(|\s\|)", glossary, re.M)
    verbs = re.findall(r"^- ([a-z, ]+)$", glossary, re.M)
    rules = load_rules()
    phrases = {p.lower() for p in rules.phrases}
    terms = {w for t in nouns if t.lower() not in phrases for w in t.split()} | {
        v.strip() for line in verbs for v in line.split(",")
    }
    missing = sorted(t for t in terms if t not in allowed and len(t) > 2)
    assert [t for t in missing if t not in rules.approved] == []


def test_allowlisted_phrases_are_removed_before_word_check(tmp_path: Path) -> None:
    allow = tmp_path / "allow.txt"
    allow.write_text("GitHub Actions\n")
    assert "1.1" not in [
        f.rule for f in check_text("CI runs in GitHub Actions.", load_rules(allow))
    ]
    assert "1.1" in [f.rule for f in check_text("The actions occur.", load_rules(allow))]


def test_quoted_text_counts_as_one_word_and_is_not_checked() -> None:
    # Rule 8.6: quoted text counts as one word. A quoted status name is a label, not prose.
    assert rules_hit('The status "label created" means that we have the data.') == []
    assert count_words('The status "label created and shipped today" is shown.') == 5
