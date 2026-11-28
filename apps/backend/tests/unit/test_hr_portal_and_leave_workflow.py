import pytest
from services.leave_service import LeaveService
from permissions.rbac import Role, can_approve_leave
from database.connection import DatabaseManager


def test_ramya_sole_active_hr_and_dummy_accounts_deactivated():
    """
    Part 1 & 8: Verify Ramya is the only active HR account, demo accounts are soft-deactivated,
    and real company employees are strictly preserved in the actual company database.
    """
    prod_db = DatabaseManager.get_db("office_hrm")

    # 1. Active HR account verification
    active_hrs = list(prod_db.users.find({"role": Role.HR, "is_active": True, "status": {"$ne": "deactivated"}}))
    assert len(active_hrs) == 1, "There must be exactly one active HR account"
    ramya = active_hrs[0]
    assert ramya["full_name"] == "Ramya"
    assert ramya["email"] in ("hr.ramya@aisamrat.com", "ramya@aisamrat.com")
    assert ramya["employee_id"] == "HR-1001"

    # 2. Confirmed dummy accounts are soft-deactivated or excluded
    for dummy_id in ["HR-1000", "HR-1002", "EMP-1001", "EMP-1002", "EMP-1003", "EMP-1004"]:
        account = prod_db.users.find_one({"employee_id": dummy_id})
        if account:
            assert account.get("is_active") is False or account.get("status") == "deactivated"

    # 3. Real company employees (EMP-1005 to EMP-1037) are preserved
    for emp_id in ["EMP-1005", "EMP-1010", "EMP-1020", "EMP-1030", "EMP-1037"]:
        emp = prod_db.users.find_one({"employee_id": emp_id})
        assert emp is not None, f"Real employee {emp_id} must be preserved"
        assert emp.get("full_name") is not None

    # 4. Strictly 4 business roles (Employee, Team Lead, Manager, HR)
    distinct_roles = set(prod_db.users.distinct("role"))
    allowed_roles = {Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.HR}
    assert distinct_roles.issubset(allowed_roles), f"Found unauthorized business roles: {distinct_roles - allowed_roles}"


def test_same_leave_request_interface_for_employees_and_team_leads(db, seeded_users):
    """
    Part 3 & 6: Employees and Team Leads can apply for leave and permission,
    track status, view manager remarks, and cancel eligible pending requests.
    """
    emp = seeded_users["emp1"]
    tl = seeded_users["team_lead"]

    # 1. Employee applies for leave
    e_leave, e_err = LeaveService.apply_leave(emp, {
        "leave_type": "Casual Leave",
        "start_date": "2026-11-20",
        "end_date": "2026-11-21",
        "reason": "Personal errands"
    })
    assert e_err is None
    assert e_leave["status"] in ("Pending", "PENDING_MANAGER", "PENDING_TEAM_LEAD")
    assert e_leave["employee_id"] == emp["employee_id"]

    # 2. Team Lead applies for leave (same interface & capability)
    tl_leave, tl_err = LeaveService.apply_leave(tl, {
        "leave_type": "Sick Leave",
        "start_date": "2026-11-22",
        "end_date": "2026-11-22",
        "reason": "Viral fever recovery"
    })
    assert tl_err is None
    assert tl_leave["status"] in ("Pending", "PENDING_MANAGER")
    assert tl_leave["employee_id"] == tl["employee_id"]

    # 3. Employee and Team Lead apply for permission
    e_perm, ep_err = LeaveService.apply_permission(emp, {
        "permission_date": "2026-11-25",
        "early_exit_time": "16:00",
        "reason": "Dentist consultation"
    })
    assert ep_err is None
    assert e_perm["status"] in ("Pending", "PENDING_MANAGER", "PENDING_TEAM_LEAD")

    tl_perm, tp_err = LeaveService.apply_permission(tl, {
        "permission_date": "2026-11-26",
        "early_exit_time": "15:30",
        "reason": "Bank appointment"
    })
    assert tp_err is None
    assert tl_perm["status"] in ("Pending", "PENDING_MANAGER")

    # 4. View own requests
    e_reqs = LeaveService.get_employee_requests(emp["employee_id"])
    assert e_reqs["summary"]["pending_count"] == 2

    tl_reqs = LeaveService.get_employee_requests(tl["employee_id"])
    assert tl_reqs["summary"]["pending_count"] == 2

    # 5. Cancel pending requests
    ok, err_c = LeaveService.cancel_request(emp, e_perm["request_id"])
    assert ok is True
    assert err_c is None

    # Check status is Cancelled
    cancelled_doc = db.leave_requests.find_one({"request_id": e_perm["request_id"]})
    assert cancelled_doc["status"] == "Cancelled"
    assert cancelled_doc.get("cancelled_at") is not None


def test_team_lead_and_employee_cannot_approve_requests(db, seeded_users):
    """
    Part 3 & 6: Unauthorized employees or TL outside their team cannot approve requests.
    """
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]
    tl = seeded_users["team_lead"]

    # emp2 is in Department 'Design', tl is in 'Engineering'
    leave, _ = LeaveService.apply_leave(emp2, {
        "start_date": "2026-11-28",
        "end_date": "2026-11-28",
        "reason": "Vacation"
    })
    req_id = leave["request_id"]

    # 1. Team Lead attempts approval of request not in their team/stage -> blocked
    _, err_tl = LeaveService.verify_request(tl, req_id, "Approved", "TL attempt")
    assert err_tl is not None and ("unauthorized" in err_tl.lower() or "cannot be reviewed" in err_tl.lower() or "access denied" in err_tl.lower())

    # 2. Peer Employee attempts approval -> blocked
    _, err_peer = LeaveService.verify_request(emp1, req_id, "Approved", "Peer attempt")
    assert "Only authorized" in err_peer

    # 3. RBAC helper also returns False for unauthorized reviewer
    assert can_approve_leave(emp1, leave) is False


def test_manager_approves_requests_and_records_audit(db, seeded_users):
    """
    Part 4: Manager reviews requests from Employees and Team Leads,
    approves or rejects with remarks, and records audit trail.
    Two-Stage Workflow: Employee -> TL First Approval -> Manager Final Approval.
    """
    emp = seeded_users["emp1"]
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]

    e_leave, _ = LeaveService.apply_leave(emp, {
        "start_date": "2026-12-01",
        "end_date": "2026-12-02",
        "reason": "Annual trip"
    })
    tl_leave, _ = LeaveService.apply_leave(tl, {
        "start_date": "2026-12-05",
        "end_date": "2026-12-06",
        "reason": "Family gathering"
    })

    # Step 1: Employee request is PENDING_TEAM_LEAD; TL request goes directly to PENDING_MANAGER
    assert e_leave["status"] == "PENDING_TEAM_LEAD"
    assert tl_leave["status"] == "PENDING_MANAGER"

    # Step 2: Team Lead approves Employee request -> transitions to PENDING_MANAGER
    tl_approved, tl_err = LeaveService.verify_request(tl, e_leave["request_id"], "Approved", "TL approved for trip.")
    assert tl_err is None
    assert tl_approved["status"] == "PENDING_MANAGER"

    # Step 3: Now both requests appear in Manager's pending approval queue
    queue = LeaveService.get_all_requests_for_reviewer(mgr, status_filter="Pending")
    req_ids = [r["request_id"] for r in queue["requests"]]
    assert e_leave["request_id"] in req_ids
    assert tl_leave["request_id"] in req_ids

    # Step 4: Manager approves Employee request
    approved_e, err_e = LeaveService.verify_request(mgr, e_leave["request_id"], "Approved", "Have a great trip.")
    assert err_e is None
    assert approved_e["status"] in ("Approved", "APPROVED")
    assert approved_e["reviewed_by_id"] == mgr["employee_id"]
    assert approved_e["review_remarks"] == "Have a great trip."
    assert len(approved_e["approval_history"]) >= 1

    # Step 5: Manager rejects Team Lead request with mandatory reason
    _, err_no_reason = LeaveService.verify_request(mgr, tl_leave["request_id"], "Rejected", "")
    assert "rejection reason is required" in err_no_reason.lower()

    rejected_tl, err_tl = LeaveService.verify_request(mgr, tl_leave["request_id"], "Rejected", "Overlaps with project milestone release.")
    assert err_tl is None
    assert rejected_tl["status"] in ("Rejected", "REJECTED")
    assert rejected_tl["rejection_reason"] == "Overlaps with project milestone release."


def test_manager_cannot_self_approve(db, seeded_users):
    """
    Part 3 & 4: Manager cannot approve their own leave requests.
    """
    mgr = seeded_users["manager"]
    mgr_leave, _ = LeaveService.apply_leave(mgr, {
        "start_date": "2026-12-10",
        "end_date": "2026-12-11",
        "reason": "Personal time off"
    })

    _, err_self = LeaveService.verify_request(mgr, mgr_leave["request_id"], "Approved", "Self approval")
    assert "Self-approval of leave requests is strictly forbidden" in err_self


def test_hr_is_strictly_excluded_from_leave_approval_workflow(db, seeded_users):
    """
    Part 3: HR is excluded from leave approval workflow.
    - HR cannot approve leave requests.
    - HR leave requests do not go to Manager approval queue.
    """
    hr = seeded_users["hr"]
    emp = seeded_users["emp1"]
    mgr = seeded_users["manager"]

    e_leave, _ = LeaveService.apply_leave(emp, {
        "start_date": "2026-12-15",
        "end_date": "2026-12-15",
        "reason": "Personal errand"
    })

    # HR attempts to approve -> denied
    _, err_hr = LeaveService.verify_request(hr, e_leave["request_id"], "Approved", "HR approval")
    assert "excluded from the leave approval workflow" in err_hr or "Unauthorized" in err_hr
    assert can_approve_leave(hr, e_leave) is False

    # HR queue returns empty
    hr_queue = LeaveService.get_all_requests_for_reviewer(hr)
    assert len(hr_queue["requests"]) == 0


def test_manager_manual_email_composer(db, seeded_users):
    """
    Part 5: Manual email composer allows Manager to dispatch leave notification to HR.
    Accurately records email history, does not claim sent unless provider confirms.
    """
    emp = seeded_users["emp1"]
    mgr = seeded_users["manager"]

    leave, _ = LeaveService.apply_leave(emp, {
        "start_date": "2026-12-20",
        "end_date": "2026-12-22",
        "reason": "Year-end vacation"
    })
    req_id = leave["request_id"]

    # 1. Must be Approved before email can be dispatched
    _, err_premature = LeaveService.send_approval_email_to_hr(mgr, req_id, to_email="hr@aisamrat.com")
    assert "only be sent for 'Approved' requests" in err_premature

    # Approve request
    LeaveService.verify_request(mgr, req_id, "Approved", "Year-end leave authorized.")

    # 2. Non-manager cannot send email
    _, err_unauth = LeaveService.send_approval_email_to_hr(emp, req_id, to_email="hr@aisamrat.com")
    assert "Only Managers can send" in err_unauth

    # 3. Manager sends email to default HR address
    result, err = LeaveService.send_approval_email_to_hr(
        sender=mgr,
        request_id=req_id,
        to_email="hr@aisamrat.com",
        cc_email="lead@aisamrat.com",
        subject="Leave Approval Notification — Employee One",
        message="Employee One has been authorized for leave from 2026-12-20 to 2026-12-22."
    )
    assert err is None
    assert result["success"] is True
    assert result["email_status"] in ("SENT", "SIMULATED")
    assert result["record"]["to"] == "hr@aisamrat.com"
    assert result["record"]["cc"] == "lead@aisamrat.com"

    # 4. Check email history recorded in database
    doc = db.leave_requests.find_one({"request_id": req_id})
    assert len(doc["email_history"]) == 1
    assert doc["email_history"][0]["subject"] == "Leave Approval Notification — Employee One"
    assert doc["email_history"][0]["sent_by_id"] == mgr["employee_id"]
