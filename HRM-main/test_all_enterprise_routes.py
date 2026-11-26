import sys
sys.path.append(r'c:\Users\Deepak\Documents\HRMS\HRM-main')
from app import create_app
from backend.database.connection import get_db
from backend.auth.security import generate_jwt_token

app = create_app()
client = app.test_client()

db = get_db()
u_emp = db.users.find_one({"emp_id": "EMP-1001"})
token_emp = generate_jwt_token(u_emp)

u_lead = db.users.find_one({"emp_id": "TL-1001"})
token_lead = generate_jwt_token(u_lead)

u_mgr = db.users.find_one({"emp_id": "MGR-1001"})
token_mgr = generate_jwt_token(u_mgr)

u_hr = db.users.find_one({"emp_id": "HR-1001"})
token_hr = generate_jwt_token(u_hr)

u_admin = db.users.find_one({"emp_id": "ADMIN-1001"})
token_admin = generate_jwt_token(u_admin)

routes_to_test = [
    ("/dashboard/employee", token_emp, "Employee Dashboard"),
    ("/dashboard/team-lead", token_lead, "Team Lead Dashboard"),
    ("/dashboard/manager", token_mgr, "Manager Dashboard"),
    ("/dashboard/hr", token_hr, "HR Dashboard"),
    ("/dashboard/admin", token_admin, "Admin Dashboard"),
    ("/facilities", token_emp, "Facilities & Meeting Rooms"),
    ("/assets", token_emp, "Assets & Software"),
    ("/performance", token_emp, "Performance & Training"),
    ("/engagement", token_emp, "Engagement & Kudos"),
    ("/policies", token_emp, "Company Policies Vault"),
    ("/separation", token_emp, "Exit & Separation"),
    ("/recruitment", token_lead, "Recruitment, ATS & Scorecards"),
    ("/payroll-center", token_hr, "Enterprise Payroll Center"),
    ("/profile/EMP-1001", token_emp, "User Profile with Nominees"),
    ("/mailbox", token_emp, "Official Mailbox & Notices"),
]

all_passed = True
for path, token, name in routes_to_test:
    client.set_cookie("hrm_access_token", token, domain="localhost")
    resp = client.get(path)
    passed = (resp.status_code == 200)
    print(f"[{'PASS' if passed else 'FAIL'}] {resp.status_code} - {name} ({path})")
    if not passed:
        all_passed = False
        print("  Error:", resp.data[:200])

if all_passed:
    print("\n>>> ALL 14 ENTERPRISE PAGES & DASHBOARDS PASSED WITH HTTP 200! <<<")
else:
    print("\n>>> SOME ROUTES FAILED! <<<")

