# AI Samrat HRMS

Enterprise Human Resource Management System for **AI Samrat Pvt Ltd** covering workforce directory & onboarding, IST attendance & punch clock, multi-tier leave/WFH/overtime approvals, skill matrix & trainer assessments, daily work diaries, project & task tracking, payroll & PDF salary slips, helpdesk/grievances, celebrations, and verified facilities/assets management.

---

## 1. Technology Stack & Architecture

| Layer | Technology & Location | Role | Status |
| :--- | :--- | :--- | :--- |
| **Frontend** | React 18.2, Vite 5.4, Tailwind CSS 3.4, React Router 6, React Query 5, Axios, Chart.js (`apps/frontend/`) | Single-Page Application (SPA) on `:5173` (dev proxy to `:5000`); production bundle builds to `apps/backend/dist/` and is served directly by Flask (`/` and `/app`). | **Active** |
| **Backend** | Python 3.11+, Flask 3.0.2, PyJWT, Argon2, ReportLab, OpenPyXL, APScheduler (`apps/backend/`) | App factory (`create_app`), REST APIs (`/api/*`, `/api/auth/*`), 30 domain services, RBAC (`employee`, `tl`, `manager`, `hr`, `admin`), background scheduler, and brand assets (`assets/img/`). | **Active** |
| **Database & Persistence** | MongoDB (`pymongo`) with automatic `mongomock` + atomic JSON disk proxy (`apps/backend/database/`) | Uses `MONGODB_URI` (`office_hrm`); when standalone MongoDB is unreachable and mock persistence is enabled, stores collections atomically in JSON under `HRMS_DATA_DIR`. | **Active** |

---

## 2. Directory Structure

```text
HRM/
├── README.md                          # Developer onboarding guide (single repo doc)
├── .gitignore                         # Ignores .env, data/, dist/, caches, node_modules/
├── start-dev.bat / stop-dev.bat       # Convenience wrappers delegating to apps/backend/*.bat
└── apps/
    ├── frontend/                      # FRONTEND APPLICATION (React + Vite SPA)
    │   ├── index.html
    │   ├── package.json
    │   ├── postcss.config.js / tailwind.config.js
    │   ├── vite.config.js             # Dev proxy -> :5000; builds -> ../backend/dist
    │   └── src/
    │       ├── main.jsx
    │       ├── app/                   # App shell (App.jsx) & router (router.jsx)
    │       ├── components/
    │       │   ├── common/            # Reusable primitives (Badge, EmptyState, Loader, Modal, StatCard)
    │       │   └── layout/            # App chrome (MainLayout, Navbar, Sidebar, ProtectedRoute, PunchClockWidget)
    │       ├── context/               # AuthContext.jsx
    │       ├── hooks/                 # useAuth.js
    │       ├── features/              # Feature views grouped by domain:
    │       │   ├── admin/             # AdminControlCenter.jsx, TeamDirectoryView.jsx
    │       │   ├── attendance/        # AttendancePortal.jsx
    │       │   ├── auth/              # LoginPage.jsx, ActivateAccountPage.jsx
    │       │   ├── dashboard/         # Role dashboards + DashboardRouter.jsx
    │       │   ├── enterprise/        # AssetsInventory.jsx (assets, rooms, seating)
    │       │   ├── helpdesk/          # ComplaintListView.jsx
    │       │   ├── holidays/          # CelebrationsView.jsx
    │       │   ├── leaves/            # LeavePortal.jsx (leaves, WFH, overtime)
    │       │   ├── payroll/           # PayrollCenter.jsx
    │       │   ├── projects/          # ProjectListView.jsx
    │       │   ├── skills/            # SkillMatrixView.jsx
    │       │   └── workDiary/         # WorkDiaryView.jsx
    │       ├── services/api/          # apiClient.js + 10 domain API wrappers (*Api.js)
    │       └── styles/                # index.css
    │
    └── backend/                       # BACKEND API & PERSISTENCE (Python + Flask)
        ├── app.py                     # Flask factory create_app(), React SPA mount, /api/health
        ├── config.py                  # Config & TestConfig, BASE_DIR, storage provenance checks
        ├── diagnose.py                # Pre-flight import, build & /api/health smoke check
        ├── pytest.ini                 # Pytest configuration (testpaths = tests)
        ├── requirements.txt           # Core Python packages (+ reportlab & mongomock)
        ├── runtime.txt / Dockerfile / docker-compose.yml
        ├── Intern-Full-Details.xlsx   # Git-tracked master intern import workbook
        ├── start-dev.bat / stop-dev.bat
        ├── .env / .env.example        # Runtime env configuration (.env is gitignored)
        ├── assets/img/                # Brand logo & favicon served at /static/img/ & used in PDF slips
        ├── auth/                      # security.py (Argon2/PyJWT), rate_limiter.py
        ├── database/                  # connection.py, indexes.py, seeds.py
        ├── dist/                      # Compiled React SPA bundle (generated via npm run build)
        ├── models/                    # user.py (SQLAlchemy lookup shim)
        ├── permissions/               # rbac.py (5 canonical roles & IDOR guards)
        ├── routes/                    # auth_routes.py, api_routes.py
        ├── scheduler/                 # scheduler.py (APScheduler distributed jobs)
        ├── services/                  # 30 domain service modules (*_service.py)
        ├── utils/                     # serializers.py, timezone.py (Asia/Kolkata), validators.py
        ├── scripts/                   # Operational & admin CLI utilities:
        │   ├── maintenance/           # backup_restore.py, check_users.py, create_initial_admin.py
        │   ├── imports/               # import_employees.py, inspect_excel_import.py
        │   ├── migrations/            # migrate_to_five_roles.py, purge_dummy_and_seed_real_team.py
        │   └── diagnostics/           # verify_persistence_and_workflows.py
        ├── data/                      # Gitignored runtime storage & import input:
        │   ├── Intern-Full-Details(1).xlsx
        │   └── storage/
        │       ├── office_hrm/        # Live local JSON persistence collections
        │       ├── backups/           # Timestamped backup snapshots
        │       ├── chat_attachments/  # Uploaded chat files
        │       └── uploads/           # Uploaded HR documents
        └── tests/                     # Authoritative test suite:
            ├── conftest.py / test_app.py
            ├── unit/
            ├── integration/
            └── security/
```

*(Historical task reports, audits, BRD/PRD records, archived legacy Jinja UI templates, superseded scripts, and pre-cleanup database snapshots are stored externally in `D:\AI_samrat\Project_Records\HRMS\`.)*

---

## 3. Prerequisites & Environment Configuration

### Prerequisites
* **Python 3.11+** (`pip install -r apps/backend/requirements.txt`, plus ensure `reportlab` and `mongomock` are installed in the Python environment for PDF salary slips and local JSON persistence).
* **Node.js 18+ & npm** (for running Vite dev server and React builds in `apps/frontend/`).
* **MongoDB 6.0+/7.0+** *(optional locally — falls back to `mongomock` + disk JSON persistence when enabled)*.

### Environment Variables
Copy `apps/backend/.env.example` to `apps/backend/.env` if missing, and configure:
* **Secrets:** `SECRET_KEY`, `JWT_SECRET_KEY`, `JWT_ACCESS_TOKEN_EXPIRES_MINUTES`
* **Database & Storage:** `MONGODB_URI`, `DATABASE_NAME` (`office_hrm`), `HRMS_DATA_DIR` (`data/storage` relative to `apps/backend/` — startup logs exact resolved path & provenance and warns prominently if overridden outside workspace)
* **Attendance Rules (`Asia/Kolkata`):** `DEFAULT_TIMEZONE`, `OFFICE_START_TIME`, `OFFICE_END_TIME`, `OFFICE_CUTOFF_TIME`, `LATE_GRACE_MINUTES`
* **Outbound Email / OTP:** `EMAIL_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS`
* **Dev Flags (Keep `false` in production):** `DEV_OTP_MODE`, `ENABLE_DEV_ENDPOINTS`, `ENABLE_DEV_TEST_ACCOUNT`

---

## 4. Starting & Stopping the Application

### Development Mode (Recommended: React Vite + Flask Backend)
1. **Start Backend API (`http://127.0.0.1:5000`):**
   ```powershell
   cd apps\backend
   python app.py
   ```
2. **Start React Dev Server (`http://localhost:5173`):**
   ```powershell
   cd apps\frontend
   npm install   # first time only
   npm run dev
   ```
   Open `http://localhost:5173/login`. Vite proxies `/api/*` and `/static/*` to Flask `:5000`.

### Production Build Served via Flask (`/`)
1. Build the React SPA into `apps/backend/dist/`:
   ```powershell
   cd apps\frontend
   npm run build
   ```
2. Run `start-dev.bat` (from root or `apps\backend\`) or `python app.py` in `apps\backend\`.
   * React SPA: `http://127.0.0.1:5000/` (`/login`, `/app`, `/dashboard`, etc.)
   * Health check: `http://127.0.0.1:5000/api/health`

### Stopping the Application
* Press `Ctrl+C` in Vite/Flask terminals, or run `stop-dev.bat` (from root or `apps\backend\`) to stop active processes listening on ports `5000` and `5173`.

---

## 5. Runtime Data & Logs

* **Active Runtime Database:** `apps/backend/data/storage/office_hrm/` (or MongoDB `office_hrm` when reachable).
* **Backups & Attachments:** `apps/backend/data/storage/backups/`, `chat_attachments/`, and `uploads/documents/`.
* **Logs:** Flask, startup storage diagnostics, and scheduler events log to standard console output (`stdout`/`stderr`) using Python `logging`.

---

## 6. Running Tests

Run tests from inside `apps/backend/` (`apps/backend/pytest.ini` sets `testpaths = tests`):

### Recommended Isolated Security, RBAC & Core Suites
```powershell
cd apps\backend
pytest tests/security/test_task15_startup_idempotency_and_storage.py tests/security/test_task13_eliminate_provisional_ui_and_storage.py tests/security/test_task12_clean_facilities_and_seating.py tests/security/test_task11_hr_api_rbac_audit.py tests/security/test_security_boundaries.py tests/unit/test_attendance_calc.py tests/unit/test_leave_service.py tests/unit/test_work_diary_service.py tests/unit/test_birthday.py -v
```

### Standalone Security Isolation Audit & Pre-Flight Check
```powershell
cd apps\backend
python tests/security/test_task10_rbac_and_isolation_audit.py
python diagnose.py
```

---

## 7. Adding New Modules

* **New Frontend Module (`apps/frontend/src/`):**
  1. Add API calls in `src/services/api/<domain>Api.js` using `apiClient.js`.
  2. Add components/views under `src/features/<domain>/` reusing shared UI primitives in `src/components/common/`.
  3. Wire the route in `src/app/router.jsx` and navigation entry in `src/components/layout/Sidebar.jsx`.
  4. Run `npm run build` in `apps/frontend/` to refresh `apps/backend/dist/`.
* **New Backend Module (`apps/backend/`):**
  1. Add business logic class in `services/<domain>_service.py` using `get_db()` / `DatabaseManager.get_db()` (never direct `MongoClient()`).
  2. Register indexes in `database/indexes.py` and IST helpers from `utils/timezone.py`.
  3. Add route handlers in `routes/` guarded by `@require_auth`, `@require_roles(...)`, and `permissions/rbac.py` record-ownership checks, with `AuditService.log_action(...)` on sensitive actions.
  4. Add isolated tests using `db` / `TestConfig` under `apps/backend/tests/`.

---

## 8. Important Safety Notes (Data & Scripts)

* **Never delete or commit `apps/backend/.env`** or overwrite active files under `apps/backend/data/storage/office_hrm/`.
* **Excel Import Source:** `apps/backend/data/Intern-Full-Details(1).xlsx` (mirrored from `apps/backend/Intern-Full-Details.xlsx`) is the default Excel path used by `EmployeeImportService` and `scripts/imports/*.py`.
* **Operational Scripts (`apps/backend/scripts/`):**
  * Scripts under `scripts/migrations/` (`purge_dummy_and_seed_real_team.py`, `migrate_to_five_roles.py`) **mutate live database state** and create automatic backups — do **not** run them casually against production `office_hrm`.
  * Always create a backup first using `python scripts/maintenance/backup_restore.py --backup` (from `apps/backend/`).
* **Legacy Pytest Caution:** Several older tests under `apps/backend/tests/unit/` and `integration/` (`test_hr_portal_and_leave_workflow.py`, `test_phase1_gmail_otp_auth.py`, `test_ats_seating_tl_dashboard.py`, `test_portal_corrections_workflow.py`, `test_enterprise_workflows_consolidated.py`) call `get_db()` or `DatabaseManager.get_db("office_hrm")` directly or expect pre-cleanup fixtures (`EMP-1001`, 100 users, pre-Task 12 provisional rooms). Do not run those legacy suites against production storage without `TESTING=true` / `TestConfig` isolation.
