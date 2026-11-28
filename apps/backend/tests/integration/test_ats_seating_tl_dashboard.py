import io
import pytest
from app import app
from database.connection import get_db
from database.seeds import seed_real_and_dummy_users
from services.enterprise_hr_service import SeatingLockerService, RecruitmentTalentService


@pytest.fixture(scope="module")
def seeded_db():
    seed_real_and_dummy_users()
    return get_db()


@pytest.fixture(scope="module")
def client():
    return app.test_client()


def test_database_seeding(seeded_db):
    assert seeded_db.users.count_documents({}) >= 100
    assert seeded_db.projects.count_documents({}) >= 3
    assert seeded_db.leave_requests.count_documents({}) >= 2
    assert seeded_db.seating_allocations.count_documents({}) >= 100


def test_tl_dashboard_and_tabs(client, seeded_db):
    with client.session_transaction() as sess:
        sess['user_id'] = '6af2bdfcf4b132def8dd8492'
        sess['emp_id'] = 'TL-1001'
        sess['employee_id'] = 'TL-1001'
        sess['role'] = 'tl'
        sess['name'] = 'Dummy Team Lead'

    res_tl = client.get('/dashboard/team-lead')
    assert res_tl.status_code == 200
    html_tl = res_tl.get_data(as_text=True)
    assert "Team Operations &amp; Verification Hub" in html_tl
    assert "Assigned Team Members" in html_tl

    res_att = client.get('/attendance')
    assert res_att.status_code == 200
    assert "Team Attendance" in res_att.get_data(as_text=True)

    res_prof = client.get('/profiles')
    assert res_prof.status_code == 200

    res_leaves = client.get('/api/leaves/all?status=Pending')
    assert res_leaves.status_code == 200
    assert len(res_leaves.get_json().get('requests', [])) >= 1

    res_att_ov = client.get('/api/attendance/team-overview')
    assert res_att_ov.status_code == 200
    assert len(res_att_ov.get_json().get('members', [])) >= 1


def test_ats_resume_import(client):
    with client.session_transaction() as sess:
        sess['user_id'] = '6af2bdfcf4b132def8dd8492'
        sess['emp_id'] = 'TL-1001'
        sess['employee_id'] = 'TL-1001'
        sess['role'] = 'tl'
        sess['name'] = 'Dummy Team Lead'

    sample_resume = """
    ADITYA VARMA
    Senior Backend Architect & Cloud Systems Engineer
    Experience: 7.5 years of experience in distributed systems
    Skills: Python, Flask, MongoDB, PostgreSQL, REST APIs, Docker, Git, Microservices, Redis, Kubernetes, AWS.
    """
    upload_data = {
        'resume_file': (io.BytesIO(sample_resume.encode('utf-8')), 'aditya_varma_cv.txt'),
        'target_role': 'Senior Backend Architect'
    }
    res_ats = client.post('/api/recruitment/ats/upload-scan', data=upload_data, content_type='multipart/form-data')
    assert res_ats.status_code == 200
    ats_json = res_ats.get_json()
    assert ats_json.get('success') is True
    assert ats_json.get('match_score') >= 70
    assert len(ats_json.get('matched_skills', [])) >= 5


def test_seating_and_locker_allocations(client, seeded_db):
    with client.session_transaction() as sess:
        sess['user_id'] = '6af2bdfcf4b132def8dd8492'
        sess['emp_id'] = 'TL-1001'
        sess['employee_id'] = 'TL-1001'
        sess['role'] = 'tl'
        sess['name'] = 'Dummy Team Lead'

    res_assets = client.get('/assets')
    assert res_assets.status_code == 200
    html_assets = res_assets.get_data(as_text=True)
    assert "My Workplace Allocation" in html_assets
    assert "Allocate Seat &amp; Locker" in html_assets
    assert "Global Enterprise Inventory" not in html_assets

    res_seat_api = client.get('/api/assets/seating-lockers')
    assert res_seat_api.status_code == 200
    seat_json = res_seat_api.get_json()
    assert seat_json.get('all_allocations') == []
    assert seat_json.get('total_allocated') == 0

    alloc_payload = {
        "employee_id": "TL-1001",
        "employee_name": "Dummy Team Lead",
        "department": "Engineering",
        "floor": "Floor 3 — AI & Engineering Hub",
        "bay": "Bay A (Frontend Web Experience)",
        "desk_number": "FL3-A-01",
        "locker_number": "LCK-301",
        "locker_location": "3rd Floor West Locker Bay",
        "key_type": "RFID Smart Passcode Card",
        "amenities": "Dual 4K Monitor Mount, Standing Desk, Ergonomic Mesh Chair, Gigabit LAN"
    }
    res_alloc = client.post('/api/assets/seating-lockers/allocate', json=alloc_payload)
    assert res_alloc.status_code == 200
    assert res_alloc.get_json().get('success') is True


def test_all_five_user_dashboards(client):
    dashboards = [
        ('employee', 'EMP-1005', 'Sneha K', '/dashboard/employee'),
        ('tl', 'TL-1001', 'Dummy Team Lead', '/dashboard/team-lead'),
        ('manager', 'MGR-1001', 'Arjun Sethi', '/dashboard/manager'),
        ('hr', 'HR-1001', 'Pooja Hegde', '/dashboard/hr'),
        ('admin', 'ADMIN-1001', 'Vikramaditya Roy', '/dashboard/admin')
    ]
    for role, emp_id, name, path in dashboards:
        with client.session_transaction() as sess:
            sess['user_id'] = f'mock-{emp_id}'
            sess['emp_id'] = emp_id
            sess['employee_id'] = emp_id
            sess['role'] = role
            sess['name'] = name
        r = client.get(path)
        assert r.status_code == 200, f"Dashboard {path} for role {role} returned {r.status_code}"
