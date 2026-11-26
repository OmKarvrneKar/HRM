# Current Task Output — Remove Fabricated Facility & Desk Data from Production

**Module:** Enterprise Assets, IT & Facilities (`AssetsInventory`, `SeatingLockerService`, `FacilityBookingService`)  
**Scope:** Backend seeds, domain services, Flask REST APIs, React SPA, legacy Jinja templates, production JSON storage, and isolated security/unit tests.

---

## 1. Objective & Business Constraints

- AI Samrat does **not** currently have an official floor plan, conference room registry, or verified desk/locker allocation list.
- All baseline/demo/fabricated meeting rooms, floors, capacities, equipment lists, and 38 provisional desk/locker allocations had to be identified and removed from production data and seed logic.
- Genuine employee records (`users.json`) could **not** be deleted.
- Verified room or workstation/locker records may **only** be created from explicit HR or Administrator input accompanied by mandatory physical inspection audit notes—never invented automatically via defaults or fallbacks.
- Empty states must appear across both Admin and Employee views when no verified records exist.

---

## 2. Sources of Fabricated / Baseline Data Identified & Removed

| Data Category | Identified Source | Resolution |
| :--- | :--- | :--- |
| **Baseline Meeting Rooms (`ROOM-MANTHAN`, `ROOM-GURUKOOL`, `ROOM-SAMVAAD`)** | `PREDEFINED_ROOMS` and startup loop in `HRM-main/backend/database/seeds.py` (invoked on Flask startup via `create_app`), `FacilityBookingService.PREDEFINED_ROOMS` & `_ensure_rooms_seeded` in `HRM-main/backend/services/enterprise_hr_service.py`, and persisted records in `HRM-main/data/storage/office_hrm/facility_rooms.json` | Purged `facility_rooms.json` (`3 -> 0` records); deleted `PREDEFINED_ROOMS`, `_ensure_rooms_seeded`, and startup room seeding |
| **Provisional Desk & Locker Layouts (`SL-ADMIN-1001`, `SL-AS-1001`..)** | `SeatingLockerService.seed_seating_allocations_if_empty` and default fallbacks in `allocate_or_update` (`enterprise_hr_service.py`), UI defaults (`FL3-A-01`, `LCK-301`, `Floor 3 — AI & Engineering Hub`, `Bay A`, `3rd Floor West Locker Bay`, `Dual 4K Monitor Mount...`, `else 100`, `autoSuggestBay`), and 38 persisted documents in `HRM-main/data/storage/office_hrm/seating_allocations.json` | Purged `seating_allocations.json` (`38 -> 0` records); deleted seeder method and all fallback/placeholder defaults across backend, React UI, and legacy templates |
| **Hardware Assets & Software Licenses** | Checked `HRM-main/data/storage/office_hrm/hardware_assets.json`, `software_licenses.json`, `asset_requests.json` | Already empty (`0` records each); verified preserved at `0` |
| **Genuine Employee Accounts** | `HRM-main/data/storage/office_hrm/users.json` | Untouched (`50` user records; SHA-256 prefix `fc0a6fa1f3689503`) |

---

## 3. Code & Test Changes Implemented

### Backend Seeds, Services & APIs
- `HRM-main/backend/database/seeds.py`:
  - Removed `PREDEFINED_ROOMS` and the `db.facility_rooms.replace_one(...)` seeding block inside `seed_real_and_dummy_users(db)`.
- `HRM-main/backend/services/enterprise_hr_service.py`:
  - Added `_persist_if_proxy(db)` helper so admin-verified room/seating/booking mutations flush cleanly under `PersistentDatabaseProxy`.
  - Removed `SeatingLockerService.seed_seating_allocations_if_empty`, `FacilityBookingService.PREDEFINED_ROOMS`, and `_ensure_rooms_seeded`.
  - Hardened `SeatingLockerService.allocate_or_update` and `FacilityBookingService.create_room` to enforce `Role.HR` / `Role.ADMIN`, require explicit physical attributes (`floor`, `bay`, `desk_number` for seating; `name`, `floor`, positive `capacity` for rooms) plus mandatory `notes`/`verification_notes`, prohibit placeholder defaults on omitted optional fields (`features`, `amenities`, `locker_number`), mark admin-created records verified with audit logging (`AuditService.log_action`), and persist to disk when using `PersistentDatabaseProxy`.
  - Required `room.get("is_verified")` in `FacilityBookingService.create_booking` so unverified rooms cannot be booked.
  - Restricted `all_seating` in `AssetSoftwareService.get_global_inventory` to `(Role.HR, Role.MANAGER, Role.ADMIN)` and normalized roles in `FacilityBookingService.delete_room` and `cancel_booking`.
- `HRM-main/backend/routes/api_routes.py`:
  - Updated `allocate_seating_locker_route` (`POST /api/assets/seating-lockers/allocate`), `create_facility_room_route` (`POST /api/facilities/rooms`), and `delete_facility_room_route` (`DELETE /api/facilities/rooms/<room_id>`) to `@require_roles(Role.HR, Role.ADMIN)`.
  - Mapped `"Unauthorized"` service errors to HTTP `403` across allocate, verify, create, and delete facility/seating endpoints.

### React SPA & Legacy Jinja Templates
- `frontend-react/src/services/api/enterpriseApi.js`:
  - Added `allocateSeating`, `createMeetingRoom`, and `deleteMeetingRoom`.
- `frontend-react/src/features/enterprise/AssetsInventory.jsx`:
  - Restricted `canManageFacilities` to `['admin', 'hr', 'hr_manager']`.
  - Removed fallback literals and outdated baseline-layout/room copy; added clear empty states when `verifiedRooms.length === 0` or `confirmedSeating.length === 0`.
  - Added HR/Admin **"Add Verified Room"**, room delete, and **"Assign Verified Workstation"** modal workflows requiring physical verification notes and zero auto-filled defaults.
- `frontend-react/src/features/admin/AdminControlCenter.jsx`:
  - Updated the registry overview panel text (`Facility, Asset & Seating Verification Registry`) to reflect purged baselines and Admin/HR verification requirements.
- `HRM-main/frontend/templates/enterprise/assets.html` & `HRM-main/frontend/templates/enterprise/facilities.html`:
  - Removed Jinja fallback literals (`FL3-A-01`, `LCK-301`, `Floor 3 — AI & Engineering Hub`, `Bay A (Frontend Web Experience)`, `3rd Floor West Locker Bay`, `Dual 4K Monitor Mount...`, `else 100`, pre-populated room capacity `12`/features, `autoSuggestBay`).
  - Added empty-state messaging, aligned HR/Admin permissions, and required physical verification notes when submitting allocations or rooms.

### Automated & Isolated Tests
- `HRM-main/tests/security/test_task12_clean_facilities_and_seating.py` (new):
  - `test_production_storage_and_seed_have_zero_fabricated_facilities_and_desks`: Proves `facility_rooms.json == []`, `seating_allocations.json == []`, `users.json` intact (`>= 38`), removed seed attributes absent, and `seed_real_and_dummy_users(db)` creates `0` rooms/desks.
  - `test_empty_state_no_defaults_and_verified_creation_across_admin_and_employee`: Proves empty initial responses for Admin & Employee, HTTP `403` on unauthorized roles, HTTP `400` when physical specs or verification notes are omitted, consistent verified visibility for Admin vs Employee (`my_seating` only on Employee; unassigned Employee sees `None`), booking block on unverified rooms, and Admin/HR delete rights.
  - `test_disk_persistence_across_reload_in_sandbox`: Proves clean empty startup and Admin-entered room/workstation persistence across simulated server restart inside a temporary directory with `PersistentDatabaseProxy`, leaving production JSONs untouched.
- `HRM-main/tests/unit/test_enterprise_hr_modules.py` & `tests/test_task10_rbac_and_isolation_audit.py`:
  - Updated `test_facility_booking_service` and Task 10 production baseline assertions (`0` unverified rooms, `0` provisional desks) while retaining synthetic test fixtures strictly inside isolated test databases.

---

## 4. Verification Results (Observed After Final Edit)

1. **Codebase Sweep (`Select-String`):**
   - `0` remaining matches for `ROOM-MANTHAN`, `ROOM-GURUKOOL`, `ROOM-SAMVAAD`, `FL3-A-01`, `LCK-301`, `3rd Floor West Locker Bay`, `Dual 4K Monitor Mount`, `Floor 3 — AI`, `PREDEFINED_ROOMS`, `seed_seating_allocations_if_empty`, `_ensure_rooms_seeded`, or `autoSuggestBay` across `HRM-main/frontend/templates`, `frontend-react/src`, and `HRM-main/backend`.
2. **React Production Build (`npm run build` in `frontend-react/`):**
   - Passed (`exit code 0`): `✓ 1631 modules transformed`, built bundle in `../HRM-main/frontend/static/dist/` (`index-7qE2VeHD.js`, `index-ClI7FyyN.css`, `index.html`) in `10.76s`.
3. **Pytest Targeted Security & Unit Suite (`office_hrm_test`):**
   - Command:
     ```bash
     pytest tests/security/test_task12_clean_facilities_and_seating.py tests/security/test_task11_hr_api_rbac_audit.py tests/security/test_security_boundaries.py tests/unit/test_enterprise_hr_modules.py::test_facility_booking_service -v
     ```
   - Result: **17 passed, 0 failed** (`exit code 0`, `14.11s`). *(Other unrelated legacy test suites were not part of this targeted verification run.)*
4. **Task 10 RBAC & Database Isolation Audit (`python ..\tests\test_task10_rbac_and_isolation_audit.py`):**
   - Passed (`exit code 0`): Confirmed JSON file persistence is disabled in tests, unauthorized roles receive HTTP `403`, authorized HR/Admin verify only synthetic fixtures, and all `21` production JSON SHA-256 checksums matched identically pre- vs post-test.
5. **Final Production Storage State (`HRM-main/data/storage/office_hrm/`):**
   - `facility_rooms.json`: `0` records (`4f53cda18c2baa0c`)
   - `seating_allocations.json`: `0` records (`4f53cda18c2baa0c`)
   - `hardware_assets.json`: `0` records (`4f53cda18c2baa0c`)
   - `software_licenses.json`: `0` records (`4f53cda18c2baa0c`)
   - `asset_requests.json`: `0` records (`4f53cda18c2baa0c`)
   - `users.json`: `50` records (`fc0a6fa1f3689503`)
6. **Live Backend Daemon Check:**
   - Flask app started on `http://127.0.0.1:5000` serving `office_hrm` from disk storage with `seed_real_and_dummy_users` leaving `facility_rooms` and `seating_allocations` empty (`0` records).
7. **Automated Browser Inspection Note:**
   - Headless Chrome verification via `chrome_devtools` could not attach because `DevToolsActivePort` was absent (`ENOENT`) and `/login` enforces an interactive CAPTCHA challenge (`GET /api/auth/captcha`), so live authenticated browser screenshots remain to be inspected interactively.

