"""Turn a pytest JUnit report into a GitHub job summary and inline failure annotations.

Usage: python .github/scripts/test_summary.py test-results.xml "Python 3.13"
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET


def main(report: str, title: str) -> None:
    try:
        root = ET.parse(report).getroot()
    except (OSError, ET.ParseError) as exc:
        write_summary(f"### {title}\n\nNo test report was produced ({exc}). The tests did not start; check the log.\n")
        return

    suites = [root] if root.tag == "testsuite" else list(root)
    total = sum(int(s.get("tests", 0)) for s in suites)
    failed = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    seconds = sum(float(s.get("time", 0)) for s in suites)

    lines = [
        f"### {title}: {'❌ failing' if failed else '✅ passing'}",
        "",
        f"{total - failed - skipped} passed, {failed} failed, {skipped} skipped in {seconds:.1f}s",
        "",
    ]
    failures = []
    for case in root.iter("testcase"):
        problem = case.find("failure") if case.find("failure") is not None else case.find("error")
        if problem is None:
            continue
        name = f"{case.get('classname', '')}::{case.get('name', '')}"
        message = (problem.get("message") or "").strip().splitlines()[0][:200] if problem.get("message") else ""
        failures.append((name, message))
        file, line = case.get("file"), case.get("line")
        if file:
            # Inline annotation on the test that failed (shown on the PR diff and the run page).
            location = f"file={file},line={int(line) + 1}" if line else f"file={file}"
            print(f"::error {location},title=Test failed: {case.get('name')}::{message or 'see log'}")

    if failures:
        lines += ["| Failed test | Reason |", "| --- | --- |"]
        lines += [f"| `{name}` | {message.replace('|', '/')} |" for name, message in failures]
    write_summary("\n".join(lines) + "\n")


def write_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
    print(text)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "Tests")
