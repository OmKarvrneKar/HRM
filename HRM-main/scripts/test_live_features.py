import requests
import json

def test_live_hrms():
    s = requests.Session()
    base_url = "http://localhost:5000"

    print("--- 1. Testing Employee Login (Rahul Verma) ---")
    login_res = s.post(f"{base_url}/api/auth/login", json={
        "email": "emp.rahul@aisamrat.com",
        "password": "Emp@Rahul2026!"
    })
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    user_info = login_res.json().get("user", {})
    print(f"Logged in as: {user_info.get('full_name')} | Role: {user_info.get('role')}")
    assert user_info.get("role") == "employee"

    print("\n--- 2. Testing Monthly Birthday Announcements ---")
    b_res = s.get(f"{base_url}/api/birthdays/monthly")
    assert b_res.status_code == 200
    b_data = b_res.json()
    birthdays = b_data.get("birthdays", [])
    print(f"Total Birthdays this month: {len(birthdays)}")
    for b in birthdays:
        print(f"  * {b.get('full_name')} | Dept: {b.get('department')} | Birthday: {b.get('day')} {b.get('month_name')}")
        # Ensure privacy: NO birth year or full dob
        assert "dob" not in b and "date_of_birth" not in b and "birth_year" not in b, "Privacy leak in monthly birthdays!"

    print("\n--- 3. Testing RBAC: Employee Blocked from Other Salaries ---")
    # Rahul trying to view Amit's salary slip
    sal_res = s.get(f"{base_url}/api/salary/slips/HR-1002/2026-10")
    print(f"Rahul accessing Amit's salary -> Status: {sal_res.status_code}")
    assert sal_res.status_code in (403, 404), f"Security violation: {sal_res.status_code}"

    print("\n--- 4. Testing HR Login (Priya Sharma) & Project Access Boundary ---")
    s_hr = requests.Session()
    hr_login = s_hr.post(f"{base_url}/api/auth/login", json={
        "email": "hr.priya@aisamrat.com",
        "password": "Hr@Priya2026!"
    })
    assert hr_login.status_code == 200
    hr_user = hr_login.json().get("user", {})
    print(f"Logged in as: {hr_user.get('full_name')} | Role: {hr_user.get('role')}")
    assert hr_user.get("role") == "hr"

    # HR attempting to access projects
    proj_res = s_hr.get(f"{base_url}/api/projects")
    print(f"HR accessing /api/projects -> Status: {proj_res.status_code}")
    assert proj_res.status_code == 403, f"HR was not blocked from projects: {proj_res.status_code}"

    proj_page_res = s_hr.get(f"{base_url}/projects")
    print(f"HR accessing /projects page -> Status: {proj_page_res.status_code}")
    assert proj_page_res.status_code == 403, f"HR was not blocked from /projects: {proj_page_res.status_code}"

    print("\n--- 5. Testing Team Lead Login (Kavita Nair) & Salary Boundary ---")
    s_lead = requests.Session()
    lead_login = s_lead.post(f"{base_url}/api/auth/login", json={
        "email": "lead.kavita@aisamrat.com",
        "password": "Lead@Kavita2026!"
    })
    assert lead_login.status_code == 200
    lead_user = lead_login.json().get("user", {})
    print(f"Logged in as: {lead_user.get('full_name')} | Role: {lead_user.get('role')}")
    assert lead_user.get("role") == "team_lead"

    # Team Lead attempting to access salary page
    sal_page_res = s_lead.get(f"{base_url}/salary")
    print(f"Team Lead accessing /salary page -> Status: {sal_page_res.status_code}")
    assert sal_page_res.status_code == 403, f"Team Lead was not blocked from /salary: {sal_page_res.status_code}"

    # Team Lead attempting to access /api/complaints
    comp_res = s_lead.get(f"{base_url}/api/complaints")
    print(f"Team Lead accessing /api/complaints -> Status: {comp_res.status_code}")
    assert comp_res.status_code == 403, f"Team Lead was not blocked from /api/complaints: {comp_res.status_code}"

    print("\n--- 6. Testing Chat Unsend & Attachment Workflow ---")
    # Rahul sends a message in a conversation or directly
    convs_res = s.get(f"{base_url}/api/conversations")
    assert convs_res.status_code == 200
    convs = convs_res.json().get("conversations", [])
    if convs:
        test_conv = convs[0]
        cid = test_conv["conversation_id"]
        # Post message
        post_msg = s.post(f"{base_url}/api/conversations/{cid}/messages", json={
            "content": "Secret test message that will be unsent"
        })
        assert post_msg.status_code in (200, 201)
        msg_id = post_msg.json().get("message", {}).get("_id")
        print(f"Posted message ID: {msg_id}")

        # Unsend message
        unsend_res = s.post(f"{base_url}/api/conversations/{cid}/messages/{msg_id}/unsend")
        assert unsend_res.status_code == 200
        unsent_msg = unsend_res.json().get("message", {})
        print(f"Unsent message status: is_unsent={unsent_msg.get('is_unsent')} | content='{unsent_msg.get('content')}'")
        assert unsent_msg.get("content") == "This message was unsent"
        assert unsent_msg.get("is_unsent") is True

    print("\n--- 7. Testing External Notification Logs ---")
    ext_logs_res = s_hr.get(f"{base_url}/api/notifications/external-logs")
    print(f"HR fetching external notification logs -> Status: {ext_logs_res.status_code}")
    assert ext_logs_res.status_code == 200
    logs = ext_logs_res.json().get("logs", [])
    print(f"External notification logs count: {len(logs)}")

    print("\n============================================================")
    print("  ALL LIVE INTEGRATION & SECURITY TESTS PASSED PERFECTLY!")
    print("============================================================")

if __name__ == "__main__":
    test_live_hrms()
