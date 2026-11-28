import hashlib
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

from auth.security import generate_jwt_token, hash_password
from permissions.rbac import (
    Role,
    can_access_employee_record,
    can_approve_leave,
    can_create_account,
    can_edit_profile,
    can_manage_roles,
    can_view_salary,
    normalize_role,
)
from services.audit_service import AuditService
from services.enterprise_hr_service import SecureDocumentViewerService
from services.export_service import ExportService
from services.leave_service import LeaveService
from services.roster_service import RosterService
from services.user_service import UserService
from config import Config, TestConfig


PROD_STORAGE_DIR = Path(__file__).resolve().parents[2] / "data" / "storage" / "office_hrm"


def _compute_prod_checksums() -> dict[str, str]:
    checksums = {}
    if PROD_STORAGE_DIR.exists():
        for f in sorted(PROD_STORAGE_DIR.glob("*.json")):
            checksums[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    return checksums


def _auth(user: dict) -> dict[str, str]:
    token = generate_jwt_token(user)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture
def task11_actors(app, db, monkeypatch):
    """Creates completely isolated synthetic test users & cleans all Task 11 test collections."""
    monkeypatch.setattr(Config, "EMAIL_ENABLED", False, raising=False)

    assert app.config.get("TESTING") is True
    assert db.name == TestConfig.DATABASE_NAME == "office_hrm_test"
    assert app.config.get("USE_FILE_PERSISTENCE") is False

    extra_cols = [
        "nominees",
        "leave_balances",
        "leave_transactions",
        "attendance_corrections",
        "salary_slips",
        "shift_profiles",
        "documents",
        "payroll_records",
    ]
    for col in extra_cols:
        db[col].delete_many({})

    now = datetime.now(timezone.utc)
    raw_users = {
        "emp_eng_1": {
            "employee_id": "T11-EMP-1",
            "emp_id": "T11-EMP-1",
            "full_name": "Task11 Engineer One",
            "email": "t11.emp1@test.local",
            "personal_email": "t11.emp1.personal@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.EMPLOYEE,
            "department": "Engineering",
            "designation": "Software Engineer",
            "team_id": "T11-TEAM-ENG",
            "assigned_tl_id": "T11-TL-1",
            "manager_id": "T11-MGR-ENG",
            "reporting_manager_id": "T11-MGR-ENG",
            "aadhaar_number": "123412349876",
            "pan_number": "ABCDE9999Z",
            "bank_account_number": "998877665544",
            "residential_address": "Secret Home Street 1",
            "activation_token": "SECRET-ACT-TOKEN-EMP1",
            "verification_status": "verified",
            "is_active": True,
            "is_email_verified": True,
            "status": "active",
            "created_at": now,
        },
        "emp_eng_2": {
            "employee_id": "T11-EMP-2",
            "emp_id": "T11-EMP-2",
            "full_name": "Task11 Engineer Two",
            "email": "t11.emp2@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.EMPLOYEE,
            "department": "Engineering",
            "designation": "QA Engineer",
            "team_id": "T11-TEAM-QA",
            "assigned_tl_id": "T11-TL-ALT",
            "manager_id": "T11-MGR-ENG",
            "reporting_manager_id": "T11-MGR-ENG",
            "verification_status": "verified",
            "is_active": True,
            "is_email_verified": True,
            "status": "active",
            "created_at": now,
        },
        "emp_sales": {
            "employee_id": "T11-EMP-3",
            "emp_id": "T11-EMP-3",
            "full_name": "Task11 Sales Executive",
            "email": "t11.sales1@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.EMPLOYEE,
            "department": "Sales",
            "designation": "Account Executive",
            "team_id": "T11-TEAM-SALES",
            "manager_id": "T11-MGR-SALES",
            "reporting_manager_id": "T11-MGR-SALES",
            "aadhaar_number": "555566667777",
            "pan_number": "XYZAB1234C",
            "verification_status": "verified",
            "is_active": True,
            "is_email_verified": True,
            "status": "active",
            "created_at": now,
        },
        "tl_eng": {
            "employee_id": "T11-TL-1",
            "emp_id": "T11-TL-1",
            "full_name": "Task11 Eng Lead",
            "email": "t11.tl1@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.TL,  # Intentional canonical "tl" string to verify normalization
            "department": "Engineering",
            "designation": "Team Lead",
            "team_id": "T11-TEAM-ENG",
            "manager_id": "T11-MGR-ENG",
            "reporting_manager_id": "T11-MGR-ENG",
            "verification_status": "verified",
            "is_active": True,
            "is_email_verified": True,
            "status": "active",
            "created_at": now,
        },
        "tl_alt": {
            "employee_id": "T11-TL-ALT",
            "emp_id": "T11-TL-ALT",
            "full_name": "Task11 QA Lead",
            "email": "t11.tlalt@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.TEAM_LEAD,
            "department": "Engineering",
            "designation": "QA Lead",
            "team_id": "T11-TEAM-QA",
            "verification_status": "verified",
            "is_active": True,
            "is_email_verified": True,
            "status": "active",
            "created_at": now,
        },
        "mgr_eng": {
            "employee_id": "T11-MGR-ENG",
            "emp_id": "T11-MGR-ENG",
            "full_name": "Task11 Engineering Manager",
            "email": "t11.mgreng@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.MANAGER,
            "department": "Engineering",
            "designation": "Engineering Manager",
            "verification_status": "verified",
            "is_active": True,
            "is_email_verified": True,
            "status": "active",
            "created_at": now,
        },
        "mgr_sales": {
            "employee_id": "T11-MGR-SALES",
            "emp_id": "T11-MGR-SALES",
            "full_name": "Task11 Sales Manager",
            "email": "t11.mgrsales@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.MANAGER,
            "department": "Sales",
            "designation": "Sales Manager",
            "verification_status": "verified",
            "is_active": True,
            "is_email_verified": True,
            "status": "active",
            "created_at": now,
        },
        "mgr_exec": {
            "employee_id": "T11-MGR-EXEC",
            "emp_id": "T11-MGR-EXEC",
            "full_name": "Task11 Management Dept Manager",
            "email": "t11.mgrexec@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.MANAGER,
            "department": "Management",
            "designation": "Operations Manager",
            "verification_status": "verified",
            "is_active": True,
            "is_email_verified": True,
            "status": "active",
            "created_at": now,
        },
        "hr": {
            "employee_id": "T11-HR-1",
            "emp_id": "T11-HR-1",
            "full_name": "Task11 HR Officer",
            "email": "t11.hr@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.HR,
            "department": "Human Resources",
            "designation": "HR Manager",
            "verification_status": "verified",
            "is_active": True,
            "is_email_verified": True,
            "status": "active",
            "created_at": now,
        },
        "admin": {
            "employee_id": "T11-ADMIN-1",
            "emp_id": "T11-ADMIN-1",
            "full_name": "Task11 System Admin",
            "email": "t11.admin@test.local",
            "password_hash": hash_password("TestPass@123"),
            "role": Role.ADMIN,
            "department": "Administration",
            "designation": "System Administrator",
            "verification_status": "verified",
            "is_active": True,
            "is_email_verified": True,
            "status": "active",
            "created_at": now,
        },
    }

    actors = {}
    for key, doc in raw_users.items():
        res = db.users.insert_one(doc)
        doc["_id"] = res.inserted_id
        actors[key] = doc

    db.teams.insert_one({
        "team_id": "T11-TEAM-ENG",
        "name": "Engineering Core",
        "lead_id": "T11-TL-1",
        "lead_employee_id": "T11-TL-1",
        "department": "Engineering",
    })
    db.teams.insert_one({
        "team_id": "T11-TEAM-QA",
        "name": "QA Automation",
        "lead_id": "T11-TL-ALT",
        "lead_employee_id": "T11-TL-ALT",
        "department": "Engineering",
    })

    # Seed finalized salary slips for isolated T11-EMP-1 and T11-EMP-3
    for eid in ("T11-EMP-1", "T11-EMP-3"):
        db.users.update_one(
            {"employee_id": eid},
            {"$set": {"salary_info": {"ctc_annual": 900000, "monthly_gross": 75000, "basic_salary": 37500, "net_salary": 68000}}},
        )
        db.salary_slips.insert_one({
            "slip_id": f"PAY-{eid}-2026-10",
            "employee_id": eid,
            "year_month": "2026-10",
            "month_name": "October 2026",
            "gross_earnings": 75000,
            "net_salary": 68000,
            "total_deductions": 7000,
            "net_salary_words": "Rupees Sixty Eight Thousand Only",
            "payment_status": "Paid",
            "earnings_breakdown": {"basic_salary": 37500},
            "deductions_breakdown": {"provident_fund": 3600},
        })

    return actors


def test_rbac_helper_consistency(task11_actors):
    """Verify service/RBAC helper alignment across roles and normalization."""
    emp1 = task11_actors["emp_eng_1"]
    emp2 = task11_actors["emp_eng_2"]
    tl = task11_actors["tl_eng"]
    mgr_eng = task11_actors["mgr_eng"]
    mgr_sales = task11_actors["mgr_sales"]
    hr = task11_actors["hr"]
    admin = task11_actors["admin"]

    assert normalize_role("tl") == Role.TL
    assert normalize_role("team_lead") == Role.TL
    assert normalize_role("organization") == Role.MANAGER
    assert normalize_role("hr_manager") == Role.HR

    # Salary visibility: self, HR, Admin only
    assert can_view_salary(emp1, emp1) is True
    assert can_view_salary(emp1, emp2) is False
    assert can_view_salary(tl, emp1) is False
    assert can_view_salary(mgr_eng, emp1) is False
    assert can_view_salary(hr, emp1) is True
    assert can_view_salary(admin, emp1) is True

    # Profile editing: self, HR, Admin only
    assert can_edit_profile(emp1, emp1) is True
    assert can_edit_profile(emp1, emp2) is False
    assert can_edit_profile(tl, emp1) is False
    assert can_edit_profile(mgr_eng, emp1) is False
    assert can_edit_profile(hr, emp1) is True
    assert can_edit_profile(admin, emp1) is True

    # Role management & account creation: HR & Admin only (Managers excluded; HR cannot create Admin)
    assert can_manage_roles(emp1) is False
    assert can_manage_roles(tl) is False
    assert can_manage_roles(mgr_eng) is False
    assert can_manage_roles(hr) is True
    assert can_manage_roles(admin) is True
    assert can_create_account(mgr_eng, Role.EMPLOYEE) is False
    assert can_create_account(hr, Role.EMPLOYEE) is True
    assert can_create_account(hr, Role.ADMIN) is False
    assert can_create_account(admin, Role.ADMIN) is True

    # Reporting scope isolation
    assert can_access_employee_record(mgr_eng, "T11-EMP-1") is True
    assert can_access_employee_record(mgr_sales, "T11-EMP-1") is False


def test_area1_personal_records_and_documents_rbac(client, db, task11_actors):
    """Area 1: Verify employee personal records, directories, nominees, history & documents RBAC."""
    emp1 = task11_actors["emp_eng_1"]
    emp2 = task11_actors["emp_eng_2"]
    emp_sales = task11_actors["emp_sales"]
    tl = task11_actors["tl_eng"]
    mgr_eng = task11_actors["mgr_eng"]
    mgr_sales = task11_actors["mgr_sales"]
    mgr_exec = task11_actors["mgr_exec"]
    hr = task11_actors["hr"]
    admin = task11_actors["admin"]

    # 1. Directory listing (/api/users & /api/profiles): blocked for Employee, scoped for TL & Manager
    for endpoint in ("/api/users", "/api/profiles"):
        assert client.get(endpoint, headers=_auth(emp1)).status_code == 403

        tl_res = client.get(endpoint, headers=_auth(tl))
        assert tl_res.status_code == 200
        tl_ids = {u["employee_id"] for u in tl_res.get_json()["users"]}
        assert tl_ids == {"T11-EMP-1"}

        mgr_res = client.get(f"{endpoint}?include_inactive=true", headers=_auth(mgr_eng))
        assert mgr_res.status_code == 200
        mgr_ids = {u["employee_id"] for u in mgr_res.get_json()["users"]}
        assert {"T11-EMP-1", "T11-EMP-2", "T11-TL-1"}.issubset(mgr_ids)
        assert "T11-EMP-3" not in mgr_ids
        assert "T11-HR-1" not in mgr_ids
        assert "T11-ADMIN-1" not in mgr_ids

        # Manager in Management dept with no direct reports cannot enumerate entire company
        exec_mgr_res = client.get(endpoint, headers=_auth(mgr_exec))
        assert exec_mgr_res.status_code == 200
        assert exec_mgr_res.get_json()["users"] == []

    # 2. Team directory endpoint (/api/users/team-directory)
    assert client.get("/api/users/team-directory", headers=_auth(emp1)).status_code == 403
    td_tl = client.get("/api/users/team-directory", headers=_auth(tl))
    assert td_tl.status_code == 200
    assert {e["employee_id"] for e in td_tl.get_json()["employees"]} == {"T11-EMP-1"}

    # 3. Single profile PII & IDOR enforcement (/api/users/<id>)
    assert client.get("/api/users/T11-EMP-2", headers=_auth(emp1)).status_code == 403
    assert client.get("/api/users/T11-EMP-2", headers=_auth(tl)).status_code == 403
    assert client.get("/api/users/T11-EMP-1", headers=_auth(mgr_sales)).status_code == 403
    assert client.get("/api/users/T11-MGR-ENG", headers=_auth(tl)).status_code == 403

    tl_view_emp1 = client.get("/api/users/T11-EMP-1", headers=_auth(tl))
    assert tl_view_emp1.status_code == 200
    emp1_for_tl = tl_view_emp1.get_json()["user"]
    for forbidden in ("aadhaar_number", "pan_number", "bank_account_number", "residential_address", "activation_token", "salary_info"):
        assert forbidden not in emp1_for_tl

    hr_view_emp1 = client.get("/api/users/T11-EMP-1", headers=_auth(hr))
    assert hr_view_emp1.status_code == 200
    assert "activation_token" not in hr_view_emp1.get_json()["user"]

    # 4. Profile modification & Tiimi profile & Change History
    assert client.put("/api/users/T11-EMP-2", headers=_auth(emp1), json={"updates": {"phone_number": "111"}}).status_code == 403
    assert client.put("/api/users/T11-EMP-1", headers=_auth(tl), json={"updates": {"department": "Hack"}}).status_code == 403
    assert client.put("/api/users/T11-EMP-1", headers=_auth(mgr_eng), json={"updates": {"department": "Hack"}}).status_code == 403
    assert client.post("/api/users/T11-EMP-1/update-tiimi-profile", headers=_auth(mgr_eng), json={"notes": "Mgr edit"}).status_code == 403

    # History contains sensitive change diffs: self, HR, Admin only
    assert client.get("/api/users/T11-EMP-1/history", headers=_auth(emp1)).status_code == 200
    assert client.get("/api/users/T11-EMP-1/history", headers=_auth(emp2)).status_code == 403
    assert client.get("/api/users/T11-EMP-1/history", headers=_auth(tl)).status_code == 403
    assert client.get("/api/users/T11-EMP-1/history", headers=_auth(mgr_eng)).status_code == 403
    assert client.get("/api/users/T11-EMP-1/history", headers=_auth(hr)).status_code == 200
    assert client.get("/api/users/T11-EMP-1/history", headers=_auth(admin)).status_code == 200

    # 5. Confidential Nominees: Self, HR, Admin ONLY (Managers & colleagues -> 403)
    save_own = client.post("/api/nominees", headers=_auth(emp1), json={"nominees": [{"name": "Asha", "relationship": "Mother", "share_percentage": 100}]})
    assert save_own.status_code == 200
    assert client.get("/api/nominees?employee_id=T11-EMP-1", headers=_auth(emp1)).status_code == 200
    assert client.get("/api/nominees?employee_id=T11-EMP-1", headers=_auth(emp2)).status_code == 403
    assert client.get("/api/nominees?employee_id=T11-EMP-1", headers=_auth(tl)).status_code == 403
    assert client.get("/api/nominees?employee_id=T11-EMP-1", headers=_auth(mgr_eng)).status_code == 403
    assert client.post("/api/nominees", headers=_auth(mgr_eng), json={"employee_id": "T11-EMP-1", "nominees": [{"name": "X", "relationship": "Sibling", "share_percentage": 100}]}).status_code == 403
    assert client.get("/api/nominees?employee_id=T11-EMP-1", headers=_auth(hr)).status_code == 200
    assert client.get("/api/nominees?employee_id=T11-EMP-1", headers=_auth(admin)).status_code == 200

    # 6. Global Search (/api/search/global) & Pagination Meta
    emp_search = client.get("/api/search/global?q=Task11", headers=_auth(emp1))
    assert emp_search.status_code == 200
    emp_search_ids = {s["employee_id"] for s in emp_search.get_json()["results"]["staff"]}
    assert emp_search_ids == {"T11-EMP-1"}

    tl_search = client.get("/api/search/global?q=Task11", headers=_auth(tl))
    assert {s["employee_id"] for s in tl_search.get_json()["results"]["staff"]} == {"T11-EMP-1", "T11-TL-1"}

    db.projects.insert_one({"project_id": "T11-PRJ-1", "name": "Task11 Secret Project", "status": "Active"})
    hr_search = client.get("/api/search/global?q=Task11", headers=_auth(hr))
    assert hr_search.get_json()["results"]["projects"] == []

    pag_emp = client.get("/api/users/pagination-meta?employee_id=T11-EMP-2", headers=_auth(emp1)).get_json()
    assert pag_emp["can_paginate"] is False
    assert pag_emp["current_id"] == "T11-EMP-1"

    # 7. Company Documents Upload/Delete & Secure PII Dockets (/api/documents/secure-records/*)
    file_payload = {"file": (BytesIO(b"Policy Doc Content"), "policy.txt"), "title": "Security Policy"}
    assert client.post("/api/documents/upload", headers={"Authorization": f"Bearer {generate_jwt_token(emp1)}"}, data=file_payload).status_code == 403
    assert client.post("/api/documents/upload", headers={"Authorization": f"Bearer {generate_jwt_token(mgr_eng)}"}, data={"file": (BytesIO(b"x"), "p.txt")}).status_code == 403

    hr_up = client.post("/api/documents/upload", headers={"Authorization": f"Bearer {generate_jwt_token(hr)}"}, data={"file": (BytesIO(b"HR Policy"), "hr_policy.txt"), "title": "HR Policy"})
    assert hr_up.status_code == 201
    doc_id = hr_up.get_json()["document"]["document_id"]
    assert client.delete(f"/api/documents/{doc_id}", headers=_auth(mgr_eng)).status_code == 403
    assert client.delete(f"/api/documents/{doc_id}", headers=_auth(admin)).status_code == 200

    for unauthorized in (emp1, emp2, tl, mgr_eng, mgr_sales):
        assert client.get("/api/documents/secure-records/T11-EMP-1", headers=_auth(unauthorized)).status_code == 403
        assert client.get("/api/documents/secure-records/T11-EMP-1/preview", headers=_auth(unauthorized)).status_code == 403

    assert "error" in SecureDocumentViewerService.get_employee_secure_docket("T11-EMP-1", actor=mgr_eng)
    assert client.get("/api/documents/secure-records/T11-EMP-1", headers=_auth(hr)).status_code == 200
    assert client.get("/api/documents/secure-records/T11-EMP-1/preview?doc=PAN", headers=_auth(admin)).status_code == 200


def test_area2_salary_payroll_and_payslips_rbac(client, task11_actors):
    """Area 2: Verify salary, payroll overview/batch-email, and payslip PDF/JSON endpoints."""
    emp1 = task11_actors["emp_eng_1"]
    emp_sales = task11_actors["emp_sales"]
    tl = task11_actors["tl_eng"]
    mgr_eng = task11_actors["mgr_eng"]
    hr = task11_actors["hr"]
    admin = task11_actors["admin"]

    # Self allowed
    assert client.get("/api/users/T11-EMP-1/salary", headers=_auth(emp1)).status_code == 200
    assert client.get("/api/salary/slips/T11-EMP-1", headers=_auth(emp1)).status_code == 200
    assert client.get("/api/salary/slips/T11-EMP-1/2026-10", headers=_auth(emp1)).status_code == 200
    assert client.get("/api/salary/slips/T11-EMP-1/2026-10/pdf", headers=_auth(emp1)).status_code == 200
    assert client.post("/api/users/T11-EMP-1/salary/generate-slip", headers=_auth(emp1), json={}).status_code == 200

    # Other employees, TL, and Manager strictly denied (403)
    for blocked in (emp_sales, tl, mgr_eng):
        assert client.get("/api/users/T11-EMP-1/salary", headers=_auth(blocked)).status_code == 403
        assert client.post("/api/users/T11-EMP-1/salary/generate-slip", headers=_auth(blocked), json={}).status_code == 403
        assert client.get("/api/salary/slips/T11-EMP-1", headers=_auth(blocked)).status_code == 403
        assert client.get("/api/salary/slips/T11-EMP-1/2026-10", headers=_auth(blocked)).status_code == 403
        assert client.get("/api/salary/slips/T11-EMP-1/2026-10/pdf", headers=_auth(blocked)).status_code == 403
        assert client.put("/api/users/T11-EMP-1/salary", headers=_auth(blocked), json={"ctc_annual": 1200000}).status_code == 403

    # HR & Admin permitted to view slips & revise salary (HR cannot revise Admin salary)
    assert client.get("/api/users/T11-EMP-1/salary", headers=_auth(admin)).status_code == 200
    assert client.get("/api/salary/slips/T11-EMP-1/2026-10/pdf", headers=_auth(hr)).status_code == 200
    assert client.put("/api/users/T11-EMP-1/salary", headers=_auth(hr), json={"ctc_annual": 1100000}).status_code == 200
    assert client.put("/api/users/T11-ADMIN-1/salary", headers=_auth(hr), json={"ctc_annual": 2600000}).status_code == 403
    assert client.put("/api/users/T11-ADMIN-1/salary", headers=_auth(admin), json={"ctc_annual": 2600000}).status_code == 200

    # Payroll overview & batch-email: HR & Admin ONLY (Manager blocked!)
    for blocked in (emp1, tl, mgr_eng):
        assert client.get("/api/payroll/overview", headers=_auth(blocked)).status_code == 403
        assert client.post("/api/payroll/batch-email", headers=_auth(blocked), json={"cycle": "2026-10"}).status_code == 403

    assert client.get("/api/payroll/overview", headers=_auth(hr)).status_code == 200
    assert client.post("/api/payroll/batch-email", headers=_auth(admin), json={"cycle": "2026-10"}).status_code == 200


def test_area3_attendance_correction_and_leave_approval_rbac(client, db, task11_actors):
    """Area 3: Verify attendance corrections, HR attendance monitors/exports & two-tier leave approvals + ledgers."""
    emp1 = task11_actors["emp_eng_1"]
    emp2 = task11_actors["emp_eng_2"]
    emp_sales = task11_actors["emp_sales"]
    tl = task11_actors["tl_eng"]
    tl_alt = task11_actors["tl_alt"]
    mgr_eng = task11_actors["mgr_eng"]
    mgr_sales = task11_actors["mgr_sales"]
    hr = task11_actors["hr"]
    admin = task11_actors["admin"]

    # Seed daily attendance for T11-EMP-1 and T11-EMP-3
    db.attendance_daily.insert_many([
        {"employee_id": "T11-EMP-1", "employee_name": "Task11 Engineer One", "department": "Engineering", "attendance_date": "2026-11-10", "status": "Late"},
        {"employee_id": "T11-EMP-3", "employee_name": "Task11 Sales Executive", "department": "Sales", "attendance_date": "2026-11-10", "status": "Late"},
    ])

    # 1. Direct manual attendance correction & HR monitors/exports
    for blocked in (emp1, tl, mgr_eng):
        assert client.post("/api/attendance/correct", headers=_auth(blocked), json={"employee_id": "T11-EMP-1", "date": "2026-11-10", "status": "Present", "reason": "Bypass"}).status_code == 403
        assert client.get("/api/attendance/hr-manager-monitor", headers=_auth(blocked)).status_code == 403
        assert client.get("/api/attendance/corrections/hr-intimations", headers=_auth(blocked)).status_code == 403

    assert client.post("/api/attendance/correct", headers=_auth(hr), json={"employee_id": "T11-EMP-1", "date": "2026-11-10", "status": "Present", "reason": "HR verified"}).status_code == 200
    assert client.get("/api/attendance/hr-manager-monitor", headers=_auth(admin)).status_code == 200

    # Attendance CSV report must not leak Engineering rows to Sales Manager
    csv_sales = client.get("/api/reports/attendance/csv?date=2026-11-10", headers=_auth(mgr_sales))
    assert csv_sales.status_code == 200
    assert b"T11-EMP-1" not in csv_sales.data

    # 2. Employee submits major attendance correction -> PENDING_TEAM_LEAD -> PENDING_MANAGER -> APPROVED
    req_res = client.post("/api/attendance/corrections/request", headers=_auth(emp1), json={
        "target_date": "2026-11-10",
        "correction_type": "MISSED_PUNCH_OUT",
        "requested_in_time": "09:30",
        "requested_out_time": "16:30",
        "reason": "Client call missed punch",
    })
    assert req_res.status_code == 200
    corr_id = req_res.get_json()["correction"]["request_id"]

    # Force a PENDING_TEAM_LEAD major shortage check via direct submission & also a T11-EMP-2 correction
    req2_res = client.post("/api/attendance/corrections/request", headers=_auth(emp2), json={
        "target_date": "2026-11-11",
        "correction_type": "MISSED_PUNCH_IN",
        "reason": "Bio failure",
    })
    corr2_id = req2_res.get_json()["correction"]["request_id"]

    # Employee cannot query pending queue; TL only sees assigned squad (T11-EMP-1, NOT T11-EMP-2)
    assert client.get("/api/attendance/corrections/pending", headers=_auth(emp1)).status_code == 403
    tl_pending = client.get("/api/attendance/corrections/pending", headers=_auth(tl))
    assert tl_pending.status_code == 200
    tl_corr_ids = {c["request_id"] for c in tl_pending.get_json()["pending_corrections"]}
    assert corr_id in tl_corr_ids
    assert corr2_id not in tl_corr_ids

    # Review authorization checks
    assert client.post(f"/api/attendance/corrections/{corr_id}/review", headers=_auth(emp1), json={"decision": "APPROVED"}).status_code == 403
    assert client.post(f"/api/attendance/corrections/{corr2_id}/review", headers=_auth(tl), json={"decision": "APPROVED"}).status_code == 403
    assert client.post(f"/api/attendance/corrections/{corr_id}/review", headers=_auth(mgr_sales), json={"decision": "APPROVED"}).status_code == 403

    # Also test TL self-review blocked & delete other employee's request blocked
    assert client.delete(f"/api/attendance/corrections/{corr_id}", headers=_auth(emp_sales)).status_code == 403
    assert client.delete(f"/api/attendance/corrections/{corr_id}", headers=_auth(mgr_eng)).status_code == 403

    # TL endorses corr_id -> PENDING_MANAGER, then cross-dept mgr_sales blocked, in-scope mgr_eng succeeds
    db.attendance_corrections.update_one({"request_id": corr_id}, {"$set": {"status": "PENDING_MANAGER"}})
    sales_pend = client.get("/api/attendance/corrections/pending", headers=_auth(mgr_sales))
    assert all(c["request_id"] != corr_id for c in sales_pend.get_json()["pending_corrections"])
    eng_pend = client.get("/api/attendance/corrections/pending", headers=_auth(mgr_eng))
    assert any(c["request_id"] == corr_id for c in eng_pend.get_json()["pending_corrections"])

    assert client.post(f"/api/attendance/corrections/{corr_id}/review", headers=_auth(mgr_sales), json={"decision": "APPROVED"}).status_code == 403
    assert client.post(f"/api/attendance/corrections/{corr_id}/review", headers=_auth(mgr_eng), json={"decision": "APPROVED", "remarks": "In-scope verified"}).status_code == 200

    # 3. Leave Approval Workflow + Leave Ledger
    leave_res = client.post("/api/leaves/apply", headers=_auth(emp1), json={
        "leave_type": "Casual Leave",
        "start_date": "2026-12-10",
        "end_date": "2026-12-11",
        "reason": "Family event",
    })
    assert leave_res.status_code == 201
    lr_id = leave_res.get_json()["request"]["request_id"]

    # Self, Employee, HR, and wrong-team TL strictly get 403 on leave approval
    assert client.post(f"/api/leaves/verify/{lr_id}", headers=_auth(emp1), json={"decision": "Approved"}).status_code == 403
    assert client.post(f"/api/leaves/verify/{lr_id}", headers=_auth(hr), json={"decision": "Approved"}).status_code == 403
    assert client.post(f"/api/leaves/verify/{lr_id}", headers=_auth(tl_alt), json={"decision": "Approved"}).status_code == 403
    assert can_approve_leave(hr, {"request_id": lr_id, "employee_id": "T11-EMP-1"}) is False

    # Assigned TL approves Stage 1 -> PENDING_MANAGER
    assert client.post(f"/api/leaves/verify/{lr_id}", headers=_auth(tl), json={"decision": "Approved", "remarks": "TL ok"}).status_code == 200

    # Sales Manager blocked (403); Engineering Manager approves Stage 2 -> Approved
    assert client.post(f"/api/leaves/verify/{lr_id}", headers=_auth(mgr_sales), json={"decision": "Approved", "remarks": "Cross-dept"}).status_code == 403
    assert client.post(f"/api/leaves/verify/{lr_id}", headers=_auth(mgr_eng), json={"decision": "Approved", "remarks": "Mgr ok"}).status_code == 200

    # Manual send-email for approved leave: HR/Employee/TL/cross-dept Manager blocked; Eng Manager permitted
    assert client.post(f"/api/leaves/{lr_id}/send-email", headers=_auth(emp1), json={"to": "hr@test.local"}).status_code == 403
    assert client.post(f"/api/leaves/{lr_id}/send-email", headers=_auth(hr), json={"to": "hr@test.local"}).status_code == 403
    assert client.post(f"/api/leaves/{lr_id}/send-email", headers=_auth(mgr_sales), json={"to": "hr@test.local"}).status_code == 403
    with patch("services.external_notification_service.ExternalNotificationService.send_email", return_value={"status": "DELIVERED"}):
        assert client.post(f"/api/leaves/{lr_id}/send-email", headers=_auth(mgr_eng), json={"to": "hr@test.local"}).status_code == 200

    # Correspondence & Admin Leave Delete: HR & Admin only
    assert client.get("/api/leaves/correspondence", headers=_auth(mgr_eng)).status_code == 403
    assert client.get("/api/leaves/correspondence", headers=_auth(hr)).status_code == 200
    assert client.delete(f"/api/leaves/{lr_id}", headers=_auth(mgr_eng)).status_code == 403
    assert client.delete(f"/api/leaves/my-requests/{lr_id}", headers=_auth(emp_sales)).status_code == 403

    # Leave Ledger (/api/leaves/ledger/<id>): scoped
    assert client.get("/api/leaves/ledger/T11-EMP-1", headers=_auth(emp1)).status_code == 200
    assert client.get("/api/leaves/ledger/T11-EMP-1", headers=_auth(emp2)).status_code == 403
    assert client.get("/api/leaves/ledger/T11-EMP-1", headers=_auth(tl_alt)).status_code == 403
    assert client.get("/api/leaves/ledger/T11-EMP-1", headers=_auth(mgr_sales)).status_code == 403
    assert client.get("/api/leaves/ledger/T11-EMP-1", headers=_auth(tl)).status_code == 200
    assert client.get("/api/leaves/ledger/T11-EMP-1", headers=_auth(mgr_eng)).status_code == 200
    assert client.get("/api/leaves/ledger/T11-EMP-1", headers=_auth(hr)).status_code == 200


def test_area4_user_admin_settings_exports_shifts_rbac(client, db, task11_actors):
    """Area 4: Verify user provisioning, activation/offboarding, settings, admin ZIP export, and shift rosters."""
    emp1 = task11_actors["emp_eng_1"]
    tl = task11_actors["tl_eng"]
    mgr_eng = task11_actors["mgr_eng"]
    mgr_sales = task11_actors["mgr_sales"]
    hr = task11_actors["hr"]
    admin = task11_actors["admin"]

    # 1. Create User: Employee, TL, Manager strictly forbidden at API & Service layers
    new_emp_payload = {
        "full_name": "Created User",
        "email": "created.user@test.local",
        "role": Role.EMPLOYEE,
        "department": "Engineering",
        "password": "Strong@Password1",
    }
    for blocked in (emp1, tl, mgr_eng):
        assert client.post("/api/users", headers=_auth(blocked), json=new_emp_payload).status_code == 403
        u, err = UserService.create_user(blocked, new_emp_payload)
        assert u is None and "not authorized" in err.lower()

    # HR cannot provision Admin accounts; Admin can
    assert client.post("/api/users", headers=_auth(hr), json={**new_emp_payload, "email": "newadmin@test.local", "role": Role.ADMIN}).status_code == 403
    assert client.post("/api/users", headers=_auth(hr), json=new_emp_payload).status_code == 201
    assert client.post("/api/users", headers=_auth(admin), json={**new_emp_payload, "email": "newadmin2@test.local", "role": Role.ADMIN}).status_code == 201

    # 2. Toggle Status, Offboarding, Reactivation, Offboardings list
    for blocked in (emp1, tl, mgr_eng):
        assert client.post("/api/users/T11-EMP-1/toggle-status", headers=_auth(blocked), json={"is_active": False}).status_code == 403
        assert client.post("/api/users/T11-EMP-1/offboard", headers=_auth(blocked), json={"reason": "Test"}).status_code == 403
        assert client.post("/api/users/T11-EMP-1/reactivate", headers=_auth(blocked), json={"reason": "Test"}).status_code == 403
        assert client.get("/api/offboardings", headers=_auth(blocked)).status_code == 403
        assert UserService.get_offboardings(blocked) == []

    # HR cannot toggle/offboard Admin; Admin can manage HR & Employee
    assert client.post("/api/users/T11-ADMIN-1/toggle-status", headers=_auth(hr), json={"is_active": False}).status_code == 403
    assert client.post("/api/users/T11-ADMIN-1/offboard", headers=_auth(hr), json={"reason": "Attempt"}).status_code == 403
    assert client.post("/api/users/T11-EMP-2/offboard", headers=_auth(hr), json={"reason": "Resigned"}).status_code == 200
    assert client.post("/api/users/T11-EMP-2/reactivate", headers=_auth(hr), json={"reason": "Rehired"}).status_code == 200
    assert client.get("/api/offboardings", headers=_auth(admin)).status_code == 200

    # 3. Organization Settings & Admin Export ZIP
    for blocked in (emp1, tl, mgr_eng):
        assert client.get("/api/settings", headers=_auth(blocked)).status_code == 403
        assert client.put("/api/settings", headers=_auth(blocked), json={"key": "p", "value": {}}).status_code == 403
        assert client.get("/api/export/zip", headers=_auth(blocked)).status_code == 403
        with pytest.raises(PermissionError):
            ExportService.export_administrative_zip(blocked)

    assert client.get("/api/settings", headers=_auth(hr)).status_code == 200
    assert client.put("/api/settings", headers=_auth(hr), json={"key": "attendance_policy", "value": {"grace": 10}}).status_code == 403
    assert client.put("/api/settings", headers=_auth(admin), json={"key": "attendance_policy", "value": {"grace": 10}}).status_code == 200
    assert client.get("/api/export/zip", headers=_auth(admin)).status_code == 200

    # 4. Shift profiles & shift assignment RBAC
    emp_shifts = client.get("/api/shifts", headers=_auth(emp1))
    assert emp_shifts.status_code == 200
    for s in emp_shifts.get_json()["shifts"]:
        assert s.get("assigned_employees") == []

    for blocked in (emp1, tl, mgr_eng):
        assert client.post("/api/shifts", headers=_auth(blocked), json={"name": "Night Test", "start_time": "22:00", "end_time": "06:00"}).status_code == 403

    created_shift = client.post("/api/shifts", headers=_auth(hr), json={"name": "Split Test", "code": "SPLT", "start_time": "10:00", "end_time": "19:00"})
    assert created_shift.status_code == 200
    sid = created_shift.get_json()["shift"]["shift_id"]

    # Sales Manager cannot assign shifts to Engineering employees or department
    assert client.post("/api/shifts/assign", headers=_auth(emp1), json={"shift_id": sid, "employee_ids": ["T11-EMP-1"]}).status_code == 403
    assert client.post("/api/shifts/assign", headers=_auth(tl), json={"shift_id": sid, "employee_ids": ["T11-EMP-1"]}).status_code == 403
    assert client.post("/api/shifts/assign", headers=_auth(mgr_sales), json={"shift_id": sid, "employee_ids": ["T11-EMP-1"]}).status_code == 403
    assert client.post("/api/shifts/assign", headers=_auth(mgr_sales), json={"shift_id": sid, "department": "Engineering"}).status_code == 403
    assert client.post("/api/shifts/assign", headers=_auth(mgr_eng), json={"shift_id": sid, "employee_ids": ["T11-EMP-1"]}).status_code == 200
    assert client.delete(f"/api/shifts/{sid}", headers=_auth(mgr_eng)).status_code == 403
    assert client.delete(f"/api/shifts/{sid}", headers=_auth(admin)).status_code == 200

    # Ensure RosterService service-level call enforces role
    saved, serr = RosterService.save_shift_profile(mgr_eng, {"name": "M", "start_time": "09:00", "end_time": "18:00"})
    assert saved is None and "Unauthorized" in serr


def test_area5_audit_logs_and_external_logs_rbac_and_prod_immutability(client, task11_actors):
    """Area 5: Verify Audit Logs & External Delivery Logs RBAC + filter-bypass block + prod checksum immutability."""
    pre_checksums = _compute_prod_checksums()

    emp1 = task11_actors["emp_eng_1"]
    tl = task11_actors["tl_eng"]
    mgr_eng = task11_actors["mgr_eng"]
    hr = task11_actors["hr"]
    admin = task11_actors["admin"]

    AuditService.log_action(admin, "UPDATE_SYSTEM_CONFIG", "system", "SYS-1", {"k": "v"})
    AuditService.log_action(hr, "OFFBOARD_EMPLOYEE", "offboarding", "T11-EMP-2", {"r": "exit"})

    # Employee, TL, Manager strictly receive 403 on audit-logs & external delivery logs
    for endpoint in ("/api/audit-logs", "/api/audit/logs", "/api/notifications/external-logs"):
        for blocked in (emp1, tl, mgr_eng):
            assert client.get(endpoint, headers=_auth(blocked)).status_code == 403

    assert AuditService.get_audit_logs("manager") == []
    assert AuditService.get_audit_logs("tl") == []
    assert AuditService.get_audit_logs("employee") == []

    # HR sees operational target_types ONLY and CANNOT bypass restriction via ?target_type=system
    hr_logs_res = client.get("/api/audit-logs", headers=_auth(hr))
    assert hr_logs_res.status_code == 200
    hr_target_types = {l["target_type"] for l in hr_logs_res.get_json()["audit_logs"]}
    assert "offboarding" in hr_target_types
    assert "system" not in hr_target_types

    hr_bypass = client.get("/api/audit-logs?target_type=system", headers=_auth(hr))
    assert hr_bypass.status_code == 200
    assert hr_bypass.get_json()["audit_logs"] == []

    # Admin sees all target types including system
    admin_logs_res = client.get("/api/audit-logs", headers=_auth(admin))
    assert admin_logs_res.status_code == 200
    admin_target_types = {l["target_type"] for l in admin_logs_res.get_json()["audit_logs"]}
    assert {"system", "offboarding"}.issubset(admin_target_types)

    assert client.get("/api/notifications/external-logs", headers=_auth(hr)).status_code == 200
    assert client.get("/api/notifications/external-logs", headers=_auth(admin)).status_code == 200

    # Verify ZERO writes to production JSON storage
    post_checksums = _compute_prod_checksums()
    assert pre_checksums == post_checksums

