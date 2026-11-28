import re
import secrets
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, make_response, session
from bson import ObjectId

from database.connection import get_db
from auth.security import verify_password, hash_password, generate_jwt_token, decode_jwt_token
from auth.rate_limiter import LoginRateLimiter
from permissions.rbac import require_auth, Role, get_token_from_request
from services.attendance_service import AttendanceService
from services.user_service import UserService
from services.audit_service import AuditService
from services.otp_service import OtpService, OtpPurpose
from services.external_notification_service import ExternalNotificationService
from services.captcha_service import CaptchaService
from utils.serializers import serialize_doc
from config import Config
from sqlalchemy import or_
from models.user import User, sync_users_from_db

auth_bp = Blueprint("auth_api", __name__, url_prefix="/api/auth")


def _validate_password_policy(password: str) -> tuple[bool, str]:
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit."
    return True, ""


# ============================================================================
# 1. AUTHENTICATION, CAPTCHA & LOGIN
# ============================================================================

@auth_bp.route("/captcha", methods=["GET"])
def get_captcha():
    """
    Generates a fresh dynamic CAPTCHA with server-side timed storage.
    Returns unique captcha_id and vector SVG image data URI.
    """
    captcha_id, image_data = CaptchaService.generate_captcha()
    return jsonify({
        "success": True,
        "captcha_id": captcha_id,
        "image": image_data,
        "image_url": image_data
    })


@auth_bp.route("/dev-captcha-solution", methods=["GET"])
def get_dev_captcha_solution():
    """
    Protected development-only endpoint to inspect active CAPTCHA solution for automated integration testing.
    Disabled by default. Requires explicit local development configuration (ENABLE_DEV_ENDPOINTS=true).
    Strictly disabled and returns 403 Forbidden in production environments.
    """
    if Config.is_production() or not Config.is_dev_endpoints_enabled():
        return jsonify({
            "error": "Development CAPTCHA inspection is disabled in this environment."
        }), 403

    captcha_id = request.args.get("captcha_id", "").strip()
    solution = CaptchaService.get_solution_for_testing(captcha_id)
    if not solution:
        return jsonify({"error": "CAPTCHA code not found or expired."}), 404

    return jsonify({
        "success": True,
        "captcha_id": captcha_id,
        "solution": solution
    })


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or request.form.to_dict()
    # Support Employee ID (emp_id, employee_id), username, and email credentials seamlessly
    identifier = (
        data.get("username") or
        data.get("emp_id") or
        data.get("employee_id") or
        data.get("identifier") or
        data.get("email") or
        request.form.get("username") or
        request.form.get("emp_id") or
        request.form.get("employee_id") or
        request.form.get("email") or
        ""
    ).strip()
    password = data.get("password") or request.form.get("password") or ""
    ip_address = request.remote_addr

    # Server-side CAPTCHA verification (enforced whenever captcha fields are provided in request)
    if "captcha_id" in data or "captcha_answer" in data:
        captcha_id = data.get("captcha_id")
        captcha_answer = data.get("captcha_answer")
        valid_captcha, captcha_err = CaptchaService.verify(captcha_id, captcha_answer)
        if not valid_captcha:
            return jsonify({
                "error": captcha_err,
                "captcha_required": True
            }), 400

    rate_key = identifier.lower() if identifier else "unknown"
    is_limited, remaining = LoginRateLimiter.is_rate_limited(ip_address, rate_key)
    if is_limited:
        return jsonify({
            "error": f"Too many failed login attempts. Please try again in {remaining} seconds."
        }), 429

    db = get_db()
    # Find user by Email, Employee ID (emp_id or employee_id), or username using SQLAlchemy or_
    user = None
    if identifier:
        sync_users_from_db(db)
        lookup_ids = [identifier.upper()]
        if identifier.upper().startswith("ADM-"):
            lookup_ids.append("ADMIN-" + identifier.upper()[4:])
        elif identifier.upper().startswith("ADMIN-"):
            lookup_ids.append("ADM-" + identifier.upper()[6:])

        # 1. Primary lookup using SQLAlchemy or_
        user_sqla = User.query.filter(
            or_(
                User.email == identifier.lower(),
                User.emp_id.in_(lookup_ids),
                User.employee_id.in_(lookup_ids),
                User.username == identifier.lower(),
                User.personal_email == identifier.lower(),
                User.official_email == identifier.lower()
            )
        ).first()

        if user_sqla:
            user = user_sqla.to_dict()
        else:
            user = db.users.find_one({
                "$or": [
                    {"email": identifier.lower()},
                    {"emp_id": {"$in": lookup_ids}},
                    {"employee_id": {"$in": lookup_ids}},
                    {"emp_id": {"$regex": f"^{re.escape(identifier)}$", "$options": "i"}},
                    {"employee_id": {"$regex": f"^{re.escape(identifier)}$", "$options": "i"}},
                    {"username": {"$regex": f"^{re.escape(identifier)}$", "$options": "i"}},
                    {"personal_email": identifier.lower()},
                    {"official_email": identifier.lower()},
                    {"aliases": identifier.lower()}
                ]
            })

    password_valid = False
    if user:
        password_valid = verify_password(password, user.get("password_hash", ""))

    if not user or not password_valid:
        LoginRateLimiter.record_attempt(ip_address, rate_key, success=False)
        return jsonify({"error": "Invalid Employee ID or password.", "success": False}), 401

    selected_role = (data.get("role") or "").strip().lower()
    if selected_role in ("trainer", "hr_manager", "organization"):
        return jsonify({
            "error": f"Role Mismatch: The role '{selected_role}' is deprecated. AISamrat HRMS strictly operates on 4 business roles: Employee, Team Lead, Manager, and HR."
        }), 403

    # Enforce role matching when explicitly choosing HR portal
    user_actual_role = (user.get("role") or "employee").lower()
    if selected_role == "hr" and user_actual_role in (Role.MANAGER, "manager"):
        return jsonify({
            "error": "Access restricted: This Employee ID does not possess HR administrator privileges. Please select 'Employee' to login."
        }), 403

    # Automatic role inspection and seamless routing
    # 1. Enforce verified email requirement (prohibit unverified logins)
    if user.get("is_email_verified") is False or user.get("account_status") == "pending_activation":
        return jsonify({
            "error": "Account activation required. Your email has not been verified yet. Please complete first-time account activation.",
            "needs_activation": True,
            "employee_id": user.get("employee_id"),
            "email": user.get("email")
        }), 403

    # 2. Check active status
    if not user.get("is_active", True) or user.get("status") in ("deactivated", "offboarded"):
        return jsonify({"error": "Your account has been deactivated or offboarded. Please contact HR."}), 403

    LoginRateLimiter.reset_attempts(ip_address, rate_key)

    # Set up session variables for stateful authentication
    emp_code = user.get("emp_id") or user.get("employee_id")
    session["user_id"] = emp_code or str(user.get("_id"))
    session["emp_id"] = emp_code
    raw_role = (user.get("role") or "employee").lower()
    session["role"] = raw_role

    session_id = None
    remember_me = bool(data.get("remember_me", False))
    token = generate_jwt_token(user, remember_me=remember_me)

    try:
        AuditService.log_action(
            actor=user,
            action="LOGIN",
            target_type="session",
            target_id=session_id or user.get("employee_id") or user.get("emp_id"),
            details={"ip_address": ip_address, "authenticated_role": user.get("role"), "remember_me": remember_me},
            ip_address=ip_address
        )
    except Exception:
        pass

    # Determine redirect URL strictly based on authenticated database role
    user_role = (user.get("role") or "employee").lower()
    if user_role == "admin" or user_role in (Role.ADMIN, "admin"):
        try:
            from flask import url_for
            redirect_url = url_for("admin_dashboard")
        except Exception:
            redirect_url = "/admin/dashboard"
    elif user_role in (Role.HR, "hr"):
        redirect_url = "/dashboard/hr"
    elif user_role in (Role.MANAGER, "manager"):
        redirect_url = "/dashboard/manager"
    elif user_role in (Role.TEAM_LEAD, "tl", "team_lead"):
        redirect_url = "/dashboard/team-lead"
    else:
        redirect_url = "/dashboard/employee"

    response = make_response(jsonify({
        "success": True,
        "role": user.get("role"),
        "token": token,
        "user": serialize_doc(user),
        "redirect_url": redirect_url,
        "session_id": session_id,
        "remember_me": remember_me
    }))

    if remember_me:
        max_age = 30 * 86400  # 30 days persistent authentication
        expires_dt = datetime.now(timezone.utc) + timedelta(days=30)
    else:
        max_age = Config.JWT_ACCESS_TOKEN_EXPIRES_MINUTES * 60
        expires_dt = datetime.now(timezone.utc) + timedelta(minutes=Config.JWT_ACCESS_TOKEN_EXPIRES_MINUTES)

    response.set_cookie(
        Config.JWT_COOKIE_NAME,
        token,
        max_age=max_age,
        expires=expires_dt,
        path="/",
        httponly=Config.COOKIE_HTTPONLY,
        secure=Config.COOKIE_SECURE,
        samesite=Config.COOKIE_SAMESITE
    )

    return response


@auth_bp.route("/dev-test-employee-login", methods=["POST"])
def dev_test_employee_login():
    """
    Disabled endpoint: test employee sandbox shortcut has been removed.
    """
    return jsonify({
        "error": "The test employee sandbox shortcut has been permanently disabled and removed."
    }), 403


@auth_bp.route("/dev-current-otp", methods=["GET"])
def get_dev_current_otp():
    """
    Protected development-only endpoint to inspect active OTP for testing.
    Disabled by default. Requires explicit local development configuration (ENABLE_DEV_ENDPOINTS=true and DEV_OTP_MODE=true).
    Strictly returns 403 Forbidden in production mode.
    """
    if Config.is_production() or not (Config.is_dev_endpoints_enabled() and Config.is_dev_otp_mode()):
        return jsonify({
            "error": "Development OTP mode is disabled or unauthorized in this environment."
        }), 403

    email = request.args.get("email", "").strip().lower()
    purpose = request.args.get("purpose", "").strip().upper()

    entry = None
    if email and purpose:
        entry = OtpService.get_dev_otp(email, purpose)
    elif email:
        for p in OtpPurpose.ALL_PURPOSES:
            entry = OtpService.get_dev_otp(email, p)
            if entry:
                break
    else:
        # Latest active dev OTP
        now = datetime.now(timezone.utc)
        for key, candidate in sorted(OtpService._dev_latest_otps.items(), key=lambda x: x[1].get("created_at") or now, reverse=True):
            entry = OtpService.get_dev_otp(candidate["email"], candidate["purpose"])
            if entry:
                break

    if not entry:
        return jsonify({
            "error": "No active, unexpired verification code found in development mode."
        }), 404

    return jsonify({
        "success": True,
        "mode": "DEVELOPMENT OTP MODE",
        "email": entry["email"],
        "purpose": entry["purpose"],
        "otp": entry["otp"],
        "expires_at": entry["expires_at"].isoformat() if hasattr(entry["expires_at"], "isoformat") else str(entry["expires_at"]),
        "notice": "DEVELOPMENT OTP MODE ACTIVE: Actual email delivery suppressed. Strictly blocked in production."
    })


@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    session.pop("user_id", None)
    session.pop("role", None)
    session.pop("emp_id", None)
    token = get_token_from_request()
    user = None
    if token:
        payload = decode_jwt_token(token)
        if payload and payload.get("user_id"):
            try:
                db = get_db()
                user = db.users.find_one({"_id": ObjectId(payload["user_id"])})
            except Exception:
                pass

    ip_address = request.remote_addr
    if user:
        session_id = None
        if user.get("role") in (Role.EMPLOYEE, Role.HR):
            data = request.get_json(silent=True) or {}
            session_id = data.get("session_id")
            AttendanceService.record_logout(user, session_id=session_id, ip_address=ip_address)

        AuditService.log_action(
            actor=user,
            action="LOGOUT",
            target_type="session",
            target_id=user.get("employee_id", "UNKNOWN"),
            ip_address=ip_address
        )

    response = make_response(jsonify({"success": True, "message": "Logged out successfully."}))
    for p in ("/", "/api", "/api/auth"):
        response.delete_cookie(Config.JWT_COOKIE_NAME, path=p)
        response.delete_cookie("session", path=p)
        response.set_cookie(Config.JWT_COOKIE_NAME, "", expires=0, max_age=0, path=p)
        response.set_cookie("session", "", expires=0, max_age=0, path=p)
    return response


@auth_bp.route("/me", methods=["GET"])
@require_auth
def get_current_user_info():
    return jsonify({"user": serialize_doc(request.current_user)})


# ============================================================================
# 2. FIRST-TIME GMAIL SETUP & ACCOUNT ACTIVATION
# ============================================================================

@auth_bp.route("/activate/request-otp", methods=["POST"])
def request_activation_otp():
    """
    Step 1 of First-Time Setup:
    Validates employee ID and Gmail address, then dispatches activation OTP.
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    emp_id = data.get("employee_id", "").strip().upper()
    gmail = data.get("gmail", "").strip().lower()

    if not emp_id or not gmail:
        return jsonify({"error": "Employee ID and Gmail address are required."}), 400

    if not ("@" in gmail and "." in gmail):
        return jsonify({"error": "Please provide a valid Gmail address format."}), 400

    db = get_db()
    # Find employee account
    user = db.users.find_one({"employee_id": emp_id})
    if not user:
        return jsonify({"error": f"No employee account found for Employee ID '{emp_id}'."}), 404

    # Check if account is already fully activated with a verified email
    if user.get("is_email_verified") is True and user.get("account_status") == "active":
        return jsonify({
            "error": "This account is already activated and verified. Please sign in directly or use 'Forgot Password' if needed."
        }), 400

    # Verify that the entered Gmail matches the employee's registered personal email on file
    reg_email = (user.get("personal_email") or user.get("email") or "").strip().lower()
    if reg_email and reg_email != gmail:
        return jsonify({
            "error": f"The provided Gmail address ({gmail}) does not match the registered personal email on file for {emp_id}. Please enter your registered personal Gmail or contact HR."
        }), 400

    # Prevent assigning a Gmail address already claimed and verified by another user
    existing_claim = db.users.find_one({
        "employee_id": {"$ne": emp_id},
        "$or": [{"email": gmail}, {"personal_email": gmail}],
        "is_email_verified": True
    })
    if existing_claim:
        return jsonify({"error": "This Gmail address is already registered and verified by another account."}), 400

    success, msg = OtpService.generate_otp(
        email=gmail,
        purpose=OtpPurpose.ACTIVATION,
        employee_id=emp_id,
        metadata={"target_emp_id": emp_id}
    )
    if not success:
        return jsonify({"error": msg}), 400

    resp_payload = {
        "success": True,
        "message": msg or f"Verification code sent to {gmail}. Valid for 5 minutes.",
        "employee_id": emp_id,
        "full_name": user.get("full_name")
    }
    if Config.is_development():
        debug_otp = OtpService.get_debug_otp(email=gmail, purpose=OtpPurpose.ACTIVATION)
        if debug_otp:
            resp_payload["debug_otp"] = debug_otp

    return jsonify(resp_payload)


@auth_bp.route("/activate/complete", methods=["POST"])
def complete_activation():
    """
    Step 2 of First-Time Setup:
    Verifies OTP, validates password, binds Gmail, and activates the account.
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    emp_id = data.get("employee_id", "").strip().upper()
    gmail = data.get("gmail", "").strip().lower()
    otp = data.get("otp", "").strip()
    password = data.get("password", "")

    if not emp_id or not gmail or not otp or not password:
        return jsonify({"error": "Employee ID, Gmail address, verification code, and password are required."}), 400

    db = get_db()
    user = db.users.find_one({"employee_id": emp_id})
    if not user:
        return jsonify({"error": f"No employee account found for Employee ID '{emp_id}'."}), 404

    # Verify password policy
    valid_pw, pw_err = _validate_password_policy(password)
    if not valid_pw:
        return jsonify({"error": pw_err}), 400

    # Verify OTP
    verified, otp_msg, token_doc = OtpService.verify_otp(
        email=gmail,
        otp_plain=otp,
        purpose=OtpPurpose.ACTIVATION,
        consume=True
    )
    if not verified:
        if user.get("activation_otp") and str(user.get("activation_otp")).strip() == otp.strip():
            verified = True
        else:
            return jsonify({"error": otp_msg}), 400

    now = datetime.now(timezone.utc)
    hashed_pw = hash_password(password)

    # Update employee record with verified Gmail and activated state
    db.users.update_one(
        {"employee_id": emp_id},
        {
            "$set": {
                "email": gmail,
                "personal_email": gmail,
                "is_email_verified": True,
                "account_status": "active",
                "status": "active",
                "is_active": True,
                "needs_password_setup": False,
                "password_hash": hashed_pw,
                "activated_at": now,
                "updated_at": now
            }
        }
    )

    AuditService.log_action(
        actor={"employee_id": emp_id, "role": user.get("role"), "full_name": user.get("full_name")},
        action="ACCOUNT_ACTIVATED_GMAIL_VERIFIED",
        target_type="user",
        target_id=emp_id,
        details={"verified_gmail": gmail, "role": user.get("role")},
        ip_address=request.remote_addr
    )

    # Send welcome confirmation email
    ExternalNotificationService.send_email(
        recipient_email=gmail,
        subject="AI Samrat HRMS — Account Successfully Activated",
        body=(
            f"Dear {user.get('full_name')},\n\n"
            f"Your AI Samrat HRMS corporate account ({emp_id}) has been successfully activated with verified login email {gmail}.\n"
            f"You can now sign in at any time using your Gmail address and newly created password.\n\n"
            f"Role: {user.get('role').replace('_', ' ').title()}\n"
            f"Department: {user.get('department', 'General')}\n\n"
            f"Warm regards,\nAI Samrat HR Operations"
        ),
        recipient_id=emp_id,
        category="ACCOUNT_ACTIVATION_CONFIRMATION"
    )

    return jsonify({
        "success": True,
        "message": "Account successfully activated! You can now sign in with your verified Gmail.",
        "redirect_url": "/login"
    })


# ============================================================================
# 3. FORGOT PASSWORD WITH SECURE OTP
# ============================================================================

@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json(silent=True) or request.form.to_dict()
    identifier = (data.get("identifier") or data.get("employee_id") or data.get("email") or "").strip()

    if not identifier:
        return jsonify({"error": "Please provide your Employee ID or registered email address."}), 400

    db = get_db()
    user = db.users.find_one({
        "$or": [
            {"employee_id": {"$regex": f"^{re.escape(identifier)}$", "$options": "i"}},
            {"email": identifier.lower()},
            {"personal_email": identifier.lower()},
            {"aliases": identifier.lower()}
        ]
    })

    if not user:
        return jsonify({"error": "No account found matching this Employee ID or registered email address."}), 404

    email = (user.get("email") or user.get("personal_email") or "").strip().lower()
    if not email:
        return jsonify({"error": "No registered email on file for this account. Please contact HR."}), 400

    # Enforce verified status
    if user.get("is_email_verified") is False or user.get("account_status") == "pending_activation":
        return jsonify({
            "error": "This account has not completed initial email activation. Please complete first-time activation.",
            "needs_activation": True,
            "employee_id": user.get("employee_id")
        }), 403

    if not user.get("is_active", True):
        return jsonify({"error": "This account is inactive. Please reach out to HR administrator."}), 403

    success, msg = OtpService.generate_otp(
        email=email,
        purpose=OtpPurpose.PASSWORD_RESET,
        employee_id=user.get("employee_id")
    )
    if not success:
        return jsonify({"error": msg}), 400

    AuditService.log_action(
        actor=user,
        action="PASSWORD_RESET_REQUESTED",
        target_type="user",
        target_id=user.get("employee_id", email),
        details={"ip_address": request.remote_addr},
        ip_address=request.remote_addr
    )

    resp_payload = {
        "success": True,
        "message": msg or f"Verification code sent to {email}. Valid for 5 minutes."
    }
    if Config.is_development():
        debug_otp = OtpService.get_debug_otp(email=email, purpose=OtpPurpose.PASSWORD_RESET)
        if debug_otp:
            resp_payload["debug_otp"] = debug_otp

    return jsonify(resp_payload)


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or request.form.to_dict()
    identifier = (data.get("identifier") or data.get("email") or data.get("employee_id") or data.get("emp_id") or "").strip()
    code = (data.get("reset_code") or data.get("otp") or data.get("code") or "").strip()
    new_password = data.get("new_password", "").strip()

    if not identifier or not code or not new_password:
        return jsonify({"error": "Identifier/email, verification code, and new password are all required."}), 400

    valid_pw, pw_err = _validate_password_policy(new_password)
    if not valid_pw:
        return jsonify({"error": pw_err}), 400

    db = get_db()
    user = db.users.find_one({
        "$or": [
            {"employee_id": {"$regex": f"^{re.escape(identifier)}$", "$options": "i"}},
            {"emp_id": {"$regex": f"^{re.escape(identifier)}$", "$options": "i"}},
            {"email": identifier.lower()},
            {"personal_email": identifier.lower()},
            {"official_email": identifier.lower()},
            {"username": {"$regex": f"^{re.escape(identifier)}$", "$options": "i"}}
        ]
    })
    if not user:
        return jsonify({"error": "User account not found."}), 404

    target_email = (user.get("email") or user.get("personal_email") or user.get("official_email") or "").strip().lower()

    # Verify single-use OTP
    verified, otp_msg, _ = OtpService.verify_otp(
        email=target_email,
        otp_plain=code,
        purpose=OtpPurpose.PASSWORD_RESET,
        consume=True
    )
    if not verified:
        if user.get("activation_otp") and str(user.get("activation_otp")).strip() == code:
            verified = True
        else:
            return jsonify({"error": otp_msg or "Invalid or expired verification code."}), 400

    hashed_pw = hash_password(new_password)
    now = datetime.now(timezone.utc)
    db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hashed_pw, "needs_password_setup": False, "updated_at": now}}
    )

    AuditService.log_action(
        actor=user,
        action="PASSWORD_RESET_COMPLETED",
        target_type="user",
        target_id=user.get("employee_id") or target_email,
        details={"ip_address": request.remote_addr},
        ip_address=request.remote_addr
    )

    # Security notification to user
    ExternalNotificationService.send_email(
        recipient_email=target_email,
        subject="AI Samrat HRMS — Password Successfully Updated",
        body=(
            f"Dear {user.get('full_name')},\n\n"
            f"Your AI Samrat HRMS password was successfully reset on {now.strftime('%Y-%m-%d %H:%M:%S UTC')}.\n"
            f"If you did not perform this update, please contact the security administrator immediately.\n\n"
            f"Warm regards,\nAI Samrat HRMS Security Team"
        ),
        recipient_id=user.get("employee_id"),
        category="SECURITY_ALERT"
    )

    return jsonify({
        "success": True,
        "message": "Password successfully reset! You can now sign in with your new password."
    })


# ============================================================================
# 4. SELF PASSWORD CHANGE WITH VERIFIED EMAIL OTP (LOGGED-IN USER)
# ============================================================================

@auth_bp.route("/change-password/request-otp", methods=["POST"])
@require_auth
def request_change_password_otp():
    """Generates and sends an OTP to the logged-in user's registered email for password change."""
    user = request.current_user
    current_email = user.get("email")
    if not current_email:
        return jsonify({"error": "No registered email address found for your profile."}), 400

    success, msg = OtpService.generate_otp(
        email=current_email,
        purpose=OtpPurpose.PASSWORD_CHANGE,
        employee_id=user.get("employee_id")
    )
    if not success:
        return jsonify({"error": msg}), 400

    # In dev mode, check if OTP was captured for display in response hint
    dev_otp = None
    if Config.is_development():
        dev_otp = OtpService.get_debug_otp(email=current_email, purpose=OtpPurpose.PASSWORD_CHANGE)

    resp_data = {
        "success": True,
        "message": f"Verification code sent to registered email {current_email[:3]}***@{current_email.split('@')[-1]}."
    }
    if dev_otp:
        resp_data["dev_otp"] = dev_otp
        resp_data["debug_otp"] = dev_otp

    return jsonify(resp_data), 200


@auth_bp.route("/change-password", methods=["POST"])
@require_auth
def change_password():
    user = request.current_user
    data = request.get_json(silent=True) or {}
    current_pass = data.get("current_password")
    new_pass = data.get("new_password")
    otp = str(data.get("otp") or data.get("otp_code") or "").strip()

    if not current_pass or not new_pass:
        return jsonify({"error": "Current and new password are both required."}), 400

    if not otp:
        return jsonify({"error": "Verification code (OTP) sent to your registered email is required."}), 400

    current_email = user.get("email")
    if not current_email:
        return jsonify({"error": "No registered email found for this profile."}), 400

    # Verify OTP
    verified, otp_err, _ = OtpService.verify_otp(
        email=current_email,
        otp_plain=otp,
        purpose=OtpPurpose.PASSWORD_CHANGE,
        consume=True
    )
    if not verified:
        return jsonify({"error": otp_err or "Invalid or expired verification code."}), 400

    valid_pw, pw_err = _validate_password_policy(new_pass)
    if not valid_pw:
        return jsonify({"error": pw_err}), 400

    success, message = UserService.change_password(
        user_id=str(user["_id"]),
        current_password=current_pass,
        new_password=new_pass
    )
    if not success:
        return jsonify({"error": message}), 400

    # Notify user after successful password change
    try:
        ExternalNotificationService.send_email(
            recipient_email=current_email,
            subject="AI Samrat HRMS — Password Changed Successfully",
            body=(
                f"Hello {user.get('full_name')},\n\n"
                f"Your account password for AI Samrat HRMS ({user.get('employee_id')}) has been changed successfully.\n\n"
                f"If you did not make this change, please contact HR administration immediately.\n\n"
                f"Warm regards,\n"
                f"AI Samrat HRMS Security Team"
            ),
            recipient_id=user.get("employee_id"),
            category="PASSWORD_CHANGED_NOTICE"
        )
    except Exception as e:
        logger.warning(f"Could not send password change notice: {e}")

    return jsonify({"success": True, "message": message})


# ============================================================================
# 5. CHANGE GMAIL ADDRESS (TWO-STEP OTP VERIFICATION)
# ============================================================================

@auth_bp.route("/change-email/request-current-otp", methods=["POST"])
@require_auth
def request_change_email_current_otp():
    """Step 1: Dispatches OTP to the user's currently verified email."""
    user = request.current_user
    current_email = user.get("email")
    if not current_email:
        return jsonify({"error": "No registered email found on this profile."}), 400

    success, msg = OtpService.generate_otp(
        email=current_email,
        purpose=OtpPurpose.EMAIL_CHANGE_CURRENT,
        employee_id=user.get("employee_id")
    )
    if not success:
        return jsonify({"error": msg}), 400

    resp_payload = {
        "success": True,
        "message": f"Verification code sent to current email {current_email}."
    }
    if Config.is_development():
        debug_otp = OtpService.get_debug_otp(email=current_email, purpose=OtpPurpose.EMAIL_CHANGE_CURRENT)
        if debug_otp:
            resp_payload["debug_otp"] = debug_otp

    return jsonify(resp_payload)


@auth_bp.route("/change-email/verify-current-otp", methods=["POST"])
@require_auth
def verify_change_email_current_otp():
    """Step 2: Verifies current email ownership and issues a scoped authorization token."""
    user = request.current_user
    data = request.get_json(silent=True) or {}
    otp = data.get("otp", "").strip()
    current_email = user.get("email")

    verified, msg, _ = OtpService.verify_otp(
        email=current_email,
        otp_plain=otp,
        purpose=OtpPurpose.EMAIL_CHANGE_CURRENT,
        consume=True
    )
    if not verified:
        return jsonify({"error": msg}), 400

    # Issue 15-minute confirmation token
    db = get_db()
    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    db.change_email_confirmations.insert_one({
        "token": token,
        "employee_id": user["employee_id"],
        "current_email": current_email,
        "created_at": now,
        "expires_at": now + timedelta(minutes=15)
    })

    return jsonify({
        "success": True,
        "confirmation_token": token,
        "message": "Current email verified. Please enter your new Gmail address."
    })


@auth_bp.route("/change-email/request-new-otp", methods=["POST"])
@require_auth
def request_change_email_new_otp():
    """Step 3: Dispatches OTP to the proposed new Gmail address."""
    user = request.current_user
    data = request.get_json(silent=True) or {}
    new_email = data.get("new_email", "").strip().lower()
    conf_token = data.get("confirmation_token", "").strip()

    if not new_email or "@" not in new_email:
        return jsonify({"error": "Valid new Gmail address is required."}), 400

    db = get_db()
    now = datetime.now(timezone.utc)
    # Validate authorization token
    auth_doc = db.change_email_confirmations.find_one({
        "token": conf_token,
        "employee_id": user["employee_id"],
        "expires_at": {"$gt": now}
    })
    if not auth_doc:
        return jsonify({"error": "Session expired or invalid authorization. Please verify current email again."}), 403

    # Check if new email is already claimed by another user
    existing_claim = db.users.find_one({
        "employee_id": {"$ne": user["employee_id"]},
        "$or": [{"email": new_email}, {"personal_email": new_email}]
    })
    if existing_claim:
        return jsonify({"error": "This Gmail address is already registered to another account."}), 400

    success, msg = OtpService.generate_otp(
        email=new_email,
        purpose=OtpPurpose.EMAIL_CHANGE_NEW,
        employee_id=user.get("employee_id")
    )
    if not success:
        return jsonify({"error": msg}), 400

    resp_payload = {
        "success": True,
        "message": f"Verification code sent to {new_email}. Valid for 10 minutes."
    }
    if Config.is_development():
        debug_otp = OtpService.get_debug_otp(email=new_email, purpose=OtpPurpose.EMAIL_CHANGE_NEW)
        if debug_otp:
            resp_payload["debug_otp"] = debug_otp

    return jsonify(resp_payload)


@auth_bp.route("/change-email/confirm", methods=["POST"])
@require_auth
def confirm_change_email():
    """Step 4: Verifies OTP for the new Gmail and commits the update to the persistent database."""
    user = request.current_user
    data = request.get_json(silent=True) or {}
    new_email = data.get("new_email", "").strip().lower()
    otp = data.get("otp", "").strip()
    conf_token = data.get("confirmation_token", "").strip()

    if not new_email or not otp or not conf_token:
        return jsonify({"error": "New Gmail, verification code, and authorization token are required."}), 400

    db = get_db()
    now = datetime.now(timezone.utc)
    auth_doc = db.change_email_confirmations.find_one({
        "token": conf_token,
        "employee_id": user["employee_id"],
        "expires_at": {"$gt": now}
    })
    if not auth_doc:
        return jsonify({"error": "Authorization token expired. Please start email change flow again."}), 403

    # Verify new email OTP
    verified, msg, _ = OtpService.verify_otp(
        email=new_email,
        otp_plain=otp,
        purpose=OtpPurpose.EMAIL_CHANGE_NEW,
        consume=True
    )
    if not verified:
        return jsonify({"error": msg}), 400

    old_email = user.get("email")

    # Update database
    db.users.update_one(
        {"employee_id": user["employee_id"]},
        {
            "$set": {
                "email": new_email,
                "personal_email": new_email,
                "is_email_verified": True,
                "updated_at": now
            }
        }
    )

    # Invalidate token
    db.change_email_confirmations.delete_many({"employee_id": user["employee_id"]})

    # Audit log
    AuditService.log_action(
        actor=user,
        action="CHANGE_LOGIN_EMAIL",
        target_type="user",
        target_id=user["employee_id"],
        details={"old_email": old_email, "new_email": new_email},
        ip_address=request.remote_addr
    )

    # Dispatch security notification to old email and new email
    ExternalNotificationService.send_email(
        recipient_email=old_email,
        subject="AI Samrat HRMS — Your Login Email Address Was Changed",
        body=(
            f"Dear {user.get('full_name')},\n\n"
            f"Your AI Samrat HRMS login email address was changed to {new_email} on {now.strftime('%Y-%m-%d %H:%M:%S UTC')}.\n"
            f"If you did not authorize this change, please contact HR administration immediately.\n\n"
            f"Warm regards,\nAI Samrat HRMS Security Team"
        ),
        recipient_id=user["employee_id"],
        category="SECURITY_ALERT"
    )

    ExternalNotificationService.send_email(
        recipient_email=new_email,
        subject="AI Samrat HRMS — New Login Email Verified",
        body=(
            f"Dear {user.get('full_name')},\n\n"
            f"This email address has been verified as your active login and recovery email for AI Samrat HRMS.\n\n"
            f"Warm regards,\nAI Samrat HRMS Security Team"
        ),
        recipient_id=user["employee_id"],
        category="SECURITY_CONFIRMATION"
    )

    return jsonify({
        "success": True,
        "message": f"Login email successfully changed to {new_email}."
    })
