import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import datetime, timezone
from backend.database.connection import DatabaseManager
from backend.services.attendance_service import AttendanceService
from backend.services.leave_service import LeaveService
from backend.services.skill_service import SkillService
from backend.services.user_service import UserService
from backend.permissions.rbac import Role
from backend.auth.security import hash_password, verify_password


def run_persistence_verification():
    print("============================================================")
    print("      AI SAMRAT HRMS — DATA PERSISTENCE VERIFICATION")
    print("============================================================")

    # 1. Initialize DB and check data directory
    db1 = DatabaseManager.get_db()
    data_dir = DatabaseManager.get_data_dir(db1.name)
    print(f"[1] Active database: {db1.name}")
    print(f"[1] Persistent data directory: {data_dir}")
    print(f"[1] Is mock engine: {DatabaseManager.is_mock()}")
    print(f"[1] Initial users count: {db1.users.count_documents({})}")

    # 2. Create a new employee record
    demo_emp_id = "EMP-DEMO-900"
    demo_email = "demo.persistence@aisamrat.com"

    # Remove if previously created from earlier run
    db1.users.delete_many({"employee_id": demo_emp_id})
    db1.attendance_events.delete_many({"employee_id": demo_emp_id})
    db1.leave_requests.delete_many({"employee_id": demo_emp_id})
    db1.skills.delete_many({"employee_id": demo_emp_id})

    new_user = {
        "employee_id": demo_emp_id,
        "full_name": "Vikram Malhotra",
        "email": demo_email,
        "password_hash": hash_password("Demo@Malhotra2026!"),
        "role": Role.EMPLOYEE,
        "department": "Engineering",
        "designation": "Staff AI Systems Engineer",
        "team_id": "TEAM-CORE-ENG",
        "joining_date": "2026-01-01",
        "employment_status": "Active",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    db1.users.insert_one(new_user)
    print(f"[2] Created Employee: {new_user['full_name']} ({demo_emp_id})")

    # 3. Record Attendance Check-In and Check-Out
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    check_in_event = {
        "employee_id": demo_emp_id,
        "employee_name": "Vikram Malhotra",
        "date": today_str,
        "session_id": "sess-demo-900",
        "event_type": "LOGIN",
        "timestamp": datetime.now(timezone.utc),
        "is_closed": False,
        "event_source": "WEB",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    db1.attendance_events.insert_one(check_in_event)
    print(f"[3] Recorded Attendance Check-In event for {demo_emp_id}")

    # 4. Submit a Leave Request
    leave_doc = {
        "employee_id": demo_emp_id,
        "employee_name": "Vikram Malhotra",
        "leave_type": "Casual Leave",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
        "days_count": 3,
        "reason": "Family engagement",
        "status": "Pending",
        "applied_at": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    db1.leave_requests.insert_one(leave_doc)
    print(f"[4] Submitted Leave Request: {leave_doc['leave_type']} ({leave_doc['days_count']} days)")

    # 5. Add Skill Matrix Entry
    skill_doc = {
        "skill_id": "SKL-DEMO-900",
        "employee_id": demo_emp_id,
        "employee_name": "Vikram Malhotra",
        "department": "Engineering",
        "team_id": "TEAM-CORE-ENG",
        "skill_name": "PyTorch & Large Language Models",
        "category": "AI/ML",
        "proficiency_level": "Expert",
        "proficiency_score": 4,
        "years_of_experience": 5.0,
        "experience_summary": "Trained and deployed LLM inference pipelines with quantization.",
        "learning_status": "Practicing",
        "certification_name": "NVIDIA Certified Generative AI Professional",
        "verified_status": "Verified",
        "trainer_rating": 5,
        "trainer_feedback": "World-class neural architecture expertise.",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    db1.skills.insert_one(skill_doc)
    print(f"[5] Added Skill Matrix Entry: {skill_doc['skill_name']} ({skill_doc['proficiency_level']})")

    # Verify files were written to disk
    persisted_files = list(data_dir.glob("*.json"))
    print(f"[6] Files written to persistent disk storage ({len(persisted_files)} files):")
    for f in persisted_files:
        print(f"    - {f.name} ({f.stat().st_size} bytes)")

    # 6. SIMULATE APPLICATION RESTART
    print("\n------------------------------------------------------------")
    print("[7] SIMULATING COMPLETE APPLICATION SHUTDOWN & RESTART...")
    print("------------------------------------------------------------")
    DatabaseManager.close()
    del db1

    # 7. RE-INITIALIZE DATABASE AS IF SERVER JUST STARTED
    db2 = DatabaseManager.get_db()
    print(f"[8] Reconnected to database: {db2.name}")

    # 8. VERIFY RECOVERED RECORDS
    restored_user = db2.users.find_one({"employee_id": demo_emp_id})
    assert restored_user is not None, "FAILED: Employee record was lost after restart!"
    assert restored_user["full_name"] == "Vikram Malhotra"
    assert verify_password("Demo@Malhotra2026!", restored_user["password_hash"]), "FAILED: Password hash invalid!"
    print(f"[SUCCESS] Employee record recovered intact: {restored_user['full_name']} ({restored_user['email']})")

    restored_att = db2.attendance_events.find_one({"employee_id": demo_emp_id})
    assert restored_att is not None, "FAILED: Attendance event lost after restart!"
    assert restored_att["event_type"] == "LOGIN"
    print(f"[SUCCESS] Attendance event recovered intact: {restored_att['event_type']} on {restored_att['date']}")

    restored_leave = db2.leave_requests.find_one({"employee_id": demo_emp_id})
    assert restored_leave is not None, "FAILED: Leave request lost after restart!"
    assert restored_leave["status"] == "Pending"
    assert restored_leave["days_count"] == 3
    print(f"[SUCCESS] Leave request recovered intact: {restored_leave['leave_type']} ({restored_leave['status']})")

    restored_skill = db2.skills.find_one({"employee_id": demo_emp_id})
    assert restored_skill is not None, "FAILED: Skill matrix entry lost after restart!"
    assert restored_skill["skill_name"] == "PyTorch & Large Language Models"
    assert restored_skill["trainer_rating"] == 5
    print(f"[SUCCESS] Skill matrix entry recovered intact: {restored_skill['skill_name']} (Rating: {restored_skill['trainer_rating']}/5)")

    # 9. TEST BACKUP FUNCTIONALITY
    backup_path = DatabaseManager.backup_database()
    assert backup_path is not None and backup_path.exists(), "FAILED: Database backup failed!"
    print(f"[SUCCESS] Database backup created successfully at: {backup_path}")

    print("\n============================================================")
    print("  RESULT: 100% PERSISTENCE VERIFICATION PASSED")
    print("  Employee, Attendance, Leave, & Skill records persist across restarts.")
    print("============================================================")


if __name__ == "__main__":
    run_persistence_verification()
