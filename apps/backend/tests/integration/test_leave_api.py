def test_leave_and_permission_api_lifecycle(client, seeded_users, tokens):
    """Integration test: employee applies for leave and early exit, HR verifies, employee checks status."""
    emp_token = tokens["emp1"]
    hr_token = tokens["hr"]
    emp2_token = tokens["emp2"]

    h_emp = {"Authorization": f"Bearer {emp_token}"}
    h_hr = {"Authorization": f"Bearer {hr_token}"}
    h_emp2 = {"Authorization": f"Bearer {emp2_token}"}

    # 1. Emp1 applies for Leave
    res = client.post("/api/leaves/apply", json={
        "leave_type": "Sick Leave",
        "start_date": "2026-10-25",
        "end_date": "2026-10-26",
        "reason": "Viral fever and doctor advised rest."
    }, headers=h_emp)
    assert res.status_code == 201
    leave_id = res.get_json()["request"]["request_id"]

    # 2. Emp1 applies for Early Exit Permission
    res = client.post("/api/leaves/permission", json={
        "permission_date": "2026-10-22",
        "early_exit_time": "16:00",
        "reason": "Parent-teacher meeting at school."
    }, headers=h_emp)
    assert res.status_code == 201
    perm_id = res.get_json()["request"]["request_id"]

    # 3. Emp1 checks my-requests -> 2 pending
    res = client.get("/api/leaves/my-requests", headers=h_emp)
    assert res.status_code == 200
    my_data = res.get_json()
    assert my_data["summary"]["pending_count"] == 2
    assert my_data["summary"]["total_count"] == 2

    # 4. Emp2 checks my-requests -> must be 0 (cannot see Emp1's requests)
    res = client.get("/api/leaves/my-requests", headers=h_emp2)
    assert res.status_code == 200
    assert res.get_json()["summary"]["total_count"] == 0

    # 5. Non-HR attempts to view all requests -> 403 Forbidden
    res = client.get("/api/leaves/all", headers=h_emp)
    assert res.status_code == 403

    # 6. HR views all requests queue
    res = client.get("/api/leaves/all?status=Pending", headers=h_hr)
    assert res.status_code == 200
    hr_data = res.get_json()
    assert hr_data["summary"]["pending_count"] == 2

    # 7. Non-HR attempts to verify request -> 403 Forbidden
    res = client.post(f"/api/leaves/verify/{leave_id}", json={
        "decision": "Approved",
        "remarks": "Self-approved"
    }, headers=h_emp)
    assert res.status_code == 403

    # 8. HR verifies and approves Leave
    res = client.post(f"/api/leaves/verify/{leave_id}", json={
        "decision": "Approved",
        "remarks": "Get well soon. Approved."
    }, headers=h_hr)
    assert res.status_code == 200
    assert res.get_json()["request"]["status"] == "Approved"

    # 9. HR verifies and rejects Permission
    res = client.post(f"/api/leaves/verify/{perm_id}", json={
        "decision": "Rejected",
        "remarks": "Team demo scheduled at 16:30."
    }, headers=h_hr)
    assert res.status_code == 200
    assert res.get_json()["request"]["status"] == "Rejected"

    # 10. Emp1 checks my-requests -> 1 approved leave, 1 rejected permission, 0 pending
    res = client.get("/api/leaves/my-requests", headers=h_emp)
    assert res.status_code == 200
    updated_my_data = res.get_json()
    assert updated_my_data["summary"]["pending_count"] == 0
    assert updated_my_data["summary"]["approved_leaves_count"] == 1
