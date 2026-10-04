"""Tests for intelligence/pain/clean.py — deterministic issue cleaning/dedup."""

from intelligence.pain.clean import (
    body_fingerprint,
    clean_issue_text,
    dedupe_issues,
    issue_key,
)


def _issue(**overrides) -> dict:
    fields = {
        "repo": "org/repo",
        "issue_number": 1,
        "title": "Agent hangs on timeout",
        "body": "",
        "url": "https://github.com/org/repo/issues/1",
        "labels": [],
    }
    fields.update(overrides)
    return fields


class TestIssueKey:
    def test_formats_repo_and_number(self):
        assert issue_key(_issue(repo="org/repo", issue_number=42)) == "org/repo#42"


class TestDedupe:
    def test_no_duplicates_keeps_all(self):
        issues = [_issue(issue_number=i, url=f"https://github.com/org/repo/issues/{i}") for i in (1, 2, 3)]
        unique, removed = dedupe_issues(issues)
        assert len(unique) == 3
        assert removed == 0

    def test_duplicate_url_removed(self):
        issues = [
            _issue(issue_number=1, url="https://github.com/org/repo/issues/1"),
            _issue(issue_number=2, url="https://github.com/org/repo/issues/1"),  # same url
        ]
        unique, removed = dedupe_issues(issues)
        assert len(unique) == 1
        assert removed == 1
        assert unique[0]["issue_number"] == 1

    def test_duplicate_repo_number_removed_without_url(self):
        issues = [
            _issue(issue_number=1, url=""),
            _issue(issue_number=1, url=""),  # same repo#number
        ]
        unique, removed = dedupe_issues(issues)
        assert len(unique) == 1
        assert removed == 1

    def test_url_normalized_case_and_slash(self):
        issues = [
            _issue(issue_number=1, url="HTTPS://GitHub.com/org/repo/issues/1/"),
            _issue(issue_number=2, url="https://github.com/org/repo/issues/1"),
        ]
        unique, removed = dedupe_issues(issues)
        assert len(unique) == 1
        assert removed == 1


class TestBodyFingerprint:
    def test_identical_bodies_share_fingerprint(self):
        assert body_fingerprint("Agent hangs on timeout") == body_fingerprint("Agent hangs on timeout")

    def test_punctuation_and_case_ignored(self):
        assert body_fingerprint("Agent Hangs! On Timeout.") == body_fingerprint("agent hangs on timeout")

    def test_different_bodies_differ(self):
        assert body_fingerprint("timeout") != body_fingerprint("latency budget")


class TestCleanIssueText:
    def test_keeps_title_and_body_words(self):
        text = clean_issue_text("Agent hangs", "when tool call times out")
        assert "Agent hangs" in text
        assert "tool call times out" in text

    def test_strips_code_blocks(self):
        text = clean_issue_text("Crash", "```\nTraceback (most recent call last)\n...\n```\nReal body")
        assert "Traceback" not in text
        assert "Real body" in text

    def test_strips_template_headers(self):
        text = clean_issue_text("Bug", "### Description\n### Environment\nActual symptom")
        assert "###" not in text
        assert "Actual symptom" in text

    def test_collapses_repeated_lines(self):
        body = "timeout\ntimeout\ntimeout\nnew info"
        text = clean_issue_text("Bug", body)
        assert text.count("timeout") == 1
        assert "new info" in text
