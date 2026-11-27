import openpyxl
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.database.connection import DatabaseManager

db = DatabaseManager.get_db()
users = list(db.users.find())

wb = openpyxl.load_workbook('data/Intern-Full-Details(1).xlsx')
ws = wb.active
excel_data = []
for r in range(3, ws.max_row + 1):
    sno = ws.cell(r, 1).value
    name = ws.cell(r, 2).value
    contact = ws.cell(r, 3).value
    email = ws.cell(r, 4).value
    dob = ws.cell(r, 5).value
    if any([sno, name, contact, email, dob]):
        excel_data.append((sno, str(name).strip() if name else '', str(email).strip().lower() if email else '', str(contact).strip() if contact else ''))

excel_emails = {x[2] for x in excel_data if x[2]}
excel_names = {x[1].lower() for x in excel_data if x[1]}

print("==========================================================================================")
print(f"DATABASE INSPECTION: Total Users = {len(users)}, Excel Rows = {len(excel_data)}")
print("==========================================================================================")

all_fields = set()
roles_found = set()
dummy_accounts = []
real_accounts = []

for u in users:
    for k in u.keys():
        all_fields.add(k)
    role = u.get('role', '')
    roles_found.add(role)
    email = (u.get('email') or '').strip().lower()
    name = (u.get('full_name') or '').strip().lower()
    in_excel = email in excel_emails or name in excel_names
    source = "REAL_EXCEL_EMPLOYEE" if in_excel else "SYSTEM_OR_DUMMY"

    # Check if dummy
    is_dummy = not in_excel and (
        email.endswith("@aisamrat.com") or 
        u.get('is_dummy') or 
        "demo" in email or 
        "test" in email or
        u.get('employee_id', '').startswith(('ADM-', 'ORG-', 'MGR-', 'HR-', 'EMP-1001', 'EMP-1002', 'EMP-1003', 'EMP-1004', 'LEAD-', 'TRN-'))
    )

    info = {
        "emp_id": u.get('employee_id', ''),
        "role": role,
        "email": u.get('email', ''),
        "full_name": u.get('full_name', ''),
        "department": u.get('department', ''),
        "designation": u.get('designation', ''),
        "in_excel": in_excel,
        "is_active": u.get('is_active', True)
    }

    if is_dummy:
        dummy_accounts.append(info)
    else:
        real_accounts.append(info)

print(f"\n--- IDENTIFIED DUMMY / SYSTEM SEED ACCOUNTS ({len(dummy_accounts)}) ---")
for d in dummy_accounts:
    print(f"  {d['emp_id']:12} | {d['role']:12} | {d['email']:30} | {d['full_name']}")

print(f"\n--- IDENTIFIED REAL EMPLOYEES ({len(real_accounts)}) ---")
for r in real_accounts:
    print(f"  {r['emp_id']:12} | {r['role']:12} | {r['email']:30} | {r['full_name']}")

print("\n--- ALL UNIQUE EMPLOYEE DATABASE FIELDS DETECTED ---")
for f in sorted(all_fields):
    print(f"  - {f}")

print("\n--- ALL ROLES PRESENT IN USERS COLLECTION ---")
print(sorted(roles_found))
