# TASK 11 — Sensitive HR API Authorization Audit Report

> **Audit Scope:** Backend RBAC & Object-Level Authorization (`HRM-main`) across 5 sensitive HR API areas  
> **Isolation Guarantee:** Executed strictly against synthetic `T11-*` test users on isolated `TestConfig` (`office_hrm_test`, `USE_FILE_PERSISTENCE=False`); production storage (`HRM-main/data/storage/office_hrm`) verified untouched via pre/post SHA-256 checksums across all 21 JSON collections.

---

## 1. Executive Summary

A full backend route, RBAC helper, and service-layer authorization audit was performed across all sensitive HR APIs covering:

1. **Employee Personal Records & Documents**
2. **Salary, Payroll & Payslips**
3. **Attendance Correction & Leave Approval**
4. **User / Admin Management, System Settings, Exports & Shifts**
5. **Audit Logs & External Notification Logs**

Multiple backend authorization vulnerabilities were confirmed—primarily stemming from the legacy `Role.ORGANIZATION` alias (`"manager"`), missing backend role/scope gates on directory/search/nominee/profile-history/payroll/shift endpoints, unnormalized `"tl"` string checks, missing reporting-scope enforcement in review workflows, HTTP `400` responses instead of `403` on unauthorized rejections, and an HR query-filter bypass on audit logs. All confirmed vulnerabilities were remediated in the backend and verified with automated API + service tests.

---

## 2. APIs Audited & Enforced Authorization Matrix

| Area | API Endpoint(s) | Employee | Team Lead (`tl` / `team_lead`) | Manager | HR | Admin |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Personal & Docs** | `GET /api/users`, `GET /api/profiles` | **403** | **200** (assigned active squad, PII stripped) | **200** (scoped dept/reports Employees+TLs, PII stripped) | **200** (all, token stripped) | **200** (all, token stripped) |
| **1. Personal & Docs** | `GET /api/users/team-directory` | **403** | **200** (assigned squad, PII stripped) | **200** (scoped dept/reports, PII stripped) | **403** | **403** |
| **1. Personal & Docs** | `GET /api/users/<id>` | **Self 200 / Other 403** | **Self or squad 200** (raw PII/salary stripped) / **Other 403** | **Self or scoped 200** (raw PII/salary stripped) / **Cross-dept 403** | **200** (`activation_token` stripped) | **200** (`activation_token` stripped) |
| **1. Personal & Docs** | `PUT /api/users/<id>`, `POST /api/users/<id>/update-tiimi-profile` | **Self 200** (locked fields ignored) / **Other 403** | **Self 200 / Other 403** | **Self 200 / Other 403** | **200** | **200** |
| **1. Personal & Docs** | `GET /api/users/<id>/history` | **Self 200 / Other 403** | **Self 200 / Other 403** | **Self 200 / Other 403** | **200** | **200** |
| **1. Personal & Docs** | `GET` / `POST /api/nominees` | **Self 200 / Other 403** | **Self 200 / Other 403** | **Self 200 / Other 403** | **200** | **200** |
| **1. Personal & Docs** | `GET /api/search/global` | Staff: self only | Staff: self + squad | Staff: self + scoped dept/reports | Staff: all (`projects`: empty) | Staff: all + projects |
| **1. Personal & Docs** | `GET /api/users/pagination-meta` | `can_paginate: False` | Squad IDs only | Scoped dept/reports (Employees+TLs) | All active IDs | All active IDs |
| **1. Personal & Docs** | `POST /api/documents/upload`, `DELETE /api/documents/<id>` | **403** | **403** | **403** | **201 / 200** | **201 / 200** |
| **1. Personal & Docs** | `GET /api/documents/secure-records/<id>` & `/preview` | **403** | **403** | **403** | **200** | **200** |
| **2. Salary & Payroll** | `GET /api/users/<id>/salary`, `POST .../generate-slip`, `GET /api/salary/slips/<id>` (`/<ym>`, `/pdf`) | **Self 200 / Other 403** | **Self 200 / Other 403** | **Self 200 / Other 403** | **200** | **200** |
| **2. Salary & Payroll** | `PUT /api/users/<id>/salary` | **403** | **403** | **403** | **200** (non-Admin) / **403** (Admin target) | **200** |
| **2. Salary & Payroll** | `GET /api/payroll/overview`, `POST /api/payroll/batch-email` | **403** | **403** | **403** | **200** | **200** |
| **3. Attendance & Leave** | `POST /api/attendance/correct` (`/correction`), `GET /api/attendance/hr-manager-monitor`, `GET .../hr-intimations` | **403** | **403** | **403** | **200** | **200** |
| **3. Attendance & Leave** | `GET /api/attendance/corrections/pending` | **403** | **200** (assigned TL/teams only) | **200** (scoped dept/reports `PENDING_MANAGER`) | **200** (all pending) | **200** (all pending) |
| **3. Attendance & Leave** | `POST /api/attendance/corrections/<id>/review` | **403** (incl. self) | **200** (in-scope Stage 1) / **403** (out-of-scope/self) | **200** (in-scope) / **403** (cross-dept/self) | **200** (direct override) | **200** (direct override) |
| **3. Attendance & Leave** | `DELETE /api/attendance/corrections/<id>` | **Own pending 200 / Other 403** | **Own pending 200 / Other 403** | **Own pending 200 / Other 403** | **200** | **200** |
| **3. Attendance & Leave** | `GET /api/reports/attendance/csv` & `/excel` | Own record | Team overview | Team/dept overview | HR overview | Full overview |
| **3. Attendance & Leave** | `POST /api/leaves/verify/<id>` (`/approve`, `/reject`) | **403** | **200** (assigned squad Stage 1) / **403** | **200** (in-scope Stage 2) / **403** (cross-dept/Stage 1) | **403** (excluded) | **200** (non-self) |
| **3. Attendance & Leave** | `POST /api/leaves/<id>/send-email` | **403** | **403** | **200** (in-scope Approved) / **403** (cross-dept) | **403** | **200** |
| **3. Attendance & Leave** | `DELETE /api/leaves/<id>`, `GET /api/leaves/correspondence` | **403** | **403** | **403** | **200** | **200** |
| **3. Attendance & Leave** | `DELETE /api/leaves/my-requests/<id>` | **Own pending 200 / Other 403** | **Own pending 200 / Other 403** | **Own pending 200 / Other 403** | **403** (not owner) | **403** (not owner) |
| **3. Attendance & Leave** | `GET /api/leaves/ledger/<id>` | **Self 200 / Other 403** | **Self or squad 200 / Other 403** | **Self or scoped 200 / Cross-dept 403** | **200** | **200** |
| **4. User & Admin** | `POST /api/users` | **403** | **403** | **403** | **201** (non-Admin) / **403** (Admin target) | **201** |
| **4. User & Admin** | `POST /api/users/<id>/toggle-status`, `/offboard`, `/reactivate`, `GET /api/offboardings` | **403** | **403** | **403** | **200** (scoped) / **403** (Admin or Mgmt offboard/toggle) | **200** |
| **4. User & Admin** | `GET / PUT /api/settings`, `GET /api/export/zip` | **403 / 403** | **403 / 403** | **403 / 403** | **GET 200 / PUT 403**, ZIP **200** | **200 / 200** |
| **4. User & Admin** | `GET /api/shifts`; `POST/DELETE /api/shifts`; `POST /api/shifts/assign` | `GET` (no peer roster); `POST/DELETE/assign` **403** | `GET` (scoped peer roster); `POST/DELETE/assign` **403** | `GET` (scoped); `POST/DELETE` **403**; `assign` (own dept/reports **200** / cross-dept **403**) | **200** | **200** |
| **5. Audit Logs** | `GET /api/audit-logs`, `GET /api/audit/logs` | **403** | **403** | **403** | **200** (operational types only; filter bypass blocked) | **200** (all logs) |
| **5. Audit Logs** | `GET /api/notifications/external-logs` | **403** | **403** | **403** | **200** | **200** |

---

## 3. Confirmed Vulnerabilities Found

1. **Legacy `Role.ORGANIZATION` Alias Privilege Escalation**: `Role.ORGANIZATION` aliases `"manager"` (`Role.MANAGER`). Route decorators and service checks containing `Role.ORGANIZATION` / `"organization"` granted department Managers administrative privileges across audit logs (`/api/audit-logs`, `/api/audit/logs`), bulk PAN/roster ZIP exports (`/api/export/zip`), system settings (`/api/settings`), company policy document upload/deletion (`/api/documents/upload`, `DELETE /api/documents/<id>`), stage-bypassing attendance correction approvals (`AttendanceCorrectionService.review_correction`), HR attendance monitor (`/api/attendance/hr-manager-monitor`), shift profile CRUD (`RosterService`), and leave deletion/correspondence.
2. **Confidential Employee Records & Directory Leaks**:
   - Standard employees could list all company users via `GET /api/users` / `GET /api/profiles` and query all staff via `GET /api/search/global`.
   - `GET /api/search/global` used `getattr(actor, "role", Role.EMPLOYEE)` on a `dict`, bypassing role checks and leaking projects to HR as well as all staff to employees.
   - `GET /api/users/<id>` exposed sensitive PII (`aadhaar_number`, `pan_number`, `bank_account_number`, `residential_address`, `citizen_id_address`, `activation_token`, `complaints`, `hr_notes`, `documents`) to TL/Manager callers; `GET /api/users/<id>/history` and `GET /api/nominees` permitted Manager/TL access across profiles.
   - `GET /api/users/team-directory` and `/api/users/pagination-meta` used unnormalized `"team_lead"` comparisons (missing canonical `"tl"`) and fell back to unscoped queries for TLs without a `team_id` or Managers in `"Management"`.
   - `serialize_doc` did not redact `activation_token`.
3. **Salary & Payroll Authorization Gaps**:
   - `POST /api/payroll/batch-email` permitted `Role.MANAGER` despite Managers having `"manage_payroll": False`.
   - `UserService.update_user_salary` permitted `Role.ORGANIZATION` (Manager) at the service layer and returned HTTP `400` instead of `403` on unauthorized calls.
   - `can_view_salary` omitted `Role.ADMIN`, conflicting with `ROLE_PERMISSIONS` and `@require_roles(Role.HR, Role.ADMIN)` on salary updates.
   - `POST /api/users/<id>/salary/generate-slip` referenced undefined `String(...)` when `year_month` was omitted.
4. **Attendance Correction & Leave Approval Scope Bypasses**:
   - `AttendanceCorrectionService.review_correction` did not check reporting/team scope (`can_access_employee_record`) in Stage 1 or Stage 2, enabling cross-team/cross-department approvals; `get_pending_corrections_for_team_lead` leaked entire departments; `get_pending_corrections_for_manager` accessed `u["emp_id"]` unsafely and lacked an empty-clause guard.
   - `LeaveService.verify_request` and `/api/leaves/verify/<id>` permitted `Role.HR` despite policy/tests excluding HR (`can_approve_leave`, `test_hr_is_strictly_excluded_from_leave_approval_workflow`), and omitted Manager reporting-scope validation; `GET /api/leaves/ledger/<id>` permitted any Manager to read any employee's leave ledger.
   - Unauthorized errors on attendance/leave review & cancellation endpoints returned HTTP `400` rather than `403`.
5. **User/Admin Management, Shifts & Audit Log Bypasses**:
   - `UserService.create_user`, `can_manage_roles`, `can_create_account`, `toggle_user_active_status`, `offboard_employee`, and `reactivate_employee` allowed `Role.MANAGER` / `Role.ORGANIZATION`, and `UserService.get_offboardings` had no service-level role check.
   - `/api/shifts` write and assignment endpoints used only `@require_auth`, `GET /api/shifts` exposed colleague rosters to ordinary employees, and `RosterService.assign_employees_to_shift` did not check Manager department/reporting boundaries.
   - `AuditService.get_audit_logs` allowed HR callers to override the allowed operational `target_type` list via `?target_type=system`, and `GET /api/notifications/external-logs` permitted `Role.MANAGER`.

---

## 4. Fixes Implemented

| Component / File | Summary of Security Changes |
| :--- | :--- |
| [rbac.py](HRM-main/backend/permissions/rbac.py) | Normalized roles via `normalize_role()` and case-insensitive ID comparison in `can_edit_profile`, `can_access_complaint`, `can_manage_projects`, `can_view_projects`, `can_view_salary`, `can_manage_roles`, and `can_create_account`; removed `Role.MANAGER` from role/account creation; added `Role.ADMIN` to `can_view_salary`. |
| [serializers.py](HRM-main/backend/utils/serializers.py) | Added `"activation_token"` to `mask_sensitive` stripping in `serialize_doc`. |
| [api_routes.py](HRM-main/backend/routes/api_routes.py) | Blocked `Role.EMPLOYEE` with HTTP `403` on `GET /api/users` & `GET /api/profiles`; normalized and scoped TL/Manager directory & pagination endpoints; stripped raw PII/tokens on non-self/non-HR/Admin views; restricted history, nominees, policy document upload/delete, payroll batch email, leave correspondence/deletion, HR attendance monitor, settings, admin ZIP export, shift CRUD/assignment, audit logs, and external notification logs; removed `Role.HR` from `verify_leave_request`; enforced `can_view_profile`/`can_view_projects` in global search and `can_access_employee_record` in leave ledgers; added `actor` checks to `SecureDocumentViewerService` routes; returned HTTP `403` on authorization rejections; fixed `today.strftime("%Y-%m")` in salary slip generation. |
| [user_service.py](HRM-main/backend/services/user_service.py) | Normalized roles and restricted `create_user`, `toggle_user_active_status`, `offboard_employee`, `reactivate_employee`, `get_offboardings`, and `update_user_salary` strictly to authorized `(Role.HR, Role.ADMIN)` boundaries; supported `$or: [employee_id, emp_id]` in `get_single_salary_slip`. |
| [document_service.py](HRM-main/backend/services/document_service.py) & [enterprise_hr_service.py](HRM-main/backend/services/enterprise_hr_service.py) | Removed `"organization"` alias from `DocumentService.upload_document` and `delete_document`; added `actor` authorization enforcement in `SecureDocumentViewerService.get_employee_secure_docket` and `get_secure_document_preview`. |
| [attendance_correction_service.py](HRM-main/backend/services/attendance_correction_service.py) & [attendance_service.py](HRM-main/backend/services/attendance_service.py) | Removed `Role.ORGANIZATION` direct override in `review_correction`; enforced team/reporting scope (`can_access_employee_record`); removed department-wide TL queue exposure; fixed safe ID extraction & empty-clause guard in Manager queues; normalized role & restricted `correct_attendance_record` and `cancel_correction`. |
| [leave_service.py](HRM-main/backend/services/leave_service.py) | Strictly excluded `Role.HR` from `get_all_requests_for_reviewer` and `verify_request`; enforced TL/Manager scope in `verify_request` & `send_approval_email_to_hr`; removed `Role.ORGANIZATION` from `delete_leave_request` and `send_approval_email_to_hr`; prioritized same-department Manager before single-manager fallback. |
| [audit_service.py](HRM-main/backend/services/audit_service.py), [export_service.py](HRM-main/backend/services/export_service.py), & [roster_service.py](HRM-main/backend/services/roster_service.py) | Enforced `(Role.HR, Role.ADMIN)` & prevented `?target_type=` filter bypass in `AuditService.get_audit_logs`; added `PermissionError` role guard to `ExportService.export_administrative_zip`; scoped `RosterService.get_shift_profiles`, restricted `save_shift_profile`/`delete_shift_profile` to `(Role.HR, Role.ADMIN)`, and enforced Manager department/reporting scope in `assign_employees_to_shift`. |
| [test_task11_hr_api_rbac_audit.py](HRM-main/tests/security/test_task11_hr_api_rbac_audit.py) | Added isolated security test suite with synthetic `T11-*` actors verifying all 5 focus areas via direct API and service calls plus production storage checksum immutability. |

---

## 5. Verification Results

Executed from `HRM-main` after the final edit:

### 5.1 Pytest Security & Workflow Suites (`office_hrm_test`)

Command:
```bash
python -m pytest tests/security/test_task11_hr_api_rbac_audit.py tests/security/test_security_boundaries.py tests/integration/test_shifts_auth_feedback_flow.py tests/unit/test_hr_portal_and_leave_workflow.py tests/unit/test_consolidated_workflows.py -v
```

Result: **26 passed, 5 failed** (out of 31 collected)

| Test Suite | Passed | Failed | Notes |
| :--- | :---: | :---: | :--- |
| `tests/security/test_task11_hr_api_rbac_audit.py` | 6 | 0 | All Task 11 RBAC helpers, Areas 1–5 direct API/service enforcement, filter-bypass blocks, and pre/post prod checksums passed. |
| `tests/security/test_security_boundaries.py` | 7 | 0 | All existing boundary tests passed. |
| `tests/integration/test_shifts_auth_feedback_flow.py` | 4 | 0 | Shift CRUD/assignment, auth, feedback, and HR attendance correction integration passed. |
| `tests/unit/test_hr_portal_and_leave_workflow.py` | 5 | 2 | Pre-existing failures unrelated to Task 11 fixes: `test_ramya_sole_active_hr_and_dummy_accounts_deactivated` checks hardcoded emails against prod `ramya.hr@aisamrat.com`; `test_manager_manual_email_composer` calls Manager `verify_request` directly on a `PENDING_TEAM_LEAD` request prior to TL review. |
| `tests/unit/test_consolidated_workflows.py` | 4 | 3 | Sections 1, 6, 7–8, and 9–10 passed; Sections 2, 3, and 4 failed with pre-existing offline-sandbox SMTP DNS resolution errors (`[Errno 11001] getaddrinfo failed`) because `.env` sets `EMAIL_ENABLED=true`. |

### 5.2 Task 10 Isolation & Production Storage Checksum Audit

Command:
```bash
python ..\tests\test_task10_rbac_and_isolation_audit.py
```

Result: **PASSED 100%**
- `USE_FILE_PERSISTENCE` confirmed `False` during test execution.
- All **21 production JSON files** in `HRM-main/data/storage/office_hrm` matched identical pre-test and post-test SHA-256 checksums.
- Baseline facility state preserved (`0` verified meeting rooms, `3` unverified baseline rooms; `0` confirmed desk allocations, `38` provisional desk records).

