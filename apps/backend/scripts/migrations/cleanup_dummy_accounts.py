import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.database.connection import DatabaseManager
from backend.permissions.rbac import Role

CANONICAL_TEST_ACCOUNTS = {
    "ADM-1001": {"email": "admin@aisamrat.com", "role": Role.MANAGER, "name": "System Administrator"},
    "LEAD-1001": {"email": "lead.kavita@aisamrat.com", "role": Role.TEAM_LEAD, "name": "Kavita Nair"},
    "HR-1001": {"email": "hr.ramya@aisamrat.com", "role": Role.HR, "name": "Ramya"}
}

DUMMY_IDS_TO_REMOVE = [
    "EMP-1001",
    "EMP-1002",
    "EMP-1003",
    "EMP-1004",
    "HR-1000",
    "HR-1002",
    "ORG-1001",
    "MGR-1001",
    "TRN-1001"
]


def run_cleanup():
    print("=" * 70)
    print("AISAMRAT HRMS — PHASE 1 DUMMY ACCOUNT PURGE & REAL EMPLOYEE ALIGNMENT")
    print("=" * 70)

    db = DatabaseManager.get_db()

    # 1. Database backup snapshot
    print("\n[1/5] Creating database snapshot...")
    backup_path = DatabaseManager.backup_database(getattr(db, "name", "office_hrm"))
    print(f"      Snapshot saved to: {backup_path}")

    # 2. Update canonical test accounts to verified active state
    print("\n[2/5] Ensuring 3 canonical test accounts are verified and active...")
    for emp_id, data in CANONICAL_TEST_ACCOUNTS.items():
        u = db.users.find_one({"employee_id": emp_id})
        if u:
            db.users.update_one(
                {"_id": u["_id"]},
                {
                    "$set": {
                        "is_email_verified": True,
                        "account_status": "active",
                        "status": "active",
                        "is_active": True,
                        "personal_email": data["email"],
                        "email": data["email"],
                        "role": data["role"]
                    }
                }
            )
            print(f"      [OK] Canonical Account: {emp_id} | {data['email']} | {data['role']}")
        else:
            print(f"      [WARN] Canonical Account {emp_id} not found!")

    # 3. Update real employees (EMP-1005 to EMP-1038) to pending_activation, is_email_verified: False
    print("\n[3/5] Aligning 34 real employee accounts (unverified Gmail pending first-time setup)...")
    real_count = 0
    all_users = list(db.users.find({}))
    for u in all_users:
        emp_id = u.get("employee_id", "")
        if emp_id.startswith("EMP-") and emp_id not in DUMMY_IDS_TO_REMOVE:
            email = u.get("email", "")
            personal = u.get("personal_email") or email
            db.users.update_one(
                {"_id": u["_id"]},
                {
                    "$set": {
                        "personal_email": personal,
                        "is_email_verified": False,
                        "account_status": "pending_activation",
                        "needs_password_setup": True,
                        "role": Role.EMPLOYEE
                    }
                }
            )
            real_count += 1
    print(f"      Aligned {real_count} real employee accounts to unverified/pending activation state.")

    # 4. Remove the 9 dummy accounts from users and clean their dummy records
    print("\n[4/5] Purging 9 dummy accounts and dummy associations...")
    users_del_res = db.users.delete_many({"employee_id": {"$in": DUMMY_IDS_TO_REMOVE}})
    print(f"      Deleted {users_del_res.deleted_count} dummy accounts from 'users'.")

    att_del = db.attendance_events.delete_many({"employee_id": {"$in": DUMMY_IDS_TO_REMOVE}})
    print(f"      Deleted {att_del.deleted_count} dummy attendance events.")

    leave_del = db.leave_requests.delete_many({"employee_id": {"$in": DUMMY_IDS_TO_REMOVE}})
    print(f"      Deleted {leave_del.deleted_count} dummy leave requests.")

    # Clean dummy IDs from teams
    for t in db.teams.find({}):
        new_members = [m for m in t.get("members", []) if m not in DUMMY_IDS_TO_REMOVE]
        new_lead = t.get("lead_id") if t.get("lead_id") not in DUMMY_IDS_TO_REMOVE else "LEAD-1001"
        db.teams.update_one({"_id": t["_id"]}, {"$set": {"members": new_members, "lead_id": new_lead}})
    print("      Cleaned team member references.")

    # 5. Final audit and verification
    print("\n[5/5] Final Database Audit:")
    remaining_users = list(db.users.find({}, {"password_hash": 0}))
    print(f"      Total Remaining Users in System: {len(remaining_users)}")
    role_tally = {}
    for ru in remaining_users:
        r = ru.get("role")
        role_tally[r] = role_tally.get(r, 0) + 1

    for r, count in sorted(role_tally.items()):
        print(f"      - {r.upper():12}: {count}")

    print("\n      Canonical Test Accounts Status:")
    for emp_id in CANONICAL_TEST_ACCOUNTS:
        u = db.users.find_one({"employee_id": emp_id})
        print(f"      - {emp_id}: {u.get('email')} | verified={u.get('is_email_verified')} | status={u.get('account_status')}")

    print("\n      Real Employee Verification Check (Sample 5):")
    sample_reals = list(db.users.find({"employee_id": {"$in": ["EMP-1005", "EMP-1010", "EMP-1020", "EMP-1030", "EMP-1038"]}}))
    for sr in sample_reals:
        print(f"      - {sr.get('employee_id')}: {sr.get('full_name')} | personal_email={sr.get('personal_email')} | verified={sr.get('is_email_verified')} | status={sr.get('account_status')}")

    print("=" * 70)
    print("PURGE AND ALIGNMENT COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    run_cleanup()
