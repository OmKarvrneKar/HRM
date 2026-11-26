Completed Task 15 (startup idempotency and storage path safety) with zero modifications to production HR records, business modules, or frontend files.

1. Root Cause & Changes Made
config.py
Added dotenv_values capture (_PRE_DOTENV_HRMS_DATA_DIR, _DOTENV_HRMS_DATA_DIR, _IMPORT_TIME_DATA_DIR, DEFAULT_DATA_DIR) and implemented Config.get_storage_path_details(cls, db_name=None) to resolve relative/absolute storage paths anchored to BASE_DIR, report provenance (environment variable (HRMS_DATA_DIR), .env configuration, or default configuration), and flag external overrides (is_external_override).
connection.py
Updated PersistentCollectionProxy (update_one, update_many, replace_one, delete_one, delete_many, find_one_and_update, find_one_and_replace, find_one_and_delete) to call self._save() only when records are actually modified (modified_count > 0), upserted (upserted_id is not None), or deleted (deleted_count > 0), eliminating unnecessary disk rewrites on no-op startup queries.
Added DatabaseManager.get_storage_details and DatabaseManager.log_active_storage, called during DatabaseManager.get_db() to log the resolved absolute database directory and its source at INFO, and emit a WARNING (EXTERNAL STORAGE OVERRIDE DETECTED: ...) whenever an external HRMS_DATA_DIR overrides the workspace default.
Replaced silent storage fallback in DatabaseManager.get_data_dir with an explicit PermissionError so failed directories never silently switch databases or migrate data.
seeds.py
Investigated seed_real_and_dummy_users(db): startup mutation was caused by unconditionally calling db.projects.replace_one({"project_id": p["project_id"]}, p, upsert=True) with fresh now timestamps (PRJ-ENG-01, PRJ-ENG-02) plus unconditional update_many/update_one backfills.
Updated seed_real_and_dummy_users(db) to check record existence first (find_one(..., {"_id": 1})) and insert missing users, PREDEFINED_TEAMS, and baseline_projects via $setOnInsert without overwriting existing records or timestamps; gated hierarchy/pending-request backfills, legacy fake-leave cleanup, and persist_to_disk() on actual missing/matching rows; and logged insertion counts (users_inserted=%d, teams_inserted=%d, projects_inserted=%d).
test_task15_startup_idempotency_and_storage.py
Added 3 isolated tests:
test_repeated_startup_does_not_mutate_projects_or_existing_records: clones production storage to a temporary directory, customizes PRJ-ENG-01 and AS-1001, runs create_app(..., start_scheduler=False) twice, and asserts all JSON SHA-256 hashes and customized records remain byte-identical.
test_missing_initial_records_seeded_safely_without_overwriting_existing: clears users, teams, projects in office_hrm_test, pre-inserts a custom PRJ-ENG-01, runs seed_real_and_dummy_users(db), and verifies missing PRJ-ENG-02, all 5 PREDEFINED_TEAMS, and 38 enterprise users are seeded while custom PRJ-ENG-01 (title, progress_percentage=88, updated_at) is preserved.
test_storage_path_reporting_and_external_override_warning: verifies default configuration, .env configuration, and environment variable (HRMS_DATA_DIR) resolution, confirms no warnings on workspace default/.env, and verifies DatabaseManager.get_db("office_hrm") honors an external directory override while logging the WARNING (EXTERNAL STORAGE OVERRIDE DETECTED).

(React frontend was unchanged, so React production build was intentionally skipped.)

2. Validation & Startup Log Output
Targeted pytest run (after final edit): pytest tests/security/test_task15_startup_idempotency_and_storage.py tests/security/test_task13_eliminate_provisional_ui_and_storage.py tests/security/test_task12_clean_facilities_and_seating.py tests/security/test_task11_hr_api_rbac_audit.py tests/security/test_security_boundaries.py tests/unit/test_purge_dummy_and_seed_real_team.py tests/unit/test_enterprise_hr_modules.py::test_facility_booking_service -v
Result: 24 passed in 14.10s (0 failed, 1 pytest-asyncio deprecation warning + RequestsDependencyWarning).
Task 10 RBAC & Database Isolation Audit (python ..\tests\test_task10_rbac_and_isolation_audit.py):
Result: ALL TASK 10 RBAC & DATABASE TEST ISOLATION CHECKS PASSED 100%!
Live Startup Logging Check (create_app(start_scheduler=False)):
Observed logs:
INFO:backend.database.connection:Resolved database storage path: D:\AI_samrat\Group3\HRM\HRM-main\data\storage\office_hrm (source: .env configuration (D:\AI_samrat\Group3\HRM\HRM-main\.env), workspace default: D:\AI_samrat\Group3\HRM\HRM-main\data\storage)
INFO:backend.database.connection:Restored 216 documents across 9 collections from persistent disk storage (D:\AI_samrat\Group3\HRM\HRM-main\data\storage\office_hrm)
INFO:hrm_seeds:Database initialization verified (users_inserted=0, teams_inserted=0, projects_inserted=0).
Note on Unrelated Pre-existing Unit Tests Observed:
Earlier regression runs encountered pre-existing failures outside Task 15 scope (left untouched per scope constraint):
test_dummy_approver_assignments.py (test_manager_overtime_view_includes_assigned_employees_outside_department failed with TypeError because MGR-1001 and all 34 seeded employee users in ENTERPRISE_USERS share department: "Engineering").
tests/unit/test_render_default_seeding_and_login.py (3 failures: expects 4 default users including EMP-1001, whereas existing DEFAULT_USERS_TO_SEED has 5 users starting with AS-1001).
3. Production Data Integrity (SHA-256 Pre vs. Post)

All 21 JSON files in office_hrm matched pre-edit SHA-256 checksums identically after all tests, Task 10 audit, and live create_app(start_scheduler=False) startup:

projects.json: c9cd1fe5e57033cf6df4f4b8d1553003d013b7f0f6131a4013f6566d01a0740f (MATCH)
users.json: fc0a6fa1f368950336a9a0a0991a74356161ef532f26e34f9e375fd2dc1624ca (MATCH)
teams.json: d9900bcc7839cdcbda7939be1a431fc04e8986b01eb0e15c439584330df848ac (MATCH)
audit_logs.json: 8cc4846caf66fb8d967a0ed441be3e5929cc0e38fca8b3e308f8a3a27df13388 (MATCH)
kudos_ledger.json: 21f964b25af0e81181e7a77d5cbb11a0110ffe4c4f70b0874fb6bc236ed3cc73 (MATCH)
leave_balances.json: 90dcfadd5628e15a0b284d41a0ac9f6ec2391505116b0063647688d7fe2a3a2d (MATCH)
leave_transactions.json: 002bddc680ce427a407e75814af58d0252d5ae8ecfde8f34e9dcc1cbc32b116a (MATCH)
notifications.json: 91686277fbddf9647cdc97f97290cbd5e7555a078aa3545805464cad9abe283c (MATCH)
profile_change_logs.json: bc896d5198ba67fd857348d25c5710ee5ca7bb5b0913b44a2060553d3e3c2735 (MATCH)
Remaining 12 empty collection JSONs (asset_requests.json, attendance_corrections.json, expense_claims.json, facility_rooms.json, hardware_assets.json, leave_requests.json, login_attempts.json, overtime_requests.json, seating_allocations.json, skill_categories.json, software_licenses.json, travel_requests.json): 4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945 (ALL MATCH)