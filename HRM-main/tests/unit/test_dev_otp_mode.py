import pytest
import os
from datetime import datetime, timezone, timedelta
from config import Config
from backend.services.otp_service import OtpService, OtpPurpose
from backend.permissions.rbac import Role
from backend.auth.security import hash_password, generate_jwt_token


def test_dev_otp_generation_and_success_verification(db):
    """Test that OTP is securely generated, printed, and verified in DEV_OTP_MODE."""
    os.environ["DEV_OTP_MODE"] = "true"
    os.environ["FLASK_ENV"] = "development"
    assert Config.is_dev_otp_mode() is True

    email = "qa.tester@aisamrat.com"
    purpose = OtpPurpose.ACTIVATION

    # 1. Generate OTP
    success, msg = OtpService.generate_otp(email=email, purpose=purpose, employee_id="EMP-TEST-001")
    assert success is True
    # Plain OTP is NOT exposed in the message string
    assert "Verification code generated" in msg

    # 2. Retrieve generated OTP via dev registry
    entry = OtpService.get_dev_otp(email=email, purpose=purpose)
    assert entry is not None
    otp_code = entry["otp"]
    assert len(otp_code) == 6
    assert otp_code.isdigit()
    assert otp_code != "123456", "OTP should be randomly generated, not a hardcoded placeholder"

    # 3. Successful verification
    verified, v_msg, token_doc = OtpService.verify_otp(
        email=email,
        otp_plain=otp_code,
        purpose=purpose,
        consume=True
    )
    assert verified is True
    assert "successful" in v_msg.lower()
    assert token_doc is not None


def test_dev_otp_incorrect_code(db):
    """Test that submitting an incorrect OTP fails and tracks attempt limits."""
    os.environ["DEV_OTP_MODE"] = "true"
    os.environ["FLASK_ENV"] = "development"

    email = "qa.incorrect@aisamrat.com"
    purpose = OtpPurpose.PASSWORD_RESET

    OtpService.generate_otp(email=email, purpose=purpose)

    # Submit wrong code
    verified, v_msg, _ = OtpService.verify_otp(
        email=email,
        otp_plain="000000",
        purpose=purpose,
        consume=True
    )
    assert verified is False
    assert "incorrect" in v_msg.lower()
    assert "attempt(s) remaining" in v_msg


def test_dev_otp_expired_code(db):
    """Test that expired OTPs are strictly rejected."""
    os.environ["DEV_OTP_MODE"] = "true"
    os.environ["FLASK_ENV"] = "development"

    email = "qa.expired@aisamrat.com"
    purpose = OtpPurpose.EMAIL_CHANGE_NEW

    OtpService.generate_otp(email=email, purpose=purpose)
    entry = OtpService.get_dev_otp(email=email, purpose=purpose)
    assert entry is not None
    otp_code = entry["otp"]

    # Artificially expire the token in DB
    past = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.otp_tokens.update_one(
        {"email": email, "purpose": purpose},
        {"$set": {"expires_at": past}}
    )

    verified, v_msg, _ = OtpService.verify_otp(
        email=email,
        otp_plain=otp_code,
        purpose=purpose,
        consume=True
    )
    assert verified is False
    assert "expired" in v_msg.lower()


def test_dev_otp_reuse_prevention(db):
    """Test that a code cannot be reused after single-use verification."""
    os.environ["DEV_OTP_MODE"] = "true"
    os.environ["FLASK_ENV"] = "development"

    email = "qa.reuse@aisamrat.com"
    purpose = OtpPurpose.ACTIVATION

    OtpService.generate_otp(email=email, purpose=purpose)
    entry = OtpService.get_dev_otp(email=email, purpose=purpose)
    otp_code = entry["otp"]

    # First verification succeeds
    ok1, _, _ = OtpService.verify_otp(email=email, otp_plain=otp_code, purpose=purpose, consume=True)
    assert ok1 is True

    # Second verification with same code fails
    ok2, v_msg2, _ = OtpService.verify_otp(email=email, otp_plain=otp_code, purpose=purpose, consume=True)
    assert ok2 is False
    assert "already been used" in v_msg2.lower()


def test_dev_otp_resend_cooldown(db):
    """Test that resending within 60 seconds is rate-limited."""
    os.environ["DEV_OTP_MODE"] = "true"
    os.environ["FLASK_ENV"] = "development"

    email = "qa.cooldown@aisamrat.com"
    purpose = OtpPurpose.PASSWORD_RESET

    # Request 1
    s1, _ = OtpService.generate_otp(email=email, purpose=purpose)
    assert s1 is True

    # Request 2 immediately
    s2, msg2 = OtpService.generate_otp(email=email, purpose=purpose)
    assert s2 is False
    assert "wait" in msg2.lower()
    assert "seconds" in msg2.lower()


def test_production_mode_locks_out_dev_otp(client, db):
    """Test that production mode strictly locks out development OTP mode and endpoints."""
    # Force production mode
    os.environ["FLASK_ENV"] = "production"
    os.environ["DEV_OTP_MODE"] = "true"  # Even if mistakenly set to true

    try:
        assert Config.is_production() is True
        assert Config.is_dev_otp_mode() is False

        # Attempt direct access to dev OTP endpoint
        res = client.get("/api/auth/dev-current-otp?email=admin@aisamrat.com&purpose=PASSWORD_RESET")
        assert res.status_code == 403, f"Expected 403 in production, got {res.status_code}"
        assert "disabled or unauthorized" in res.get_json()["error"]

        # OtpService.get_dev_otp must return None
        entry = OtpService.get_dev_otp("admin@aisamrat.com", OtpPurpose.PASSWORD_RESET)
        assert entry is None
    finally:
        os.environ["FLASK_ENV"] = "development"
        os.environ["DEV_OTP_MODE"] = "true"


def test_dev_current_otp_endpoint_in_dev_mode(client, db):
    """Test that /api/auth/dev-current-otp returns the code in development mode with dev endpoints enabled."""
    os.environ["FLASK_ENV"] = "development"
    os.environ["DEV_OTP_MODE"] = "true"
    os.environ["ENABLE_DEV_ENDPOINTS"] = "true"

    email = "dev.endpoint.test@aisamrat.com"
    purpose = OtpPurpose.PASSWORD_RESET

    OtpService.generate_otp(email=email, purpose=purpose)

    res = client.get(f"/api/auth/dev-current-otp?email={email}&purpose={purpose}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["mode"] == "DEVELOPMENT OTP MODE"
    assert data["email"] == email
    assert len(data["otp"]) == 6


def test_end_to_end_activation_with_dev_otp(client, db):
    """Test complete employee activation flow with DEV_OTP_MODE and ENABLE_DEV_ENDPOINTS."""
    os.environ["FLASK_ENV"] = "development"
    os.environ["DEV_OTP_MODE"] = "true"
    os.environ["ENABLE_DEV_ENDPOINTS"] = "true"

    # Insert employee needing activation
    db.users.insert_one({
        "employee_id": "EMP-ACT-100",
        "full_name": "Activation Candidate",
        "email": "candidate@aisamrat.com",
        "personal_email": "candidate.personal@gmail.com",
        "role": Role.EMPLOYEE,
        "is_active": True,
        "is_email_verified": False,
        "account_status": "pending_activation"
    })


    # Step 1: Request OTP
    res_req = client.post("/api/auth/activate/request-otp", json={
        "employee_id": "EMP-ACT-100",
        "gmail": "candidate.personal@gmail.com"
    })
    assert res_req.status_code == 200
    req_data = res_req.get_json()
    assert req_data["success"] is True
    # OTP is NOT exposed in public API response
    assert "otp" not in req_data

    # Fetch OTP from protected dev endpoint
    res_dev = client.get("/api/auth/dev-current-otp?email=candidate.personal@gmail.com&purpose=ACTIVATION")
    assert res_dev.status_code == 200
    otp = res_dev.get_json()["otp"]

    # Step 2: Complete activation
    res_comp = client.post("/api/auth/activate/complete", json={
        "employee_id": "EMP-ACT-100",
        "gmail": "candidate.personal@gmail.com",
        "otp": otp,
        "password": "Valid@Password2026!"
    })
    assert res_comp.status_code == 200
    assert res_comp.get_json()["success"] is True

    # User in DB is now active and email-verified
    user = db.users.find_one({"employee_id": "EMP-ACT-100"})
    assert user["is_email_verified"] is True
    assert user["account_status"] == "active"
    assert user["personal_email"] == "candidate.personal@gmail.com"
