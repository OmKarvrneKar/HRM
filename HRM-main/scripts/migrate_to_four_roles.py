import sys
import os
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database.connection import DatabaseManager
from backend.permissions.rbac import Role, ROLE_LABELS

CANONICAL_ROLES = {Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR}

# Explicit mappings approved by system administrator
EXPLICIT_ACCOUNT_MAPPINGS = {
    "admin@aisamrat.com": {
        "role": Role.MANAGER,
        "designation": "Principal Infrastructure & Operations Manager",
        "reason": "Administrative infrastructure oversight mapped to Manager"
    },
    "mgr@aisamrat.com": {
        "role": Role.HR,
        "designation": "Head of HR Operations & People Lead",
        "reason": "HR management operations mapped to HR"
    },
    "org@aisamrat.com": {
        "role": Role.MANAGER,
        "designation": "Operations Director",
        "reason": "Company operational leadership mapped to Manager"
    },
    "trainer.rajesh@aisamrat.com": {
        "role": Role.TEAM_LEAD,
        "designation": "Technical Training & Competency Lead",
        "reason": "Technical training lead mapped to Team Lead"
    }
}


def run_migration():
    print("=" * 65)
    print("  AISAMRAT HRMS — 4-ROLE CANONICAL DATA MIGRATION")
    print("  Canonical Roles: EMPLOYEE, TEAM_LEAD, MANAGER, HR")
    print("=" * 65)

    db = DatabaseManager.get_db()

    # 1. Create safety backup snapshot before mutating any user records
    print("\n[1/5] Creating database snapshot before role migration...")
    backup_path = DatabaseManager.backup_database(getattr(db, "name", "office_hrm"))
    if backup_path:
        print(f"      Snapshot successfully saved to: {backup_path}")
    else:
        print("      Warning: Backup snapshot creation returned None.")

    # 2. Inspect all existing user accounts
    print("\n[2/5] Inspecting accounts for 4-role conformance...")
    users = list(db.users.find({}))
    migrated_count = 0
    flagged_count = 0
    already_canonical_count = 0

    for u in users:
        emp_id = u.get("employee_id")
        email = u.get("email", "").lower().strip()
        current_role = u.get("role")
        updates = {}

        # Check explicit admin-confirmed account overrides first
        if email in EXPLICIT_ACCOUNT_MAPPINGS:
            mapping = EXPLICIT_ACCOUNT_MAPPINGS[email]
            target_role = mapping["role"]
            if current_role != target_role:
                updates["role"] = target_role
                updates["legacy_role"] = current_role
                updates["designation"] = mapping["designation"]
                updates["migrated_at"] = datetime.now(timezone.utc)
                print(f"  -> Explicit Mapping: {emp_id} ({email}): '{current_role}' -> '{target_role}' ({mapping['reason']})")
                migrated_count += 1
            else:
                already_canonical_count += 1
        elif current_role in CANONICAL_ROLES:
            already_canonical_count += 1
        elif current_role in ("hr_manager",):
            updates["role"] = Role.HR
            updates["legacy_role"] = current_role
            updates["migrated_at"] = datetime.now(timezone.utc)
            print(f"  -> Standard Mapping: {emp_id} ({email}): 'hr_manager' -> 'hr'")
            migrated_count += 1
        elif current_role in ("trainer",):
            updates["role"] = Role.TEAM_LEAD
            updates["legacy_role"] = current_role
            updates["migrated_at"] = datetime.now(timezone.utc)
            print(f"  -> Standard Mapping: {emp_id} ({email}): 'trainer' -> 'team_lead'")
            migrated_count += 1
        elif current_role in ("admin", "organization"):
            updates["role"] = Role.MANAGER
            updates["legacy_role"] = current_role
            updates["migrated_at"] = datetime.now(timezone.utc)
            print(f"  -> Standard Mapping: {emp_id} ({email}): '{current_role}' -> 'manager'")
            migrated_count += 1
        else:
            # Ambiguous/Uncertain role: Do NOT automatically convert!
            updates["requires_role_review"] = True
            updates["role_review_reason"] = f"Uncertain role '{current_role}'. Flagged for explicit administrator decision."
            print(f"  [FLAGGED] {emp_id} ({email}): Unknown role '{current_role}' flagged for manual review.")
            flagged_count += 1

        if updates:
            db.users.update_one({"_id": u["_id"]}, {"$set": updates})

    print(f"\n[3/5] Migration Summary: {migrated_count} updated, {already_canonical_count} already canonical, {flagged_count} flagged.")

    # 3. Verify data preservation (attendance, leaves, salaries, projects)
    print("\n[4/5] Verifying integrity of associated employee records...")
    total_attendance = db.attendance_events.count_documents({})
    total_leaves = db.leave_requests.count_documents({})
    total_projects = db.projects.count_documents({})
    print(f"      Preserved Attendance Events: {total_attendance}")
    print(f"      Preserved Leave Requests:    {total_leaves}")
    print(f"      Preserved Projects:          {total_projects}")

    # 4. Final verification that all active accounts belong to the 4 roles
    print("\n[5/5] Enforcing 4-role model across 100% of accounts...")
    all_users = list(db.users.find({}, {"password_hash": 0}))
    non_canonical = []
    role_counts = {r: 0 for r in CANONICAL_ROLES}

    for u in all_users:
        r = u.get("role")
        if r in CANONICAL_ROLES:
            role_counts[r] += 1
        else:
            non_canonical.append((u.get("employee_id"), u.get("email"), r))

    if non_canonical:
        print(f"ERROR: Found non-canonical accounts requiring attention: {non_canonical}")
        return False

    print("SUCCESS: 100% of accounts confirmed in canonical 4-role structure:")
    for r in sorted(list(CANONICAL_ROLES)):
        print(f"  - {ROLE_LABELS[r].upper():18}: {role_counts[r]} account(s)")

    print("=" * 65)
    return True


if __name__ == "__main__":
    success = run_migration()
    if not success:
        sys.exit(1)
