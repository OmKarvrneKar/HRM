import pytest
from datetime import datetime, timezone, timedelta
from bson import ObjectId

from auth.security import hash_password, verify_password
from permissions.rbac import Role
from services.otp_service import OtpService, OtpPurpose, OTP_EXPIRY_MINUTES, MAX_VERIFICATION_ATTEMPTS
from services.external_notification_service import ExternalNotificationService
from database.connection import DatabaseManager


def test_otp_generation_and_five_minute_expiry(db):
    """Verify OTP generation, secure hashing, and strict 5-minute expiry."""
    assert OTP_EXPIRY_MINUTES == 5, "OTP expiry must be strictly 5 minutes"

    test_email = "test.employee.otp@aisamrat.com"
    success, msg = OtpService.generate_otp(
        email=test_email,
        purpose=OtpPurpose.ACTIVATION,
        employee_id="EMP-TEST-OTP1"
    )
    assert success is True
    assert "Valid for 5 minutes" in msg

    # Plain OTP must NOT be stored in DB
    token_doc = db.otp_tokens.find_one({"email": test_email, "purpose": OtpPurpose.ACTIVATION, "is_used": False})
    assert token_doc is not None
    assert "otp_hash" in token_doc
    assert "otp" not in token_doc
    assert token_doc["attempts"] == 0

    # Verify expiry is set to 5 minutes from creation
    created_at = token_doc["created_at"]
    expires_at = token_doc["expires_at"]
    diff_minutes = (expires_at - created_at).total_seconds() / 60.0
    assert abs(diff_minutes - 5.0) < 0.1, f"Expected 5.0 minute expiry, got {diff_minutes}"


def test_correct_otp_accepted_and_incorrect_otp_rejected(db):
    """Verify correct OTP verification and attempt tracking for incorrect OTPs."""
    test_email = "test.verify.otp@aisamrat.com"
    OtpService.generate_otp(email=test_email, purpose=OtpPurpose.PASSWORD_RESET)

    plain_otp = OtpService.get_latest_otp_for_test(test_email, OtpPurpose.PASSWORD_RESET)
    assert plain_otp is not None
    assert len(plain_otp) == 6

    # 1. Incorrect OTP is rejected with remaining attempts count
    bad_ok, bad_msg, _ = OtpService.verify_otp(test_email, "000000", OtpPurpose.PASSWORD_RESET)
    assert bad_ok is False
    assert "Incorrect verification code" in bad_msg
    assert "4 attempt(s) remaining" in bad_msg

    # 2. Correct OTP is accepted
    good_ok, good_msg, doc = OtpService.verify_otp(test_email, plain_otp, OtpPurpose.PASSWORD_RESET, consume=True)
    assert good_ok is True
    assert good_msg == "Verification successful."
    assert doc is not None


def test_expired_otp_rejected_with_clear_error(db):
    """Verify expired OTP is rejected with clear message stating 5-minute expiry."""
    test_email = "test.expired.otp@aisamrat.com"
    now = datetime.now(timezone.utc)

    # Insert an already expired token (created 6 minutes ago)
    otp_plain = "654321"
    db.otp_tokens.insert_one({
        "email": test_email,
        "otp_hash": OtpService._hash_otp(otp_plain),
        "purpose": OtpPurpose.ACTIVATION,
        "employee_id": "EMP-EXPIRED-1",
        "attempts": 0,
        "is_used": False,
        "created_at": now - timedelta(minutes=6),
        "last_sent_at": now - timedelta(minutes=6),
        "expires_at": now - timedelta(minutes=1)
    })

    ok, msg, _ = OtpService.verify_otp(test_email, otp_plain, OtpPurpose.ACTIVATION)
    assert ok is False
    assert "expired" in msg.lower()
    assert "valid for 5 minutes" in msg.lower()


def test_reused_single_use_otp_rejected_with_clear_error(db):
    """Verify single-use OTP cannot be reused after consumption."""
    test_email = "test.reused.otp@aisamrat.com"
    OtpService.generate_otp(email=test_email, purpose=OtpPurpose.PASSWORD_RESET)
    plain_otp = OtpService.get_latest_otp_for_test(test_email, OtpPurpose.PASSWORD_RESET)

    # First consumption -> succeeds
    ok1, msg1, _ = OtpService.verify_otp(test_email, plain_otp, OtpPurpose.PASSWORD_RESET, consume=True)
    assert ok1 is True

    # Second consumption attempt -> rejected
    ok2, msg2, _ = OtpService.verify_otp(test_email, plain_otp, OtpPurpose.PASSWORD_RESET, consume=True)
    assert ok2 is False
    assert "already been used" in msg2.lower()


def test_max_verification_attempts_invalidates_otp(db):
    """Verify that 5 failed attempts permanently invalidates the code."""
    test_email = "test.maxattempts.otp@aisamrat.com"
    OtpService.generate_otp(email=test_email, purpose=OtpPurpose.ACTIVATION)
    plain_otp = OtpService.get_latest_otp_for_test(test_email, OtpPurpose.ACTIVATION)

    # 4 bad attempts
    for i in range(1, 5):
        ok, msg, _ = OtpService.verify_otp(test_email, f"11111{i}", OtpPurpose.ACTIVATION)
        assert ok is False

    # 5th bad attempt -> triggers permanent invalidation
    ok5, msg5, _ = OtpService.verify_otp(test_email, "999999", OtpPurpose.ACTIVATION)
    assert ok5 is False
    assert "Too many incorrect attempts" in msg5

    # Even providing the correct OTP now must be rejected
    ok_final, msg_final, _ = OtpService.verify_otp(test_email, plain_otp, OtpPurpose.ACTIVATION)
    assert ok_final is False
    assert "Too many incorrect attempts" in msg_final or "invalidated" in msg_final


def test_resend_limits_and_hourly_rate_limiting(db):
    """Verify 60-second cooldown interval and 5-per-hour limit."""
    test_email = "test.ratelimit.otp@aisamrat.com"

    # First generation -> succeeds
    ok1, _ = OtpService.generate_otp(email=test_email, purpose=OtpPurpose.PASSWORD_RESET)
    assert ok1 is True

    # Immediate resend (< 60s) -> blocked
    ok2, msg2 = OtpService.generate_otp(email=test_email, purpose=OtpPurpose.PASSWORD_RESET)
    assert ok2 is False
    assert "Please wait" in msg2
    assert "seconds" in msg2

    # Simulate 5 requests within the last hour
    now = datetime.now(timezone.utc)
    db.otp_tokens.delete_many({"email": test_email})
    for i in range(5):
        db.otp_tokens.insert_one({
            "email": test_email,
            "otp_hash": "dummyhash",
            "purpose": OtpPurpose.PASSWORD_RESET,
            "created_at": now - timedelta(minutes=10 * (i + 1)),
            "last_sent_at": now - timedelta(minutes=10 * (i + 1)),
            "expires_at": now - timedelta(minutes=5),
            "is_used": True
        })

    # 6th attempt within the hour -> blocked by hourly limit
    ok_hourly, msg_hourly = OtpService.generate_otp(email=test_email, purpose=OtpPurpose.PASSWORD_RESET)
    assert ok_hourly is False
    assert "Maximum verification requests reached for this hour" in msg_hourly


def test_first_time_account_activation_complete_flow(client, db):
    """
    Test complete first-time account activation flow:
    1. HR creates unverified employee account with registered Gmail.
    2. Employee entering mismatched Gmail is rejected.
    3. Employee entering correct registered Gmail receives 5-minute OTP.
    4. Submitting incorrect OTP fails.
    5. Submitting correct OTP activates account and creates password.
    6. Employee can log in with verified Gmail and password.
    """
    emp_id = "EMP-OTP-VERIF-10"
    registered_gmail = "intern.sanjay.test@gmail.com"
    mismatched_gmail = "attacker.impostor@gmail.com"

    # Step 1: HR creates unverified employee account
    db.users.insert_one({
        "employee_id": emp_id,
        "full_name": "Sanjay Verma",
        "email": registered_gmail,
        "personal_email": registered_gmail,
        "role": Role.EMPLOYEE,
        "department": "Engineering",
        "designation": "AI Intern",
        "is_active": True,
        "is_email_verified": False,
        "account_status": "pending_activation",
        "needs_password_setup": True,
        "password_hash": hash_password("TempPassword@2026!"),
        "created_at": datetime.now(timezone.utc)
    })

    # Step 2: Employee entering mismatched Gmail is rejected
    mismatch_resp = client.post("/api/auth/activate/request-otp", json={
        "employee_id": emp_id,
        "gmail": mismatched_gmail
    })
    assert mismatch_resp.status_code == 400
    assert "does not match the registered personal email" in mismatch_resp.get_json()["error"]

    # Step 3: Employee entering registered Gmail receives 5-minute OTP
    req_resp = client.post("/api/auth/activate/request-otp", json={
        "employee_id": emp_id,
        "gmail": registered_gmail
    })
    assert req_resp.status_code == 200
    req_data = req_resp.get_json()
    assert req_data["success"] is True
    assert "Valid for 5 minutes" in req_data["message"]

    # Step 4: Retrieve generated plain OTP from simulated logs
    plain_otp = OtpService.get_latest_otp_for_test(registered_gmail, OtpPurpose.ACTIVATION)
    assert plain_otp is not None
    assert len(plain_otp) == 6

    # Step 5: Submitting incorrect OTP fails
    bad_resp = client.post("/api/auth/activate/complete", json={
        "employee_id": emp_id,
        "gmail": registered_gmail,
        "otp": "000000",
        "password": "NewStrongPass@2026!"
    })
    assert bad_resp.status_code == 400
    assert "Incorrect verification code" in bad_resp.get_json()["error"]

    # Step 6: Submitting correct OTP activates account
    act_resp = client.post("/api/auth/activate/complete", json={
        "employee_id": emp_id,
        "gmail": registered_gmail,
        "otp": plain_otp,
        "password": "NewStrongPass@2026!"
    })
    assert act_resp.status_code == 200
    assert act_resp.get_json()["success"] is True

    # Verify user record is active and verified in database
    user = db.users.find_one({"employee_id": emp_id})
    assert user["is_email_verified"] is True
    assert user["account_status"] == "active"
    assert verify_password("NewStrongPass@2026!", user["password_hash"]) is True

    # Step 7: Employee can sign in with verified Gmail and password
    login_resp = client.post("/api/auth/login", json={
        "email": registered_gmail,
        "password": "NewStrongPass@2026!"
    })
    assert login_resp.status_code == 200
    assert login_resp.get_json()["success"] is True
    assert login_resp.get_json()["redirect_url"] == "/dashboard/employee"


def test_same_otp_service_applies_across_all_four_roles(client, db):
    """
    Verify the unified OTP engine applies identically to all 4 business roles:
    Employee, Team Lead, Manager, and HR.
    """
    roles_test_data = [
        (Role.EMPLOYEE, "EMP-UNIF-1", "Aditi Rao", "aditi.unif@gmail.com"),
        (Role.TEAM_LEAD, "LEAD-UNIF-1", "Kavita Nair", "kavita.unif@gmail.com"),
        (Role.MANAGER, "MGR-UNIF-1", "Rajesh Kumar", "rajesh.unif@gmail.com"),
        (Role.HR, "HR-UNIF-1", "Ramya HR", "ramya.unif@gmail.com")
    ]

    for role, emp_id, name, email in roles_test_data:
        db.users.insert_one({
            "employee_id": emp_id,
            "full_name": name,
            "email": email,
            "personal_email": email,
            "role": role,
            "is_active": True,
            "is_email_verified": False,
            "account_status": "pending_activation",
            "created_at": datetime.now(timezone.utc)
        })

        # Request OTP
        res = client.post("/api/auth/activate/request-otp", json={
            "employee_id": emp_id,
            "gmail": email
        })
        assert res.status_code == 200
        assert "Valid for 5 minutes" in res.get_json()["message"]

        otp = OtpService.get_latest_otp_for_test(email, OtpPurpose.ACTIVATION)
        assert otp is not None

        # Verify and complete
        c_res = client.post("/api/auth/activate/complete", json={
            "employee_id": emp_id,
            "gmail": email,
            "otp": otp,
            "password": "SecurePassword@2026!"
        })
        assert c_res.status_code == 200

        user = db.users.find_one({"employee_id": emp_id})
        assert user["is_email_verified"] is True
        assert user["role"] == role
