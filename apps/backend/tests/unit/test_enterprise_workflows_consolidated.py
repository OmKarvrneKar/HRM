import pytest
from datetime import datetime, timezone
from database.connection import get_db, DatabaseManager
from permissions.rbac import Role
from services.attendance_service import AttendanceService
from services.attendance_correction_service import AttendanceCorrectionService
from services.leave_service import LeaveService
from services.chat_service import ChatService
from services.enterprise_hr_service import (
    EnterpriseMailboxService,
    RecruitmentTalentService,
    SecureDocumentViewerService,
    EnterprisePayrollService
)


@pytest.fixture(autouse=True)
def setup_isolated_db():
    db = get_db()
    # Use real seeded users directly
    emp_user = db.users.find_one({"employee_id": "EMP-1005"})
    if not emp_user:
        emp_user = {
            "employee_id": "EMP-1005",
            "full_name": "Deepak S J",
            "email": "deepaksj.in@gmail.com",
            "role": Role.EMPLOYEE,
            "department": "AI & Engineering",
            "team_lead_id": "LEAD-1001",
            "reporting_manager_id": "MGR-1001",
            "is_active": True
        }
        db.users.insert_one(emp_user)
    else:
        db.users.update_one({"employee_id": "EMP-1005"}, {"$set": {
            "team_lead_id": "LEAD-1001",
            "reporting_manager_id": "MGR-1001",
            "is_active": True
        }})

    tl_user = db.users.find_one({"employee_id": "LEAD-1001"})
    if not tl_user:
        tl_user = {
            "employee_id": "LEAD-1001",
            "full_name": "Kavita Nair",
            "email": "kavita.nair@aisamrat.com",
            "role": Role.TEAM_LEAD,
            "department": "AI & Engineering",
            "reporting_manager_id": "MGR-1001",
            "is_active": True
        }
        db.users.insert_one(tl_user)

    mgr_user = db.users.find_one({"employee_id": "MGR-1001"})
    if not mgr_user:
        mgr_user = {
            "employee_id": "MGR-1001",
            "full_name": "Vikramaditya Roy",
            "email": "vikramaditya.roy@aisamrat.com",
            "role": Role.MANAGER,
            "department": "Engineering Management",
            "is_active": True
        }
        db.users.insert_one(mgr_user)

    hr_user = db.users.find_one({"employee_id": "HR-1001"})
    if not hr_user:
        hr_user = {
            "employee_id": "HR-1001",
            "full_name": "Ramya HR",
            "email": "ramya.hr@aisamrat.com",
            "role": Role.HR,
            "department": "Human Resources",
            "is_active": True
        }
        db.users.insert_one(hr_user)

    admin_user = (
        db.users.find_one({"employee_id": "ADM-1001"})
        or db.users.find_one({"email": "admin@aisamrat.com"})
    )
    if not admin_user:
        admin_user = {
            "employee_id": "ADM-1001",
            "full_name": "System Administrator",
            "email": "admin@aisamrat.com",
            "role": Role.ADMIN,
            "department": "Executive Management",
            "is_active": True
        }
        db.users.insert_one(admin_user)

    yield db




def test_communication_split_official_mailbox(setup_isolated_db):
    """Verifies official mailbox returns categorized letters, payslips, and memos separated from chat."""
    db = setup_isolated_db
    user = db.users.find_one({"employee_id": "EMP-1005"})

    # Fetch initial mailbox
    box = EnterpriseMailboxService.get_user_mailbox(user, folder="all")
    assert "items" in box
    assert len(box["items"]) >= 3
    assert box["counts"]["all"] >= 3

    # Dispatch a new official circular
    admin_user = db.users.find_one({"employee_id": "ADM-1001"})
    new_doc, err = EnterpriseMailboxService.dispatch_official_notice(admin_user, {
        "subject": "Statutory Annual General Meeting Notification",
        "content": "Official announcement regarding company statutory compliance and performance overview.",
        "category": "ADMIN_MEMO",
        "recipient_group": "ALL_EMPLOYEES"
    })
    assert err is None
    assert new_doc["subject"] == "Statutory Annual General Meeting Notification"
    assert new_doc["mail_id"].startswith("MAIL-PUB-")

    # Fetch updated mailbox
    box_updated = EnterpriseMailboxService.get_user_mailbox(user, folder="memos")
    assert any(m["subject"] == "Statutory Annual General Meeting Notification" for m in box_updated["items"])


def test_hr_isolation_chat_restriction(setup_isolated_db):
    """Verifies HR and Admin have ZERO access to project chats in conversation queries."""
    db = setup_isolated_db
    hr_user = db.users.find_one({"employee_id": "HR-1001"})
    admin_user = db.users.find_one({"employee_id": "ADM-1001"})
    emp_user = db.users.find_one({"employee_id": "EMP-1005"})

    # Seed a project chat
    db.conversations.insert_one({
        "conversation_id": "PRJ-CHAT-PRJ-ALPHA",
        "type": "project",
        "project_id": "PRJ-ALPHA",
        "title": "Project Alpha Sprint Chat",
        "participant_ids": ["EMP-1005", "HR-1001", "ADM-1001"],
        "status": "active",
        "updated_at": datetime.now(timezone.utc)
    })
    # Seed a direct chat
    db.conversations.insert_one({
        "conversation_id": "DM-EMP-1005-HR-1001",
        "type": "direct",
        "title": "Deepak & Ramya HR",
        "participant_ids": ["EMP-1005", "HR-1001"],
        "status": "active",
        "updated_at": datetime.now(timezone.utc)
    })

    # HR gets conversation list: must NOT contain project chat
    hr_convs = ChatService.get_user_conversations(hr_user)
    assert not any(c.get("type") == "project" or c.get("is_project") for c in hr_convs)
    assert any(c.get("type") == "direct" for c in hr_convs)

    # Admin gets conversation list: must NOT contain project chat
    admin_convs = ChatService.get_user_conversations(admin_user)
    assert not any(c.get("type") == "project" or c.get("is_project") for c in admin_convs)

    # Direct access to project chat by HR must fail with 403
    conv, err = ChatService.get_conversation(hr_user, "PRJ-CHAT-PRJ-ALPHA")
    assert conv is None
    assert "Access Denied" in err


def test_morning_afternoon_granular_shift_split(setup_isolated_db):
    """Verifies timing status computes Pre-Break (Morning) and Post-Break (Afternoon) half-splits."""
    timing = AttendanceService.get_office_timing_status(employee_id="EMP-1005")
    assert "shift_split" in timing
    sp = timing["shift_split"]

    assert "morning" in sp
    assert sp["morning"]["target_hours"] == 3.5
    assert "10:00" in sp["morning"]["window"]

    assert "break" in sp
    assert sp["break"]["target_hours"] == 1.0

    assert "afternoon" in sp
    assert sp["afternoon"]["target_hours"] == 3.5
    assert "06:00" in sp["afternoon"]["window"]


def test_multi_tier_attendance_shortage_minor(setup_isolated_db):
    """Verifies minor shortage (<= 1h deficit) gives direct approval authority to Team Lead with Manager/HR notification."""
    db = setup_isolated_db
    emp_user = db.users.find_one({"employee_id": "EMP-1005"})
    tl_user = db.users.find_one({"employee_id": "LEAD-1001"})

    # Seed or update daily attendance with 7.5 hours logged (deficit = 0.5h <= 1.0h -> Minor)
    db.attendance_corrections.delete_many({"employee_id": "EMP-1005", "target_date": "2026-11-04"})
    db.attendance_daily.update_one(
        {"employee_id": "EMP-1005", "attendance_date": "2026-11-04"},
        {"$set": {
            "employee_id": "EMP-1005",
            "attendance_date": "2026-11-04",
            "active_seconds": 27000,
            "official_working_duration_seconds": 27000,
            "status": "PRESENT"
        }},
        upsert=True
    )

    req, err = AttendanceCorrectionService.request_correction(
        employee_user=emp_user,
        target_date="2026-11-04",
        correction_type="MISSED_PUNCH_OUT",
        reason="Biometric turnstile timeout during evening exit",
        requested_status="PRESENT"
    )
    assert err is None
    assert req["shortage_tier"] == "MINOR"
    assert req["status"] == "PENDING_TEAM_LEAD"
    assert req["assigned_tl_id"] == "LEAD-1001"

    # Team Lead directly approves minor shortage
    reviewed_req, review_err = AttendanceCorrectionService.review_correction(
        reviewer_user=tl_user,
        request_id=req["request_id"],
        decision="APPROVED",
        remarks="Verified logs with turnstile security; approved under TL authority."
    )
    assert review_err is None
    assert reviewed_req["status"] == "APPROVED"
    assert reviewed_req["hr_notified"] is True

    # Confirm daily attendance is regularized
    daily = db.attendance_daily.find_one({"employee_id": "EMP-1005", "attendance_date": "2026-11-04"})
    assert daily["clock_out_state"] == "Regularized"


def test_multi_tier_attendance_shortage_major(setup_isolated_db):
    """Verifies major shortage (> 1h deficit) requires TL endorsement and final Manager sign-off."""
    db = setup_isolated_db
    emp_user = db.users.find_one({"employee_id": "EMP-1005"})
    tl_user = db.users.find_one({"employee_id": "LEAD-1001"})
    mgr_user = db.users.find_one({"employee_id": "MGR-1001"})

    # Seed or update daily attendance with 4.0 hours logged (deficit = 4.0h > 1.0h -> Major)
    db.attendance_corrections.delete_many({"employee_id": "EMP-1005", "target_date": "2026-11-03"})
    db.attendance_daily.update_one(
        {"employee_id": "EMP-1005", "attendance_date": "2026-11-03"},
        {"$set": {
            "employee_id": "EMP-1005",
            "attendance_date": "2026-11-03",
            "active_seconds": 14400,
            "status": "PRESENT"
        }},
        upsert=True
    )

    req, err = AttendanceCorrectionService.request_correction(
        employee_user=emp_user,
        target_date="2026-11-03",
        correction_type="STATUS_DISPUTE",
        reason="Attended off-site client architectural workshop in afternoon",
        requested_status="PRESENT"
    )
    assert err is None
    assert req["shortage_tier"] == "MAJOR"
    assert req["status"] == "PENDING_TEAM_LEAD_REVIEW"

    # Stage 1: Team Lead reviews and endorses
    endorsed_req, end_err = AttendanceCorrectionService.review_correction(
        reviewer_user=tl_user,
        request_id=req["request_id"],
        decision="ENDORSED",
        remarks="Client workshop verified by team lead. Endorsed for manager sign-off."
    )
    assert end_err is None
    assert endorsed_req["status"] == "PENDING_MANAGER"
    assert endorsed_req["tl_endorsed"] is True

    # Stage 2: Manager provides final approval
    final_req, final_err = AttendanceCorrectionService.review_correction(
        reviewer_user=mgr_user,
        request_id=req["request_id"],
        decision="APPROVED",
        remarks="Client engagement verified with partner POC. Final sign-off granted."
    )
    assert final_err is None
    assert final_req["status"] == "APPROVED"
    assert final_req["hr_notified"] is True


def test_simultaneous_manager_hr_leave_visibility(setup_isolated_db):
    """Verifies leave application routes to TL and simultaneously sends notification copies to Manager and HR."""
    db = setup_isolated_db
    emp_user = db.users.find_one({"employee_id": "EMP-1005"})

    # Seed leave balance
    db.leave_balances.insert_one({
        "employee_id": "EMP-1005",
        "year": 2026,
        "balances": {"Casual Leave": 12.0}
    })

    leave_doc, err = LeaveService.apply_leave(emp_user, {
        "leave_type": "Casual Leave",
        "start_date": "2026-11-15",
        "end_date": "2026-11-16",
        "days_count": 2.0,
        "reason": "Personal family commitment"
    })
    assert err is None
    assert leave_doc["status"] == "PENDING_TEAM_LEAD"
    assert leave_doc["assigned_tl_id"] == "LEAD-1001"

    # Verify notifications created: 1 for TL, 1 for Manager, 1 for HR
    tl_notifs = list(db.notifications.find({"recipient_id": "LEAD-1001"}))
    assert len(tl_notifs) >= 1

    mgr_notifs = list(db.notifications.find({"recipient_id": "MGR-1001", "category": "LEAVE_FYI"}))
    assert len(mgr_notifs) >= 1
    assert "Routed to TL" in mgr_notifs[0]["message"]

    hr_notifs = list(db.notifications.find({"recipient_group": "HR", "category": "LEAVE_FYI"}))
    assert len(hr_notifs) >= 1


def test_ats_resume_scanner(setup_isolated_db):
    """Verifies ATS resume scanner computes accurate skill match %, identifies missing skills, and fit tier."""
    resume_sample = """
    Aditya Varma | Senior Backend Software Architect with 8 years of experience.
    Core competencies: Python, Flask, MongoDB, PostgreSQL, Docker, Redis, REST APIs, Git, Microservices.
    Designed high-concurrency microservices, optimized database query execution plans, and enforced RBAC.
    """
    result = RecruitmentTalentService.scan_resume(
        resume_text=resume_sample,
        target_role="Senior Backend Architect"
    )
    assert result["match_score"] >= 80
    assert "Python" in result["matched_skills"]
    assert "MongoDB" in result["matched_skills"]
    assert result["fit_badge"] == "success"
    assert result["detected_experience_years"] == 8.0


def test_secure_document_viewer_redaction(setup_isolated_db):
    """Verifies Secure Document Viewer redacts Aadhaar, PAN, and Bank Account digits and outputs watermarked preview."""
    docket = SecureDocumentViewerService.get_employee_secure_docket("EMP-1005")
    assert "error" not in docket
    assert docket["employee_id"] == "EMP-1005"
    assert len(docket["docket_records"]) == 4

    pan_doc = next(r for r in docket["docket_records"] if "PAN" in r["doc_type"])
    assert "XXX" in pan_doc["doc_number"]  # Redacted PAN

    aadhaar_doc = next(r for r in docket["docket_records"] if "Aadhaar" in r["doc_type"])
    assert "XXXX-XXXX-" in aadhaar_doc["doc_number"]  # Masked Aadhaar

    bank_doc = next(r for r in docket["docket_records"] if "Bank" in r["doc_type"])
    assert "XXXXXXXX" in bank_doc["doc_number"]  # Masked Bank

    # Test preview generation
    preview = SecureDocumentViewerService.get_secure_document_preview("EMP-1005", "PAN")
    assert preview["success"] is True
    assert "CONFIDENTIAL" in preview["preview_html"]
    assert "DPDP Act 2023" in preview["preview_html"]
