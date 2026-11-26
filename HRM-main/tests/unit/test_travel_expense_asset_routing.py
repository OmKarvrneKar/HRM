from backend.database.seeds import seed_real_and_dummy_users


def use_session(client, employee_id, role):
    with client.session_transaction() as session:
        session["user_id"] = employee_id
        session["emp_id"] = employee_id
        session["employee_id"] = employee_id
        session["role"] = role
        session["name"] = employee_id


def setup_roster(db):
    for collection in (
        "travel_requests",
        "expense_claims",
        "asset_requests",
        "leave_requests",
        "attendance_corrections",
        "notifications"
    ):
        db[collection].delete_many({})
    seed_real_and_dummy_users(db)
    return (
        db.users.find_one({"employee_id": "AS-1001"}),
        db.users.find_one({"employee_id": "MGR-1001"}),
        db.users.find_one({"employee_id": "HR-1001"})
    )


def test_travel_routes_to_assigned_manager_then_hr_for_logistics(db, client):
    employee, manager, hr = setup_roster(db)
    use_session(client, employee["employee_id"], "employee")

    response = client.post("/api/travel/requests", json={
        "destination": "Pune",
        "trip_purpose": "Customer workshop",
        "start_date": "2026-12-01",
        "end_date": "2026-12-02",
        "estimated_cost": 12000
    })
    assert response.status_code == 201
    request_id = response.get_json()["request"]["request_id"]
    stored = db.travel_requests.find_one({"request_id": request_id})
    assert stored["assigned_manager_id"] == manager["employee_id"]
    assert stored["status"] == "PENDING_MANAGER"
    page = client.get("/facilities?tab=travel")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Pending Manager Approval" in html
    assert "bootstrap.Tab.getOrCreateInstance(requestedTabButton).show()" in html

    use_session(client, "MGR-OTHER", "manager")
    denied = client.post(
        f"/api/travel/requests/{request_id}/review",
        json={"decision": "Approved"}
    )
    assert denied.status_code == 400

    use_session(client, manager["employee_id"], "manager")
    pending = client.get("/api/travel/requests").get_json()["requests"]
    assert any(item["request_id"] == request_id for item in pending)
    approved = client.post(
        f"/api/travel/requests/{request_id}/review",
        json={"decision": "Endorsed"}
    )
    assert approved.status_code == 200
    assert approved.get_json()["request"]["status"] == "APPROVED"

    use_session(client, hr["employee_id"], "hr")
    allocated = client.post(
        f"/api/travel/requests/{request_id}/allocate",
        json={"pnr_or_ticket": "PNR-123"}
    )
    assert allocated.status_code == 200
    assert allocated.get_json()["request"]["status"] == "ALLOCATED"


def test_expense_claim_lands_in_assigned_manager_queue(db, client):
    employee, manager, _ = setup_roster(db)
    use_session(client, employee["employee_id"], "employee")

    response = client.post("/api/expenses/claims/submit", json={
        "trip_purpose": "Customer workshop",
        "travel_dates": "2026-12-01 to 2026-12-02",
        "items": [{"category": "Travel", "amount": 800, "description": "Taxi"}]
    })
    assert response.status_code == 201
    claim_id = response.get_json()["claim"]["claim_id"]
    assert db.expense_claims.find_one({"claim_id": claim_id})["assigned_manager_id"] == manager["employee_id"]

    use_session(client, manager["employee_id"], "manager")
    pending = client.get("/api/expenses/claims/pending").get_json()["claims"]
    assert any(claim["claim_id"] == claim_id for claim in pending)
    reviewed = client.post(
        f"/api/expenses/claims/{claim_id}/review",
        json={"decision": "Approved"}
    )
    assert reviewed.status_code == 200
    assert reviewed.get_json()["claim"]["status"] == "Approved"

    use_session(client, "MGR-OTHER", "manager")
    denied = client.post(
        f"/api/expenses/claims/{claim_id}/review",
        json={"decision": "Approved"}
    )
    assert denied.status_code == 403

    use_session(client, manager["employee_id"], "manager")
    reviewed = client.post(
        f"/api/expenses/claims/{claim_id}/review",
        json={"decision": "Approved"}
    )
    assert reviewed.status_code == 409


def test_asset_request_lands_in_assigned_manager_queue(db, client):
    employee, manager, _ = setup_roster(db)
    use_session(client, employee["employee_id"], "employee")

    response = client.post("/api/assets/request", json={
        "category": "Hardware",
        "item_name": "Monitor",
        "justification": "Needed for development work",
        "urgency": "Medium"
    })
    assert response.status_code == 201
    request_id = response.get_json()["request"]["request_id"]
    assert db.asset_requests.find_one({"request_id": request_id})["assigned_manager_id"] == manager["employee_id"]

    use_session(client, manager["employee_id"], "manager")
    pending = client.get("/api/assets/requests/pending").get_json()["requests"]
    assert any(item["request_id"] == request_id for item in pending)
    reviewed = client.post(
        f"/api/assets/requests/{request_id}/review",
        json={"decision": "Approved"}
    )
    assert reviewed.status_code == 200
    assert reviewed.get_json()["request"]["status"] == "Approved"

    use_session(client, "MGR-OTHER", "manager")
    denied = client.post(
        f"/api/assets/requests/{request_id}/review",
        json={"decision": "Approved"}
    )
    assert denied.status_code == 400


def test_invalid_claim_and_travel_amounts_return_validation_errors(db, client):
    employee, _, _ = setup_roster(db)
    use_session(client, employee["employee_id"], "employee")

    expense = client.post("/api/expenses/claims/submit", json={
        "trip_purpose": "Customer workshop",
        "items": [{"category": "Travel", "amount": "not a number"}]
    })
    assert expense.status_code == 400
    assert db.expense_claims.count_documents({}) == 0

    travel = client.post("/api/travel/requests", json={
        "destination": "Pune",
        "trip_purpose": "Customer workshop",
        "start_date": "2026-12-01",
        "end_date": "2026-12-02",
        "estimated_cost": "invalid"
    })
    assert travel.status_code == 400
    assert db.travel_requests.count_documents({}) == 0

def test_app_startup_seeding_preserves_real_users(db):
    db.users.insert_one({
        "employee_id": "REAL-KEEP",
        "emp_id": "REAL-KEEP",
        "email": "real.user@company.test",
        "role": "employee",
        "full_name": "Real User"
    })

    setup_roster(db)

    preserved = db.users.find_one({"employee_id": "REAL-KEEP"})
    assert preserved is not None
    assert preserved["full_name"] == "Real User"
    assert preserved["assigned_tl_id"] == "TL-1001"
    assert preserved["manager_id"] == "MGR-1001"
    assert preserved["reporting_manager_id"] == "MGR-1001"


def test_startup_seeding_reassigns_existing_pending_requests(db):
    employee, _, _ = setup_roster(db)
    employee_id = employee["employee_id"]
    db.leave_requests.insert_one({
        "request_id": "LR-OLD",
        "employee_id": employee_id,
        "status": "PENDING_TEAM_LEAD",
        "assigned_tl_id": "TL-1002",
        "assigned_manager_id": "MGR-1002"
    })
    db.attendance_corrections.insert_one({
        "request_id": "AC-OLD",
        "employee_id": employee_id,
        "status": "PENDING_MANAGER",
        "assigned_tl_id": "TL-1002",
        "assigned_manager_id": "MGR-1002"
    })
    db.travel_requests.insert_one({
        "request_id": "TRV-OLD",
        "employee_id": employee_id,
        "status": "PENDING_MANAGER",
        "assigned_manager_id": "MGR-1002"
    })
    db.expense_claims.insert_one({
        "claim_id": "EXP-OLD",
        "employee_id": employee_id,
        "status": "Submitted",
        "assigned_manager_id": "MGR-1002"
    })
    db.asset_requests.insert_one({
        "request_id": "AST-OLD",
        "employee_id": employee_id,
        "status": "Pending Review",
        "assigned_manager_id": "MGR-1002"
    })

    seed_real_and_dummy_users(db)

    for collection, request_key, request_id in (
        ("leave_requests", "request_id", "LR-OLD"),
        ("attendance_corrections", "request_id", "AC-OLD"),
        ("travel_requests", "request_id", "TRV-OLD"),
        ("expense_claims", "claim_id", "EXP-OLD"),
        ("asset_requests", "request_id", "AST-OLD")
    ):
        request = db[collection].find_one({request_key: request_id})
        assert request["assigned_manager_id"] == "MGR-1001"

    assert db.leave_requests.find_one({"request_id": "LR-OLD"})["assigned_tl_id"] == "TL-1001"
    assert db.attendance_corrections.find_one({"request_id": "AC-OLD"})["assigned_tl_id"] == "TL-1001"
