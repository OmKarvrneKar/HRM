import pytest
from services.user_service import (
    UserService,
    amount_to_words,
    calculate_salary_components,
    get_default_banking_info
)
from permissions.rbac import Role, can_view_profile


def test_amount_to_words():
    """Verify Indian currency amount to words conversion."""
    assert amount_to_words(0) == "Rupees Zero Only"
    assert amount_to_words(88000) == "Rupees Eighty Eight Thousand Only"
    assert amount_to_words(103700) == "Rupees One Lakh Three Thousand Seven Hundred Only"
    assert amount_to_words(1250000) == "Rupees Twelve Lakh Fifty Thousand Only"
    assert amount_to_words(10000000) == "Rupees One Crore Only"


def test_calculate_salary_components():
    """Test standard salary breakdown from annual CTC."""
    ctc = 1200000
    comp = calculate_salary_components(ctc)

    assert comp["ctc_annual"] == 1200000
    assert comp["monthly_gross"] == 100000
    assert comp["basic_salary"] == 50000  # 50%
    assert comp["hra"] == 20000  # 40% of basic
    assert comp["conveyance_allowance"] == 5000
    assert comp["medical_allowance"] == 3000
    assert comp["special_allowance"] == 22000  # remainder
    assert comp["pf_deduction"] == 3600  # max cap
    assert comp["professional_tax"] == 200
    assert comp["total_deductions"] > 0
    assert comp["net_salary"] == comp["monthly_gross"] - comp["total_deductions"]


def test_get_salary_info_for_all_roles(seeded_users):
    """Test salary retrieval for employee, hr, and manager."""
    mgr = seeded_users["manager"]
    hr = seeded_users["hr"]
    emp = seeded_users["emp1"]

    sal_mgr = UserService.get_salary_info(mgr)
    assert sal_mgr["ctc_annual"] >= 2000000
    assert sal_mgr["monthly_gross"] > 0
    assert sal_mgr["net_salary"] > 0
    assert "HDFC" in sal_mgr["bank_name"]

    sal_hr = UserService.get_salary_info(hr)
    assert sal_hr["ctc_annual"] >= 1000000
    assert sal_hr["monthly_gross"] > 0
    assert "ICICI" in sal_hr["bank_name"]

    sal_emp = UserService.get_salary_info(emp)
    assert sal_emp["ctc_annual"] == 450000  # 4.5 Lac CTC
    assert sal_emp["monthly_gross"] > 0
    assert "State Bank" in sal_emp["bank_name"]


def test_get_salary_slips_historical(seeded_users):
    """Test generating 6 months of historical salary slips."""
    emp = seeded_users["emp1"]
    slips = UserService.get_salary_slips(emp, count=6)

    assert len(slips) == 6
    for s in slips:
        assert s["employee_id"] == emp["employee_id"]
        assert s["slip_id"].startswith("PAY-")
        assert s["payment_status"] == "Paid"
        assert s["gross_earnings"] > 0
        assert s["net_salary"] > 0
        assert "Rupees" in s["net_salary_words"]
        assert "earnings_breakdown" in s
        assert "deductions_breakdown" in s
        assert s["earnings_breakdown"]["basic_salary"] > 0
        assert s["deductions_breakdown"]["provident_fund"] > 0


def test_get_single_salary_slip_and_permissions(seeded_users):
    """Test single slip endpoint with authorization boundaries."""
    mgr = seeded_users["manager"]
    hr = seeded_users["hr"]
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    slips = UserService.get_salary_slips(emp1, count=1)
    target_ym = slips[0]["year_month"]

    # 1. Employee self viewing own slip
    slip_self, err = UserService.get_single_salary_slip(emp1, emp1["employee_id"], target_ym)
    assert err is None
    assert slip_self["year_month"] == target_ym

    # 2. HR viewing employee slip
    slip_hr, err_hr = UserService.get_single_salary_slip(hr, emp1["employee_id"], target_ym)
    assert err_hr is None
    assert slip_hr["employee_id"] == emp1["employee_id"]

    # 3. Manager attempting to view employee slip (forbidden: strict data separation)
    slip_mgr, err_mgr = UserService.get_single_salary_slip(mgr, emp1["employee_id"], target_ym)
    assert slip_mgr is None
    assert "Access Denied" in err_mgr

    # 4. Another regular employee attempting to view employee slip (forbidden)
    slip_emp2, err_emp2 = UserService.get_single_salary_slip(emp2, emp1["employee_id"], target_ym)
    assert slip_emp2 is None
    assert "Access Denied" in err_emp2


def test_skills_management(db, seeded_users):
    """Test adding, updating proficiency, and removing skills."""
    emp1 = seeded_users["emp1"]
    hr = seeded_users["hr"]

    # 1. Employee adds a new skill to their profile
    skills, err = UserService.add_user_skill(emp1, emp1["employee_id"], "Docker", "Expert")
    assert err is None
    docker_skill = next((s for s in skills if s["name"] == "Docker"), None)
    assert docker_skill is not None
    assert docker_skill["level"] == "Expert"

    # 2. Update existing skill level
    skills, err = UserService.add_user_skill(emp1, emp1["employee_id"], "Docker", "Advanced")
    assert err is None
    docker_skill = next((s for s in skills if s["name"] == "Docker"), None)
    assert docker_skill["level"] == "Advanced"

    # 3. HR adds a skill to employee profile
    skills, err = UserService.add_user_skill(hr, emp1["employee_id"], "Microservices", "Proficient")
    assert err is None
    assert any(s["name"] == "Microservices" for s in skills)

    # 4. Remove skill
    skills, err = UserService.remove_user_skill(emp1, emp1["employee_id"], "Docker")
    assert err is None
    assert not any(s["name"] == "Docker" for s in skills)


def test_update_salary_by_hr(db, seeded_users):
    """Test HR / HR Manager revising employee salary structure."""
    hr = seeded_users["hr"]
    emp1 = seeded_users["emp1"]

    new_salary, err = UserService.update_user_salary(
        actor=hr,
        target_employee_id=emp1["employee_id"],
        salary_data={"ctc_annual": 1800000, "bank_name": "HDFC Bank"},
        reason="Promoted to Lead Architect"
    )
    assert err is None
    assert new_salary["ctc_annual"] == 1800000
    assert new_salary["monthly_gross"] == 150000
    assert new_salary["bank_name"] == "HDFC Bank"

    # Verify persisted in database
    db_user = db.users.find_one({"employee_id": emp1["employee_id"]})
    assert db_user["salary_info"]["ctc_annual"] == 1800000
    assert db_user["salary_info"]["monthly_gross"] == 150000


def test_enrich_user_profile(seeded_users):
    """Test profile enrichment contains salary_info, salary_slips, and skills for all roles."""
    for role_key in ["emp1", "hr", "hr_manager"]:
        u = seeded_users[role_key]
        enriched = UserService.enrich_user_profile(u)
        assert "salary_info" in enriched
        assert enriched["salary_info"]["monthly_gross"] > 0
        assert "skills" in enriched
        assert len(enriched["skills"]) > 0
        assert "salary_slips" in enriched
        assert len(enriched["salary_slips"]) == 6
