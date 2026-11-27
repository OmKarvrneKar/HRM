import urllib.request
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.database.connection import DatabaseManager
from backend.auth.security import generate_jwt_token

def verify():
    db = DatabaseManager.get_db()
    total_users = db.users.count_documents({})
    print(f"Total DB users: {total_users}")

    # 1. Role verification
    imported_users = list(db.users.find({"employee_id": {"$regex": r"^EMP-10(0[5-9]|[1-3][0-9])$"}}))
    print(f"Total imported users found: {len(imported_users)}")
    all_emp_role = all(u.get("role") == "employee" for u in imported_users)
    print(f"All imported users have role EMPLOYEE: {all_emp_role}")

    # 2. Existing users preserved
    orig_users = list(db.users.find({"employee_id": {"$in": ["ADM-1001", "HR-1000", "EMP-1001", "LEAD-1001"]}}))
    print(f"Original anchor users preserved: {[u['employee_id'] for u in orig_users]}")

    def api_get(endpoint, token):
        req = urllib.request.Request(f"http://localhost:5000{endpoint}", headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req) as resp:
            return resp.getcode(), json.loads(resp.read())

    hr_user = db.users.find_one({"email": "hr@aisamrat.com"})
    hr_token = generate_jwt_token(hr_user)

    # 3. HR Directory
    c_dir, d_dir = api_get("/api/users", hr_token)
    print(f"HR Directory GET /api/users: status={c_dir}, total_users_returned={len(d_dir.get('users', []))}")

    # 4. Profile check for first imported employee (Sneha K - EMP-1005)
    first_emp = db.users.find_one({"employee_id": "EMP-1005"})
    c_prof, d_prof = api_get("/api/users/EMP-1005", hr_token)
    u_prof = d_prof.get("user", {})
    print(f"Profile EMP-1005: Name={u_prof.get('full_name')}, Role={u_prof.get('role')}, Phone={u_prof.get('phone_number')}, DOB={u_prof.get('date_of_birth')}, Skills={len(u_prof.get('skills', []))}")

    # 5. Attendance & Leave for imported employee
    emp_token = generate_jwt_token(first_emp)
    c_att, d_att = api_get("/api/attendance/today", emp_token)
    att_rec = d_att.get("attendance") or {}
    print(f"Attendance /api/attendance/today: status={c_att}, today_status={att_rec.get('status', 'NOT_CLOCKED_IN')}")

    c_leave, d_leave = api_get("/api/leaves/my-requests?status=ALL", emp_token)
    print(f"Leaves /api/leaves/my-requests: status={c_leave}, requests_count={len(d_leave.get('requests', []))}")

    # 6. Notifications for imported employee
    c_notif, d_notif = api_get("/api/notifications", emp_token)
    print(f"Notifications /api/notifications: status={c_notif}, count={len(d_notif.get('notifications', []))}")

    # 7. Check birthday service integration
    from backend.services.birthday_service import BirthdayService
    birthdays = BirthdayService.get_monthly_birthdays(year=2026, month=10)
    print(f"Birthday Service: {len(birthdays)} active celebrants found for October 2026.")
    nov_birthdays = BirthdayService.get_monthly_birthdays(year=2026, month=11)
    print(f"Birthday Service: {len(nov_birthdays)} active celebrants found for November 2026.")

if __name__ == "__main__":
    verify()
