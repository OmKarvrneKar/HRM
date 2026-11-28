import pytest
from services.enterprise_hr_service import (
    NomineeManagementService,
    AssetSoftwareService,
    FacilityBookingService,
    PerformanceLearningService,
    EngagementSupportService,
    SeparationService,
    RecruitmentTalentService,
    SecureDocumentViewerService,
    EnterprisePayrollService
)

def test_nominee_management_service():
    actor = {"employee_id": "EMP-1005", "role": "employee"}
    # Valid 100% distribution
    valid_nominees = [
        {"name": "Anita S", "relationship": "Spouse", "share_percentage": 60},
        {"name": "Rohan S", "relationship": "Child", "share_percentage": 40}
    ]
    success, msg = NomineeManagementService.save_nominees(actor, "EMP-1005", valid_nominees)
    assert success is True

    # Invalid distribution (> 100%)
    invalid_nominees = [
        {"name": "Anita S", "relationship": "Spouse", "share_percentage": 70},
        {"name": "Rohan S", "relationship": "Child", "share_percentage": 40}
    ]
    success_err, err_msg = NomineeManagementService.save_nominees(actor, "EMP-1005", invalid_nominees)
    assert success_err is False
    assert "must equal exactly 100%" in err_msg

def test_facility_booking_service(db):
    # Clean production does not pre-seed fabricated rooms; start from empty state
    db.facility_rooms.delete_many({})
    empty_data = FacilityBookingService.get_rooms_and_bookings("2026-11-07")
    assert empty_data["rooms"] == []

    # Seed isolated synthetic rooms in test DB only
    admin_actor = {"employee_id": "SYN-ADM-1", "full_name": "Test Admin", "role": "admin"}
    r1, err1 = FacilityBookingService.create_room(admin_actor, {
        "name": "Synthetic Conference Room A",
        "floor": "Test Floor 1",
        "capacity": 8,
        "features": ["Display"],
        "notes": "Isolated test room inspection"
    })
    assert err1 is None and r1["is_verified"] is True

    rooms_data = FacilityBookingService.get_rooms_and_bookings("2026-11-07")
    assert len(rooms_data["rooms"]) == 1
    assert rooms_data["rooms"][0]["name"] == "Synthetic Conference Room A"

def test_performance_learning_service():
    hub = PerformanceLearningService.get_employee_performance_hub("EMP-1005")
    assert "courses" in hub
    assert len(hub["courses"]) >= 4
    course_ids = [c["course_id"] for c in hub["courses"]]
    assert "CRS-SEC-101" in course_ids
    assert "CRS-DPDP-201" in course_ids

def test_engagement_support_service():
    feed = EngagementSupportService.get_community_feed()
    assert isinstance(feed, list)
    assert len(feed) > 0

    kudos_data = EngagementSupportService.get_kudos_leaderboard()
    assert "leaderboard" in kudos_data
    assert len(kudos_data["leaderboard"]) > 0

    policies = EngagementSupportService.get_company_policy_vault()
    assert len(policies) >= 4

def test_separation_service():
    data = SeparationService.get_tenure_and_status("EMP-1005")
    assert "tenure" in data
    assert "years" in data["tenure"]
    assert "clearance_stages" in data
    assert "manager" in data["clearance_stages"]

def test_recruitment_talent_service():
    scorecards = RecruitmentTalentService.get_candidate_scorecards()
    assert len(scorecards) >= 2
    ats = RecruitmentTalentService.get_ats_pipeline()
    assert "candidates" in ats
    assert len(ats["candidates"]) >= 4

def test_secure_document_viewer_service():
    docket = SecureDocumentViewerService.get_employee_secure_docket("EMP-1005")
    assert "docket_records" in docket
    assert len(docket["docket_records"]) >= 3
    doc_types = [d["doc_type"] for d in docket["docket_records"]]
    assert any("Aadhaar Card" in t for t in doc_types)

def test_enterprise_payroll_service():
    overview = EnterprisePayrollService.get_payroll_overview()
    assert "total_gross_outlay" in overview
    assert "net_disbursement" in overview
    assert "statutory_breakdown" in overview
