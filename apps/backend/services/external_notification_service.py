import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
import requests
from database.connection import get_db

logger = logging.getLogger(__name__)

FORBIDDEN_EXTERNAL_KEYWORDS = [
    "salary", "payslip", "bank account", "ifsc", "pan number", 
    "aadhaar", "net pay", "ctc", "gross pay", "complaint"
]


class ExternalNotificationService:
    """
    Reliable, modular external notification service for Email and WhatsApp Business dispatch.
    
    Adheres strictly to enterprise data protection policies:
    - Automatically audits all dispatch attempts with status and provider IDs.
    - Idempotency deduplication prevents duplicate notifications.
    - Prohibits transmission of confidential payroll, banking, or disciplinary records.
    - Gracefully enters SIMULATED mode when external provider credentials are not configured.
    """

    @classmethod
    def is_email_configured(cls) -> bool:
        enabled_env = os.getenv("EMAIL_ENABLED")
        if enabled_env is not None and enabled_env.strip().lower() in ("false", "0", "no"):
            return False
        host = (os.getenv("SMTP_HOST") or "").strip()
        user = (os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME") or "").strip()
        # Email is considered configured if host and user/credentials are supplied,
        # or if EMAIL_ENABLED is explicitly true with a host.
        if enabled_env is not None and enabled_env.strip().lower() in ("true", "1", "yes") and host:
            return True
        return bool(host and user)

    @classmethod
    def is_whatsapp_configured(cls) -> bool:
        enabled = os.getenv("WHATSAPP_ENABLED", "false").lower() in ("true", "1", "yes")
        token = os.getenv("WHATSAPP_ACCESS_TOKEN")
        phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        return bool(enabled and token and phone_id)

    @classmethod
    def _contains_forbidden_terms(cls, text: str) -> bool:
        if not text:
            return False
        lower = text.lower()
        return any(term in lower for term in FORBIDDEN_EXTERNAL_KEYWORDS)

    @classmethod
    def log_dispatch(
        cls,
        channel: str,
        recipient_target: str,
        recipient_id: str | None,
        category: str,
        subject: str,
        body: str,
        status: str,
        provider_message_id: str | None = None,
        failure_reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        db = get_db()
        log_entry = {
            "channel": channel.upper(),
            "recipient_target": recipient_target,
            "recipient_id": recipient_id,
            "category": category.upper(),
            "subject": subject,
            "body": body[:500] if body else "",
            "status": status,
            "provider_message_id": provider_message_id,
            "failure_reason": failure_reason,
            "idempotency_key": idempotency_key,
            "created_at": datetime.now(timezone.utc),
        }
        try:
            db.external_message_logs.insert_one(log_entry)
        except Exception as e:
            logger.warning("Could not write external message log to DB: %s", e)
        return log_entry

    @classmethod
    def send_email(
        cls,
        recipient_email: str,
        subject: str,
        body: str,
        recipient_id: str | None = None,
        category: str = "GENERAL",
        idempotency_key: str | None = None,
        cc_email: str | None = None,
    ) -> dict:
        """Dispatches an enterprise email with deduplication and delivery audit logging."""
        db = get_db()
        recipient_email = (recipient_email or "").strip()
        cc_email = (cc_email or "").strip() or None
        if not recipient_email or "@" not in recipient_email:
            return cls.log_dispatch(
                "EMAIL", recipient_email or "UNKNOWN", recipient_id, category, subject, body,
                "FAILED", failure_reason="Invalid recipient email address", idempotency_key=idempotency_key
            )

        # Idempotency check
        if idempotency_key:
            existing = db.external_message_logs.find_one({
                "channel": "EMAIL",
                "idempotency_key": idempotency_key,
                "status": {"$in": ["DELIVERED", "SIMULATED_NO_CREDENTIALS"]}
            })
            if existing:
                logger.info("Email with idempotency key %s already sent.", idempotency_key)
                return existing

        # Privacy guard
        if cls._contains_forbidden_terms(subject) or cls._contains_forbidden_terms(body):
            logger.warning("Email dispatch blocked by privacy policy: confidential HR terms detected.")
            return cls.log_dispatch(
                "EMAIL", recipient_email, recipient_id, category, subject, body,
                "BLOCKED_PRIVACY", failure_reason="Confidential HR terms cannot be sent via external email",
                idempotency_key=idempotency_key
            )

        # Check configuration
        if not cls.is_email_configured():
            logger.info("Email provider not active/configured. Logging as SIMULATED_NO_CREDENTIALS.")
            res = cls.log_dispatch(
                "EMAIL", recipient_email, recipient_id, category, subject, body,
                "SIMULATED_NO_CREDENTIALS",
                provider_message_id=f"sim_email_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                failure_reason="SMTP provider credentials not configured in environment (SMTP_HOST / SMTP_USER).",
                idempotency_key=idempotency_key
            )
            if cc_email:
                res["cc_email"] = cc_email
            return res

        # Real SMTP delivery
        try:
            host = os.getenv("SMTP_HOST", "").strip()
            port = int(os.getenv("SMTP_PORT", "587"))
            user = (os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME") or "").strip()
            password = os.getenv("SMTP_PASSWORD", "")
            sender = (os.getenv("SMTP_FROM") or user or "noreply@aisamrat.com").strip()
            use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            if "<" not in sender and "@" in sender:
                msg["From"] = f"AI Samrat HRMS <{sender}>"
            else:
                msg["From"] = sender
            msg["To"] = recipient_email
            recipients = [recipient_email]
            if cc_email:
                msg["Cc"] = cc_email
                recipients.append(cc_email)
            msg.attach(MIMEText(body, "plain"))

            # Determine envelope sender
            envelope_sender = sender
            if "<" in sender and ">" in sender:
                envelope_sender = sender.split("<")[1].split(">")[0].strip()

            # Connect via SSL for port 465, or standard SMTP + STARTTLS for port 587/25
            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=15)
            else:
                server = smtplib.SMTP(host, port, timeout=15)
                if use_tls:
                    server.starttls()

            with server:
                if user and password:
                    server.login(user, password)
                server.sendmail(envelope_sender, recipients, msg.as_string())

            logger.info("Successfully dispatched email to %s (Subject: %s)", recipient_email, subject)
            res = cls.log_dispatch(
                "EMAIL", recipient_email, recipient_id, category, subject, body,
                "DELIVERED", provider_message_id=f"smtp_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                idempotency_key=idempotency_key
            )
            if cc_email:
                res["cc_email"] = cc_email
            return res
        except smtplib.SMTPAuthenticationError as e:
            err_msg = f"SMTP Authentication failed: {e}. If using Gmail, an App Password is required."
            logger.error(err_msg)
            res = cls.log_dispatch(
                "EMAIL", recipient_email, recipient_id, category, subject, body,
                "FAILED", failure_reason=err_msg, idempotency_key=idempotency_key
            )
            if cc_email:
                res["cc_email"] = cc_email
            return res
        except Exception as e:
            err_msg = f"SMTP dispatch error: {e}"
            logger.error("Failed to send email to %s: %s", recipient_email, err_msg)
            res = cls.log_dispatch(
                "EMAIL", recipient_email, recipient_id, category, subject, body,
                "FAILED", failure_reason=err_msg, idempotency_key=idempotency_key
            )
            if cc_email:
                res["cc_email"] = cc_email
            return res

    @classmethod
    def send_whatsapp(
        cls,
        recipient_phone: str,
        message: str,
        recipient_id: str | None = None,
        category: str = "GENERAL",
        template_name: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """Dispatches an enterprise WhatsApp notification adhering to consent and template standards."""
        db = get_db()
        recipient_phone = (recipient_phone or "").strip().replace(" ", "").replace("-", "")
        if not recipient_phone or len(recipient_phone) < 8:
            return cls.log_dispatch(
                "WHATSAPP", recipient_phone or "UNKNOWN", recipient_id, category, template_name or "TEXT", message,
                "FAILED", failure_reason="Invalid recipient phone number", idempotency_key=idempotency_key
            )

        # Idempotency check
        if idempotency_key:
            existing = db.external_message_logs.find_one({
                "channel": "WHATSAPP",
                "idempotency_key": idempotency_key,
                "status": {"$in": ["DELIVERED", "SIMULATED_NO_CREDENTIALS"]}
            })
            if existing:
                logger.info("WhatsApp message with idempotency key %s already sent.", idempotency_key)
                return existing

        # Privacy guard
        if cls._contains_forbidden_terms(message):
            logger.warning("WhatsApp dispatch blocked by privacy policy: confidential HR terms detected.")
            return cls.log_dispatch(
                "WHATSAPP", recipient_phone, recipient_id, category, template_name or "TEXT", message,
                "BLOCKED_PRIVACY", failure_reason="Confidential HR records cannot be sent via external WhatsApp",
                idempotency_key=idempotency_key
            )

        # Check recipient consent / opt-in
        if recipient_id:
            user = db.users.find_one({"employee_id": recipient_id})
            if user and user.get("whatsapp_opt_in") is False:
                logger.info("WhatsApp dispatch skipped for %s: user opted out.", recipient_id)
                return cls.log_dispatch(
                    "WHATSAPP", recipient_phone, recipient_id, category, template_name or "TEXT", message,
                    "SKIPPED_OPT_OUT", failure_reason="User has explicitly opted out of WhatsApp alerts.",
                    idempotency_key=idempotency_key
                )

        # Check configuration
        if not cls.is_whatsapp_configured():
            logger.info("WhatsApp Business API not configured. Logging as SIMULATED_NO_CREDENTIALS.")
            return cls.log_dispatch(
                "WHATSAPP", recipient_phone, recipient_id, category, template_name or "TEXT", message,
                "SIMULATED_NO_CREDENTIALS",
                provider_message_id=f"sim_wa_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                failure_reason="WhatsApp Business Cloud API credentials not configured in environment.",
                idempotency_key=idempotency_key
            )

        # Real WhatsApp Business Platform / Meta Cloud API delivery
        try:
            api_url = os.getenv("WHATSAPP_API_URL") or "https://graph.facebook.com/v19.0"
            phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
            access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")

            endpoint = f"{api_url.rstrip('/')}/{phone_id}/messages"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            if template_name:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": recipient_phone,
                    "type": "template",
                    "template": {
                        "name": template_name,
                        "language": {"code": "en_US"}
                    }
                }
            else:
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": recipient_phone,
                    "type": "text",
                    "text": {"preview_url": False, "body": message}
                }

            resp = requests.post(endpoint, json=payload, headers=headers, timeout=10)
            res_json = resp.json() if resp.status_code == 200 else {}
            provider_id = (res_json.get("messages") or [{}])[0].get("id")

            if resp.status_code in (200, 201):
                logger.info("Successfully dispatched WhatsApp message to %s", recipient_phone)
                return cls.log_dispatch(
                    "WHATSAPP", recipient_phone, recipient_id, category, template_name or "TEXT", message,
                    "DELIVERED", provider_message_id=provider_id, idempotency_key=idempotency_key
                )
            else:
                err_msg = res_json.get("error", {}).get("message") or resp.text
                logger.error("WhatsApp provider rejected dispatch: %s", err_msg)
                return cls.log_dispatch(
                    "WHATSAPP", recipient_phone, recipient_id, category, template_name or "TEXT", message,
                    "FAILED", failure_reason=err_msg, idempotency_key=idempotency_key
                )
        except Exception as e:
            logger.error("Failed to send WhatsApp message to %s: %s", recipient_phone, e)
            return cls.log_dispatch(
                "WHATSAPP", recipient_phone, recipient_id, category, template_name or "TEXT", message,
                "FAILED", failure_reason=str(e), idempotency_key=idempotency_key
            )

    @classmethod
    def dispatch_birthday_greeting(cls, user: dict, target_year: int) -> dict:
        """Dispatches external email and WhatsApp birthday wishes to the celebrating employee."""
        emp_id = user["employee_id"]
        full_name = user.get("full_name", "Valued Colleague")
        email = user.get("email")
        phone = user.get("phone") or user.get("contact_number")

        results = {}
        if email:
            email_idempotency = f"bday_ext_email_{emp_id}_{target_year}"
            results["email"] = cls.send_email(
                recipient_email=email,
                subject=f"🎉 Happy Birthday from AI Samrat HRMS, {full_name}!",
                body=(
                    f"Dear {full_name},\n\n"
                    f"On behalf of everyone at AI Samrat, we wish you a joyous and fulfilling Happy Birthday! "
                    f"Thank you for your valuable dedication and contributions to our team.\n\n"
                    f"Wishing you continued health, happiness, and success in the year ahead!\n\n"
                    f"Warm regards,\nAI Samrat HR Team"
                ),
                recipient_id=emp_id,
                category="BIRTHDAY_PERSONAL",
                idempotency_key=email_idempotency,
            )

        if phone:
            wa_idempotency = f"bday_ext_wa_{emp_id}_{target_year}"
            results["whatsapp"] = cls.send_whatsapp(
                recipient_phone=phone,
                message=f"🎉 Happy Birthday, {full_name}! The entire AI Samrat team wishes you a fantastic day and a wonderful year ahead!",
                recipient_id=emp_id,
                category="BIRTHDAY_PERSONAL",
                idempotency_key=wa_idempotency,
            )

        return results

    @classmethod
    def dispatch_birthday_announcement(cls, celebrating_user: dict, all_active_users: list, target_year: int) -> int:
        """Dispatches company-wide birthday announcement to other active employees."""
        full_name = celebrating_user.get("full_name", "Our Colleague")
        dept = celebrating_user.get("department", "Team")
        celebrant_id = celebrating_user["employee_id"]

        count = 0
        for u in all_active_users:
            if u["employee_id"] == celebrant_id:
                continue
            email = u.get("email")
            if email:
                idempotency = f"bday_ext_announce_{celebrant_id}_to_{u['employee_id']}_{target_year}"
                cls.send_email(
                    recipient_email=email,
                    subject=f"🎂 Celebrating {full_name}'s Birthday Today!",
                    body=(
                        f"Hello {u.get('full_name', 'Colleague')},\n\n"
                        f"Today we celebrate the birthday of {full_name} from the {dept} department! "
                        f"Please join us in wishing them a wonderful day!\n\n"
                        f"Best regards,\nAI Samrat HRMS"
                    ),
                    recipient_id=u["employee_id"],
                    category="BIRTHDAY_ANNOUNCEMENT",
                    idempotency_key=idempotency,
                )
                count += 1
        return count

    @classmethod
    def dispatch_monthly_announcement(cls, monthly_summary: str, all_active_users: list, year: int, month: int) -> int:
        """Dispatches the monthly birthday announcement email to all active corporate employees."""
        count = 0
        for u in all_active_users:
            email = u.get("email")
            if email:
                idempotency = f"bday_ext_monthly_to_{u['employee_id']}_{year}_{month:02d}"
                cls.send_email(
                    recipient_email=email,
                    subject=f"🎂 AI Samrat Birthday Celebrations for This Month",
                    body=(
                        f"Hello {u.get('full_name', 'Team')},\n\n"
                        f"As we begin this month, let's celebrate our colleagues having birthdays:\n\n"
                        f"{monthly_summary}\n\n"
                        f"Wishing all our celebrants a memorable and joyful month!\n\n"
                        f"Warm regards,\nAI Samrat HRMS"
                    ),
                    recipient_id=u["employee_id"],
                    category="BIRTHDAY_MONTHLY",
                    idempotency_key=idempotency,
                )
                count += 1
        return count

    @classmethod
    def get_delivery_logs(cls, recipient_id: str | None = None, channel: str | None = None, limit: int = 50) -> list:
        """Retrieves delivery audit records."""
        db = get_db()
        q = {}
        if recipient_id:
            q["recipient_id"] = recipient_id
        if channel:
            q["channel"] = channel.upper()
        return list(db.external_message_logs.find(q).sort("created_at", -1).limit(limit))
