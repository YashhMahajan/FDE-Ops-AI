"""Check the licenses of the runtime dependencies. CI runs it; it fails on a license we cannot use.

Usage: uv run python scripts/license_check.py [--markdown OUT.md]

It reads the names from `uv export` (runtime dependencies only, no dev tools) and the license of
each installed distribution from its metadata (License-Expression, then License, then classifiers).
"""

import re
import subprocess
import sys
from importlib import metadata

from packaging.markers import Marker

# Copyleft licenses that would put obligations on this project's own code if we ship them linked in.
DENY = re.compile(r"\b(A?GPL(?!.*LGPL)|SSPL|Commons Clause|BUSL)\b", re.I)
# Weak copyleft: allowed for use as an unmodified library. Each entry says why it is acceptable.
REVIEWED = {
    "psycopg": "LGPL-3.0: used as an unmodified library through SQLAlchemy",
    "psycopg-binary": "LGPL-3.0: the binary build of psycopg, used unmodified",
    "certifi": "MPL-2.0: file-level copyleft, used unmodified",
    "pathspec": "MPL-2.0: file-level copyleft, used unmodified",
}


def runtime_names() -> list[str]:
    out = subprocess.run(
        ["uv", "export", "--locked", "--all-extras", "--no-dev", "--no-hashes", "--no-emit-project"],
        capture_output=True, text=True, check=True,
    ).stdout
    names = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        req, _, marker = line.partition(";")
        if marker.strip() and not Marker(marker.strip()).evaluate():
            continue  # a dependency for a different platform (for example, Windows only)
        names.append(re.split(r"[=<>\[ ]", req.strip(), maxsplit=1)[0].lower())
    return sorted(set(names))


def license_of(name: str) -> str:
    try:
        meta = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return "NOT INSTALLED"
    if meta.get("License-Expression"):
        return str(meta["License-Expression"])
    lic = (meta.get("License") or "").strip()
    if lic and len(lic) < 80 and "\n" not in lic:
        return lic
    classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    if classifiers:
        return " OR ".join(classifiers)
    return lic.splitlines()[0][:60] if lic else "UNKNOWN"


def main() -> int:
    rows = [(n, license_of(n)) for n in runtime_names()]
    problems = []
    for name, lic in rows:
        if name in REVIEWED:
            continue
        if lic in ("UNKNOWN", "NOT INSTALLED") or DENY.search(lic):
            problems.append(f"{name}: {lic}")
    if "--markdown" in sys.argv:
        path = sys.argv[sys.argv.index("--markdown") + 1]
        with open(path, "w", encoding="utf-8") as f:
            f.write("| package | license | note |\n|---|---|---|\n")
            for name, lic in rows:
                f.write(f"| {name} | {lic} | {REVIEWED.get(name, '')} |\n")
    for name, lic in rows:
        print(f"{name:32} {lic}")
    if problems:
        print("\nLicenses that need a review:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
