import pytest
from backend.permissions.rbac import Role
from backend.services.skill_service import SkillService


def test_role_based_login_matching_and_mismatch(client, seeded_users):
    """Test that login validates selected role against actual user role."""
    # 1. Matching role: Employee logs in as 'employee' -> 200 OK
    res1 = client.post("/api/auth/login", json={
        "email": "emp1.test@hrm.local",
        "password": "Emp1@Pass123",
        "role": "employee"
    })
    assert res1.status_code == 200
    data1 = res1.get_json()
    assert data1["success"] is True
    assert data1["redirect_url"] == "/dashboard/employee"

    # 2. Selected role does not escalate permissions: Employee logs in with role='hr' -> 200 OK but strictly routed to Employee dashboard
    res2 = client.post("/api/auth/login", json={
        "email": "emp1.test@hrm.local",
        "password": "Emp1@Pass123",
        "role": "hr"
    })
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2["success"] is True
    assert data2["redirect_url"] == "/dashboard/employee"
    assert data2["user"]["role"] == Role.EMPLOYEE

    # 4. Trainer account (migrated to TEAM_LEAD) logs in through Employee selector -> 200 OK
    res4 = client.post("/api/auth/login", json={
        "email": "trainer.test@hrm.local",
        "password": "Trainer@123",
        "role": "employee"
    })
    assert res4.status_code == 200
    data4 = res4.get_json()
    assert data4["redirect_url"] == "/dashboard/team-lead"

    # 5. Team Lead logs in through Employee selector -> 200 OK
    res5 = client.post("/api/auth/login", json={
        "email": "lead.test@hrm.local",
        "password": "Lead@123",
        "role": "employee"
    })
    assert res5.status_code == 200
    data5 = res5.get_json()
    assert data5["redirect_url"] == "/dashboard/team-lead"

    # 6. Deprecated role 'trainer' selector is rejected -> 403 Forbidden
    res6 = client.post("/api/auth/login", json={
        "email": "lead.test@hrm.local",
        "password": "Lead@123",
        "role": "trainer"
    })
    assert res6.status_code == 403

    # 7. Unified Employee Selector: Team Lead logs in through visible 'employee' option -> routes to /dashboard/team-lead
    res7 = client.post("/api/auth/login", json={
        "email": "lead.test@hrm.local",
        "password": "Lead@123",
        "role": "employee"
    })
    assert res7.status_code == 200
    data7 = res7.get_json()
    assert data7["redirect_url"] == "/dashboard/team-lead"

    # 8. Unified Employee Selector: Trainer (migrated to Team Lead) logs in -> routes to /dashboard/team-lead
    res8 = client.post("/api/auth/login", json={
        "email": "trainer.test@hrm.local",
        "password": "Trainer@123",
        "role": "employee"
    })
    assert res8.status_code == 200
    data8 = res8.get_json()
    assert data8["redirect_url"] == "/dashboard/team-lead"

    # 9. Manager logs in through 'employee' tab -> routes to /dashboard/manager
    res9 = client.post("/api/auth/login", json={
        "email": "manager.test@hrm.local",
        "password": "Manager@123",
        "role": "employee"
    })
    assert res9.status_code == 200
    data9 = res9.get_json()
    assert data9["redirect_url"] == "/dashboard/manager"

    # 9b. Manager attempting 'hr' tab -> Authenticated & routed to /dashboard/manager based on DB role
    res9b = client.post("/api/auth/login", json={
        "email": "manager.test@hrm.local",
        "password": "Manager@123",
        "role": "hr"
    })
    assert res9b.status_code == 200
    assert res9b.get_json()["redirect_url"] == "/dashboard/manager"

    # 10. HR attempting to select 'employee' -> Authenticated & routed to /dashboard/hr based on DB role
    res10 = client.post("/api/auth/login", json={
        "email": "hr.test@hrm.local",
        "password": "Hr@Pass123",
        "role": "employee"
    })
    assert res10.status_code == 200
    assert res10.get_json()["redirect_url"] == "/dashboard/hr"


def test_skill_matrix_crud_for_employee(client, tokens, seeded_users):
    """Test employee adding, updating, and deleting own skills."""
    emp_token = tokens["emp1"]
    headers = {"Authorization": f"Bearer {emp_token}"}
    emp_id = seeded_users["emp1"]["employee_id"]

    # 1. Add skill
    payload = {
        "employee_id": emp_id,
        "skill_name": "FastAPI & Microservices",
        "category": "Web Development",
        "proficiency_level": "Advanced",
        "years_of_experience": 3.5,
        "learning_status": "Practicing",
        "experience_summary": "Built high-throughput payment webhook APIs.",
        "certification_name": ""
    }
    res_add = client.post("/api/skills", json=payload, headers=headers)
    assert res_add.status_code == 201
    skill_data = res_add.get_json()["skill"]
    skill_id = skill_data["skill_id"]
    assert skill_data["skill_name"] == "FastAPI & Microservices"
    assert skill_data["proficiency_score"] == 4

    # 2. Get user skills
    res_get = client.get(f"/api/skills/user/{emp_id}", headers=headers)
    assert res_get.status_code == 200
    skills = res_get.get_json()["skills"]
    assert any(s["skill_id"] == skill_id for s in skills)

    # 3. Update skill
    update_payload = {
        "proficiency_level": "Expert",
        "experience_summary": "Promoted to lead API developer."
    }
    res_up = client.put(f"/api/skills/{skill_id}", json=update_payload, headers=headers)
    assert res_up.status_code == 200
    assert res_up.get_json()["skill"]["proficiency_level"] == "Expert"
    assert res_up.get_json()["skill"]["proficiency_score"] == 5

    # 4. IDOR check: Employee cannot delete or modify another employee's skill
    emp2_token = tokens["emp2"]
    res_idor = client.delete(f"/api/skills/{skill_id}", headers={"Authorization": f"Bearer {emp2_token}"})
    assert res_idor.status_code == 400 or res_idor.status_code == 403

    # 5. Owner deletes skill
    res_del = client.delete(f"/api/skills/{skill_id}", headers=headers)
    assert res_del.status_code == 200


def test_trainer_skill_assessment_and_feedback(client, tokens, seeded_users):
    """Test Trainer evaluating trainee skills with ratings and feedback."""
    emp_token = tokens["emp1"]
    trainer_token = tokens["trainer"]
    emp_id = seeded_users["emp1"]["employee_id"]

    # 1. Employee records a skill
    client.post("/api/skills", json={
        "employee_id": emp_id,
        "skill_name": "Docker Container Security",
        "category": "Cloud & DevOps",
        "proficiency_level": "Intermediate",
        "years_of_experience": 2.0
    }, headers={"Authorization": f"Bearer {emp_token}"})

    skills_res = client.get(f"/api/skills/user/{emp_id}", headers={"Authorization": f"Bearer {emp_token}"})
    skill = [s for s in skills_res.get_json()["skills"] if s["skill_name"] == "Docker Container Security"][0]
    skill_id = skill["skill_id"]

    # 2. Employee cannot assess own or others' skills
    res_emp_assess = client.post(f"/api/skills/{skill_id}/assess", json={"trainer_rating": 5}, headers={"Authorization": f"Bearer {emp_token}"})
    assert res_emp_assess.status_code == 403

    # 3. Trainer assesses the skill
    assess_payload = {
        "trainer_rating": 4,
        "verified_status": "Verified",
        "proficiency_level": "Advanced",
        "trainer_feedback": "Demonstrated sound container scanning and minimal image construction."
    }
    res_assess = client.post(f"/api/skills/{skill_id}/assess", json=assess_payload, headers={"Authorization": f"Bearer {trainer_token}"})
    assert res_assess.status_code == 200
    assessed = res_assess.get_json()["skill"]
    assert assessed["verified_status"] == "Verified"
    assert assessed["trainer_rating"] == 4
    assert assessed["assessor_role"] == "trainer"


def test_team_lead_matrix_and_training_recommendation(client, tokens, seeded_users, db):
    """Test Team Lead reviewing team skill coverage, gaps, and issuing training recommendations."""
    lead_token = tokens["team_lead"]
    lead_headers = {"Authorization": f"Bearer {lead_token}"}
    emp_id = seeded_users["emp1"]["employee_id"]

    # Assign emp1 to team lead's team
    db.users.update_one({"employee_id": emp_id}, {"$set": {"team_id": "TEAM-TEST-ENG"}})

    # Add Python skill for emp1
    SkillService.add_skill(seeded_users["emp1"], {
        "employee_id": emp_id,
        "skill_name": "Python",
        "category": "Programming",
        "proficiency_level": "Advanced"
    })

    # Team Lead fetches team matrix
    res_matrix = client.get("/api/skills/team/TEAM-TEST-ENG", headers=lead_headers)
    assert res_matrix.status_code == 200
    data = res_matrix.get_json()
    assert data["team_id"] == "TEAM-TEST-ENG"
    assert "Programming" in data["category_coverage"]
    assert len(data["skill_gaps"]) > 0  # Missing AI/ML, Tools, etc.

    # Team Lead recommends training
    rec_payload = {
        "employee_id": emp_id,
        "target_skill": "Kubernetes Orchestration",
        "category": "Cloud & DevOps",
        "priority": "High",
        "reason_or_gap": "Cloud migration requirement.",
        "action_plan": "Complete 20-hour CKA container lab."
    }
    res_rec = client.post("/api/skills/recommend-training", json=rec_payload, headers=lead_headers)
    assert res_rec.status_code == 201
    assert res_rec.get_json()["recommendation"]["target_skill"] == "Kubernetes Orchestration"
