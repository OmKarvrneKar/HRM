# AI Samrat HRMS — Full Project Current Stage & Remaining Stages

**Workspace:** `d:\AI_samrat\Group3\HRM` (`HRM-main/` Flask backend + legacy templates, `frontend-react/` React 18 SPA)  
**Active Database / Storage (`HRM-main/.env`):** `office_hrm` (`MONGODB_URI=mongodb://localhost:27017/`, falling back automatically to `PersistentDatabaseProxy` over `mongomock` at `HRM-main/data/storage/office_hrm` when local MongoDB socket `27017` is unreachable)

---

## 1. Current Architecture Summary

| Layer | Technology & Location | Current State |
| :--- | :--- | :--- |
| **Primary UI (React SPA)** | React 18.2, Vite 5.4, Tailwind CSS 3.4, Lucide Icons, React Router 6, React Query 5 (`frontend-react/`) | `12` protected app routes + `2` public auth routes built cleanly into `HRM-main/frontend/static/dist/` (`1631` Vite modules) and served on `:5173` (dev) / `/app` (Flask static dist) |
| **Backend API & Server** | Python 3.11 / Flask 3.0.2 (`HRM-main/app.py`, `backend/routes/auth_routes.py`, `api_routes.py` [4,737 lines], `page_routes.py`) | Blueprint architecture with `30` domain services (`backend/services/`), ReportLab PDF salary slips, OpenPyXL exports, APScheduler background jobs |
| **Security & Auth** | Argon2 password hashing, PyJWT cookies/Bearer tokens, SVG CAPTCHA (`/api/auth/captcha`), MongoDB-backed `LoginRateLimiter` (`login_attempts`), OTP activation (`otp_service.py`), 5-role RBAC (`backend/permissions/rbac.py`) | Canonical roles: `employee`, `tl`, `manager`, `hr`, `admin` (plus legacy aliases `team_lead` -> `tl`, `hr_manager` -> `hr`, `organization` -> `manager`); Tasks 10, 11, and 12 security & isolation audits passing |
| **Legacy Templates** | `47` Jinja2 HTML files (`HRM-main/frontend/templates/`) | Still mounted under legacy server-rendered routes (`page_routes.py`); `enterprise/assets.html` and `enterprise/facilities.html` also cleaned of fabricated facility/desk fallbacks |

---

## 2. Live Production Storage Snapshot (`HRM-main/data/storage/office_hrm/`)

Measured directly across all `21` collection JSON files:

| Collection File | Records | Status / Meaning |
| :--- | :---: | :--- |
| `users.json` | **50** | `38` active verified accounts (`34` engineering interns `employee`, `1` `tl`, `1` `manager`, `1` `hr`, `1` `admin`) + `12` inactive imported candidates (`profile_status: pending_verification`, email-only records awaiting HR onboarding) |
| `teams.json` | **11** | Active organizational team structure |
| `projects.json` | **3** | Baseline/active project records |
| `leave_balances.json` / `leave_transactions.json` | **3 / 30** | Initialized leave balance ledger & history |
| `audit_logs.json` / `profile_change_logs.json` | **55 / 55** | Recorded security audit trail & profile history |
| `notifications.json` | **6** | Stored notification entries |
| `kudos_ledger.json` | **3** | Remaining kudos recognition entries |
| `facility_rooms.json` | **0** | Cleaned baseline (`ROOM-MANTHAN`, `ROOM-GURUKOOL`, `ROOM-SAMVAAD` purged; empty until HR/Admin adds physically verified rooms) |
| `seating_allocations.json` | **0** | Cleaned baseline (all `38` algorithmic desk/locker layouts purged; empty until HR/Admin assigns physically verified workstations) |
| `hardware_assets.json` / `software_licenses.json` / `asset_requests.json` | **0 / 0 / 0** | Empty clean inventory |
| `attendance_corrections.json`, `overtime_requests.json`, `leave_requests.json`, `travel_requests.json`, `expense_claims.json`, `login_attempts.json`, `skill_categories.json` | **0** each | Clean initial operational queues |

---

## 3. Current Stage — Completed Capabilities

### A. Implemented & Wired in the Active React SPA (`frontend-react/src/app/router.jsx`)
1. **Authentication & Account Activation** (`/login`, `/activate`): CAPTCHA verification, Employee ID/email login, OTP account activation, password reset flows.
2. **Role-Specific Dashboards** (`/dashboard` via `DashboardRouter.jsx`): Dedicated views for `AdminDashboard`, `HRDashboard`, `ManagerDashboard`, `TeamLeadDashboard`, and `EmployeeDashboard`.
3. **Attendance & Punch Clock** (`/attendance` + `PunchClockWidget`): IST (`Asia/Kolkata`) punch-in/punch-out, breaks, monthly calendar, attendance correction requests & multi-stage reviews, HR/team monitor.
4. **Leaves, WFH & Overtime** (`/leaves`): Leave balance checks, apply/cancel leave, TL/Manager approvals (HR strictly excluded from direct approvals per RBAC policy), WFH requests, and overtime portal.
5. **Skill Matrix** (`/skills`): Personal skills CRUD, trainer assessments & ratings, TL team matrix/gap view, and HR/Admin category management.
6. **Work Diary & Projects/Tasks** (`/work-diary`, `/projects`): Daily/monthly work diary logging, TL feedback, project approvals, eligible members, task creation, and weighted progress updates.
7. **Payroll & Payslips** (`/payroll`): Personal salary view, Admin/HR salary configuration (`AdminControlCenter`), payslip generation, and ReportLab PDF slip support.
8. **Enterprise Assets & Verified Facilities** (`/enterprise`): Hardware, software, meeting rooms, and workstation seating registry displaying honest empty states until HR/Admin registers verified records with physical inspection audit notes.
9. **Helpdesk & Grievances** (`/helpdesk`): Confidential complaint submission and authorized handling (isolated per RBAC).
10. **Celebrations, Birthdays & Holidays** (`/celebrations`): Monthly birthdays, kudos feed/leaderboard, and HR/Admin holiday management.
11. **Workforce Directory & Admin Control Center** (`/directory`, `/admin`): Verified vs `pending_verification` user filtering, HR/Admin user provisioning & onboarding, salary configuration, holidays, skill categories, and registry overview.

### B. Security & Data Isolation Hardening (Tasks 5–12)
- **Task 10 (RBAC & DB Isolation):** Verified strict `(Role.HR, Role.ADMIN)` gates on room/seating verification, `USE_FILE_PERSISTENCE=False` isolation during tests, and unchanged production JSON checksums (`test_task10_rbac_and_isolation_audit.py`).
- **Task 11 (Sensitive HR API Audit):** Remediated legacy `Role.ORGANIZATION` alias leaks, directory/search PII stripping, manager reporting-scope checks on leave/attendance reviews, and `target_type` audit-log filter bypasses (`TASK11_HR_API_AUTHORIZATION_AUDIT_REPORT.md` & `test_task11_hr_api_rbac_audit.py`).
- **Task 12 (Current Task — Clean Production Facilities & Desks):** Removed all `3` baseline rooms, `38` provisional desk layouts, backend seed loops, and UI placeholder defaults (`test_task12_clean_facilities_and_seating.py`).

---

## 4. Remaining Stages & Outstanding Items

Directly observed gaps across UI parity, operational readiness, tests, and technical debt:

### Stage 1 — Live Interactive QA & Production Operational Readiness
- **Interactive Browser E2E Walkthrough:** Automated Chrome attachment previously failed (`DevToolsActivePort` missing) and `/login` enforces interactive CAPTCHA; perform manual/browser verification across `:5173` and `:5000/app` for all 5 roles (`Employee`, `TL`, `Manager`, `HR`, `Admin`).
- **Pending Workforce Onboarding:** Review and onboard the `12` imported `pending_verification` candidates in `users.json` (`is_active: false`) via `/admin` once HR confirms their details (`profile_status`, names, roles, IDs).
- **Genuine Facility & Asset Entry:** Keep `facility_rooms`, `seating_allocations`, `hardware_assets`, and `software_licenses` empty until official floor plans and asset registries exist; enter verified records through HR/Admin workflows only.
- **Database & Mail Infrastructure Decisions:**
  - Confirm whether local MongoDB (`mongodb://localhost:27017/`) will run as a service in deployment or remain on `PersistentDatabaseProxy` disk storage.
  - Verify live SMTP configuration (`EMAIL_ENABLED=true` in `.env` fails with DNS resolution errors `[Errno 11001]` in offline/sandbox environments).
  - Confirm with HR whether the `3` remaining records in `kudos_ledger.json` are genuine or should be cleared.

### Stage 2 — React SPA Feature Parity for Unmigrated Backend Modules
The Flask backend (`api_routes.py`) and `47` legacy Jinja templates contain modules that do **not** yet have React pages or active `.jsx` wiring in `frontend-react/src/app/router.jsx`:
- **Direct Chat & Unified Communication:** `frontend-react/src/features/communication/` contains no `.jsx` views (`chat_service.py` & `communication/*.html` exist in Flask only).
- **In-App Notifications UI & Audit/Settings Consoles:** `enterpriseApi.getNotifications` and `adminApi.getAuditLogs` / `getSettings` / `updateSettings` exist in API service wrappers, but are not called in `Navbar.jsx` or `AdminControlCenter.jsx`.
- **Unmigrated Enterprise / HR Workflows:** Travel Desk & Expense Claims UI (`facilities.html` parity), Recruitment & ATS (`recruitment.html`), Separation & 4-Way Clearance (`separation.html`), Policy Vault (`policies.html`), Performance KRA & L&D Courses (`performance.html`), PIP & Feedback (`pip_service.py`, `feedback_service.py`), Analytics Dashboard (`analytics.html`), Shift Roster Management UI (`roster_service.py`), Secure Document Vault (`document_service.py`), and Multi-Sheet Administrative ZIP Export (`export_service.py`).

### Stage 3 — UI Cleanup, Packaging & Full Pytest Synchronization
- **Remaining Minor UI Defaults in React:** Clean leftover visual fallbacks observed outside Assets/Facilities (e.g., `'AS-1001'` fallback in `PayrollCenter.jsx`, `users.length || 38` in `HRDashboard.jsx`, `users.length || 50` in `TeamDirectoryView.jsx`, and pre-selected `'Engineering'` / `'Engineering Intern'` modal defaults in `AdminControlCenter.jsx`), plus configure code-splitting for the `506.51 kB` Vite bundle warning.
- **Legacy Jinja Deprecation Decision:** Either sync or retire server-rendered HTML templates under `HRM-main/frontend/templates/` so `/app` (React) is the single UI surface.
- **`requirements.txt` & Pytest Suite Alignment:**
  - Add `reportlab` and `mongomock` explicitly to `HRM-main/requirements.txt` (currently imported by `salary_pdf_service.py` and `connection.py`, missing from `requirements.txt`).
  - Of `290` collected pytest tests in `HRM-main/tests/`, security suites (`test_task12`, `test_task11`, `test_security_boundaries`, `test_task10`) pass, whereas older unit/integration suites (such as `test_hr_portal_and_leave_workflow.py`, `test_consolidated_workflows.py`, `test_ats_seating_tl_dashboard.py`, `test_app.py`, and other tests in `test_enterprise_hr_modules.py`) still reflect pre-Task 10/11/12 assertions, empty-fixture assumptions, or live SMTP expectations and need alignment.

### Stage 4 — Backend Modularization & Repository Delivery
- **Monolith Refactoring (Ongoing Technical Debt):**
  - Split `HRM-main/backend/routes/api_routes.py` (`4,737` lines) and `HRM-main/backend/services/enterprise_hr_service.py` (`2,765` lines) into focused domain blueprints/services.
  - Retire the in-memory SQLite SQLAlchemy shim in `HRM-main/backend/models/user.py` in favor of native MongoDB queries (noting `backend/auth/rate_limiter.py` already uses MongoDB `db.login_attempts`).
  - Add explicit CSRF token header validation if required alongside `HttpOnly`, `SameSite=Lax` JWT cookies.
- **Git Remote Push (Awaiting User Confirmation):** Repository replacement/push to `https://github.com/OmkarvrneKar/HRM` remains paused pending explicit confirmation.

