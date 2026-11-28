import pytest
from app import app
from database.connection import get_db
from database.seeds import seed_real_and_dummy_users
from services.enterprise_hr_service import SeparationService, PerformanceLearningService


@pytest.fixture(scope="module")
def seeded_db():
    seed_real_and_dummy_users()
    return get_db()


@pytest.fixture(scope="module")
def client():
    return app.test_client()


def test_navigation_renames_and_routes(client, seeded_db):
    """Test renamed portal tabs: Tasks & Certificates, Kudos & Support, Exit & Tenure."""
    with client.session_transaction() as sess:
        sess['emp_id'] = 'EMP-1005'
        sess['employee_id'] = 'EMP-1005'
        sess['role'] = 'employee'
        sess['name'] = 'Sneha K'

    # 1. Tasks & Certificates
    res1 = client.get('/tasks-certificates')
    assert res1.status_code == 200
    html1 = res1.get_data(as_text=True)
    assert "Tasks &amp; Certificates" in html1
    assert "Mandatory Statutory Compliance Certifications" in html1

    # 2. Kudos & Support
    res2 = client.get('/kudos-support')
    assert res2.status_code == 200
    html2 = res2.get_data(as_text=True)
    assert "Kudos &amp; Support" in html2
    assert "Send Kudos Points" in html2

    # 3. Meeting Rooms & Facilities (with Travel & Expense Claims)
    res_fac = client.get('/facilities')
    assert res_fac.status_code == 200
    html_fac = res_fac.get_data(as_text=True)
    assert "Claim Travel Expense" in html_fac
    assert "Travel &amp; Expense Claims" in html_fac

    # 4. Exit & Tenure
    res3 = client.get('/exit-tenure')
    assert res3.status_code == 200
    html3 = res3.get_data(as_text=True)
    assert "Exit &amp; Tenure" in html3
    assert "4-Way Departmental Clearance" in html3


def test_policy_vault_modal_reader(client, seeded_db):
    """Test that policy vault has full document reading modal and acknowledgments."""
    with client.session_transaction() as sess:
        sess['emp_id'] = 'EMP-1005'
        sess['employee_id'] = 'EMP-1005'
        sess['role'] = 'employee'
        sess['name'] = 'Sneha K'

    res = client.get('/policies')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "viewPolicyDocModal" in html
    assert "Official Workforce Policy &amp; Statutory Directives" in html
    assert "readPolicyDoc(" in html
    assert "acknowledgePolicyDoc(" in html


def test_course_learning_and_certificate(client, seeded_db):
    """Test interactive course learning, assessment quiz, and certificate accessibility."""
    with client.session_transaction() as sess:
        sess['emp_id'] = 'EMP-1005'
        sess['employee_id'] = 'EMP-1005'
        sess['role'] = 'employee'
        sess['name'] = 'Sneha K'

    # Verify modal exists in template
    res = client.get('/tasks-certificates')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "courseLearningModal" in html
    assert "viewCertificateModal" in html
    assert "submitCourseAssessment" in html
    assert "certificate-sheet" in html
    assert "certificate-watermark" in html
    assert "certificate-signatures" in html
    assert "festivalCelebrationButton" in html
    assert "globalFestiveBanner" not in html

    # Test completing course via API
    res_comp = client.post(
        '/api/performance/courses/complete',
        json={'course_id': 'CRS-SEC-101', 'score': 98}
    )
    assert res_comp.status_code == 200
    data = res_comp.get_json()
    assert data.get('success') is True
    assert 'certificate' in data
    assert data['certificate']['certificate_id'].startswith('CERT-')
    assert data['certificate']['score'] == 98

    failed_score = client.post(
        '/api/performance/courses/complete',
        json={'course_id': 'CRS-SEC-101', 'score': 79}
    )
    assert failed_score.status_code == 400
    assert 'at least 80%' in failed_score.get_json()['error']


def test_travel_dates_auto_fetch_facilities(client, seeded_db):
    """Test travel date auto-fetching mechanism in Meeting Rooms / Facilities claims."""
    with client.session_transaction() as sess:
        sess['emp_id'] = 'EMP-1005'
        sess['employee_id'] = 'EMP-1005'
        sess['role'] = 'employee'
        sess['name'] = 'Sneha K'

    res = client.get('/facilities')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "linkedTravelRequest" in html
    assert "autoFetchLatestTravelDates" in html
    assert "autoFetchIndicator" in html


def test_profile_salary_and_generate_slip(client, seeded_db):
    """Test salary info and on-demand payslip generation in profile."""
    with client.session_transaction() as sess:
        sess['emp_id'] = 'EMP-1005'
        sess['employee_id'] = 'EMP-1005'
        sess['role'] = 'employee'
        sess['name'] = 'Sneha K'

    # 1. Fetch salary and pre-calculated slips
    res_sal = client.get('/api/users/EMP-1005/salary')
    assert res_sal.status_code == 200
    sal_data = res_sal.get_json()
    assert sal_data.get('success') is True
    assert 'salary' in sal_data
    assert 'slips' in sal_data
    assert len(sal_data['slips']) > 0

    # 2. Generate on-demand slip
    res_gen = client.post('/api/users/EMP-1005/salary/generate-slip', json={'year_month': '2026-11'})
    assert res_gen.status_code == 200
    gen_data = res_gen.get_json()
    assert gen_data.get('success') is True
    assert gen_data['slip']['year_month'] == '2026-11'
    assert gen_data['slip']['net_salary'] > 0

    # 3. View profile page template has salary slip table & generator
    res_prof = client.get('/profile/EMP-1005')
    assert res_prof.status_code == 200
    html_prof = res_prof.get_data(as_text=True)
    assert "tiimiSalarySlipsBody" in html_prof
    assert "genSlipPickerMonth" in html_prof
    assert "generateProfilePayslip" in html_prof


def test_resignation_and_four_way_clearance(client, seeded_db):
    """Test formal resignation workflow and 4-way clearance (Manager + IT + Finance + HR)."""
    # Clear any previous test resignation for EMP-1005
    seeded_db.resignations.delete_many({'employee_id': 'EMP-1005'})

    with client.session_transaction() as sess:
        sess['emp_id'] = 'EMP-1005'
        sess['employee_id'] = 'EMP-1005'
        sess['role'] = 'employee'
        sess['name'] = 'Sneha K'
        sess['department'] = 'Engineering'

    # 1. Initiate formal resignation with frontend payload structure
    res_sub = client.post(
        '/api/separation/resign',
        json={
            'reason': 'Better Career Opportunity',
            'proposed_lwd': '2026-12-31',
            'handover_notes': 'Transferred sprint deliverables, PR access, and API keys to team lead.'
        }
    )
    assert res_sub.status_code == 201
    sub_data = res_sub.get_json()
    assert sub_data.get('success') is True
    res_id = sub_data['resignation']['resignation_id']
    assert res_id.startswith('RES-')

    # 2. Stage 1 Clearance: Manager / TL Sign-off
    with client.session_transaction() as sess:
        sess['emp_id'] = 'TL-1001'
        sess['employee_id'] = 'TL-1001'
        sess['role'] = 'tl'
        sess['name'] = 'Dummy Team Lead'

    res_mgr = client.post(
        '/api/separation/clearance/approve',
        json={'resignation_id': res_id, 'stage': 'manager', 'remarks': 'Code reviews & PR ownership transitioned.'}
    )
    assert res_mgr.status_code == 200
    mgr_data = res_mgr.get_json()
    assert mgr_data['resignation']['manager_approval'] is True

    # 3. Stage 2 Clearance: IT Infrastructure
    with client.session_transaction() as sess:
        sess['emp_id'] = 'HR-1001'
        sess['employee_id'] = 'HR-1001'
        sess['role'] = 'hr'
        sess['name'] = 'HR Admin'

    res_it = client.post(
        '/api/separation/clearance/approve',
        json={'resignation_id': res_id, 'stage': 'it', 'remarks': 'MacBook Pro & VPN tokens returned in working order.'}
    )
    assert res_it.status_code == 200
    it_data = res_it.get_json()
    assert it_data['resignation']['it_clearance'] is True

    # 4. Stage 3 Clearance: Finance & Accounts
    res_fin = client.post(
        '/api/separation/clearance/approve',
        json={'resignation_id': res_id, 'stage': 'finance', 'remarks': 'All travel expense claims settled.'}
    )
    assert res_fin.status_code == 200
    fin_data = res_fin.get_json()
    assert fin_data['resignation']['finance_clearance'] is True

    # 5. Stage 4 Clearance: HR Exit Interview
    res_hr = client.post(
        '/api/separation/clearance/approve',
        json={'resignation_id': res_id, 'stage': 'hr', 'remarks': 'Exit questionnaire recorded and relieving docket generated.'}
    )
    assert res_hr.status_code == 200
    hr_data = res_hr.get_json()
    assert hr_data['resignation']['hr_clearance'] is True
    assert hr_data['resignation']['status'] == 'Cleared & Ready for FnF'


def test_taskbox_and_shortcut_tooltips(client, seeded_db):
    """Test taskbox deliverable creation, status changes, and verify clean shortcut tooltips."""
    with client.session_transaction() as sess:
        sess['emp_id'] = 'EMP-1005'
        sess['employee_id'] = 'EMP-1005'
        sess['role'] = 'employee'
        sess['name'] = 'Sneha K'

    # 1. Verify tasks rendered on /tasks-certificates
    res = client.get('/tasks-certificates')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'Taskbox &amp; Sprint Deliverables' in html
    assert 'shortcutFlyoutCard' not in html

    # 2. Create task
    t_res = client.post(
        '/api/performance/tasks/create',
        json={
            'title': 'Automated Sprint Task Test',
            'project': 'HRMS Platform',
            'priority': 'High',
            'due_date': '2026-11-30',
            'description': 'Integration verification of sprint tasks.'
        }
    )
    assert t_res.status_code == 201
    task_id = t_res.get_json()['task']['task_id']

    # 3. Update task status
    s_res = client.post(
        f'/api/performance/tasks/{task_id}/status',
        json={'status': 'Completed'}
    )
    assert s_res.status_code == 200
    assert s_res.get_json()['task']['status'] == 'Completed'
