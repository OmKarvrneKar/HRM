import pytest
from services.leave_service import LeaveService, PROGRESSIVE_LEAVE_POLICIES
from database.connection import get_db
from permissions.rbac import Role
from utils.timezone import now_utc


def test_progressive_leave_policies_structure():
    """Verify the progressive leave policies match the exact specified structure."""
    expected_codes = {"WFA", "MHL", "WND", "PCL", "NGL"}
    policies = LeaveService.get_progressive_policies()
    assert len(policies) == 5

    policy_map = {p["code"]: p for p in policies}
    assert set(policy_map.keys()) == expected_codes

    assert policy_map["WFA"]["name"] == "Work from Anywhere (WFA) & Flexible Leave"
    assert policy_map["WFA"]["default_days"] == 12
    assert policy_map["WFA"]["carry_forward"] is False

    assert policy_map["MHL"]["name"] == "Mental Health Leave"
    assert policy_map["MHL"]["default_days"] == 5
    assert policy_map["MHL"]["carry_forward"] is False

    assert policy_map["WND"]["name"] == "Wellness Days"
    assert policy_map["WND"]["default_days"] == 3
    assert policy_map["WND"]["carry_forward"] is False

    assert policy_map["PCL"]["name"] == "Pet Care Leave"
    assert policy_map["PCL"]["default_days"] == 3
    assert policy_map["PCL"]["carry_forward"] is False

    assert policy_map["NGL"]["name"] == "Neutral Gender Leave"
    assert policy_map["NGL"]["default_days"] == 10
    assert policy_map["NGL"]["carry_forward"] is True


def test_progressive_leave_type_normalization():
    """Verify codes and variations normalize to full canonical policy names."""
    assert LeaveService.normalize_leave_type("WFA") == "Work from Anywhere (WFA) & Flexible Leave"
    assert LeaveService.normalize_leave_type("wfa") == "Work from Anywhere (WFA) & Flexible Leave"
    assert LeaveService.normalize_leave_type("MHL") == "Mental Health Leave"
    assert LeaveService.normalize_leave_type("WND") == "Wellness Days"
    assert LeaveService.normalize_leave_type("PCL") == "Pet Care Leave"
    assert LeaveService.normalize_leave_type("NGL") == "Neutral Gender Leave"
    assert LeaveService.normalize_leave_type("Flexible Leave") == "Work from Anywhere (WFA) & Flexible Leave"


def test_leave_balance_initialization_with_progressive_policies(db):
    """Test that new leave balance documents contain all 5 progressive policies with default days."""
    test_emp_id = "EMP-TEST-PROG-01"
    fy = LeaveService.get_financial_year()

    bal = LeaveService.get_or_create_leave_balance(test_emp_id, fy)
    balances = bal.get("balances", {})

    assert "Work from Anywhere (WFA) & Flexible Leave" in balances
    assert balances["Work from Anywhere (WFA) & Flexible Leave"]["total"] == 12.0
    assert balances["Work from Anywhere (WFA) & Flexible Leave"]["available"] == 12.0

    assert "Mental Health Leave" in balances
    assert balances["Mental Health Leave"]["total"] == 5.0

    assert "Wellness Days" in balances
    assert balances["Wellness Days"]["total"] == 3.0

    assert "Pet Care Leave" in balances
    assert balances["Pet Care Leave"]["total"] == 3.0

    assert "Neutral Gender Leave" in balances
    assert balances["Neutral Gender Leave"]["total"] == 10.0


def test_backfill_progressive_policies_to_existing_balance(db):
    """Test that existing balance records missing progressive policies are automatically backfilled."""
    test_emp_id = "EMP-TEST-LEGACY-02"
    fy = LeaveService.get_financial_year()

    # Insert a legacy balance record with only standard policies
    legacy_balances = {
        "Casual Leave": {"total": 12.0, "used": 2.0, "available": 10.0},
        "Sick Leave": {"total": 10.0, "used": 0.0, "available": 10.0}
    }
    db.leave_balances.insert_one({
        "employee_id": test_emp_id,
        "financial_year": fy,
        "balances": legacy_balances,
        "created_at": now_utc(),
        "updated_at": now_utc()
    })

    # Calling get_or_create_leave_balance should backfill all 5 progressive policies
    updated_bal = LeaveService.get_or_create_leave_balance(test_emp_id, fy)
    b = updated_bal.get("balances", {})

    # Existing balances preserved
    assert b["Casual Leave"]["available"] == 10.0
    # Progressive policies backfilled
    assert b["Work from Anywhere (WFA) & Flexible Leave"]["total"] == 12.0
    assert b["Mental Health Leave"]["total"] == 5.0
    assert b["Wellness Days"]["total"] == 3.0
    assert b["Pet Care Leave"]["total"] == 3.0
    assert b["Neutral Gender Leave"]["total"] == 10.0

    # Ensure ledger credit transactions were generated
    credit_txns = list(db.leave_transactions.find({
        "employee_id": test_emp_id,
        "leave_type": "Work from Anywhere (WFA) & Flexible Leave"
    }))
    assert len(credit_txns) == 1
    assert credit_txns[0]["days"] == 12.0


def test_apply_and_approve_progressive_leave(db, seeded_users):
    """Test full application, approval, and balance deduction cycle for a progressive leave policy."""
    emp1 = seeded_users["emp1"]
    mgr = seeded_users["manager"]
    fy = LeaveService.get_financial_year()

    # Pre-initialize balance
    LeaveService.get_or_create_leave_balance(emp1["employee_id"], fy)

    # 1. Apply for Mental Health Leave (MHL)
    doc, err = LeaveService.apply_leave(emp1, {
        "leave_type": "MHL",
        "start_date": "2026-11-25",
        "end_date": "2026-11-26",  # 2 days
        "reason": "Mental health and decompression days."
    })
    assert err is None
    assert doc is not None
    assert doc["leave_type"] == "Mental Health Leave"
    assert doc["days_count"] == 2.0
    req_id = doc["request_id"]

    # 2. Sequential approval: if PENDING_TEAM_LEAD, TL reviews first
    if doc["status"] == "PENDING_TEAM_LEAD":
        tl_user = db.users.find_one({"employee_id": doc["assigned_tl_id"]})
        if not tl_user:
            tl_user = {
                "employee_id": doc["assigned_tl_id"],
                "full_name": "Test Assigned Team Lead",
                "role": Role.TEAM_LEAD,
                "is_active": True
            }
            db.users.insert_one(tl_user)
        tl_doc, tl_err = LeaveService.verify_request(tl_user, req_id, "Approved", "TL approved for team coverage.")
        assert tl_err is None
        assert tl_doc["status"] == "PENDING_MANAGER"

    # 3. Manager reviews and gives final approval
    app_doc, app_err = LeaveService.verify_request(mgr, req_id, "Approved", "Approved, take care.")
    assert app_err is None
    assert app_doc["status"] in ("Approved", "APPROVED")

    # 4. Check balance deducted from 5.0 to 3.0
    bal = LeaveService.get_or_create_leave_balance(emp1["employee_id"], fy)
    mhl_bal = bal["balances"]["Mental Health Leave"]
    assert mhl_bal["total"] == 5.0
    assert mhl_bal["used"] == 2.0
    assert mhl_bal["available"] == 3.0

    # 5. Check debit ledger transaction
    debit_txn = db.leave_transactions.find_one({
        "employee_id": emp1["employee_id"],
        "reference_request_id": req_id,
        "transaction_type": "DEBIT"
    })
    assert debit_txn is not None
    assert debit_txn["days"] == 2.0
    assert debit_txn["balance_after"] == 3.0


def test_api_leaves_policies_endpoint(client, seeded_users):
    """Test GET /api/leaves/policies returns complete policy metadata."""
    emp1 = seeded_users["emp1"]
    from auth.security import generate_jwt_token
    token = generate_jwt_token(emp1)

    res = client.get("/api/leaves/policies", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.get_json()

    assert "policies" in data
    assert "progressive_policies" in data
    assert len(data["progressive_policies"]) == 5

    codes = [p["code"] for p in data["progressive_policies"]]
    assert set(codes) == {"WFA", "MHL", "WND", "PCL", "NGL"}
