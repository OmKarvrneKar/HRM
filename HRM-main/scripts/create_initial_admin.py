import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database.connection import get_db
from backend.auth.security import hash_password
from backend.permissions.rbac import Role
from backend.utils.validators import validate_email, validate_password_strength
from backend.services.audit_service import AuditService


def create_initial_hr_manager(full_name: str, email: str, password: str, employee_id: str = "MGR-1001"):
    db = get_db()
    email = email.strip().lower()

    if not validate_email(email):
        print(f"Error: Invalid email format '{email}'")
        sys.exit(1)

    valid, msg = validate_password_strength(password)
    if not valid:
        print(f"Error: Password too weak. {msg}")
        sys.exit(1)

    existing_email = db.users.find_one({"email": email})
    if existing_email:
        print(f"Error: User with email '{email}' already exists.")
        sys.exit(1)

    existing_id = db.users.find_one({"employee_id": employee_id})
    if existing_id:
        print(f"Error: Employee ID '{employee_id}' already exists.")
        sys.exit(1)

    admin_user = {
        "employee_id": employee_id,
        "full_name": full_name.strip(),
        "email": email,
        "password_hash": hash_password(password),
        "role": Role.HR_MANAGER,
        "department": "Human Resources Executive",
        "designation": "Chief HR Manager",
        "team_id": "TEAM-EXECUTIVE",
        "joining_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "employment_status": "Active",
        "is_active": True,
        "created_by": "SYSTEM_INIT",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }

    db.users.insert_one(admin_user)
    AuditService.log_action(
        actor=admin_user,
        action="INITIAL_HR_MANAGER_BOOTSTRAP",
        target_type="hr_manager",
        target_id=employee_id,
        details={"email": email, "full_name": full_name}
    )

    print(f"\n[SUCCESS] Initial HR Manager account created successfully!")
    print(f"   Name:        {full_name}")
    print(f"   Employee ID: {employee_id}")
    print(f"   Email:       {email}")
    print(f"   Role:        {Role.HR_MANAGER}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create the Initial HR Manager Account")
    parser.add_argument("--name", default="Vikramaditya Roy", help="Full name of the HR Manager")
    parser.add_argument("--email", default="admin.hrmanager@aisamrat.com", help="Email address")
    parser.add_argument("--password", default="Admin@Nexus2026!", help="Strong password")
    parser.add_argument("--id", default="MGR-1001", help="Employee ID")

    args = parser.parse_args()
    create_initial_hr_manager(args.name, args.email, args.password, args.id)
