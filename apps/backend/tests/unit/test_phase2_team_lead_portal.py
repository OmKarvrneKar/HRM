import pytest
from datetime import datetime, timezone, timedelta
from services.skill_service import SkillService
from services.attendance_service import AttendanceService
from services.project_service import ProjectService
from services.leave_service import LeaveService
from services.work_diary_service import WorkDiaryService
from permissions.rbac import Role
from utils.timezone import now_utc, get_local_date_str


def test_team_size_and_skill_diagnostics_no_dummy_data(db, seeded_users):
    """
    Part 1 & 2: Test team size strictly counts active Role.EMPLOYEE in lead's team_id,
    and skill diagnostics uses neutral indicators, flags real critical gaps, and invents no dummy data.
    """
    tl = seeded_users["team_lead"]

    # 1. When team has no members assigned yet
    diag = SkillService.get_team_skill_diagnostics(tl)
    assert diag["team_size"] == 0
    assert diag["has_pending_assignment"] is True
    assert diag["is_healthy"] is True  # No fake red high-severity alarms when 0 members configured

    # 2. Assign real employee to team
    emp1 = seeded_users["emp1"]
    tl_team_id = tl.get("team_id", "TEAM-TEST-ENG")
    db.users.update_one({"employee_id": emp1["employee_id"]}, {"$set": {"team_id": tl_team_id}})

    # Do not count HR, Manager or other TL even if in same team_id
    hr = seeded_users["hr"]
    db.users.update_one({"employee_id": hr["employee_id"]}, {"$set": {"team_id": tl_team_id}})
    mgr = seeded_users["manager"]
    db.users.update_one({"employee_id": mgr["employee_id"]}, {"$set": {"team_id": tl_team_id}})

    diag2 = SkillService.get_team_skill_diagnostics(tl)
    assert diag2["team_size"] == 1  # Only emp1 is Role.EMPLOYEE
    assert diag2["has_pending_assignment"] is False

    # Check skill items formatting
    for skill in diag2["skills"]:
        assert "severity" in skill
        assert skill["severity"] in ("normal", "critical", "covered")
        assert "actionable_recommendation" in skill
        assert "employee_count" in skill


def test_attendance_time_tracking_elapsed_vs_active(db, seeded_users):
    """
    Part 3: Test separate calculation of Elapsed time, Break duration, and Active working time.
    Active working time = Elapsed time - Total recorded break duration.
    """
    emp = seeded_users["emp1"]
    today = get_local_date_str()

    # Create paired punch with breaks
    # Clock in at 09:00:00 (1000 seconds ago)
    t0 = datetime(2026, 10, 20, 9, 0, 0, tzinfo=timezone.utc)
    t_break_start = datetime(2026, 10, 20, 11, 0, 0, tzinfo=timezone.utc)
    t_break_end = datetime(2026, 10, 20, 11, 45, 0, tzinfo=timezone.utc)  # 45 mins = 2700s
    t_logout = datetime(2026, 10, 20, 17, 0, 0, tzinfo=timezone.utc)  # 8 hrs = 28800s total elapsed

    # Insert raw events into attendance_events
    db.attendance_events.insert_many([
        {
            "employee_id": emp["employee_id"],
            "session_id": "SESSION-TEST-1",
            "event_type": "LOGIN",
            "timestamp": t0,
            "date": "2026-10-20",
            "is_closed": True
        },
        {
            "employee_id": emp["employee_id"],
            "session_id": "SESSION-TEST-1",
            "event_type": "BREAK_START",
            "timestamp": t_break_start,
            "date": "2026-10-20",
            "is_closed": True,
            "notes": "Lunch break"
        },
        {
            "employee_id": emp["employee_id"],
            "session_id": "SESSION-TEST-1",
            "event_type": "BREAK_END",
            "timestamp": t_break_end,
            "date": "2026-10-20",
            "is_closed": False,
            "notes": "Resume work"
        },
        {
            "employee_id": emp["employee_id"],
            "session_id": "SESSION-TEST-1",
            "event_type": "LOGOUT",
            "timestamp": t_logout,
            "date": "2026-10-20",
            "is_closed": True
        }
    ])

    summary = AttendanceService.recalculate_daily_summary(emp["employee_id"], "2026-10-20")
    assert summary is not None
    assert summary["total_break_seconds"] == 2700  # 45 minutes
    assert summary["break_taken_display"] == "0h 45m"
    assert summary["elapsed_seconds"] == 28800  # 8 hours
    assert summary["elapsed_display"] in ("8h 0m", "8h 00m")
    assert summary["active_working_seconds"] == 28800 - 2700  # 26100s = 7h 15m
    assert summary["active_working_display"] == "7h 15m"
    assert summary["clock_out_state"] == "Clocked Out"


def test_project_creation_and_automatic_group_chat(db, seeded_users):
    """
    Critical Workflow: Team Lead creates a project proposal awaiting Manager approval.
    At proposal stage:
      - Project status is PENDING_APPROVAL, is_approved is False.
      - Members are not actively assigned yet.
      - No group chat is created.
    After Manager approval:
      - Project status becomes ACTIVE.
      - Members are activated.
      - Project group chat is automatically created with TL, Manager, and members.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    payload = {
        "name": "HRMS Automation Suite",
        "description": "Enterprise automated workflow testing",
        "objectives": "Automate regression tests and deployment pipelines",
        "deliverables": "Core CI/CD scripts, automated test suite, coverage reports",
        "start_date": "2026-11-05",
        "expected_completion_date": "2026-12-15",
        "priority": "High",
        "status": "In Progress",
        "category": "Internal Operations",
        "assigned_manager": mgr["employee_id"],
        "selected_members": [emp1["employee_id"], emp2["employee_id"]],
        "project_lead": tl["employee_id"]
    }

    doc, err = ProjectService.create_project(tl, payload)
    assert err is None
    assert doc is not None
    assert doc["name"] == "HRMS Automation Suite"
    assert doc["objectives"] == "Automate regression tests and deployment pipelines"
    assert doc["status"] == "PENDING_APPROVAL"
    assert doc["is_approved"] is False

    project_id = doc["project_id"]

    # Verify NO group chat is created before Manager approval
    conv_before = db.conversations.find_one({"project_id": project_id})
    assert conv_before is None

    # Manager approves proposal
    approved_doc, app_err = ProjectService.approve_project(mgr, project_id, review_notes="Approved for Q4 sprint")
    assert app_err is None
    assert approved_doc is not None
    assert approved_doc["status"] == "ACTIVE"
    assert approved_doc["is_approved"] is True
    assert len(approved_doc["members"]) == 2

    # Verify associated private project group chat is created ONLY after Manager approval
    conv = db.conversations.find_one({"project_id": project_id})
    assert conv is not None
    assert conv["is_group"] is True
    assert conv["name"] == "HRMS Automation Suite"
    assert tl["employee_id"] in conv["participants"]
    assert mgr["employee_id"] in conv["participants"]
    assert emp1["employee_id"] in conv["participants"]
    assert emp2["employee_id"] in conv["participants"]


def test_two_stage_leave_approval_workflow(db, seeded_users):
    """
    Test two-stage leave approval workflow:
    - Employee submits leave request -> PENDING_TEAM_LEAD.
    - Assigned Team Lead approves -> moves to PENDING_MANAGER.
    - Manager gives final approval -> APPROVED.
    - Team Lead personal leave goes directly to Manager -> PENDING_MANAGER.
    - Self-approval strictly forbidden for both Employee and Team Lead.
    - Peer employees cannot approve.
    - Rejection stops the workflow.
    """
    emp1 = seeded_users["emp1"]
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp2 = seeded_users["emp2"]

    # Assign emp1 to tl's team so tl is assigned approver
    db.users.update_one({"employee_id": emp1["employee_id"]}, {"$set": {"team_id": tl.get("team_id", "TEAM-TEST-ENG"), "reporting_manager_id": tl["employee_id"]}})
    emp1["team_id"] = tl.get("team_id", "TEAM-TEST-ENG")
    emp1["reporting_manager_id"] = tl["employee_id"]

    # 1. Emp1 applies for leave -> enters PENDING_TEAM_LEAD
    leave_doc, err = LeaveService.apply_leave(emp1, {
        "leave_type": "Casual Leave",
        "start_date": "2026-11-10",
        "end_date": "2026-11-11",
        "reason": "Personal family function."
    })
    assert err is None
    req_id = leave_doc["request_id"]
    assert leave_doc["status"] == "PENDING_TEAM_LEAD"
    assert leave_doc["assigned_tl_id"] == tl["employee_id"]

    # 2. Self-approval strictly forbidden
    _, err_self = LeaveService.verify_request(emp1, req_id, "Approved", "Self approve")
    assert "Self-approval of leave requests is strictly forbidden" in err_self

    # 3. Unrelated Employee cannot approve
    _, err_unauth = LeaveService.verify_request(emp2, req_id, "Approved", "Peer approve")
    assert "Only authorized" in err_unauth

    # 4. Team Lead approves stage 1 -> moves to PENDING_MANAGER
    tl_doc, err_tl = LeaveService.verify_request(tl, req_id, "Approved", "TL approved for sprint coverage")
    assert err_tl is None
    assert tl_doc["status"] == "PENDING_MANAGER"
    assert tl_doc["tl_reviewed_by_id"] == tl["employee_id"]

    # 5. Manager provides final approval -> APPROVED
    mgr_doc, err_mgr = LeaveService.verify_request(mgr, req_id, "Approved", "Final approval granted.")
    assert err_mgr is None
    assert mgr_doc["status"] in ("Approved", "APPROVED")
    assert mgr_doc["reviewed_by_id"] == mgr["employee_id"]
    assert mgr_doc["review_remarks"] == "Final approval granted."

    # 6. Team Lead applies for their own personal leave -> goes directly to Manager (PENDING_MANAGER)
    tl_leave, tl_err = LeaveService.apply_leave(tl, {
        "leave_type": "Privilege Leave",
        "start_date": "2026-11-15",
        "end_date": "2026-11-16",
        "reason": "Conference attendance"
    })
    assert tl_err is None
    assert tl_leave["status"] == "PENDING_MANAGER"
    assert tl_leave["employee_id"] == tl["employee_id"]

    # Team Lead cannot self-approve personal leave
    _, err_tl_self = LeaveService.verify_request(tl, tl_leave["request_id"], "Approved", "Self approve")
    assert "Self-approval of leave requests is strictly forbidden" in err_tl_self

    # Manager approves Team Lead's personal leave
    tl_approved, tl_app_err = LeaveService.verify_request(mgr, tl_leave["request_id"], "Approved", "Approved for conference.")
    assert tl_app_err is None
    assert tl_approved["status"] in ("Approved", "APPROVED")

    # 7. Test Rejection flow stops the workflow
    perm_doc, _ = LeaveService.apply_permission(emp1, {
        "permission_date": "2026-11-12",
        "early_exit_time": "15:00",
        "reason": "Doctor visit"
    })
    perm_id = perm_doc["request_id"]

    rej_doc, err_rej = LeaveService.verify_request(tl, perm_id, "Rejected", "Critical sprint delivery scheduled.")
    assert err_rej is None
    assert rej_doc["status"] in ("Rejected", "REJECTED")
    assert "Critical sprint delivery" in rej_doc["rejection_reason"]


def test_work_diary_team_review_and_feedback(db, seeded_users):
    """
    Part 8: Test Team Lead can review team work diaries and post feedback comments
    without overwriting or modifying the employee's original log submission.
    """
    emp1 = seeded_users["emp1"]
    tl = seeded_users["team_lead"]
    today = get_local_date_str()

    # Assign emp1 to TL's team
    tl_team_id = tl.get("team_id", "TEAM-TEST-ENG")
    db.users.update_one({"employee_id": emp1["employee_id"]}, {"$set": {"team_id": tl_team_id}})
    emp1["team_id"] = tl_team_id

    # Emp1 logs a work diary entry
    entry = WorkDiaryService.create_entry(
        employee_id=emp1["employee_id"],
        employee_name=emp1["full_name"],
        payload={
            "diary_date": today,
            "start_time": "10:00",
            "end_time": "13:00",
            "activity_title": "Database Optimization",
            "work_description": "Added indexes on leave_requests and work_diary",
            "project_name": "HRMS Performance",
            "blockers": "None",
            "planned_next": "API caching",
            "category": "Development",
            "status": "Completed"
        }
    )
    diary_id = entry["diary_id"]
    assert entry["project_name"] == "HRMS Performance"

    # Team Lead queries team work diaries
    team_diaries = WorkDiaryService.get_team_work_diaries(tl, today)
    assert team_diaries["summary"]["total_team_members"] >= 1
    assert team_diaries["summary"]["submitted_count"] >= 1

    # Team Lead adds feedback comment
    updated_entry = WorkDiaryService.add_review_comment(
        reviewer=tl,
        diary_id=diary_id,
        comment_text="Great work on index optimization! Please benchmark queries."
    )
    assert len(updated_entry["comments"]) == 1
    cmt = updated_entry["comments"][0]
    assert cmt["author_id"] == tl["employee_id"]
    assert cmt["comment"] == "Great work on index optimization! Please benchmark queries."
    # Original submission preserved
    assert updated_entry["work_description"] == "Added indexes on leave_requests and work_diary"


def test_team_attendance_cutoff_logic(db, seeded_users):
    """
    Part 9: Test team attendance overview distinguishes between Not Yet Clocked In
    and Absent before 7:00 PM cutoff.
    """
    tl = seeded_users["team_lead"]
    emp1 = seeded_users["emp1"]
    today = get_local_date_str()

    # Assign emp1 to TL's team
    tl_team_id = tl.get("team_id", "TEAM-TEST-ENG")
    db.users.update_one({"employee_id": emp1["employee_id"]}, {"$set": {"team_id": tl_team_id}})
    emp1["team_id"] = tl_team_id

    # Before cutoff for today: emp1 has not clocked in yet -> NOT_CLOCKED_IN (not Absent)
    overview = AttendanceService.get_team_attendance_overview(tl, today)
    assert overview["summary"]["total_team_members"] >= 1
    # Check emp1's status in the list
    emp_record = next(m for m in overview["members"] if m["employee_id"] == emp1["employee_id"])
    assert emp_record["status"] in ("NOT_CLOCKED_IN", "PRESENT", "WEEKEND")
