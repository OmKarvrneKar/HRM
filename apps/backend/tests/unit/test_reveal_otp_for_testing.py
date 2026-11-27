import pytest
import os
from config import Config
from backend.services.otp_service import OtpService, OtpPurpose
from backend.permissions.rbac import Role


def test_otp_generation_prints_to_terminal_logs(capsys):
    """Verify that OtpService.generate_otp prints the 6-digit OTP clearly to terminal console logs."""
    email = "test.reveal@aisamrat.com"
    purpose = OtpPurpose.ACTIVATION

    success, msg = OtpService.generate_otp(email=email, purpose=purpose, employee_id="EMP-TEST-REVEAL")
    assert success is True

    captured = capsys.readouterr()
    assert "[DEV TESTING] OTP:" in captured.out
    assert email in captured.out
    assert purpose in captured.out

    # Verify debug_otp retrieval
    debug_otp = OtpService.get_debug_otp(email=email, purpose=purpose)
    assert debug_otp is not None
    assert len(debug_otp) == 6
    assert debug_otp.isdigit()
    assert f"[DEV TESTING] OTP: {debug_otp}" in captured.out


def test_activate_request_otp_returns_debug_otp_in_dev_mode(client, db):
    """Verify that /api/auth/activate/request-otp includes debug_otp in dev mode."""
    os.environ["FLASK_ENV"] = "development"
    assert Config.is_development() is True

    emp_id = "EMP-REVEAL-01"
    email = "reveal.candidate@gmail.com"

    db.users.insert_one({
        "employee_id": emp_id,
        "full_name": "Reveal Candidate",
        "email": "candidate@aisamrat.com",
        "personal_email": email,
        "role": Role.EMPLOYEE,
        "is_active": True,
        "is_email_verified": False,
        "account_status": "pending_activation"
    })

    res = client.post("/api/auth/activate/request-otp", json={
        "employee_id": emp_id,
        "gmail": email
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "debug_otp" in data
    assert len(data["debug_otp"]) == 6
    assert data["debug_otp"].isdigit()

    # Complete activation using the returned debug_otp
    res_comp = client.post("/api/auth/activate/complete", json={
        "employee_id": emp_id,
        "gmail": email,
        "otp": data["debug_otp"],
        "password": "SecurePassword@123"
    })
    assert res_comp.status_code == 200
    assert res_comp.get_json()["success"] is True


def test_forgot_password_returns_debug_otp_in_dev_mode(client, db):
    """Verify that /api/auth/forgot-password includes debug_otp in dev mode."""
    os.environ["FLASK_ENV"] = "development"

    emp_id = "EMP-FORGOT-01"
    email = "forgot.tester@gmail.com"

    db.users.insert_one({
        "employee_id": emp_id,
        "full_name": "Forgot Tester",
        "email": email,
        "personal_email": email,
        "role": Role.EMPLOYEE,
        "is_active": True,
        "is_email_verified": True,
        "account_status": "active"
    })

    res = client.post("/api/auth/forgot-password", json={"email": email})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "debug_otp" in data
    assert len(data["debug_otp"]) == 6
    assert data["debug_otp"].isdigit()

    # Complete reset password using the returned debug_otp
    res_reset = client.post("/api/auth/reset-password", json={
        "email": email,
        "otp": data["debug_otp"],
        "new_password": "NewSecurePassword@123"
    })
    assert res_reset.status_code == 200
    assert res_reset.get_json()["success"] is True


def test_change_password_request_otp_returns_debug_otp(client, tokens):
    """Verify that /api/auth/change-password/request-otp includes debug_otp for authenticated users."""
    os.environ["FLASK_ENV"] = "development"

    headers = {"Authorization": f"Bearer {tokens['emp1']}"}
    res = client.post("/api/auth/change-password/request-otp", headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "debug_otp" in data
    assert len(data["debug_otp"]) == 6


def test_production_mode_does_not_reveal_debug_otp(client, db):
    """Verify that in production mode (FLASK_ENV=production), debug_otp is never revealed in responses."""
    os.environ["FLASK_ENV"] = "production"

    try:
        assert Config.is_production() is True
        assert Config.is_development() is False

        emp_id = "EMP-PROD-01"
        email = "prod.user@gmail.com"

        db.users.insert_one({
            "employee_id": emp_id,
            "full_name": "Prod User",
            "email": email,
            "personal_email": email,
            "role": Role.EMPLOYEE,
            "is_active": True,
            "is_email_verified": True,
            "account_status": "active"
        })

        res = client.post("/api/auth/forgot-password", json={"email": email})
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert "debug_otp" not in data
        assert "otp" not in data

        # OtpService.get_debug_otp also returns None
        assert OtpService.get_debug_otp(email=email, purpose=OtpPurpose.PASSWORD_RESET) is None
    finally:
        os.environ["FLASK_ENV"] = "development"

