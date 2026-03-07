"""
Smoke tests for Toty Desktop Pet core modules.

Run with:  python -m pytest tests/ -v
"""
import json
import os
import sys
import tempfile

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ─── Settings Tests ───

class TestSettings:
    def test_defaults_loaded(self):
        from core.settings import Settings
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            s = Settings(path=path)
            assert s.get("pet_name") == "Blobby"
            assert s.get("pomodoro_work_min") == 25
            assert s.get("current_skin") == "default"
        finally:
            os.unlink(path)

    def test_set_and_persist(self):
        from core.settings import Settings
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            s = Settings(path=path)
            s.set("pet_name", "Toty")
            s.save()
            # Reload
            s2 = Settings(path=path)
            assert s2.get("pet_name") == "Toty"
        finally:
            os.unlink(path)

    def test_missing_key_returns_default(self):
        from core.settings import Settings
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            s = Settings(path=path)
            assert s.get("nonexistent_key") is None
        finally:
            os.unlink(path)


# ─── MoodEngine Tests ───

class TestMoodEngine:
    def _make_engine(self):
        from core.settings import Settings
        from core.mood import MoodEngine
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        s = Settings(path=path)
        return MoodEngine(s), path

    def test_initial_mood(self):
        engine, path = self._make_engine()
        try:
            assert 0 <= engine.mood <= 100
        finally:
            os.unlink(path)

    def test_boost_mood(self):
        engine, path = self._make_engine()
        try:
            old = engine.mood
            engine.boost_mood(10)
            assert engine.mood >= old
            assert engine.mood <= 100
        finally:
            os.unlink(path)

    def test_drain_mood(self):
        engine, path = self._make_engine()
        try:
            engine.mood = 50
            engine.drain_mood(10)
            assert engine.mood <= 50
            assert engine.mood >= 0
        finally:
            os.unlink(path)


# ─── PersistentStats Tests ───

class TestPersistentStats:
    def test_stats_creation(self):
        from core.stats import PersistentStats
        s = PersistentStats()
        assert "total_sessions" in s.data
        assert "level" in s.data

    def test_level_info(self):
        from core.stats import PersistentStats
        s = PersistentStats()
        info = s.get_level_info()
        assert isinstance(info, str)
        assert "Lv" in info


# ─── Sprite Engine Tests ───

class TestSpriteEngine:
    def test_get_available_skins(self):
        from core.sprite_engine import get_available_skins
        skins = get_available_skins()
        assert isinstance(skins, list)
        # At least default skin should exist
        ids = [s["id"] for s in skins]
        assert "default" in ids

    def test_load_skin(self):
        from core.sprite_engine import load_skin
        skin = load_skin("assets/skins/default")
        assert "body" in skin
        assert "limbs" in skin
        assert "face" in skin

    def test_generate_skin_assets(self):
        from core.sprite_engine import generate_skin_assets
        with tempfile.TemporaryDirectory() as tmpdir:
            ok = generate_skin_assets("default", assets_folder=tmpdir)
            assert ok
            assert os.path.isfile(os.path.join(tmpdir, "pet_sheet.png"))
            assert os.path.isfile(os.path.join(tmpdir, "pet_atlas.json"))
            assert os.path.isfile(os.path.join(tmpdir, "pet_animations.json"))

    def test_caching_skips_regeneration(self):
        from core.sprite_engine import generate_skin_assets
        with tempfile.TemporaryDirectory() as tmpdir:
            # First generation
            ok1 = generate_skin_assets("default", assets_folder=tmpdir)
            assert ok1
            mtime1 = os.path.getmtime(os.path.join(tmpdir, "pet_sheet.png"))
            # Second call should skip (cached)
            import time
            time.sleep(0.05)
            ok2 = generate_skin_assets("default", assets_folder=tmpdir)
            assert ok2
            mtime2 = os.path.getmtime(os.path.join(tmpdir, "pet_sheet.png"))
            assert mtime1 == mtime2  # file was NOT regenerated

    def test_atlas_contains_skin_hash(self):
        from core.sprite_engine import generate_skin_assets
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_skin_assets("default", assets_folder=tmpdir)
            with open(os.path.join(tmpdir, "pet_atlas.json")) as f:
                atlas = json.load(f)
            assert "skin_hash" in atlas
            assert len(atlas["skin_hash"]) == 64  # SHA-256 hex


# ─── AchievementEngine Tests ───

class TestAchievementEngine:
    def test_achievements_dict_populated(self):
        from core.achievements import ACHIEVEMENTS
        assert len(ACHIEVEMENTS) > 0

    def test_engine_check_runs(self):
        from core.settings import Settings
        from core.stats import PersistentStats
        from core.achievements import AchievementEngine
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            s = Settings(path=path)
            stats = PersistentStats()
            engine = AchievementEngine(stats, s)
            # Should not crash
            engine.check_all()
            pending = engine.pop_pending()
            assert isinstance(pending, list)
        finally:
            os.unlink(path)
