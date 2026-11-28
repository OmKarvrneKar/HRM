"""
Unit test for Database Cleanup & Real Employee Seeding Script
AISAMRAT HRMS — Enterprise Workforce Synchronization
"""

import pytest
from database.connection import get_db
from permissions.rbac import Role
from scripts.migrations.purge_dummy_and_seed_real_team import purge_dummy_users_and_seed_real_team


def test_purge_dummy_and_seed_real_team_execution():
    """Verify that purge_dummy_users_and_seed_real_team seeds exactly 38 users and 34 employees."""
    res = purge_dummy_users_and_seed_real_team()
    assert res is True

    db = get_db()
    users = list(db.users.find({}))
    assert len(users) == 38, f"Expected exactly 38 users, got {len(users)}"

    # Verify Core Hierarchy Roles
    ramya = db.users.find_one({"employee_id": "HR-1001"})
    assert ramya is not None
    assert ramya["full_name"] == "Ramya"
    assert ramya["email"] == "ramya.hr@aisamrat.com"
    assert ramya["role"] == Role.HR
    assert ramya.get("is_admin") is True

    mgr = db.users.find_one({"employee_id": "MGR-1001"})
    assert mgr is not None
    assert mgr["full_name"] == "Vikramaditya Roy"
    assert mgr["email"] == "manager@aisamrat.com"
    assert mgr["role"] == Role.MANAGER

    tl = db.users.find_one({"employee_id": "LEAD-1001"})
    assert tl is not None
    assert tl["full_name"] == "Kavita Nair"
    assert tl["email"] == "lead.kavita@aisamrat.com"
    assert tl["role"] == Role.TEAM_LEAD
    assert tl["reporting_manager_id"] == "MGR-1001"

    adm = db.users.find_one({"employee_id": "ADM-1001"})
    assert adm is not None
    assert adm["role"] == Role.ADMIN

    # Verify exactly 34 real employees
    employees = list(db.users.find({"role": Role.EMPLOYEE}))
    assert len(employees) == 34, f"Expected 34 real employees, got {len(employees)}"

    # Verify no dummy accounts exist
    dummy_ids = ["EMP-1001", "EMP-1002", "EMP-1003", "EMP-1004", "HR-1000", "HR-1002", "ORG-1001", "TRN-1001"]
    for d_id in dummy_ids:
        assert db.users.find_one({"employee_id": d_id}) is None, f"Dummy account {d_id} should be purged"

    # Verify team TEAM-AIML-01
    team = db.teams.find_one({"team_id": "TEAM-AIML-01"})
    assert team is not None
    assert team["lead_id"] == "LEAD-1001"
    assert team["manager_id"] == "MGR-1001"
    assert len(team.get("members", [])) == 34

    # Verify all 12 leave balances exist for employees
    sample_emp = db.users.find_one({"employee_id": "EMP-1005"})
    assert sample_emp is not None
    bal = db.leave_balances.find_one({"employee_id": "EMP-1005"})
    assert bal is not None
    balances = bal.get("balances", {})
    assert len(balances) == 12
    assert "Casual Leave" in balances
    assert "Work from Anywhere (WFA) & Flexible Leave" in balances
    assert "Mental Health Leave" in balances
    assert "Wellness Days" in balances
    assert "Pet Care Leave" in balances
    assert "Neutral Gender Leave" in balances

