"""Tests for BuilderMemory — SQLite-backed rule persistence."""
import pytest
from control_plane.memory import BuilderMemory


class TestBuilderMemory:
    def test_record_and_search(self, tmp_path):
        db = str(tmp_path / "test.db")
        mem = BuilderMemory(db)
        mem.record(
            {
                "rule_text": "Avoid blockchain projects with no working product",
                "source_opportunity": "DeFi opp #1",
                "decision_type": "reject",
            }
        )
        mem.record(
            {
                "rule_text": "Prefer B2B SaaS with strong unit economics",
                "source_opportunity": "SaaS opp #2",
                "decision_type": "approve",
            }
        )
        results = mem.search("blockchain", top_k=5)
        assert len(results) >= 1
        assert "blockchain" in results[0]["rule"].lower()
        mem.close()

    def test_search_empty(self, tmp_path):
        mem = BuilderMemory(str(tmp_path / "empty.db"))
        results = mem.search("anything", top_k=5)
        assert results == []
        mem.close()

    def test_search_returns_top_k(self, tmp_path):
        mem = BuilderMemory(str(tmp_path / "topk.db"))
        for i in range(10):
            mem.record(
                {
                    "rule_text": f"Rule about AI project number {i}",
                    "source_opportunity": f"opp-{i}",
                    "decision_type": "modify",
                }
            )
        # search for "AI" — all 10 match, but top_k should cap it
        results = mem.search("AI", top_k=3)
        assert len(results) == 3
        mem.close()

    def test_inject_constraints_with_rules(self, tmp_path):
        mem = BuilderMemory(str(tmp_path / "inject.db"))
        mem.record(
            {
                "rule_text": "Never invest in meme coins",
                "source_opportunity": "crypto opp",
                "decision_type": "reject",
            }
        )
        prompt = "Evaluate this opportunity."
        result = mem.inject_constraints("meme coin opportunity", prompt)
        assert "User Preferences from past feedback" in result
        assert "Never invest in meme coins" in result
        assert prompt in result
        mem.close()

    def test_inject_constraints_no_rules(self, tmp_path):
        mem = BuilderMemory(str(tmp_path / "noinject.db"))
        prompt = "Evaluate this opportunity."
        result = mem.inject_constraints("unrelated topic", prompt)
        assert result == prompt
        mem.close()

    def test_record_returns_id(self, tmp_path):
        mem = BuilderMemory(str(tmp_path / "id.db"))
        rid = mem.record(
            {
                "rule_text": "Test rule",
                "source_opportunity": "test",
                "decision_type": "modify",
            }
        )
        assert isinstance(rid, int)
        assert rid > 0
        mem.close()
