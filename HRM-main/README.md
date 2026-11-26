# AI Samrat HRMS — Unified Enterprise Edition

Welcome to the **AI Samrat HRMS (Human Resource Management System)**, a unified, production-grade, and secure enterprise platform built for **AI Samrat Pvt Ltd**. 

This system merges the robust backend architecture, strict Role-Based Access Control (RBAC), and verified attendance calculation engine of `HRM-main` with authentic company branding, ReportLab vector salary slips, Indian holiday calendars, multi-sheet administrative ZIP exports, role-based login validation, and a **complete Competency & Skill Matrix module**.

---

## 1. High-Level Architecture & Tech Stack

- **Backend Framework**: Python 3.11+ / Python 3.14, Flask (Modular Blueprints: `auth_bp`, `api_bp`, `page_bp`).
- **Security & Cryptography**: Argon2 (`argon2-cffi`), PyJWT, HttpOnly SameSite Secure Cookies, server-side object-level access controls (IDOR protection), and server-side role validation during authentication.
- **Database Layer**: MongoDB 6.0+ / 7.0+ (`pymongo`) with resilient automated in-memory `mongomock` fallback for local evaluation when a standalone MongoDB service is not running.
- **Reporting & Generation**: ReportLab Platypus (high-fidelity vector PDF salary slips with company branding), OpenPyXL & ZipFile (multi-sheet Excel backup archives).
- **Task Scheduling**: APScheduler with distributed MongoDB lock synchronization for automated birthday greetings, morning cutoffs, and evening attendance reconciliation.
- **Frontend Architecture**: Light Enterprise Design System (Vanilla CSS tokens, responsive flex/grid layouts, Bootstrap 5.3 + Icons, Chart.js), no external dependencies or mock frames.
- **Test Automation**: Pytest suite (**62 automated unit, integration, role-security, persistence, and skill matrix tests**).

---

## 2. Company Branding & Design System

The application features a **Clean, Commercial Enterprise Light Theme**:
- **Official AI Samrat Branding**: Authentic company logo (`frontend/static/img/ai_samrat_logo.jpeg`) integrated into the login card, sidebar, topbar, and ReportLab PDF salary slips.
- **Curated Palette**: Soft slate-white background (`#f8fafc`), pristine white card surfaces (`#ffffff`), deep corporate navy for primary headers and actions (`#0f2942`, `#1e3a8a`), refined borders (`#e2e8f0`), and accessible high-contrast text.
- **Responsive Layout**: Full support for desktop, laptop, tablet, and mobile with a collapsible sidebar and sticky breadcrumb top navigation.
- **Zero Dead Elements**: Every button, navigation item, modal, and export link is connected to a live backend endpoint.

---

## 3. Supported User Roles & Permission Boundaries

The platform provides dedicated experiences for all six enterprise roles:

1. **ADMIN**: Highest-trust system administrator. Full configuration, user provisioning, system diagnostics, and audit logs.
2. **ORGANIZATION**: Company operations director. High-level team/project coordination and aggregated operational metrics. Strictly isolated from confidential employee complaints.
3. **HR**: HR generalist. Employee onboarding, attendance review & corrections, leave approvals, salary structure revisions, staff complaints handling.
4. **TEAM_LEAD**: Engineering/department lead. Project task assignments, member tracking, team skill matrices, and training recommendations.
5. **TRAINER**: Technical trainer. Skill evaluations with verified assessments, proficiency ratings, and trainee feedback.
6. **EMPLOYEE**: Core employee. Self attendance punch clock, profile, leaves, salary slip downloads, personal skill matrix, assigned tasks, and private direct messages.

---

## 4. Role-Based Login & Escalation Prevention

The login screen features **two visible tabs**: **Employee** and **HR**:
- **Employee Tab**:
  - `EMPLOYEE` accounts route to `/dashboard/employee`.
  - `TEAM_LEAD` accounts route to `/dashboard/team-lead`.
  - `TRAINER` accounts route to `/dashboard/trainer`.
  - `ADMIN`, `ORGANIZATION`, and `HR` accounts attempting login via Employee tab are safely rejected with **HTTP 403 Forbidden**.
- **HR Tab**:
  - `HR` accounts route to `/dashboard/hr`.
  - `ADMIN`, `ORGANIZATION`, and `HR_MANAGER` accounts route to `/dashboard/hr-manager`.
  - `EMPLOYEE`, `TEAM_LEAD`, and `TRAINER` accounts attempting login via HR tab are safely rejected with **HTTP 403 Forbidden**.

---

## 5. Skill Matrix Module

The platform features a dedicated **Skill Matrix** tab in the sidebar (`/skills`) connected to a live MongoDB backend:

### Employee Skill Matrix
- View personal skill matrix grouped by category.
- **Add New Skill Modal**: Record skills with name, category (*Programming, Web Development, Database, AI/ML, Cloud & DevOps, Tools, Soft Skills*), proficiency level (*Beginner, Intermediate, Advanced, Expert*), years of experience, learning status, certification name, and practical experience summary.
- Edit or delete self-reported skills.
- View Trainer verification status, 1–5 star ratings, and feedback notes.
- View training recommendations issued by Trainers and Team Leads.

### Corporate Trainer Center (`/dashboard/trainer` & `/skills`)
- Assigned trainees list with department and active status.
- **Assess Skill Modal**: Evaluate competencies, assign 1–5 star ratings, adjust verified proficiency levels, provide feedback notes, and mark as "Verified by Trainer".
- Dispatches automated notification to the employee upon assessment.

### Team Lead Center (`/dashboard/team-lead` & `/skills`)
- Team competency coverage matrix by category with average proficiency scores.
- **Skill Gap Diagnostics**: Automatically identifies high-severity gaps (categories with zero coverage) and medium-severity gaps (categories with low proficiency).
- **Recommend Training Modal**: Suggest targeted courses, certifications, or workshops with priority rankings (*Critical, High, Medium, Low*).

### HR Skill Overview (`/skills`)
- Company-wide skill inventory with keyword search and category filters.
- Real-time verified competency statistics and department breakdowns.

---

## 6. Attendance Calculation Engine (Asia/Kolkata)

1. **Office Start Time (`10:00 AM IST`)**:
   - Earliest login $\le$ 10:00 AM: marked as **`ON_TIME`**, delay = 0 minutes.
   - Earliest login $>$ 10:00 AM: marked as **`LATE`**, delay = minutes past 10:00 AM.
2. **Intermediate Sessions**:
   - Every login and logout event is permanently stored in `attendance_events`.
   - Multiple sessions during a single day are preserved without overwriting prior events.
3. **Official Final Qualifying Logout & Working Duration**:
   - Official working day threshold: `06:00 PM IST` (`18:00`).
   - Logout before 6:00 PM: daily summary remains **`INCOMPLETE`** (Pending Final Logout).
   - Valid logout at or after 6:00 PM: status becomes **`PRESENT`**.
   - **Official Working Duration**: Elapsed span between earliest login and qualifying final logout.

---

## 7. Startup & Windows Operations

The system provides easy 1-click batch scripts for rapid startup, health verification, and graceful shutdown.

### 1-Click Startup (Recommended)
Double-click `start-dev.bat` in the project root or run from PowerShell / Command Prompt:
```cmd
start-dev.bat
```
This script automatically:
1. Validates Python installation.
2. Checks and frees port 5000 if occupied by a stale zombie process.
3. Initializes the persistent data directory (`%USERPROFILE%\.ai_samrat_hrms\data\office_hrm`).
4. Verifies/seeds demo accounts without wiping existing real user modifications.
5. Launches the Flask server in a dedicated monitored console window.
6. Waits for `/api/health` to confirm server readiness, then automatically opens `http://localhost:5000/login` in your default browser.

### Graceful Shutdown
Double-click `stop-dev.bat` or run:
```cmd
stop-dev.bat
```
This safely terminates all background development server processes and releases port 5000.

### Health Check Endpoint
To verify server health and database persistence status at any time:
```
GET http://localhost:5000/api/health
```
Response:
```json
{
  "status": "healthy",
  "app_name": "AI Samrat HRMS",
  "database": {
    "name": "office_hrm",
    "mode": "persistent_disk",
    "is_mock": true,
    "data_dir": "C:\\Users\\Deepak\\.ai_samrat_hrms\\data\\office_hrm",
    "total_users": 11
  },
  "server_time_utc": "2026-10-25T16:49:09.522517+00:00"
}
```

---

## 8. Data Persistence Architecture

The application implements a **high-reliability dual-mode persistence architecture**:

1. **MongoDB Standalone Mode (Production & Staging)**:
   - When a MongoDB service (`mongodb://...` or Atlas cluster) is configured via `MONGO_URI`, PyMongo connects directly to the live server.
2. **Persistent Disk Proxy Mode (Local Development & Demo)**:
   - When running locally without a separate MongoDB daemon, the application engages `PersistentDatabaseProxy` and `PersistentCollectionProxy`.
   - All collections are atomically serialized to disk in BSON/JSON format at:
     ```
     %USERPROFILE%\.ai_samrat_hrms\data\office_hrm\
     ```
   - **Why this path?**: Storing data inside `%USERPROFILE%\.ai_samrat_hrms` completely avoids Windows Defender Controlled Folder Access blocks that intercept file creation in `%USERPROFILE%\Documents`.
   - **Atomic Writes**: Data is written via temporary swap files (`.tmp` -> atomic rename) with sync-to-disk guarantees on every mutating operation (`insert_one`, `insert_many`, `update_one`, `update_many`, `delete_one`, `delete_many`, `find_one_and_update`).
   - **Non-Destructive Seeding**: Startup seed scripts inspect existing collections and insert only missing baseline records. Existing employee changes, attendance logs, leave balances, and skill matrix updates are **strictly preserved** across reboots.
   - **Automated Snapshot Backups**: Any administrative reset automatically creates a timestamped archive under `%USERPROFILE%\.ai_samrat_hrms\data\backups\`.

---

## 9. Demo Credentials (For Local Evaluation)

| Role to Select on Login | Email | Password | Primary Dashboard & Capabilities |
|---|---|---|---|
| **Employee** | `emp.rahul@aisamrat.com` | `Emp@Rahul2026!` | `/dashboard/employee` &bull; Punch clock, work diary, personal skill matrix, salary PDF |
| **HR Operations** | `hr.priya@aisamrat.com` | `Hr@Priya2026!` | `/dashboard/hr` &bull; Staff directory, employee onboarding, leave approvals, ZIP export |
| **Trainer** | `trainer.rajesh@aisamrat.com` | `Trainer@Rajesh2026!` | `/dashboard/trainer` &bull; Trainee directory, evaluate skills, rate 1–5 stars, upskill |
| **Team Lead** | `lead.kavita@aisamrat.com` | `Lead@Kavita2026!` | `/dashboard/team-lead` &bull; Team roster, skill coverage matrix, gap diagnostics, training plan |
| **HR Manager** | `mgr@aisamrat.com` | `Admin@Nexus2026!` | `/dashboard/hr-manager` &bull; Org policies, system audit logs, administrative ZIP export |

---

## 10. Recommended Demo Walkthrough Script

For tomorrow's demonstration, follow this sequence:

1. **Launch**:
   - Double-click `start-dev.bat`. Watch the console confirm port availability, database persistence, and automated browser launch.
2. **Employee Workflow**:
   - Select role **Employee**, log in as `emp.rahul@aisamrat.com`.
   - Click **Check-In / Punch In** to record current attendance timestamp.
   - Navigate to **Skill Matrix**: Add a new skill (e.g. *FastAPI* or *Docker*, Advanced level, 2 years).
   - Navigate to **Leave Application**: Submit a leave request (e.g. Casual Leave for 2 days).
   - View **Salary Slip**: Click download to inspect the ReportLab vector PDF with AI Samrat header.
   - Log out.
3. **HR Operations Workflow**:
   - Select role **HR Operations**, log in as `hr.priya@aisamrat.com`.
   - Navigate to **Leave Approvals**: View Rahul's pending leave request and approve it with comments.
   - Navigate to **Employee Directory**: Onboard a new employee account (e.g. `EMP-NEW-101`).
   - Navigate to **Skill Inventory**: Verify Rahul's newly added skill appears in company inventory.
   - Log out.
4. **Trainer & Team Lead Workflow**:
   - Select role **Trainer**, log in as `trainer.rajesh@aisamrat.com`.
   - Navigate to Trainees: Find Rahul's new skill, give it a 5-star rating, and mark as "Verified".
   - Select role **Team Lead**, log in as `lead.kavita@aisamrat.com`.
   - View Team Skill Coverage Matrix and Diagnostic Gap analysis.
5. **Persistence Proof**:
   - Close the browser and terminate the server (`stop-dev.bat`).
   - Run `start-dev.bat` again.
   - Log back in as `emp.rahul@aisamrat.com` or `hr.priya@aisamrat.com`.
   - Demonstrate that Rahul's attendance punch, newly created employee, approved leave status, and verified skill matrix entries remain 100% saved and intact!

---

## 11. Automated Testing & Verification

Run the full automated test suite using Pytest:
```bash
python -m pytest tests/ -v
```

### Test Suite Summary: **62 Passed, 0 Failed (100% Success Rate)**
- `tests/unit/test_skill_matrix_and_roles.py` (4 tests): Role selection matching, privilege escalation rejection (HTTP 403), employee Skill Matrix CRUD, trainer assessments with star ratings, team lead coverage and gap recommendations.
- `tests/unit/test_attendance_calc.py` (7 tests): On-time, late delay calculations, multi-session preservation, 6 PM qualifying logout, elapsed span vs active session duration.
- `tests/unit/test_attendance_calendar.py` (3 tests): Monthly attendance grid generation and status collation.
- `tests/unit/test_birthday.py` (3 tests): Leap-year safe birthday detection and automated greeting dispatch.
- `tests/unit/test_holidays_and_exports.py` (6 tests): Holiday seeding, CRUD operations, ReportLab PDF salary slip byte generation, multi-sheet ZIP archive creation.
- `tests/unit/test_leave_service.py` (4 tests): Leave balances, deductions, weekend handling, and approval workflows.
- `tests/unit/test_profile_salary_skills.py` (8 tests): Salary information computation, historical salary slip generation, skills management.
- `tests/unit/test_work_diary_service.py` (4 tests): Work diary logging, validation, date filtering, and team reviews.
- `tests/integration/test_leave_api.py` (1 test): REST endpoints for leave submission and processing.
- `tests/integration/test_projects_complaints.py` (4 tests): Team creation, weighted project milestones, confidential complaint workflows.
- `tests/integration/test_work_diary_api.py` (2 tests): Work diary HTTP endpoints and authorization.
- `tests/security/test_security_boundaries.py` (7 tests): Strict RBAC validation, IDOR prevention, and HR Manager isolation from employee attendance and private complaints.
- `tests/integration/test_persistence_health.py` (3 tests): API health check endpoint, disk persistence proxy integrity, and non-destructive database seeding safety.

---

## 12. Production Deployment Readiness

The codebase is prepared for cloud deployment. To transition from local demo to cloud hosting:

### Environment Configuration
1. Copy `.env.production.example` to `.env`:
   ```bash
   cp .env.production.example .env
   ```
2. Configure production secrets:
   - `SECRET_KEY`: High-entropy 64+ char random string (e.g. `openssl rand -hex 32`).
   - `JWT_SECRET_KEY`: Distinct high-entropy 64+ char random string.
   - `MONGO_URI`: Production connection string (e.g. `mongodb+srv://admin:<password>@cluster0.mongodb.net/office_hrm?retryWrites=true&w=majority`).
   - `APP_URL`: Production domain (e.g. `https://hrms.aisamrat.com`).
   - `SESSION_COOKIE_SECURE`: `True` (forces HTTPS).

### Production WSGI Server
Do not run `python app.py` (Werkzeug development server) in production. Instead, run with a production WSGI server:
- **Linux / Docker**:
  ```bash
  pip install gunicorn
  gunicorn -w 4 -b 0.0.0.0:5000 --access-logfile - --error-logfile - "app:app"
  ```
- **Windows Server**:
  ```cmd
  pip install waitress
  waitress-serve --port=5000 "app:app"
  ```

### Nginx Reverse Proxy & SSL
Configure Nginx as a reverse proxy terminating SSL:
```nginx
server {
    listen 80;
    server_name hrms.aisamrat.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name hrms.aisamrat.com;

    ssl_certificate /etc/letsencrypt/live/hrms.aisamrat.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/hrms.aisamrat.com/privkey.pem;

    location /static/ {
        alias /path/to/HRM-main/frontend/static/;
        expires 30d;
    }

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
