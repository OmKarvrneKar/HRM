import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from database.connection import DatabaseManager
from permissions.rbac import Role

def run_migration():
    print("=" * 60)
    print("MIGRATION: AISAMRAT HRMS 5-ROLE CANONICAL STRUCTURE")
    print("=" * 60)
    
    db = DatabaseManager.get_db()
    
    # Backup current DB state before running migration
    print("[1/4] Creating snapshot backup before role migration...")
    DatabaseManager.backup_database(getattr(db, "name", "office_hrm"))
    
    print("[2/4] Inspecting users for legacy roles...")
    users = list(db.users.find({}))
    migrated_count = 0
    flagged_count = 0
    
    for u in users:
        emp_id = u.get("employee_id")
        email = u.get("email")
        current_role = u.get("role")
        updates = {}
        
        if current_role == "hr_manager":
            updates["role"] = Role.MANAGER
            updates["legacy_role"] = "hr_manager"
            print(f"  -> Migrating {emp_id} ({email}): 'hr_manager' -> 'manager'")
            migrated_count += 1
            
        elif current_role == "organization":
            # Map to manager, but flag for Admin review per prompt requirement
            updates["role"] = Role.MANAGER
            updates["legacy_role"] = "organization"
            updates["requires_role_review"] = True
            updates["role_review_reason"] = (
                "Account migrated from legacy 'organization' role to 'manager'. "
                "Admin confirmation required for departmental & operational scope."
            )
            print(f"  -> Migrating & FLAGGING {emp_id} ({email}): 'organization' -> 'manager' (flagged for review)")
            migrated_count += 1
            flagged_count += 1
            
        elif current_role == "trainer":
            # Map to team_lead, but flag for Admin review per prompt requirement
            updates["role"] = Role.TEAM_LEAD
            updates["legacy_role"] = "trainer"
            updates["requires_role_review"] = True
            updates["role_review_reason"] = (
                "Account migrated from legacy 'trainer' role to 'team_lead'. "
                "Admin confirmation required for assigned engineering team."
            )
            print(f"  -> Migrating & FLAGGING {emp_id} ({email}): 'trainer' -> 'team_lead' (flagged for review)")
            migrated_count += 1
            flagged_count += 1
            
        if updates:
            db.users.update_one({"_id": u["_id"]}, {"$set": updates})

    print(f"[3/4] Role Migration Complete: {migrated_count} accounts migrated, {flagged_count} flagged for Admin review.")
    
    # Verify all accounts now belong to the canonical 5 roles
    print("[4/4] Verifying all accounts adhere to 5-role model...")
    all_users = list(db.users.find({}, {"password_hash": 0}))
    canonical_roles = {Role.EMPLOYEE, Role.TEAM_LEAD, Role.HR, Role.MANAGER, Role.ADMIN}
    
    non_canonical = []
    for u in all_users:
        r = u.get("role")
        if r not in canonical_roles:
            non_canonical.append((u.get("employee_id"), u.get("email"), r))
            
    if non_canonical:
        print(f"ERROR: Found non-canonical roles: {non_canonical}")
        return False
    else:
        print("SUCCESS: 100% of accounts verified within 5 canonical roles:")
        for r in canonical_roles:
            count = sum(1 for u in all_users if u.get("role") == r)
            print(f"  - {r.upper():10}: {count} users")
            
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = run_migration()
    if not success:
        sys.exit(1)
