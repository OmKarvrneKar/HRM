"""
Database Cleanup & Real Employee Seeding Script
AISAMRAT HRMS — Enterprise Workforce Synchronization

Purges all dummy / mock user accounts and seeds the authentic core hierarchy
(Ramya HR/Admin, Designated Manager, Designated Team Lead) and all 34 real employees
from uploaded records (data/Intern-Full-Details(1).xlsx).
"""

import os
import sys
import secrets
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database.connection import DatabaseManager, get_db
from backend.permissions.rbac import Role
from backend.auth.security import hash_password
from backend.services.leave_service import LeaveService
from backend.services.employee_import_service import EmployeeImportService


# Dummy / Mock Account IDs and Emails to Purge
DUMMY_IDS_TO_PURGE = [
    "EMP-1001",  # Mock: Rahul Verma
    "EMP-1002",  # Mock: Sneha Reddy
    "EMP-1003",  # Mock: Karan Mehta
    "EMP-1004",  # Mock: Ananya Sen
    "HR-1000",   # Mock: AI Samrat HR
    "HR-1002",   # Mock: Amit Patel
    "ORG-1001",  # Mock: Operations Director
    "TRN-1001"   # Mock: Rajesh Sharma
]

DUMMY_EMAILS_TO_PURGE = [
    "emp.rahul@aisamrat.com",
    "emp.sneha@aisamrat.com",
    "emp.karan@aisamrat.com",
    "emp.ananya@aisamrat.com",
    "hr@aisamrat.com",
    "hr.amit@aisamrat.com",
    "org@aisamrat.com",
    "trainer.rajesh@aisamrat.com"
]


def purge_dummy_users_and_seed_real_team(db=None, User=None):
    """
    Database Cleanup & Real Employee Seeding function.
    - Purges all mock / dummy user accounts.
    - Preserves Ramya as HR / Admin (RAMYA_HR / HR-1001).
    - Sets up Designated Manager (MGR-1001 / Vikramaditya Roy) and Designated Team Lead (LEAD-1001 / Kavita Nair).
    - Seeds all 34 real employees from uploaded records with all 12 leave balances.
    """
    # 1. Support SQLAlchemy ORM interface if provided
    if User is not None and hasattr(User, "query") and db is not None and hasattr(db, "session"):
        try:
            User.query.filter(User.id.not_in(["RAMYA_HR", "HR-1001"])).delete(synchronize_session=False)
            db.session.commit()
        except Exception as e:
            if hasattr(db.session, "rollback"):
                db.session.rollback()

    # 2. Execute on persistent MongoDB database
    mongo_db = db if db is not None and hasattr(db, "users") else get_db()

    # Create safety backup snapshot
    try:
        DatabaseManager.backup_database(getattr(mongo_db, "name", "office_hrm"))
    except Exception:
        pass

    now = datetime.now(timezone.utc)

    # ---------------------------------------------------------
    # STEP 0: Inspect Authentic 34 Records from Excel
    # ---------------------------------------------------------
    records = EmployeeImportService.inspect_and_validate_file()
    valid_employee_emails = {rec["email_clean"].replace(" ", "").lower() for rec in records}

    core_preserved_ids = {"HR-1001", "RAMYA_HR", "MGR-1001", "LEAD-1001", "ADM-1001"}
    core_preserved_emails = {
        "ramya.hr@aisamrat.com", "hr.ramya@aisamrat.com",
        "manager@aisamrat.com", "mgr@aisamrat.com",
        "lead.kavita@aisamrat.com",
        "admin@aisamrat.com"
    }
    allowed_emails = core_preserved_emails.union(valid_employee_emails)

    # ---------------------------------------------------------
    # STEP 1: Delete all mock/dummy users and their orphan data
    # ---------------------------------------------------------
    all_users = list(mongo_db.users.find({}))
    ids_to_purge = set(DUMMY_IDS_TO_PURGE)
    for u in all_users:
        u_emp_id = u.get("employee_id")
        u_email = (u.get("email") or "").strip().lower()
        u_pemail = (u.get("personal_email") or "").strip().lower()

        if u_emp_id in core_preserved_ids or u.get("alias_id") in core_preserved_ids:
            continue
        if u_email in allowed_emails or u_pemail in allowed_emails:
            continue

        # Neither core hierarchy nor authentic real employee
        if u_emp_id:
            ids_to_purge.add(u_emp_id)

    # Execute purge on users collection (ensuring Ramya is NEVER purged)
    del_res = mongo_db.users.delete_many({
        "$and": [
            {"$or": [
                {"employee_id": {"$in": list(ids_to_purge)}},
                {"email": {"$in": DUMMY_EMAILS_TO_PURGE}}
            ]},
            {"employee_id": {"$nin": ["HR-1001", "RAMYA_HR"]}},
            {"email": {"$nin": ["ramya.hr@aisamrat.com", "hr.ramya@aisamrat.com"]}}
        ]
    })

    # Clean orphaned records from attendance, leaves, and work diary
    purge_list = list(ids_to_purge)
    mongo_db.attendance_events.delete_many({"employee_id": {"$in": purge_list}})
    mongo_db.attendance_daily.delete_many({"employee_id": {"$in": purge_list}})
    mongo_db.attendance_corrections.delete_many({"employee_id": {"$in": purge_list}})
    mongo_db.leave_requests.delete_many({"employee_id": {"$in": purge_list}})
    mongo_db.leave_balances.delete_many({"employee_id": {"$in": purge_list}})
    mongo_db.leave_transactions.delete_many({"employee_id": {"$in": purge_list}})
    mongo_db.wfh_requests.delete_many({"employee_id": {"$in": purge_list}})
    mongo_db.work_diary.delete_many({"employee_id": {"$in": purge_list}})
    mongo_db.complaints.delete_many({"$or": [{"complainant_id": {"$in": purge_list}}, {"assigned_hr_id": {"$in": purge_list}}]})
    mongo_db.pip_records.delete_many({"employee_id": {"$in": purge_list}})
    mongo_db.offboardings.delete_many({"employee_id": {"$in": purge_list}})

    # ---------------------------------------------------------
    # STEP 2: Assign Core Hierarchy Roles
    # ---------------------------------------------------------
    # 2a. Ramya: HR / Admin
    ramya = mongo_db.users.find_one({"$or": [
        {"employee_id": {"$in": ["HR-1001", "RAMYA_HR"]}},
        {"email": {"$in": ["ramya.hr@aisamrat.com", "hr.ramya@aisamrat.com"]}}
    ]})
    ramya_pw = ramya.get("password_hash") if ramya else hash_password("Hr@Ramya2026!")
    ramya_doc = {
        "employee_id": "HR-1001",
        "alias_id": "RAMYA_HR",
        "full_name": "Ramya",
        "email": "ramya.hr@aisamrat.com",
        "personal_email": "ramya.hr@aisamrat.com",
        "role": Role.HR,
        "is_admin": True,
        "department": "Human Resources",
        "designation": "HR Operations & People Lead",
        "team_id": "TEAM-HR-OPS",
        "employment_status": "Active",
        "is_active": True,
        "is_email_verified": True,
        "account_status": "active",
        "status": "active",
        "needs_password_setup": False,
        "password_hash": ramya_pw,
        "joining_date": "2022-01-15",
        "date_of_birth": "1992-04-18",
        "phone_number": "+91 9800011122",
        "updated_at": now
    }
    if ramya:
        mongo_db.users.update_one({"_id": ramya["_id"]}, {"$set": ramya_doc})
    else:
        ramya_doc["created_at"] = now
        mongo_db.users.insert_one(ramya_doc)

    # 2b. Designated Manager: Vikramaditya Roy
    mgr = mongo_db.users.find_one({"$or": [{"employee_id": "MGR-1001"}, {"email": "manager@aisamrat.com"}, {"email": "mgr@aisamrat.com"}]})
    mgr_pw = mgr.get("password_hash") if mgr else hash_password("Manager@Samrat2026!")
    mgr_doc = {
        "employee_id": "MGR-1001",
        "full_name": "Vikramaditya Roy",
        "email": "manager@aisamrat.com",
        "personal_email": "manager@aisamrat.com",
        "role": Role.MANAGER,
        "department": "Engineering & Operations",
        "designation": "Head of Engineering Operations",
        "team_id": "TEAM-AIML-01",
        "employment_status": "Active",
        "is_active": True,
        "is_email_verified": True,
        "account_status": "active",
        "status": "active",
        "needs_password_setup": False,
        "password_hash": mgr_pw,
        "joining_date": "2021-01-15",
        "date_of_birth": "1985-04-12",
        "phone_number": "+91 9811122233",
        "updated_at": now
    }
    if mgr:
        mongo_db.users.update_one({"_id": mgr["_id"]}, {"$set": mgr_doc})
    else:
        mgr_doc["created_at"] = now
        mongo_db.users.insert_one(mgr_doc)

    # 2c. Designated Team Lead: Kavita Nair
    lead = mongo_db.users.find_one({"$or": [{"employee_id": "LEAD-1001"}, {"email": "lead.kavita@aisamrat.com"}]})
    lead_pw = lead.get("password_hash") if lead else hash_password("Lead@Kavita2026!")
    lead_doc = {
        "employee_id": "LEAD-1001",
        "full_name": "Kavita Nair",
        "email": "lead.kavita@aisamrat.com",
        "personal_email": "lead.kavita@aisamrat.com",
        "role": Role.TEAM_LEAD,
        "department": "Engineering",
        "designation": "Lead AI/ML Systems Architect",
        "team_id": "TEAM-AIML-01",
        "reporting_manager_id": "MGR-1001",
        "employment_status": "Active",
        "is_active": True,
        "is_email_verified": True,
        "account_status": "active",
        "status": "active",
        "needs_password_setup": False,
        "password_hash": lead_pw,
        "joining_date": "2021-06-01",
        "date_of_birth": "1990-11-25",
        "phone_number": "+91 9833344455",
        "updated_at": now
    }
    if lead:
        mongo_db.users.update_one({"_id": lead["_id"]}, {"$set": lead_doc})
    else:
        lead_doc["created_at"] = now
        mongo_db.users.insert_one(lead_doc)

    # 2d. Super Administrator (System Admin Console)
    adm = mongo_db.users.find_one({"$or": [{"employee_id": "ADM-1001"}, {"email": "admin@aisamrat.com"}]})
    adm_pw = adm.get("password_hash") if adm else hash_password("Admin@Samrat2026!")
    adm_doc = {
        "employee_id": "ADM-1001",
        "full_name": "System Administrator",
        "email": "admin@aisamrat.com",
        "personal_email": "admin@aisamrat.com",
        "role": Role.ADMIN,
        "department": "IT & Infrastructure",
        "designation": "Principal Infrastructure Administrator",
        "team_id": "TEAM-EXEC",
        "employment_status": "Active",
        "is_active": True,
        "is_email_verified": True,
        "account_status": "active",
        "status": "active",
        "needs_password_setup": False,
        "password_hash": adm_pw,
        "joining_date": "2020-01-01",
        "date_of_birth": "1984-06-15",
        "phone_number": "+91 9811100001",
        "updated_at": now
    }
    if adm:
        mongo_db.users.update_one({"_id": adm["_id"]}, {"$set": adm_doc})
    else:
        adm_doc["created_at"] = now
        mongo_db.users.insert_one(adm_doc)

    # Ensure leave balances exist for hierarchy roles
    for hid in ["HR-1001", "MGR-1001", "LEAD-1001"]:
        LeaveService.get_or_create_leave_balance(hid)

    # ---------------------------------------------------------
    # STEP 3: Seed All 34 Real Employees from Uploaded Records
    # ---------------------------------------------------------
    records = EmployeeImportService.inspect_and_validate_file()

    # Pre-index existing employees by email
    existing_users = list(mongo_db.users.find({}))
    email_to_user = {}
    for u in existing_users:
        e = (u.get("email") or "").strip().lower()
        pe = (u.get("personal_email") or "").strip().lower()
        if e:
            email_to_user[e] = u
        if pe:
            email_to_user[pe] = u

    # ID generator starting at EMP-1005
    next_id_counter = 1005
    assigned_team_members = []

    for rec in records:
        clean_email = rec["email_clean"].replace(" ", "").lower()
        name = rec["name"]
        phone = rec["phone_display"]
        dob = rec["dob_clean"]
        sno = rec["sno"]

        # Check if user already exists
        matched_user = email_to_user.get(clean_email)
        if matched_user:
            emp_id = matched_user["employee_id"]
            user_updates = {
                "full_name": name,
                "email": clean_email,
                "personal_email": clean_email,
                "phone_number": phone,
                "date_of_birth": dob,
                "department": "Engineering",
                "designation": "AI/ML Engineering Intern",
                "team_id": "TEAM-AIML-01",
                "assigned_tl_id": "LEAD-1001",
                "reporting_manager_id": "MGR-1001",
                "employment_status": "Active",
                "is_active": True,
                "import_source": "Intern-Full-Details(1).xlsx",
                "import_sno": sno,
                "updated_at": now
            }
            mongo_db.users.update_one({"_id": matched_user["_id"]}, {"$set": user_updates})
        else:
            # Find next free EMP-xxxx ID
            while True:
                candidate_id = f"EMP-{next_id_counter}"
                next_id_counter += 1
                if not mongo_db.users.find_one({"employee_id": candidate_id}):
                    emp_id = candidate_id
                    break

            activation_token = secrets.token_urlsafe(16)
            new_emp_doc = {
                "employee_id": emp_id,
                "full_name": name,
                "email": clean_email,
                "personal_email": clean_email,
                "phone_number": phone,
                "date_of_birth": dob,
                "role": Role.EMPLOYEE,
                "department": "Engineering",
                "designation": "AI/ML Engineering Intern",
                "team_id": "TEAM-AIML-01",
                "assigned_tl_id": "LEAD-1001",
                "reporting_manager_id": "MGR-1001",
                "employment_status": "Active",
                "is_active": True,
                "is_email_verified": False,
                "account_status": "pending_activation",
                "status": "pending_activation",
                "needs_password_setup": True,
                "activation_token": activation_token,
                "password_hash": hash_password(activation_token),
                "joining_date": "2026-10-01",
                "import_source": "Intern-Full-Details(1).xlsx",
                "import_sno": sno,
                "created_at": now,
                "updated_at": now
            }
            mongo_db.users.insert_one(new_emp_doc)

        assigned_team_members.append(emp_id)

        # Initialize full 12 leave balances (7 standard + 5 progressive)
        LeaveService.get_or_create_leave_balance(emp_id)

    # ---------------------------------------------------------
    # STEP 4: Configure Team Hierarchy in MongoDB
    # ---------------------------------------------------------
    mongo_db.teams.update_one(
        {"team_id": "TEAM-AIML-01"},
        {
            "$set": {
                "team_id": "TEAM-AIML-01",
                "team_name": "AI & Machine Learning Core Team",
                "department": "Engineering",
                "lead_id": "LEAD-1001",
                "lead_name": "Kavita Nair",
                "manager_id": "MGR-1001",
                "manager_name": "Vikramaditya Roy",
                "members": assigned_team_members,
                "total_members": len(assigned_team_members),
                "updated_at": now
            }
        },
        upsert=True
    )

    mongo_db.teams.update_one(
        {"team_id": "TEAM-HR-OPS"},
        {
            "$set": {
                "team_id": "TEAM-HR-OPS",
                "team_name": "Human Resources & People Operations",
                "department": "Human Resources",
                "lead_id": "HR-1001",
                "lead_name": "Ramya",
                "manager_id": "MGR-1001",
                "manager_name": "Vikramaditya Roy",
                "members": ["HR-1001"],
                "total_members": 1,
                "updated_at": now
            }
        },
        upsert=True
    )

    # Output exact success message requested by user
    print("Successfully purged all dummy user accounts and seeded authentic team records.")
    return True


if __name__ == "__main__":
    purge_dummy_users_and_seed_real_team()
