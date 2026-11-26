# 15. Master Project Context & AI Coding Agent Protocol

> [!IMPORTANT]
> **READ THIS DOCUMENT FIRST BEFORE TOUCHING OR MODIFYING ANY CODE IN THIS REPOSITORY.**
> This file contains the complete, authoritative operational protocol, architectural contracts, and safety rules for any human developer or AI coding agent working on AI Samrat HRMS.

---

## 1. System Identity & Mission

**AI Samrat HRMS** is an enterprise Human Resource Management System built for **AI Samrat Pvt Ltd**. It is a monolithic Python/Flask application serving 100 enterprise users across 11 squads, including 34 interns (`AS-1001` to `AS-1034`) sourced from `Intern-Full-Details.xlsx`.

### Core Operational Invariants:
- **Default Timezone**: All time calculations MUST use `Asia/Kolkata` (Indian Standard Time, UTC+05:30).
- **Office Hours**:
  - Official start: `10:00 AM IST` (logins after 10:00 are `LATE`).
  - Qualifying departure: `06:00 PM IST` (checkouts before 18:00 remain `INCOMPLETE`).
- **Canonical Roles**: Exactly five normalized roles exist:
  `Role.EMPLOYEE`, `Role.TL`, `Role.MANAGER`, `Role.HR`, `Role.ADMIN`.
- **Database Resilience**: Uses MongoDB on port 27017, but MUST gracefully fall back to `mongomock` with atomic JSON file persistence in `~/.ai_samrat_hrms/data/office_hrm/` whenever standalone MongoDB is unreachable.

---

## 2. Directory Layout & Critical File Map

```
HRM/
├── Intern-Full-Details.xlsx         # Master source for 34 intern profiles
├── LOGIN-CREDENTIALS.txt            # Quick testing accounts (EMP-1001, TL-1001, MGR-1001, HR-1001, ADM-1001)
├── start-dev.bat / stop-dev.bat     # Windows service control scripts
└── HRM-main/
    ├── app.py                       # App factory create_app(), blueprint registrations, root routes
    ├── config.py                    # Environment settings, secret validation, paths
    ├── diagnose.py                  # Pre-flight health and route test utility
    ├── requirements.txt             # Python dependencies
    ├── backend/
    │   ├── auth/                    # security.py (Argon2, JWT), rate_limiter.py
    │   ├── database/                # connection.py (MongoDB + mock proxy), seeds.py, indexes.py
    │   ├── models/                  # user.py (SQLAlchemy in-memory User model shim)
    │   ├── permissions/             # rbac.py (Role definitions, @require_auth, IDOR guards)
    │   ├── routes/                  # api_routes.py (254 routes), auth_routes.py, page_routes.py
    │   ├── scheduler/               # scheduler.py (APScheduler background jobs + locks)
    │   └── services/                # 30 domain services (attendance, skills, salary, leaves, etc.)
    └── frontend/
        ├── static/                  # css/style.css (188 KB), js/app.js (72 KB), img/
        └── templates/               # 47 Jinja2 templates (dashboards, attendance, skills, etc.)
```

---

## 3. Mandatory Architectural Contracts

### Contract 1: Authentication & Dual-Tab Login
- The login portal (`/login`) MUST enforce the dual-tab boundary:
  - **Employee Tab**: Accepts only `EMPLOYEE`, `TL`, and `TRAINER`. Reject `ADMIN`, `MANAGER`, and `HR` with **HTTP 403 Forbidden**.
  - **HR Tab**: Accepts only `HR`, `MANAGER`, and `ADMIN`. Reject `EMPLOYEE`, `TL`, and `TRAINER` with **HTTP 403 Forbidden**.
- JWT tokens MUST be stored in `HttpOnly`, `SameSite=Lax` browser cookies under the cookie name defined by `Config.JWT_COOKIE_NAME`. Never return raw JWT tokens in browser JavaScript contexts.

### Contract 2: IDOR Protection & Self-Service Isolation
- Interns (`AS-1001` through `AS-1034`) and general employees MUST be strictly isolated to their own records.
- Any new endpoint exposing employee data MUST wrap access with `can_access_employee_record(current_user, target_employee_id)`.
- Never expose salary CTC structures, confidential complaints, or audit logs to employee or manager roles without role validation.

### Contract 3: Database Persistence Proxy
- When writing code that interacts with the database, ALWAYS use `get_db()` from `backend.database.connection`.
- NEVER bypass `DatabaseManager.get_db()` or instantiate direct `pymongo.MongoClient()` instances in domain services. Direct client instantiation breaks the transparent JSON file persistence proxy used during local evaluation and sandboxed runs.

### Contract 4: Timezone Safety
- NEVER use raw `datetime.now()` or `datetime.utcnow()`.
- ALWAYS use `backend.utils.timezone.now_local()` or `datetime.now(timezone.utc)` converted to `Asia/Kolkata` for display and business logic calculations.

---

## 4. Instructions for Future AI Coding Agents

When tasked with modifying, fixing, or extending this codebase, adhere strictly to these rules:

1. **Read Existing Documentation First**: Review files in `PROJECT_DOCUMENTATION/` before writing any code.
2. **Inspect Existing Implementations**: Do not invent new services, utilities, or tables. Inspect `backend/services/` first. In 95% of cases, a service or helper already exists for your task.
3. **Preserve the Dual Database Model**: Ensure changes work seamlessly both with standalone MongoDB and the `mongomock` disk proxy fallback.
4. **Never Hardcode Secrets**: Always reference `Config.SECRET_KEY`, `Config.JWT_SECRET_KEY`, etc.
5. **Do Not Break Role Escalation Checks**: When writing tests or refactoring login routes, remember that attempting to login as an Admin via the Employee tab MUST yield HTTP 403.
6. **Always Verify Locally**:
   - Run `python diagnose.py` to confirm the Flask context and database initialize properly.
   - Run `pytest tests/unit/test_attendance_calc.py` to verify attendance engine integrity.
   - Run `Invoke-RestMethod -Uri "http://localhost:5000/api/health"` to confirm API health.

