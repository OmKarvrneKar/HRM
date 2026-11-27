import os
from pathlib import Path
from dotenv import load_dotenv, dotenv_values

BASE_DIR = Path(__file__).resolve().parent
DOTENV_PATH = BASE_DIR / ".env"
_PRE_DOTENV_HRMS_DATA_DIR = (os.getenv("HRMS_DATA_DIR") or "").strip() or None
_DOTENV_VALUES = dotenv_values(DOTENV_PATH) if DOTENV_PATH.exists() else {}
_DOTENV_HRMS_DATA_DIR = (_DOTENV_VALUES.get("HRMS_DATA_DIR") or "").strip() or None
load_dotenv(DOTENV_PATH)


class Config:
    BASE_DIR = BASE_DIR
    DOTENV_PATH = DOTENV_PATH
    SECRET_KEY = os.getenv("SECRET_KEY")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "480"))

    @classmethod
    def validate_secrets(cls) -> None:
        """
        Validates that required cryptographic secrets are configured via environment.
        Fails safely with a clear, sanitized error when required secrets are missing.
        Never reveals or prints secret values in logs or diagnostic output.
        """
        missing = []
        if not cls.SECRET_KEY or not str(cls.SECRET_KEY).strip():
            missing.append("SECRET_KEY")
        if not cls.JWT_SECRET_KEY or not str(cls.JWT_SECRET_KEY).strip():
            missing.append("JWT_SECRET_KEY")

        if missing:
            raise RuntimeError(
                f"Critical Security Configuration Failure: Missing required environment secret(s): {', '.join(missing)}. "
                f"Application startup aborted safely. Secrets must be supplied through environment configuration."
            )
    
    # MongoDB & Persistence
    MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "office_hrm")
    USE_MOCK_DB = os.getenv("USE_MOCK_DB", "false").lower() == "true"
    USE_FILE_PERSISTENCE = os.getenv("USE_FILE_PERSISTENCE", "true").lower() == "true"
    
    # Persistent storage directory defaults to workspace data/storage so unconfigured runs stay synchronized
    DEFAULT_DATA_DIR = BASE_DIR / "data" / "storage"
    _IMPORT_TIME_ENV_HRMS_DATA_DIR = _PRE_DOTENV_HRMS_DATA_DIR
    _DOTENV_HRMS_DATA_DIR = _DOTENV_HRMS_DATA_DIR
    _IMPORT_TIME_DATA_DIR = Path(os.getenv("HRMS_DATA_DIR", str(DEFAULT_DATA_DIR)))
    DATA_DIR = _IMPORT_TIME_DATA_DIR
    PERSISTENT_DATA_DIR = DATA_DIR

    @classmethod
    def get_storage_path_details(cls, db_name: str = None) -> dict:
        """
        Resolves the active storage base and database directory alongside configuration provenance.
        Distinguishes between external/process environment variable, .env file, class override, and default config.
        """
        workspace_default_base = (cls.BASE_DIR / "data" / "storage").resolve()
        target_db = db_name or cls.DATABASE_NAME
        env_now = (os.getenv("HRMS_DATA_DIR") or "").strip() or None

        class_data_dir_overridden = (
            cls is not Config
            and Path(cls.DATA_DIR) != Path(Config._IMPORT_TIME_DATA_DIR)
        ) or (
            cls is Config
            and Path(cls.DATA_DIR) != Path(cls._IMPORT_TIME_DATA_DIR)
        )

        if class_data_dir_overridden:
            base_dir = Path(cls.DATA_DIR)
            source = "config attribute override (DATA_DIR)"
        elif env_now and (
            cls._IMPORT_TIME_ENV_HRMS_DATA_DIR is not None
            or env_now != cls._DOTENV_HRMS_DATA_DIR
        ):
            base_dir = Path(env_now)
            source = "environment variable (HRMS_DATA_DIR)"
        elif cls._DOTENV_HRMS_DATA_DIR and Path(cls.DATA_DIR) == Path(cls._DOTENV_HRMS_DATA_DIR):
            base_dir = Path(cls.DATA_DIR)
            source = f".env configuration ({cls.DOTENV_PATH})"
        elif env_now:
            base_dir = Path(env_now)
            source = "environment variable (HRMS_DATA_DIR)"
        else:
            base_dir = Path(cls.DEFAULT_DATA_DIR)
            source = "default configuration (Config.DEFAULT_DATA_DIR)"

        expanded_base = base_dir.expanduser()
        resolved_base = (
            expanded_base.resolve()
            if expanded_base.is_absolute()
            else (cls.BASE_DIR / expanded_base).resolve()
        )
        resolved_db_dir = (resolved_base / target_db).resolve()
        is_external_override = bool(
            source.startswith(("environment variable", ".env configuration"))
            and resolved_base != workspace_default_base
        )

        return {
            "database_name": target_db,
            "raw_base_dir": str(base_dir),
            "resolved_base_dir": str(resolved_base),
            "resolved_db_dir": str(resolved_db_dir),
            "workspace_default_dir": str(workspace_default_base),
            "source": source,
            "is_external_override": is_external_override,
        }

    # Timezone & Office Rules
    DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Asia/Kolkata")
    OFFICE_START_TIME = os.getenv("OFFICE_START_TIME", "10:00")
    OFFICE_END_TIME = os.getenv("OFFICE_END_TIME", "18:00")
    OFFICE_CUTOFF_TIME = os.getenv("OFFICE_CUTOFF_TIME", "19:00")
    CUTOFF_INTIMATION_MINUTES = int(os.getenv("CUTOFF_INTIMATION_MINUTES", "45"))
    LATE_GRACE_MINUTES = int(os.getenv("LATE_GRACE_MINUTES", "0"))

    # Server & Environment
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = FLASK_ENV == "development"
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "5000"))

    # Development Test Account Control (Strictly disabled by default, disabled in production)
    ENABLE_DEV_TEST_ACCOUNT = os.getenv("ENABLE_DEV_TEST_ACCOUNT", "false").lower() in ("true", "1", "yes")

    @classmethod
    def is_production(cls) -> bool:
        """Returns True if the application is running in production mode."""
        env = os.getenv("FLASK_ENV", getattr(cls, "FLASK_ENV", "development")).lower()
        return env in ("production", "prod")

    @classmethod
    def is_development(cls) -> bool:
        """Returns True if the application is running in development mode."""
        return not cls.is_production()

    @classmethod
    def allows_test_account(cls) -> bool:
        """Returns True only in non-production environments with test account explicitly enabled."""
        if cls.is_production():
            return False
        return os.getenv("ENABLE_DEV_TEST_ACCOUNT", "false").lower() in ("true", "1", "yes")

    # Development Inspection Endpoints Control (Strictly disabled by default, disabled in production)
    ENABLE_DEV_ENDPOINTS = os.getenv("ENABLE_DEV_ENDPOINTS", "false").lower() in ("true", "1", "yes")

    @classmethod
    def is_dev_endpoints_enabled(cls) -> bool:
        """
        Returns True ONLY if in development mode AND ENABLE_DEV_ENDPOINTS is explicitly enabled.
        Strictly returns False in production mode under all circumstances.
        Defaults to False.
        """
        if cls.is_production():
            return False
        return os.getenv("ENABLE_DEV_ENDPOINTS", "false").lower() in ("true", "1", "yes")

    # Development OTP Testing Mode (Strictly disabled by default, disabled in production)
    DEV_OTP_MODE = os.getenv("DEV_OTP_MODE", "false").lower() in ("true", "1", "yes")

    @classmethod
    def is_dev_otp_mode(cls) -> bool:
        """
        Returns True ONLY if in development mode AND DEV_OTP_MODE is explicitly enabled.
        Strictly returns False in production mode under all circumstances.
        Defaults to False.
        """
        if cls.is_production():
            return False
        return os.getenv("DEV_OTP_MODE", "false").lower() in ("true", "1", "yes")



    # Rate Limiting
    LOGIN_RATE_LIMIT_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "10"))
    LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300"))

    # Cookie settings
    JWT_COOKIE_NAME = "hrm_access_token"
    COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    COOKIE_HTTPONLY = True
    COOKIE_SAMESITE = "Lax"

    # Outbound SMTP Email Configuration
    HR_EMAIL = os.getenv("HR_EMAIL", "hr.ramya@aisamrat.com").strip()
    EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "").lower() in ("true", "1", "yes")
    SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = (os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME") or "").strip()
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "noreply@aisamrat.com").strip()
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")



class TestConfig(Config):
    TESTING = True
    DATABASE_NAME = "office_hrm_test"
    SECRET_KEY = os.getenv("SECRET_KEY") or "test-isolated-unit-test-secret-key-32-chars-minimum"
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or "test-isolated-unit-test-jwt-secret-key-32-chars-min"
    LOGIN_RATE_LIMIT_ATTEMPTS = 100
    LOGIN_RATE_LIMIT_WINDOW_SECONDS = 60
    USE_FILE_PERSISTENCE = False

    @classmethod
    def validate_secrets(cls) -> None:
        pass
