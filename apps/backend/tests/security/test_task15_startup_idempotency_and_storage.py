import hashlib
import json
import logging
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app import create_app
from database.connection import DatabaseManager, PersistentDatabaseProxy
from database.seeds import PREDEFINED_TEAMS, seed_real_and_dummy_users
from config import Config, TestConfig


PROD_STORAGE_DIR = Path(__file__).resolve().parents[2] / "data" / "storage" / "office_hrm"


def _dir_hashes(directory: Path) -> dict[str, str]:
    return {
        f.name: hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(directory.glob("*.json"))
    }


def _reset_db_singleton():
    DatabaseManager._db = None
    DatabaseManager._client = None
    DatabaseManager._data_dir = None
    DatabaseManager._is_mock = False


def test_repeated_startup_does_not_mutate_projects_or_existing_records(monkeypatch):
    """Repeated create_app() runs with existing data must keep projects.json and all other JSONs byte-identical."""
    orig_db = DatabaseManager._db
    orig_client = DatabaseManager._client
    orig_data_dir = DatabaseManager._data_dir
    orig_is_mock = DatabaseManager._is_mock

    with tempfile.TemporaryDirectory() as tmp:
        tmp_base = Path(tmp)
        clone_db_dir = tmp_base / "office_hrm"
        shutil.copytree(PROD_STORAGE_DIR, clone_db_dir)

        # Customize an existing project and an employee manager assignment to verify startup preserves them
        projects_file = clone_db_dir / "projects.json"
        projects_data = json.loads(projects_file.read_text(encoding="utf-8"))
        for prj in projects_data:
            if prj.get("project_id") == "PRJ-ENG-01":
                prj["title"] = "Custom Preserved Project Title"
                prj["progress_percentage"] = 91
                prj["updated_at"] = {"$date": "2026-01-01T00:00:00.000Z"}
        projects_file.write_text(json.dumps(projects_data, indent=2), encoding="utf-8")

        users_file = clone_db_dir / "users.json"
        users_data = json.loads(users_file.read_text(encoding="utf-8"))
        for usr in users_data:
            if usr.get("employee_id") == "AS-1001":
                usr["assigned_tl_id"] = "TL-CUSTOM-99"
                usr["manager_id"] = "MGR-CUSTOM-99"
                usr["reporting_manager_id"] = "MGR-CUSTOM-99"
        users_file.write_text(json.dumps(users_data, indent=2), encoding="utf-8")

        hashes_before = _dir_hashes(clone_db_dir)

        class IsolatedStartupConfig(Config):
            TESTING = False
            DATABASE_NAME = "office_hrm"
            USE_MOCK_DB = True
            USE_FILE_PERSISTENCE = True
            DATA_DIR = tmp_base
            PERSISTENT_DATA_DIR = tmp_base
            ENABLE_DEV_TEST_ACCOUNT = False

        monkeypatch.setattr(Config, "DATA_DIR", tmp_base, raising=False)
        monkeypatch.setattr(Config, "PERSISTENT_DATA_DIR", tmp_base, raising=False)
        monkeypatch.setattr(Config, "USE_MOCK_DB", True, raising=False)
        monkeypatch.setattr(Config, "USE_FILE_PERSISTENCE", True, raising=False)

        try:
            # First startup
            _reset_db_singleton()
            create_app(config_class=IsolatedStartupConfig, start_scheduler=False)
            hashes_after_first = _dir_hashes(clone_db_dir)
            assert hashes_after_first == hashes_before

            # Second startup
            _reset_db_singleton()
            create_app(config_class=IsolatedStartupConfig, start_scheduler=False)
            hashes_after_second = _dir_hashes(clone_db_dir)
            assert hashes_after_second == hashes_before

            # Verify customized project and employee hierarchy remained completely intact
            saved_projects = json.loads(projects_file.read_text(encoding="utf-8"))
            p1 = next(p for p in saved_projects if p["project_id"] == "PRJ-ENG-01")
            assert p1["title"] == "Custom Preserved Project Title"
            assert p1["progress_percentage"] == 91
            assert p1["updated_at"] == {"$date": "2026-01-01T00:00:00.000Z"}

            saved_users = json.loads(users_file.read_text(encoding="utf-8"))
            u1 = next(u for u in saved_users if u.get("employee_id") == "AS-1001")
            assert u1["assigned_tl_id"] == "TL-CUSTOM-99"
            assert u1["manager_id"] == "MGR-CUSTOM-99"
        finally:
            DatabaseManager._db = orig_db
            DatabaseManager._client = orig_client
            DatabaseManager._data_dir = orig_data_dir
            DatabaseManager._is_mock = orig_is_mock


def test_missing_initial_records_seeded_safely_without_overwriting_existing(db):
    """seed_real_and_dummy_users seeds genuinely missing baseline rows while preserving existing rows."""
    assert db.name == TestConfig.DATABASE_NAME
    for col in ("users", "teams", "projects"):
        db[col].delete_many({})

    # Pre-seed an existing modified project and modified user before calling seeder
    fixed_ts = datetime(2025, 5, 1, tzinfo=timezone.utc)
    db.projects.insert_one({
        "project_id": "PRJ-ENG-01",
        "title": "Existing Production Project",
        "progress_percentage": 88,
        "created_at": fixed_ts,
        "updated_at": fixed_ts,
    })

    seed_real_and_dummy_users(db)

    # Missing baseline project PRJ-ENG-02, all 5 predefined teams, and 38 enterprise users should be created
    assert db.projects.find_one({"project_id": "PRJ-ENG-02"}) is not None
    assert len(PREDEFINED_TEAMS) == 5
    assert db.teams.count_documents({}) == len(PREDEFINED_TEAMS)
    assert db.users.count_documents({}) >= 38

    # Pre-existing PRJ-ENG-01 must NOT be overwritten or timestamp-bumped
    p1 = db.projects.find_one({"project_id": "PRJ-ENG-01"})
    assert p1["title"] == "Existing Production Project"
    assert p1["progress_percentage"] == 88
    assert p1["updated_at"].replace(tzinfo=None) == fixed_ts.replace(tzinfo=None)


def test_storage_path_reporting_and_external_override_warning(monkeypatch, caplog):
    """Startup clearly reports resolved path provenance and warns prominently on external HRMS_DATA_DIR."""
    orig_db = DatabaseManager._db
    orig_client = DatabaseManager._client
    orig_data_dir = DatabaseManager._data_dir
    orig_is_mock = DatabaseManager._is_mock

    # 1. Default configuration check (neither OS env nor .env overriding)
    monkeypatch.delenv("HRMS_DATA_DIR", raising=False)
    monkeypatch.setattr(Config, "_IMPORT_TIME_ENV_HRMS_DATA_DIR", None, raising=False)
    monkeypatch.setattr(Config, "_DOTENV_HRMS_DATA_DIR", None, raising=False)
    monkeypatch.setattr(Config, "DATA_DIR", Config.DEFAULT_DATA_DIR, raising=False)
    monkeypatch.setattr(Config, "_IMPORT_TIME_DATA_DIR", Config.DEFAULT_DATA_DIR, raising=False)

    default_info = Config.get_storage_path_details("office_hrm")
    assert Path(default_info["resolved_db_dir"]) == (Path(Config.BASE_DIR) / "data" / "storage" / "office_hrm").resolve()
    assert "default configuration" in default_info["source"]
    assert default_info["is_external_override"] is False
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="database.connection"):
        DatabaseManager.log_active_storage("office_hrm")
    assert "default configuration" in caplog.text
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)

    # 2. .env configuration check pointing to workspace storage
    ws_path = str((Path(Config.BASE_DIR) / "data" / "storage").resolve())
    monkeypatch.setenv("HRMS_DATA_DIR", ws_path)
    monkeypatch.setattr(Config, "_DOTENV_HRMS_DATA_DIR", ws_path, raising=False)
    monkeypatch.setattr(Config, "DATA_DIR", Path(ws_path), raising=False)
    monkeypatch.setattr(Config, "_IMPORT_TIME_DATA_DIR", Path(ws_path), raising=False)

    dotenv_info = Config.get_storage_path_details("office_hrm")
    assert ".env configuration" in dotenv_info["source"]
    assert dotenv_info["is_external_override"] is False
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="database.connection"):
        DatabaseManager.log_active_storage("office_hrm")
    assert ".env configuration" in caplog.text
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)

    # 3. External HRMS_DATA_DIR environment variable override logs prominent warning and is honored
    with tempfile.TemporaryDirectory() as ext_tmp:
        ext_path = Path(ext_tmp).resolve()
        monkeypatch.setenv("HRMS_DATA_DIR", str(ext_path))
        monkeypatch.setattr(Config, "USE_MOCK_DB", True, raising=False)
        monkeypatch.setattr(Config, "USE_FILE_PERSISTENCE", True, raising=False)

        ext_info = Config.get_storage_path_details("office_hrm")
        assert Path(ext_info["resolved_db_dir"]) == (ext_path / "office_hrm").resolve()
        assert "environment variable" in ext_info["source"]
        assert ext_info["is_external_override"] is True

        caplog.clear()
        with caplog.at_level(logging.INFO, logger="database.connection"):
            try:
                _reset_db_singleton()
                db = DatabaseManager.get_db("office_hrm")
                assert isinstance(db, PersistentDatabaseProxy)
                assert Path(DatabaseManager._data_dir).resolve() == (ext_path / "office_hrm").resolve()
            finally:
                DatabaseManager._db = orig_db
                DatabaseManager._client = orig_client
                DatabaseManager._data_dir = orig_data_dir
                DatabaseManager._is_mock = orig_is_mock

        log_text = caplog.text
        assert str((ext_path / "office_hrm").resolve()) in log_text
        assert "environment variable (HRMS_DATA_DIR)" in log_text
        assert "EXTERNAL STORAGE OVERRIDE DETECTED" in log_text
        assert any(r.levelno == logging.WARNING and "EXTERNAL STORAGE OVERRIDE DETECTED" in r.message for r in caplog.records)

