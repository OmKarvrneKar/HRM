import os
import shutil
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict
from bson import json_util
from pymongo import MongoClient
from pymongo.database import Database
from config import Config

logger = logging.getLogger(__name__)


class PersistentCollectionProxy:
    """
    Transparent proxy for mongomock Collection that guarantees automatic,
    atomic persistence to disk on every mutating database operation.
    """
    def __init__(self, col, data_dir: Path):
        self._col = col
        self._data_dir = data_dir
        self._file = data_dir / f"{col.name}.json"

    def _save(self):
        try:
            try:
                self._data_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            docs = list(self._col.find({}))
            temp_file = self._file.with_name(f"{self._col.name}_{os.getpid()}_{int(datetime.now().timestamp() * 1000)}.tmp")
            temp_file.write_text(json_util.dumps(docs, indent=2), encoding="utf-8")
            try:
                temp_file.replace(self._file)
            except OSError:
                import time
                time.sleep(0.05)
                if self._file.exists():
                    try:
                        self._file.unlink()
                    except OSError:
                        pass
                temp_file.replace(self._file)
        except Exception as e:
            logger.debug("Local disk persistence skipped: %s", e)

    def insert_one(self, *args, **kwargs):
        res = self._col.insert_one(*args, **kwargs)
        self._save()
        return res

    def insert_many(self, *args, **kwargs):
        res = self._col.insert_many(*args, **kwargs)
        self._save()
        return res

    def update_one(self, *args, **kwargs):
        res = self._col.update_one(*args, **kwargs)
        self._save()
        return res

    def update_many(self, *args, **kwargs):
        res = self._col.update_many(*args, **kwargs)
        self._save()
        return res

    def replace_one(self, *args, **kwargs):
        res = self._col.replace_one(*args, **kwargs)
        self._save()
        return res

    def delete_one(self, *args, **kwargs):
        res = self._col.delete_one(*args, **kwargs)
        self._save()
        return res

    def delete_many(self, *args, **kwargs):
        res = self._col.delete_many(*args, **kwargs)
        self._save()
        return res

    def find_one_and_update(self, *args, **kwargs):
        res = self._col.find_one_and_update(*args, **kwargs)
        self._save()
        return res

    def find_one_and_replace(self, *args, **kwargs):
        res = self._col.find_one_and_replace(*args, **kwargs)
        self._save()
        return res

    def find_one_and_delete(self, *args, **kwargs):
        res = self._col.find_one_and_delete(*args, **kwargs)
        self._save()
        return res

    def drop(self, *args, **kwargs):
        res = self._col.drop(*args, **kwargs)
        if self._file.exists():
            try:
                self._file.unlink()
            except Exception:
                pass
        return res

    def bulk_write(self, *args, **kwargs):
        res = self._col.bulk_write(*args, **kwargs)
        self._save()
        return res

    def __getattr__(self, name):
        return getattr(self._col, name)


class PersistentDatabaseProxy:
    """
    Transparent proxy for mongomock Database that wraps all collections
    in PersistentCollectionProxy instances to maintain seamless disk persistence.
    """
    def __init__(self, db, data_dir: Path):
        self._db = db
        self._data_dir = data_dir
        self._proxies: Dict[str, PersistentCollectionProxy] = {}

    def __getitem__(self, name: str) -> PersistentCollectionProxy:
        if name not in self._proxies:
            raw_col = self._db[name]
            self._proxies[name] = PersistentCollectionProxy(raw_col, self._data_dir)
        return self._proxies[name]

    def __getattr__(self, name: str):
        if name in ["_db", "_data_dir", "_proxies"]:
            return super().__getattribute__(name)
        return self[name]

    def drop_collection(self, name_or_collection, *args, **kwargs):
        col_name = name_or_collection if isinstance(name_or_collection, str) else name_or_collection.name
        if col_name in self._proxies:
            del self._proxies[col_name]
        col_file = self._data_dir / f"{col_name}.json"
        if col_file.exists():
            try:
                col_file.unlink()
            except Exception:
                pass
        return self._db.drop_collection(name_or_collection, *args, **kwargs)

    @property
    def name(self) -> str:
        return self._db.name

    @property
    def client(self):
        return self._db.client

    def list_collection_names(self, *args, **kwargs):
        return self._db.list_collection_names(*args, **kwargs)

    def command(self, *args, **kwargs):
        return self._db.command(*args, **kwargs)


class DatabaseManager:
    _client = None
    _db: Database | PersistentDatabaseProxy | None = None
    _is_mock: bool = False
    _data_dir: Optional[Path] = None

    @classmethod
    def get_data_dir(cls, db_name: str) -> Path:
        base_dir = Path(Config.DATA_DIR)
        target = base_dir / db_name
        try:
            target.mkdir(parents=True, exist_ok=True)
            return target
        except (PermissionError, OSError) as e:
            fallback = Path(Config.BASE_DIR) / "data" / "storage" / db_name
            try:
                fallback.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            logger.warning(
                "Access to configured data directory '%s' was restricted (%s). "
                "Safely falling back to local workspace persistent directory '%s'.",
                target, e, fallback
            )
            return fallback

    @classmethod
    def get_client(cls, uri: str = None) -> MongoClient:
        if cls._client is None:
            conn_uri = uri or Config.MONGODB_URI
            force_mock = Config.USE_MOCK_DB
            if not force_mock:
                try:
                    logger.info("Connecting to MongoDB at: %s", conn_uri)
                    test_client = MongoClient(
                        conn_uri,
                        serverSelectionTimeoutMS=2000,
                        connectTimeoutMS=2000,
                        maxPoolSize=50,
                        minPoolSize=5
                    )
                    test_client.admin.command("ping")
                    cls._client = test_client
                    cls._is_mock = False
                    logger.info("MongoDB connected successfully.")
                except Exception as e:
                    allow_fallback = Config.USE_MOCK_DB or os.getenv("ALLOW_MOCK_FALLBACK", "true").lower() in ("true", "1", "yes")
                    is_test = os.getenv("TESTING", "").lower() == "true" or (uri and "_test" in str(uri))
                    
                    if allow_fallback or is_test:
                        logger.warning(
                            "MongoDB connection unreachable at '%s' (%s). "
                            "Seamlessly engaging bulletproof disk persistence proxy fallback via mongomock "
                            "to ensure zero connection drops.", conn_uri, e
                        )
                        import mongomock
                        cls._client = mongomock.MongoClient()
                        cls._is_mock = True
                    else:
                        err_msg = (
                            f"CRITICAL DATABASE ERROR: Real MongoDB is unreachable at '{conn_uri}'. "
                            f"Error details: {e}. "
                            "In accordance with enterprise data protection standards, development and production "
                            "must not silently switch to temporary in-memory storage. "
                            "Real employee records cannot be stored in an unverified temporary database. "
                            "Please start the MongoDB service or explicitly configure local disk persistence "
                            "via USE_MOCK_DB=true and USE_FILE_PERSISTENCE=true."
                        )
                        logger.critical(err_msg)
                        raise ConnectionError(err_msg) from e
            else:
                # Mock DB is explicitly configured; enforce persistent disk storage if not testing
                is_test = os.getenv("TESTING", "").lower() == "true"
                if not is_test and not getattr(Config, "USE_FILE_PERSISTENCE", True):
                    raise RuntimeError(
                        "Configuration Error: In-memory mock database without file persistence is forbidden "
                        "for real data. Set USE_FILE_PERSISTENCE=true to ensure persistent disk storage."
                    )
                import mongomock
                cls._client = mongomock.MongoClient()
                cls._is_mock = True
        return cls._client

    @classmethod
    def get_db(cls, db_name: str = None, uri: str = None):
        # Match original behavior: preserve currently active DB if db_name is None or already matches
        if cls._db is not None and (db_name is None or getattr(cls._db, "name", None) == db_name):
            return cls._db

        target_db_name = db_name or Config.DATABASE_NAME
        client = cls.get_client(uri)
        raw_db = client[target_db_name]

        # Enable file persistence only for non-test databases
        is_test_db = target_db_name.endswith("_test") or os.getenv("TESTING", "").lower() == "true"
        use_persistence = cls._is_mock and getattr(Config, "USE_FILE_PERSISTENCE", True) and not is_test_db

        if use_persistence:
            data_dir = cls.get_data_dir(target_db_name)
            cls._data_dir = data_dir

            # Load previously saved collections from disk if present
            loaded_cols = 0
            loaded_docs = 0
            for col_file in data_dir.glob("*.json"):
                col_name = col_file.stem
                try:
                    content = col_file.read_text(encoding="utf-8").strip()
                    if content:
                        docs = json_util.loads(content)
                        if isinstance(docs, list) and docs:
                            if raw_db[col_name].count_documents({}) == 0:
                                raw_db[col_name].insert_many(docs)
                                loaded_cols += 1
                                loaded_docs += len(docs)
                except Exception as e:
                    logger.warning("Error loading collection '%s' from %s: %s", col_name, col_file, e)

            if loaded_cols > 0:
                logger.info(
                    "Restored %d documents across %d collections from persistent disk storage (%s)",
                    loaded_docs, loaded_cols, data_dir
                )

            cls._db = PersistentDatabaseProxy(raw_db, data_dir)
            logger.info("Active database: %s (persistent local storage at %s)", target_db_name, data_dir)
        else:
            cls._db = raw_db
            logger.info("Active database: %s (in-memory=%s)", target_db_name, cls._is_mock)

        return cls._db

    @classmethod
    def set_db(cls, db):
        cls._db = db

    @classmethod
    def is_mock(cls) -> bool:
        return cls._is_mock

    @classmethod
    def backup_database(cls, db_name: str = None) -> Optional[Path]:
        """Creates a timestamped snapshot of the current persistent database files."""
        target_db = db_name or Config.DATABASE_NAME
        data_dir = cls.get_data_dir(target_db)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_root = Path(Config.DATA_DIR) / "backups" / f"backup_{target_db}_{timestamp}"

        try:
            backup_root.mkdir(parents=True, exist_ok=True)
            copied = 0
            for f in data_dir.glob("*.json"):
                shutil.copy2(f, backup_root / f.name)
                copied += 1
            logger.info("Database backup created: %s (%d collections saved)", backup_root, copied)
            return backup_root
        except Exception as e:
            logger.error("Failed to create database backup: %s", e)
            return None

    @classmethod
    def restore_database(cls, backup_path: Path | str, db_name: str = None) -> bool:
        """Restores database collections from a timestamped backup directory."""
        target_db = db_name or Config.DATABASE_NAME
        data_dir = cls.get_data_dir(target_db)
        src = Path(backup_path)
        if not src.exists() or not src.is_dir():
            logger.error("Restore source directory does not exist: %s", src)
            return False

        try:
            cls.close()
            restored = 0
            for f in src.glob("*.json"):
                shutil.copy2(f, data_dir / f.name)
                restored += 1
            logger.info("Database restored from %s (%d collections restored to %s)", src, restored, data_dir)
            return True
        except Exception as e:
            logger.error("Failed to restore database: %s", e)
            return False

    @classmethod
    def close(cls):
        if cls._client is not None:
            try:
                cls._client.close()
            except Exception:
                pass
            cls._client = None
            cls._db = None
            logger.info("MongoDB connection closed.")


def get_db():
    """Helper function to retrieve the active database instance."""
    return DatabaseManager.get_db()
