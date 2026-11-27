import pytest
from backend.services.leave_service import LeaveService
from backend.permissions.rbac import Role


def test_apply_leave_and_calculation(db, seeded_users):
    """Test applying for leave with date validation, days calculation, and Manager notification."""
    emp1 = seeded_users["emp1"]

    # 1. Valid leave application
    doc, err = LeaveService.apply_leave(emp1, {
        "leave_type": "Casual Leave",
        "start_date": "2026-10-20",
        "end_date": "2026-10-22",
        "reason": "Attending family wedding ceremony."
    })
    assert err is None
    assert doc["request_id"].startswith("LR-")
    assert doc["days_count"] == 3.0
    assert doc["status"] in ("Pending", "PENDING_MANAGER", "PENDING_TEAM_LEAD")
    assert doc["employee_id"] == emp1["employee_id"]

    # Notification generated for approver (Team Lead / Approver queue)
    approver_notif = db.notifications.find_one({"category": "LEAVE"})
    assert approver_notif is not None
    assert emp1["full_name"] in approver_notif["title"]

    # 2. Invalid dates: end date prior to start date
    doc_bad, err_bad = LeaveService.apply_leave(emp1, {
        "start_date": "2026-10-25",
        "end_date": "2026-10-20",
        "reason": "Test"
    })
    assert doc_bad is None
    assert "End date cannot be prior to start date" in err_bad

    # 3. Half day leave
    doc_half, err_half = LeaveService.apply_leave(emp1, {
        "leave_type": "Casual Leave",
        "start_date": "2026-10-20",
        "end_date": "2026-10-20",
        "is_half_day": True,
        "reason": "Personal work in morning."
    })
    assert err_half is None
    assert doc_half["days_count"] == 0.5


def test_apply_permission_early_exit(db, seeded_users):
    """Test applying for early exit permission with Manager notification."""
    emp1 = seeded_users["emp1"]

    doc, err = LeaveService.apply_permission(emp1, {
        "permission_date": "2026-10-16",
        "early_exit_time": "16:30",
        "permission_type": "Early Exit",
        "reason": "Medical appointment with dentist."
    })
    assert err is None
    assert doc["request_id"].startswith("PR-")
    assert doc["request_type"] == "PERMISSION"
    assert doc["early_exit_time"] == "16:30"
    assert doc["status"] in ("Pending", "PENDING_MANAGER", "PENDING_TEAM_LEAD")

    # Approver Notification generated
    perm_notif = db.notifications.find_one({"category": "PERMISSION"})
    assert perm_notif is not None


def test_manager_leave_approval_workflow_and_employee_notification(db, seeded_users):
    """Test Manager approving and rejecting requests and notifying the applicant."""
    emp1 = seeded_users["emp1"]
    mgr = seeded_users["manager"]
    hr = seeded_users["hr"]
    emp2 = seeded_users["emp2"]

    # 1. Emp1 applies for leave
    leave_doc, _ = LeaveService.apply_leave(emp1, {
        "start_date": "2026-10-21",
        "end_date": "2026-10-21",
        "reason": "Need leave for renewal of driving license."
    })
    req_id = leave_doc["request_id"]

    # 2. Emp2 (non-manager) attempts to verify -> must be denied
    _, err_unauth = LeaveService.verify_request(emp2, req_id, "Approved", "Approved by colleague")
    assert "Only authorized" in err_unauth

    # 3. HR attempts to verify -> must be denied (HR excluded from leave workflow)
    _, err_hr = LeaveService.verify_request(hr, req_id, "Approved", "Approved by HR")
    assert "excluded from the leave approval workflow" in err_hr or "Unauthorized" in err_hr

    # 4. Self-approval strictly forbidden
    _, err_self = LeaveService.verify_request(emp1, req_id, "Approved", "Self approve")
    assert "Self-approval of leave requests is strictly forbidden" in err_self

    # 5. Manager approves with remarks
    verified_doc, err = LeaveService.verify_request(mgr, req_id, "Approved", "Approved. Ensure tasks are handed over.")
    assert err is None
    assert verified_doc["status"] in ("Approved", "APPROVED")
    assert verified_doc["reviewed_by_id"] == mgr["employee_id"]
    assert verified_doc["review_remarks"] == "Approved. Ensure tasks are handed over."
    assert len(verified_doc["approval_history"]) >= 1

    # Verify notification generated specifically for emp1
    emp_notif = db.notifications.find_one({"recipient_id": emp1["employee_id"], "category": "LEAVE"})
    assert emp_notif is not None
    assert "Approved" in emp_notif["title"]

    # 6. Manager manual email composer dispatches notification to HR
    email_res, email_err = LeaveService.send_approval_email_to_hr(
        sender=mgr,
        request_id=req_id,
        to_email="hr@aisamrat.com",
        subject="Leave Approval Notification — Employee One",
        message="Employee One has been approved for leave on 2026-10-21."
    )
    assert email_err is None
    assert email_res["success"] is True
    assert email_res["email_status"] in ("SENT", "SIMULATED")
    assert email_res["record"]["to"] == "hr@aisamrat.com"

    # 7. Emp1 applies for permission, Manager rejects with remarks
    perm_doc, _ = LeaveService.apply_permission(emp1, {
        "permission_date": "2026-10-18",
        "early_exit_time": "14:00",
        "reason": "Early movie show."
    })
    perm_id = perm_doc["request_id"]

    # Rejection requires reason
    _, err_no_reason = LeaveService.verify_request(mgr, perm_id, "Rejected", "")
    assert "rejection reason is required" in err_no_reason.lower()

    rejected_doc, err_rej = LeaveService.verify_request(mgr, perm_id, "Rejected", "Critical release scheduled on this day.")
    assert err_rej is None
    assert rejected_doc["status"] in ("Rejected", "REJECTED")
    assert "Critical release" in rejected_doc["review_remarks"]
    assert rejected_doc["rejection_reason"] == "Critical release scheduled on this day."


def test_cancel_pending_request(db, seeded_users):
    """Test cancelling own pending request and ensuring status is set to Cancelled."""
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    doc, _ = LeaveService.apply_leave(emp1, {
        "start_date": "2026-10-23",
        "end_date": "2026-10-23",
        "reason": "Tentative travel"
    })
    rid = doc["request_id"]

    # Emp2 cannot cancel Emp1's request
    ok, err = LeaveService.cancel_request(emp2, rid)
    assert not ok
    assert "Access Denied" in err

    # Emp1 can cancel their pending request
    ok, err = LeaveService.cancel_request(emp1, rid)
    assert ok
    assert err is None

    # Check request is marked Cancelled (preserving historical record)
    found = db.leave_requests.find_one({"request_id": rid})
    assert found is not None
    assert found["status"] == "Cancelled"
    assert found.get("cancelled_at") is not None
