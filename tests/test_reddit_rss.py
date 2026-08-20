import json
import urllib.error

from scripts.reddit_rss import build_url, main, parse_atom

FIXTURE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>r/SaaS</title>
  <entry>
    <title>Anyone else struggling to automate onboarding?</title>
    <author><name>/u/jane_doe</name></author>
    <link href="https://www.reddit.com/r/SaaS/comments/abc123/automate_onboarding/" />
    <published>2026-08-19T12:00:00+00:00</published>
    <id>/r/SaaS/comments/abc123/automate_onboarding/</id>
    <content>We keep copy-pasting the same onboarding steps.</content>
    <category term="r/SaaS" label="r/SaaS"/>
  </entry>
</feed>"""


def test_build_url():
    assert build_url("SaaS", "new", 25) == "https://www.reddit.com/r/SaaS/.rss?sort=new&limit=25"


def test_parse_atom_extracts_all_fields():
    posts = parse_atom(FIXTURE_ATOM)
    assert len(posts) == 1
    p = posts[0]
    assert p["title"] == "Anyone else struggling to automate onboarding?"
    assert p["author"] == "/u/jane_doe"
    assert p["permalink"] == "https://www.reddit.com/r/SaaS/comments/abc123/automate_onboarding/"
    assert p["published"] == "2026-08-19T12:00:00+00:00"
    assert p["selftext"] == "We keep copy-pasting the same onboarding steps."
    assert p["category"] == "r/SaaS"
    assert p["id"] == "/r/SaaS/comments/abc123/automate_onboarding/"


def test_parse_atom_missing_fields_become_empty():
    xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>x</title></entry></feed>"""
    posts = parse_atom(xml)
    assert posts[0]["author"] == ""
    assert posts[0]["permalink"] == ""
    assert posts[0]["selftext"] == ""


def test_main_success(monkeypatch, capsys):
    monkeypatch.setattr("scripts.reddit_rss.fetch", lambda url, timeout=15: FIXTURE_ATOM)
    code = main(["SaaS"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert len(out) == 1
    assert out[0]["id"] == "/r/SaaS/comments/abc123/automate_onboarding/"


def test_main_rate_limited(monkeypatch, capsys):
    def raise_429(url, timeout=15):
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
    monkeypatch.setattr("scripts.reddit_rss.fetch", raise_429)
    code = main(["SaaS"])
    out = json.loads(capsys.readouterr().out)
    assert code == 2
    assert out["error"] == "rate_limited"
    assert out["code"] == 429


def test_main_not_found(monkeypatch, capsys):
    def raise_404(url, timeout=15):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    monkeypatch.setattr("scripts.reddit_rss.fetch", raise_404)
    code = main(["SaaS"])
    out = json.loads(capsys.readouterr().out)
    assert code == 3
    assert out["error"] == "not_found"
