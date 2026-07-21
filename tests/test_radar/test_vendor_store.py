"""Tests for vendor store."""
from backend.models.vendor import VendorProfile, VendorSnapshot
from backend.store.vendor_store import VendorStore


class TestVendorStore:
    def test_save_and_retrieve(self, tmp_path):
        store = VendorStore(str(tmp_path / "vendor.db"))
        snap = VendorSnapshot(
            domain="agent", window_days=60,
            profiles=[VendorProfile(name="test-org", display_name="Test Org", accounts=["test-org"], tags=["🇨🇳"], comparison_group="domestic")],
        )
        sid = store.save(snap)
        assert sid == snap.id
        loaded = store.get_latest("agent")
        assert loaded is not None
        assert len(loaded.profiles) == 1

    def test_get_latest_empty_returns_none(self, tmp_path):
        store = VendorStore(str(tmp_path / "empty.db"))
        assert store.get_latest("agent") is None

    def test_get_profiles_by_group(self, tmp_path):
        store = VendorStore(str(tmp_path / "group.db"))
        snap = VendorSnapshot(
            domain="agent", window_days=60,
            profiles=[
                VendorProfile(name="org-a", accounts=["org-a"], tags=["🇨🇳"], comparison_group="domestic"),
                VendorProfile(name="org-b", accounts=["org-b"], tags=["🌍"], comparison_group="overseas"),
            ],
        )
        store.save(snap)
        domestic = store.get_profiles_by_group("domestic")
        assert len(domestic) == 1
        assert domestic[0].name == "org-a"
