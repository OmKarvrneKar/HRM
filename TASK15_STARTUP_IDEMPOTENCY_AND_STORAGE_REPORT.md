# TASK 15 — STARTUP DATA MUTATION FIX & STORAGE PATH SAFETY REPORT

**Status:** Completed  
**Scope:** Application startup initialization and database storage path configuration only  
**Frontend Build:** Intentionally skipped (no frontend files were affected)

---

## 1. Root Cause of Startup Data Mutation

Investigation of `seed_real_and_dummy_users(db)` in [seeds.py](file:///d:/AI_samrat/Group3/HRM/HRM-main/backend/database/seeds.py) and persistence handling in [connection.py](file:///d:/AI_samrat/Group3/HRM/HRM-main/backend/database/connection.py) identified two causes for repeated startup writes to `projects.json` and database collections:

1. **Unconditional Project Overwrites (`seeds.py`)**
   - `seed_real_and_dummy_users(db)` previously called `db.projects.replace_one({"project_id": p["project_id"]}, p, upsert=True)` with freshly computed `now` timestamps (`created_at` / `updated_at`), overwriting `PRJ-ENG-01` and `PRJ-ENG-02` and mutating `projects.json` on every startup.
   - Hierarchy/approver backfills on `users`, `leave_requests`, `attendance_corrections`, `travel_requests`, `expense_claims`, and `asset_requests` were executed unconditionally on every startup even when nothing was missing.
2. **Unconditional Disk Rewrites on No-Op Operations (`connection.py`)**
   - `PersistentCollectionProxy` previously invoked `self._save()` after write methods even when zero documents were modified (`modified_count == 0`), upserted (`upserted_id is None`), or deleted (`deleted_count == 0`).

---

## 2. Files Changed & Fixes Implemented

| File | Summary of Changes |
| :--- | :--- |
| [config.py](file:///d:/AI_samrat/Group3/HRM/HRM-main/config.py) | Captured pre-`.env` OS environment `HRMS_DATA_DIR`, `.env` `HRMS_DATA_DIR` (via `dotenv_values`), and import-time `DATA_DIR` (`DEFAULT_DATA_DIR = BASE_DIR / "data" / "storage"`). Added `Config.get_storage_path_details(cls, db_name=None)` returning `database_name`, `raw_base_dir`, `resolved_base_dir`, `resolved_db_dir`, `workspace_default_dir`, provenance `source` (`environment variable (HRMS_DATA_DIR)`, `.env configuration`, or `default configuration`), and `is_external_override`. |
| [connection.py](file:///d:/AI_samrat/Group3/HRM/HRM-main/backend/database/connection.py) | Updated `PersistentCollectionProxy` (`update_one`, `update_many`, `replace_one`, `delete_one`, `delete_many`, `find_one_and_update`, `find_one_and_replace`, `find_one_and_delete`) to call `self._save()` only when records are actually modified, upserted, replaced, or deleted. Added `DatabaseManager.get_storage_details` and `DatabaseManager.log_active_storage` invoked during `DatabaseManager.get_db()` to log `INFO` path provenance and a `WARNING` (`EXTERNAL STORAGE OVERRIDE DETECTED: ...`) when `is_external_override` is `True`. Replaced silent fallback in `DatabaseManager.get_data_dir` with explicit `PermissionError` so unusable paths never silently switch databases or migrate data. |
| [seeds.py](file:///d:/AI_samrat/Group3/HRM/HRM-main/backend/database/seeds.py) | Made `seed_real_and_dummy_users(db)` idempotent: checks existence (`find_one(..., {"_id": 1})`) and uses `$setOnInsert` with `upsert=True` for `users`, `PREDEFINED_TEAMS` (5 teams), and `baseline_projects` (`PRJ-ENG-01`, `PRJ-ENG-02`) without overwriting existing records or timestamps; checks whether target missing/empty fields exist before running hierarchy/request backfills; deletes `legacy_fake_ids` only if matching rows exist; triggers `persist_to_disk()` only when `inserted_users`, `inserted_teams`, or `inserted_projects` is non-zero; and logs insertion counts. |
| [test_task15_startup_idempotency_and_storage.py](file:///d:/AI_samrat/Group3/HRM/HRM-main/tests/security/test_task15_startup_idempotency_and_storage.py) | Added 3 isolated tests covering repeated startup immutability, safe seeding of genuinely missing baseline rows without overwriting existing data, and storage path provenance / external `HRMS_DATA_DIR` warning logging. |

---

## 3. Task 15 Test Coverage

1. **`test_repeated_startup_does_not_mutate_projects_or_existing_records`**
   - Clones `office_hrm` into an isolated `TemporaryDirectory`, customizes `PRJ-ENG-01` (`title`, `progress_percentage=91`, `updated_at`) and `AS-1001` (`assigned_tl_id`, `manager_id`, `reporting_manager_id`), runs `create_app(..., start_scheduler=False)` twice, and verifies all JSON SHA-256 hashes (including `projects.json` and `users.json`) remain byte-identical across both startups and customized fields remain intact.
2. **`test_missing_initial_records_seeded_safely_without_overwriting_existing`**
   - Clears `users`, `teams`, and `projects` in `office_hrm_test`, pre-inserts a custom `PRJ-ENG-01` (`progress_percentage=88`, fixed `updated_at`), runs `seed_real_and_dummy_users(db)`, and verifies `PRJ-ENG-02`, all 5 `PREDEFINED_TEAMS`, and `>= 38` enterprise users are seeded while existing `PRJ-ENG-01` values and timestamps are untouched.
3. **`test_storage_path_reporting_and_external_override_warning`**
   - Verifies resolved paths and `source` reporting for `default configuration`, `.env configuration`, and `environment variable (HRMS_DATA_DIR)`.
   - Verifies `INFO` storage path logs with zero warnings for default and `.env` configurations.
   - Verifies `DatabaseManager.get_db("office_hrm")` honors a temporary external `HRMS_DATA_DIR` override while emitting a `WARNING` log containing `EXTERNAL STORAGE OVERRIDE DETECTED`.

---

## 4. Verification Results

### Targeted Pytest Suite (Run After Final Edit)
```powershell
pytest tests/security/test_task15_startup_idempotency_and_storage.py tests/security/test_task13_eliminate_provisional_ui_and_storage.py tests/security/test_task12_clean_facilities_and_seating.py tests/security/test_task11_hr_api_rbac_audit.py tests/security/test_security_boundaries.py tests/unit/test_purge_dummy_and_seed_real_team.py tests/unit/test_enterprise_hr_modules.py::test_facility_booking_service -v
```
* **Result:** `24 passed, 1 warning in 14.10s` (`0 failed`).

### Task 10 RBAC & Isolation Audit (Run After Final Edit)
```powershell
python ..\tests\test_task10_rbac_and_isolation_audit.py
```
* **Result:** `ALL TASK 10 RBAC & DATABASE TEST ISOLATION CHECKS PASSED 100%!` (Verified clean baseline: `0` rooms, `0` desks, and all 21 collection JSON hashes matched pre-test == post-test).

### Live Startup Logging Check (`create_app(start_scheduler=False)`, Run After Final Edit)
Observed startup logs:
```text
INFO:backend.database.connection:Resolved database storage path: D:\AI_samrat\Group3\HRM\HRM-main\data\storage\office_hrm (source: .env configuration (D:\AI_samrat\Group3\HRM\HRM-main\.env), workspace default: D:\AI_samrat\Group3\HRM\HRM-main\data\storage)
INFO:backend.database.connection:Restored 216 documents across 9 collections from persistent disk storage (D:\AI_samrat\Group3\HRM\HRM-main\data\storage\office_hrm)
INFO:backend.database.connection:Active database: office_hrm (persistent local storage at D:\AI_samrat\Group3\HRM\HRM-main\data\storage\office_hrm)
INFO:hrm_seeds:Database initialization verified (users_inserted=0, teams_inserted=0, projects_inserted=0).
```

### Unrelated Pre-Existing Unit Test Failures Observed (Not Modified per Scope)
Earlier exploratory regression runs surfaced pre-existing failures outside Task 15 scope:
* [test_dummy_approver_assignments.py](file:///d:/AI_samrat/Group3/HRM/HRM-main/tests/unit/test_dummy_approver_assignments.py) — `test_manager_overtime_view_includes_assigned_employees_outside_department` failed with `TypeError: 'NoneType' object is not subscriptable` because `MGR-1001` and all 34 seeded `employee` users in `ENTERPRISE_USERS` share `department: "Engineering"`.
* `tests/unit/test_render_default_seeding_and_login.py` — 3 failures (`test_seed_default_users_function` asserts `count == 4` vs. existing `DEFAULT_USERS_TO_SEED` size `5`, and `test_login_via_emp_id_json_employee` / `test_login_case_insensitivity` query legacy `EMP-1001` whereas `DEFAULT_USERS_TO_SEED` uses `AS-1001`, `TL-1001`, `MGR-1001`, `HR-1001`, `ADMIN-1001`).

---

## 5. Production Data Integrity (SHA-256 Checksums Pre vs. Post)

All 21 JSON files in [office_hrm](file:///d:/AI_samrat/Group3/HRM/HRM-main/data/storage/office_hrm) retained identical SHA-256 checksums before and after all tests, Task 10 audit, and live `create_app(start_scheduler=False)` execution:

| Collection File | SHA-256 Digest | Status |
| :--- | :--- | :--- |
| `asset_requests.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | MATCH |
| `attendance_corrections.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | MATCH |
| `audit_logs.json` | `8cc4846caf66fb8d967a0ed441be3e5929cc0e38fca8b3e308f8a3a27df13388` | MATCH |
| `expense_claims.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | MATCH |
| `facility_rooms.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | MATCH |
| `hardware_assets.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | MATCH |
| `kudos_ledger.json` | `21f964b25af0e81181e7a77d5cbb11a0110ffe4c4f70b0874fb6bc236ed3cc73` | MATCH |
| `leave_balances.json` | `90dcfadd5628e15a0b284d41a0ac9f6ec2391505116b0063647688d7fe2a3a2d` | MATCH |
| `leave_requests.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | MATCH |
| `leave_transactions.json` | `002bddc680ce427a407e75814af58d0252d5ae8ecfde8f34e9dcc1cbc32b116a` | MATCH |
| `login_attempts.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | MATCH |
| `notifications.json` | `91686277fbddf9647cdc97f97290cbd5e7555a078aa3545805464cad9abe283c` | MATCH |
| `overtime_requests.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | MATCH |
| `profile_change_logs.json` | `bc896d5198ba67fd857348d25c5710ee5ca7bb5b0913b44a2060553d3e3c2735` | MATCH |
| `projects.json` | `c9cd1fe5e57033cf6df4f4b8d1553003d013b7f0f6131a4013f6566d01a0740f` | MATCH |
| `seating_allocations.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | MATCH |
| `skill_categories.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | MATCH |
| `software_licenses.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | MATCH |
| `teams.json` | `d9900bcc7839cdcbda7939be1a431fc04e8986b01eb0e15c439584330df848ac` | MATCH |
| `travel_requests.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | MATCH |
| `users.json` | `fc0a6fa1f368950336a9a0a0991a74356161ef532f26e34f9e375fd2dc1624ca` | MATCH |

