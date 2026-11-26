import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any

from backend.database.connection import get_db
from backend.services.external_notification_service import ExternalNotificationService

logger = logging.getLogger(__name__)

OTP_EXPIRY_MINUTES = 5
MAX_VERIFICATION_ATTEMPTS = 5
MIN_RESEND_INTERVAL_SECONDS = 60
MAX_HOURLY_RESENDS = 5


class OtpPurpose:
    ACTIVATION = "ACTIVATION"
    PASSWORD_RESET = "PASSWORD_RESET"
    EMAIL_CHANGE_CURRENT = "EMAIL_CHANGE_CURRENT"
    EMAIL_CHANGE_NEW = "EMAIL_CHANGE_NEW"
    PASSWORD_CHANGE = "PASSWORD_CHANGE"

    ALL_PURPOSES = [ACTIVATION, PASSWORD_RESET, EMAIL_CHANGE_CURRENT, EMAIL_CHANGE_NEW, PASSWORD_CHANGE]


class OtpService:
    """
    Centralized OTP generation, hashing, rate-limiting, and verification engine.
    Ensures that plain OTPs are never stored in the database or exposed in responses.
    Applies uniformly across all 4 business roles: Employee, Team Lead, Manager, and HR.
    """

    _dev_latest_otps: Dict[str, Dict[str, Any]] = {}
    _last_generated_otp: Optional[str] = None

    @staticmethod
    def _hash_otp(otp_plain: str) -> str:
        """Computes SHA-256 hash of plain OTP for secure storage."""
        return hashlib.sha256(otp_plain.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_email(email: str) -> bool:
        if not email or "@" not in email:
            return False
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        return bool(re.match(pattern, email.strip()))

    @classmethod
    def generate_otp(
        cls,
        email: str,
        purpose: str,
        employee_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str]:
        """
        Generates a secure 6-digit OTP, stores its SHA-256 hash, and dispatches via email.
        Enforces rate limiting (60s resend cooldown, 5/hour), single-use invalidation,
        and 5-minute expiry.
        Returns: (success: bool, message: str)
        """
        db = get_db()
        email_clean = (email or "").strip().lower()

        if not cls._validate_email(email_clean):
            return False, "Invalid email address format."

        if purpose not in OtpPurpose.ALL_PURPOSES:
            return False, f"Invalid OTP purpose: {purpose}"

        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)

        # 1. Global hourly rate limiting across all requests in the last hour
        all_recent_tokens = list(db.otp_tokens.find({
            "email": email_clean,
            "purpose": purpose
        }))
        recent_count = 0
        for tok in all_recent_tokens:
            c_at = tok.get("created_at")
            if c_at:
                if c_at.tzinfo is None:
                    c_at = c_at.replace(tzinfo=timezone.utc)
                if c_at > one_hour_ago:
                    recent_count += 1

        if recent_count >= MAX_HOURLY_RESENDS:
            return False, f"Maximum verification requests reached for this hour ({MAX_HOURLY_RESENDS} per hour). Please try again later."

        # 2. Resend interval cooldown check (60 seconds)
        latest_token = db.otp_tokens.find_one(
            {"email": email_clean, "purpose": purpose},
            sort=[("created_at", -1)]
        )
        if latest_token:
            last_sent = latest_token.get("last_sent_at") or latest_token.get("created_at")
            if last_sent:
                if last_sent.tzinfo is None:
                    last_sent = last_sent.replace(tzinfo=timezone.utc)
                elapsed = (now - last_sent).total_seconds()
                if elapsed < MIN_RESEND_INTERVAL_SECONDS:
                    wait_sec = int(MIN_RESEND_INTERVAL_SECONDS - elapsed)
                    return False, f"Please wait {wait_sec} seconds before requesting a new code."

        # 3. Invalidate any older unused tokens for this email and purpose (single active code rule)
        db.otp_tokens.update_many(
            {"email": email_clean, "purpose": purpose, "is_used": False},
            {"$set": {"is_used": True, "invalidated_at": now, "invalidated_reason": "SUPERSEDED_BY_NEW_REQUEST"}}
        )

        # 4. Generate cryptographically secure 6-digit numeric code
        otp_plain = f"{secrets.randbelow(900000) + 100000}"
        otp_hash = cls._hash_otp(otp_plain)
        expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

        # REVEAL OTP FOR TESTING (Console Terminal Logs)
        print("\n" + "=" * 60, flush=True)
        print(f"[DEV TESTING] OTP: {otp_plain}", flush=True)
        print(f"[DEV TESTING] Target: {email_clean} | Purpose: {purpose} | EmpID: {employee_id or 'N/A'}", flush=True)
        print("=" * 60 + "\n", flush=True)
        logger.info("[DEV TESTING] OTP: %s generated for %s [%s]", otp_plain, email_clean, purpose)

        # Cache debug OTP in memory for development inspection & JSON responses
        cls._last_generated_otp = otp_plain
        cls._dev_latest_otps[f"{email_clean}:{purpose}"] = {
            "otp": otp_plain,
            "email": email_clean,
            "purpose": purpose,
            "employee_id": employee_id,
            "expires_at": expires_at,
            "created_at": now
        }

        doc = {
            "email": email_clean,
            "otp_hash": otp_hash,
            "purpose": purpose,
            "employee_id": employee_id,
            "metadata": metadata or {},
            "attempts": 0,
            "is_used": False,
            "created_at": now,
            "last_sent_at": now,
            "expires_at": expires_at
        }
        db.otp_tokens.insert_one(doc)

        # 5. Format message and dispatch via ExternalNotificationService
        subject_map = {
            OtpPurpose.ACTIVATION: "AI Samrat HRMS — Account Activation Verification Code",
            OtpPurpose.PASSWORD_RESET: "AI Samrat HRMS — Password Reset Verification Code",
            OtpPurpose.EMAIL_CHANGE_CURRENT: "AI Samrat HRMS — Verify Current Email for Update",
            OtpPurpose.EMAIL_CHANGE_NEW: "AI Samrat HRMS — Verify New Gmail Address",
            OtpPurpose.PASSWORD_CHANGE: "AI Samrat HRMS — Password Change Verification Code"
        }
        subject = subject_map.get(purpose, "AI Samrat HRMS — Verification Code")

        body = (
            f"Hello,\n\n"
            f"Your verification code for AI Samrat HRMS ({purpose.replace('_', ' ').title()}) is:\n\n"
            f"    {otp_plain}\n\n"
            f"This code will expire in {OTP_EXPIRY_MINUTES} minutes.\n"
            f"If you did not request this verification, please contact HR administration immediately.\n\n"
            f"Warm regards,\n"
            f"AI Samrat HRMS Security Team"
        )

        idempotency_key = f"otp_{purpose}_{email_clean}_{now.strftime('%Y%m%d%H%M%S%f')}"

        from config import Config
        is_dev_mode = Config.is_dev_otp_mode()

        if is_dev_mode:
            # DEVELOPMENT OTP MODE:
            # 1. Suppress real outbound SMTP email delivery
            # 2. Record in-memory for protected development interface
            cls._dev_latest_otps[f"{email_clean}:{purpose}"] = {
                "otp": otp_plain,
                "email": email_clean,
                "purpose": purpose,
                "employee_id": employee_id,
                "expires_at": expires_at,
                "created_at": now
            }

            # 3. Print prominent, clearly labeled banner to local backend development console
            console_banner = (
                "\n" + "=" * 80 + "\n"
                " [DEVELOPMENT OTP MODE ACTIVE]\n"
                f"  Target Recipient: {email_clean}\n"
                f"  Employee ID:      {employee_id or 'N/A'}\n"
                f"  Purpose:          {purpose}\n"
                f"  Generated OTP:    {otp_plain}\n"
                f"  Validity:         {OTP_EXPIRY_MINUTES} minutes (Single-use, max {MAX_VERIFICATION_ATTEMPTS} attempts)\n"
                "  Notice:           Actual SMTP email delivery suppressed in development mode.\n"
                + "=" * 80 + "\n"
            )
            print(console_banner, flush=True)
            logger.info("[DEVELOPMENT OTP MODE] Code generated for %s [%s]", email_clean, purpose)

            # 4. Log simulated dispatch in audit logs
            ExternalNotificationService.log_dispatch(
                channel="EMAIL",
                recipient_target=email_clean,
                recipient_id=employee_id,
                category=f"OTP_{purpose}",
                subject=subject,
                body=body,
                status="DEV_MODE_SIMULATED",
                provider_message_id=f"dev_otp_{now.strftime('%Y%m%d%H%M%S%f')}",
                idempotency_key=idempotency_key
            )

            return True, f"Verification code generated for {email_clean}. Valid for {OTP_EXPIRY_MINUTES} minutes."

        # PRODUCTION / REAL SMTP DELIVERY MODE:
        dispatch_res = ExternalNotificationService.send_email(
            recipient_email=email_clean,
            subject=subject,
            body=body,
            recipient_id=employee_id,
            category=f"OTP_{purpose}",
            idempotency_key=idempotency_key
        )

        # 6. Verify dispatch result
        dispatch_status = dispatch_res.get("status")
        if dispatch_status == "FAILED":
            fail_reason = dispatch_res.get("failure_reason", "Email delivery failed.")
            logger.error("OTP email delivery failed for %s: %s", email_clean, fail_reason)
            return False, f"Failed to deliver verification code: {fail_reason}"
        elif dispatch_status == "BLOCKED_PRIVACY":
            return False, "Verification email was blocked by privacy policy."

        logger.info(
            "Generated OTP for %s [purpose=%s, status=%s]. Valid for %d mins.",
            email_clean, purpose, dispatch_status, OTP_EXPIRY_MINUTES
        )
        return True, f"Verification code sent to {email_clean}. Valid for {OTP_EXPIRY_MINUTES} minutes."


    @classmethod
    def verify_otp(
        cls,
        email: str,
        otp_plain: str,
        purpose: str,
        consume: bool = True
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Verifies candidate OTP against stored SHA-256 hash.
        Enforces 5-minute expiration, max 5 attempts, single-use,
        and returns distinct, clear error messages for expired or reused codes.
        """
        db = get_db()
        email_clean = (email or "").strip().lower()
        candidate = (otp_plain or "").strip()

        if not email_clean or not candidate:
            return False, "Email and verification code are required.", None

        if len(candidate) != 6 or not candidate.isdigit():
            return False, "Verification code must be exactly 6 digits.", None

        now = datetime.now(timezone.utc)

        # 1. Query all unused tokens for this email and purpose, finding active unexpired token
        tokens = list(db.otp_tokens.find({
            "email": email_clean,
            "purpose": purpose,
            "is_used": False
        }, sort=[("created_at", -1)]))

        token_doc = None
        for tok in tokens:
            exp = tok.get("expires_at")
            if exp:
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp > now:
                    token_doc = tok
                    break

        if not token_doc:
            # Provide clear, specific diagnostic errors for expired vs used vs invalidated tokens
            candidate_hash = cls._hash_otp(candidate)
            recent_tokens = list(db.otp_tokens.find(
                {"email": email_clean, "purpose": purpose},
                sort=[("created_at", -1)],
                limit=10
            ))

            for tok in recent_tokens:
                if hmac.compare_digest(candidate_hash, tok.get("otp_hash", "")):
                    if tok.get("invalidated_reason") == "MAX_ATTEMPTS_EXCEEDED":
                        return False, "Too many incorrect attempts. This code has been invalidated. Please request a new code.", None
                    if tok.get("is_used"):
                        return False, "This verification code has already been used. Please request a new code.", None
                    if tok.get("expires_at"):
                        exp = tok["expires_at"]
                        if exp.tzinfo is None:
                            exp = exp.replace(tzinfo=timezone.utc)
                        if exp <= now:
                            return False, f"This verification code has expired (valid for {OTP_EXPIRY_MINUTES} minutes). Please request a new code.", None

            # Check if any token exists that just expired
            latest_unexpired = db.otp_tokens.find_one({
                "email": email_clean,
                "purpose": purpose,
                "is_used": False
            }, sort=[("created_at", -1)])
            if latest_unexpired and latest_unexpired.get("expires_at"):
                exp = latest_unexpired["expires_at"]
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp <= now:
                    return False, f"This verification code has expired (valid for {OTP_EXPIRY_MINUTES} minutes). Please request a new code.", None

            return False, "Invalid or expired verification code. Please request a new code.", None

        # 2. Check maximum attempts
        current_attempts = token_doc.get("attempts", 0)
        if current_attempts >= MAX_VERIFICATION_ATTEMPTS:
            db.otp_tokens.update_one(
                {"_id": token_doc["_id"]},
                {"$set": {"is_used": True, "invalidated_reason": "MAX_ATTEMPTS_EXCEEDED"}}
            )
            return False, "Too many incorrect attempts. This code has been invalidated. Please request a new code.", None

        candidate_hash = cls._hash_otp(candidate)
        stored_hash = token_doc.get("otp_hash", "")

        # 3. Constant-time comparison
        is_match = hmac.compare_digest(candidate_hash, stored_hash)

        if not is_match:
            new_attempts = current_attempts + 1
            remaining = MAX_VERIFICATION_ATTEMPTS - new_attempts
            if remaining <= 0:
                db.otp_tokens.update_one(
                    {"_id": token_doc["_id"]},
                    {"$set": {"attempts": new_attempts, "is_used": True, "invalidated_reason": "MAX_ATTEMPTS_EXCEEDED"}}
                )
                return False, "Too many incorrect attempts. This code has been invalidated. Please request a new code.", None

            db.otp_tokens.update_one(
                {"_id": token_doc["_id"]},
                {"$set": {"attempts": new_attempts}}
            )
            return False, f"Incorrect verification code. {remaining} attempt(s) remaining.", None

        # 4. Successfully matched — single-use consumption
        if consume:
            db.otp_tokens.update_one(
                {"_id": token_doc["_id"]},
                {"$set": {"is_used": True, "used_at": now}}
            )

        logger.info("Successfully verified OTP for %s [purpose=%s]", email_clean, purpose)
        return True, "Verification successful.", token_doc

    @classmethod
    def get_latest_otp_for_test(cls, email: str, purpose: str) -> Optional[str]:
        """
        Test helper method used ONLY in automated test execution.
        Extracts the generated OTP from simulated dispatch logs.
        """
        db = get_db()
        email_clean = (email or "").strip().lower()
        log = db.external_message_logs.find_one(
            {
                "recipient_target": email_clean,
                "category": f"OTP_{purpose}"
            },
            sort=[("created_at", -1)]
        )
        if not log:
            return None
        body = log.get("body", "")
        match = re.search(r"\b(\d{6})\b", body)
        return match.group(1) if match else None

    @classmethod
    def get_dev_otp(cls, email: str, purpose: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the latest generated OTP for dev testing.
        Strictly returns None if not in development OTP mode or if running in production.
        """
        from config import Config
        if not Config.is_dev_otp_mode():
            return None

        email_clean = (email or "").strip().lower()
        purpose_clean = (purpose or "").strip().upper()
        key = f"{email_clean}:{purpose_clean}"
        entry = cls._dev_latest_otps.get(key)
        if not entry:
            return None

        now = datetime.now(timezone.utc)
        exp = entry.get("expires_at")
        if exp:
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp <= now:
                return None

        # Verify against DB to ensure not already used or invalidated
        db = get_db()
        candidate_hash = cls._hash_otp(entry["otp"])
        active_tok = db.otp_tokens.find_one({
            "email": email_clean,
            "purpose": purpose_clean,
            "otp_hash": candidate_hash,
            "is_used": False
        })
        if not active_tok:
            return None

        return entry

    @classmethod
    def get_debug_otp(cls, email: Optional[str] = None, purpose: Optional[str] = None) -> Optional[str]:
        """
        Retrieves the generated 6-digit OTP for development/testing environments.
        Strictly returns None if running in production mode.
        """
        from config import Config
        if Config.is_production():
            return None

        email_clean = (email or "").strip().lower()
        purpose_clean = (purpose or "").strip().upper()

        if email_clean and purpose_clean:
            entry = cls._dev_latest_otps.get(f"{email_clean}:{purpose_clean}")
            if entry:
                return entry.get("otp")

        if email_clean:
            for p in OtpPurpose.ALL_PURPOSES:
                entry = cls._dev_latest_otps.get(f"{email_clean}:{p}")
                if entry:
                    return entry.get("otp")

        return cls._last_generated_otp

