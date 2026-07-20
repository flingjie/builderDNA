"""Tests for follow snapshot store."""

import tempfile
from pathlib import Path

from follow.scorer import AccountScore, GroupResult
from follow.store import FollowStore


class TestFollowStore:
    def test_save_and_retrieve(self):
        db_path = Path(tempfile.mktemp(suffix=".db"))
        try:
            store = FollowStore(db_path)
            groups = [
                GroupResult(
                    group_name="Group A",
                    accounts=[
                        AccountScore(actor="alice", total_stars=100, followers=10,
                                     star_score=100, follower_score=80, composite=86,
                                     rating="✅ 值得关注"),
                    ],
                ),
                GroupResult(
                    group_name="Group B",
                    accounts=[
                        AccountScore(actor="bob", total_stars=50, followers=5,
                                     star_score=70, follower_score=60, composite=63,
                                     rating="✅ 值得关注"),
                    ],
                ),
            ]
            snap_id = store.save(groups)
            assert len(snap_id) == 8

            last = store.get_last()
            assert last is not None
            assert "Group A" in last
            assert "Group B" in last
            assert last["Group A"]["alice"] == 86
            assert last["Group B"]["bob"] == 63
        finally:
            db_path.unlink(missing_ok=True)

    def test_list_snapshots(self):
        db_path = Path(tempfile.mktemp(suffix=".db"))
        try:
            store = FollowStore(db_path)
            grp = GroupResult(
                group_name="G", accounts=[
                    AccountScore(actor="x", total_stars=1, followers=1,
                                 star_score=50, follower_score=50, composite=50,
                                 rating="⚠️ 可以观望"),
                ],
            )
            store.save([grp])
            store.save([grp])
            snaps = store.list_snapshots()
            assert len(snaps) == 2
            assert snaps[0]["created_at"] > snaps[1]["created_at"]
        finally:
            db_path.unlink(missing_ok=True)

    def test_get_last_empty_db(self):
        db_path = Path(tempfile.mktemp(suffix=".db"))
        try:
            store = FollowStore(db_path)
            assert store.get_last() is None
        finally:
            db_path.unlink(missing_ok=True)
