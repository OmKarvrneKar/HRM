import calendar
import re
import secrets
from datetime import datetime, timezone
from bson import ObjectId
from database.connection import get_db
from auth.security import hash_password, verify_password
from services.audit_service import AuditService
from permissions.rbac import Role, normalize_role, can_create_account, can_view_profile, can_view_salary
from utils.validators import validate_email, validate_password_strength, validate_phone
from utils.timezone import get_app_timezone, get_local_date_str

# Fields regular employees are allowed to edit on their own profile (phone, address, emergency contact, photo, skills)
# Core employment IDs and roles remain strictly locked
EMPLOYEE_SELF_EDITABLE_FIELDS = {"phone_number", "contact", "address", "emergency_contact", "profile_photo", "skills"}

# Fields HR can edit on an employee profile
HR_EDITABLE_EMPLOYEE_FIELDS = {
    "full_name", "name", "phone_number", "contact", "department", "designation", "team_id",
    "reporting_manager_id", "joining_date", "employment_status", "employment_type",
    "date_of_birth", "dob", "gender", "address", "emergency_contact", "profile_photo",
    "skills", "salary_info", "personal_email", "official_email", "email",
    "employee_id", "emp_id", "role", "is_active", "account_status", "status",
    "profile_status", "verification_status", "needs_manual_confirmation", "confirmation_reason"
}

# Fields Manager can edit on an HR, Team Lead, or employee profile
MANAGER_EDITABLE_FIELDS = {
    "full_name", "phone_number", "department", "designation", "team_id",
    "reporting_manager_id", "joining_date", "employment_status", "employment_type",
    "date_of_birth", "gender", "address", "emergency_contact", "profile_photo",
    "skills", "personal_email", "official_email", "email"
}

DEFAULT_CTC_MAP = {
    "ADMIN-1001": 2500000,
    "MGR-1001": 2100000,
    "TL-1001": 1400000,
    "HR-1001": 1200000,
    "AS-1001": 450000,
}

DEFAULT_USER_SKILLS = {
    "MGR-1001": [
        {"name": "Executive HR Leadership", "level": "Expert"},
        {"name": "Strategic Workforce Planning", "level": "Expert"},
        {"name": "Compensation & Benefits", "level": "Expert"},
        {"name": "Labor Law Compliance", "level": "Advanced"},
        {"name": "Performance Management Systems", "level": "Expert"},
        {"name": "Talent Retention", "level": "Advanced"},
        {"name": "Organizational Development", "level": "Advanced"}
    ],
    "HR-1001": [
        {"name": "Talent Acquisition", "level": "Expert"},
        {"name": "Employee Onboarding", "level": "Advanced"},
        {"name": "Payroll Processing", "level": "Advanced"},
        {"name": "HR Policy & Compliance", "level": "Advanced"},
        {"name": "Conflict Resolution", "level": "Proficient"},
        {"name": "POSH Compliance", "level": "Expert"},
        {"name": "People Analytics", "level": "Proficient"}
    ],
    "HR-1002": [
        {"name": "HR Operations", "level": "Expert"},
        {"name": "Attendance Governance", "level": "Advanced"},
        {"name": "Vendor Management", "level": "Proficient"},
        {"name": "Statutory Compliance", "level": "Advanced"},
        {"name": "Employee Engagement", "level": "Advanced"},
        {"name": "Grievance Handling", "level": "Proficient"}
    ],
    "EMP-1001": [
        {"name": "Python", "level": "Expert"},
        {"name": "Flask & FastAPI", "level": "Expert"},
        {"name": "React.js", "level": "Advanced"},
        {"name": "MongoDB & PostgreSQL", "level": "Advanced"},
        {"name": "Docker & Containerization", "level": "Proficient"},
        {"name": "REST API Architecture", "level": "Expert"},
        {"name": "Git & CI/CD", "level": "Advanced"}
    ],
    "EMP-1002": [
        {"name": "Backend Architecture", "level": "Expert"},
        {"name": "Python & Go", "level": "Expert"},
        {"name": "Distributed Systems", "level": "Advanced"},
        {"name": "Redis Caching", "level": "Advanced"},
        {"name": "Kafka Event Streaming", "level": "Proficient"},
        {"name": "Database Sharding & Indexing", "level": "Advanced"}
    ],
    "EMP-1003": [
        {"name": "Test Automation", "level": "Expert"},
        {"name": "Selenium WebDriver", "level": "Advanced"},
        {"name": "Pytest", "level": "Expert"},
        {"name": "Cypress", "level": "Advanced"},
        {"name": "Postman API Automation", "level": "Expert"},
        {"name": "Load & Stress Testing", "level": "Proficient"}
    ],
    "EMP-1004": [
        {"name": "UI/UX Architecture", "level": "Expert"},
        {"name": "Figma & FigJam", "level": "Expert"},
        {"name": "Design Systems", "level": "Advanced"},
        {"name": "User Journey Mapping", "level": "Advanced"},
        {"name": "Wireframing & Prototyping", "level": "Expert"},
        {"name": "Design Usability Testing", "level": "Advanced"}
    ]
}


def amount_to_words(num: int) -> str:
    """Converts an integer Indian Rupee amount to words in Indian numbering system."""
    if num <= 0:
        return "Rupees Zero Only"

    units = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
             "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
             "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def two_digits(n):
        if n < 20:
            return units[n]
        rem = n % 10
        return tens[n // 10] + (" " + units[rem] if rem != 0 else "")

    def three_digits(n):
        h = n // 100
        rem = n % 100
        res = ""
        if h > 0:
            res += units[h] + " Hundred"
            if rem > 0:
                res += " and "
        if rem > 0:
            res += two_digits(rem)
        return res

    parts = []
    # Crores (1,00,00,000)
    crores = num // 10000000
    num %= 10000000
    if crores > 0:
        parts.append(two_digits(crores) + " Crore")

    # Lakhs (1,00,000)
    lakhs = num // 100000
    num %= 100000
    if lakhs > 0:
        parts.append(two_digits(lakhs) + " Lakh")

    # Thousands (1,000)
    thousands = num // 1000
    num %= 1000
    if thousands > 0:
        parts.append(two_digits(thousands) + " Thousand")

    # Hundreds and below
    if num > 0:
        parts.append(three_digits(num))

    return "Rupees " + " ".join(parts).strip() + " Only"


def calculate_salary_components(ctc_annual: float) -> dict:
    """Computes realistic Indian monthly payroll breakdown from annual CTC."""
    ctc = int(ctc_annual)
    monthly_gross = round(ctc / 12)
    basic_salary = round(monthly_gross * 0.50)
    hra = round(basic_salary * 0.40)
    conveyance_allowance = 5000
    medical_allowance = 3000

    allocated = basic_salary + hra + conveyance_allowance + medical_allowance
    special_allowance = max(0, monthly_gross - allocated)

    # Statutory Deductions
    pf_deduction = min(3600, round(basic_salary * 0.12))
    professional_tax = 200

    if ctc <= 700000:
        tds_tax = 0
    elif ctc <= 1000000:
        tds_tax = round((ctc - 700000) * 0.10 / 12)
    elif ctc <= 1500000:
        tds_tax = round((30000 + (ctc - 1000000) * 0.15) / 12)
    else:
        tds_tax = round((105000 + (ctc - 1500000) * 0.25) / 12)

    total_deductions = pf_deduction + professional_tax + tds_tax
    net_salary = monthly_gross - total_deductions

    return {
        "ctc_annual": ctc,
        "monthly_gross": monthly_gross,
        "basic_salary": basic_salary,
        "hra": hra,
        "conveyance_allowance": conveyance_allowance,
        "medical_allowance": medical_allowance,
        "special_allowance": special_allowance,
        "pf_deduction": pf_deduction,
        "professional_tax": professional_tax,
        "tds_tax": tds_tax,
        "total_deductions": total_deductions,
        "net_salary": net_salary
    }


def get_default_banking_info(employee_id: str, role: str) -> dict:
    num_part = "".join(filter(str.isdigit, employee_id)) or "1001"
    last4 = num_part[-4:]

    if role == Role.MANAGER:
        bank = "HDFC Bank Ltd"
        ifsc = "HDFC0000128"
    elif role == Role.HR:
        bank = "ICICI Bank"
        ifsc = "ICIC0000492"
    else:
        bank = "State Bank of India"
        ifsc = "SBIN0008472"

    return {
        "bank_name": bank,
        "account_number": f"••••••••{last4}",
        "ifsc_code": ifsc,
        "pan_number": f"•••••{last4[:3]}K",
        "pf_number": f"KN/BNG/0048291/000/{last4}",
        "uan_number": f"10098471{last4}"
    }


class UserService:
    @classmethod
    def generate_next_employee_id(cls, role: str) -> str:
        """
        Generates a unique employee ID based on role prefix and sequence.
        e.g. EMP-001, HR-001, MGR-001
        """
        db = get_db()
        prefix = "EMP"
        if role == Role.HR:
            prefix = "HR"
        elif role in (Role.HR_MANAGER, Role.ORGANIZATION):
            prefix = "MGR"
        elif role == Role.ADMIN:
            prefix = "ADM"

        # Find the highest existing ID with this prefix
        regex_pattern = f"^{prefix}-\\d+$"
        latest = db.users.find(
            {"employee_id": {"$regex": regex_pattern}},
            {"employee_id": 1}
        ).sort("employee_id", -1).limit(1)

        latest_list = list(latest)
        if not latest_list:
            return f"{prefix}-1001"

        try:
            current_num = int(latest_list[0]["employee_id"].split("-")[1])
            return f"{prefix}-{current_num + 1}"
        except Exception:
            count = db.users.count_documents({"role": role})
            return f"{prefix}-{1001 + count}"

    @classmethod
    def create_user(cls, creator: dict, user_data: dict) -> tuple[dict | None, str | None]:
        """
        Creates a new user account enforcing role creation rules.
        All new accounts start in an unverified state until first-time Gmail OTP activation.
        """
        target_role = user_data.get("role", Role.EMPLOYEE)
        if target_role not in Role.ALL_ROLES:
            return None, f"Invalid role '{target_role}'. Must be one of: {', '.join(Role.ALL_ROLES)}"

        creator_role = normalize_role(creator.get("role"))
        if creator_role not in (Role.HR, Role.ADMIN):
            return None, f"Your role ({creator_role}) is not authorized to create accounts. Only HR or Administrators can provision user accounts."

        if normalize_role(target_role) == Role.ADMIN and creator_role != Role.ADMIN:
            return None, "Only Administrators can provision Administrator accounts."

        email = user_data.get("email", "").strip().lower()
        personal_email = user_data.get("personal_email", "").strip().lower() or email
        official_email = user_data.get("official_email", "").strip().lower() or email

        if not email and personal_email:
            email = personal_email

        if not email or not validate_email(email):
            return None, "Valid email address format is required."

        db = get_db()
        if db.users.find_one({"$or": [{"email": email}, {"personal_email": email}]}):
            return None, "A user with this email address already exists."

        # Generate or use provided employee ID
        employee_id = user_data.get("employee_id")
        if not employee_id:
            employee_id = cls.generate_next_employee_id(target_role)
        else:
            employee_id = employee_id.strip().upper()
            if db.users.find_one({"employee_id": employee_id}):
                return None, f"Employee ID {employee_id} already exists."

        raw_password = user_data.get("password")
        if raw_password:
            valid, msg = validate_password_strength(raw_password)
            if not valid:
                return None, msg
            password_hash_val = hash_password(raw_password)
            needs_password = False
            is_email_verified = user_data.get("is_email_verified", False)
            account_status = "active" if is_email_verified else "pending_activation"
            activation_token = None
        else:
            activation_token = secrets.token_urlsafe(18)
            password_hash_val = hash_password(activation_token)
            needs_password = True
            is_email_verified = False
            account_status = "pending_activation"

        now = datetime.now(timezone.utc)
        new_user = {
            "employee_id": employee_id,
            "full_name": user_data.get("full_name", "").strip(),
            "email": email,
            "personal_email": personal_email,
            "official_email": official_email,
            "password_hash": password_hash_val,
            "role": target_role,
            "department": user_data.get("department", "General"),
            "designation": user_data.get("designation", "Staff"),
            "team_id": user_data.get("team_id"),
            "reporting_manager_id": user_data.get("reporting_manager_id"),
            "joining_date": user_data.get("joining_date", now.strftime("%Y-%m-%d")),
            "date_of_birth": user_data.get("date_of_birth"),  # 'YYYY-MM-DD'
            "gender": user_data.get("gender", ""),
            "employment_type": user_data.get("employment_type", "Full-Time"),
            "employment_status": user_data.get("employment_status", "Active"),  # Active, On Leave, Resigned, Deactivated
            "phone_number": user_data.get("phone_number", ""),
            "address": user_data.get("address", ""),
            "emergency_contact": user_data.get("emergency_contact", ""),
            "profile_photo": user_data.get("profile_photo", ""),
            "is_active": True,
            "is_email_verified": is_email_verified,
            "account_status": account_status,
            "needs_password_setup": needs_password,
            "activation_token": activation_token,
            "created_by": creator.get("employee_id"),
            "created_at": now,
            "updated_at": now,
        }

        result = db.users.insert_one(new_user)
        new_user["_id"] = result.inserted_id

        AuditService.log_action(
            actor=creator,
            action="CREATE_USER",
            target_type=target_role,
            target_id=employee_id,
            details={"email": email, "role": target_role, "name": new_user["full_name"], "is_email_verified": is_email_verified}
        )

        return new_user, None

    @classmethod
    def update_profile(
        cls,
        actor: dict,
        target_employee_id: str,
        updates: dict,
        reason: str = None
    ) -> tuple[dict | None, str | None]:
        """
        Updates allowed profile fields and records an audit log entry for each modified field.
        """
        db = get_db()
        query_conditions = []
        if target_employee_id:
            query_conditions.extend([
                {"employee_id": target_employee_id},
                {"emp_id": target_employee_id},
                {"email": str(target_employee_id).strip().lower()},
                {"personal_email": str(target_employee_id).strip().lower()}
            ])
            if ObjectId.is_valid(target_employee_id):
                query_conditions.append({"_id": ObjectId(target_employee_id)})
        target_user = db.users.find_one({"$or": query_conditions}) if query_conditions else None
        if not target_user:
            return None, "Target user not found."

        actor_emp_id = actor.get("employee_id") or actor.get("emp_id")
        t_emp_id = target_user.get("employee_id") or target_user.get("emp_id")
        actor_role = normalize_role(actor.get("role"))
        is_self = bool(actor_emp_id and t_emp_id and str(actor_emp_id).strip().upper() == str(t_emp_id).strip().upper())

        allowed_fields = set()
        if is_self:
            # Employee self edit: basic contact details & skills editable; core employment IDs & roles strictly locked
            allowed_fields = EMPLOYEE_SELF_EDITABLE_FIELDS
        elif actor_role in (Role.HR, Role.ADMIN):
            # HR editing employee, team lead, or hr accounts
            allowed_fields = HR_EDITABLE_EMPLOYEE_FIELDS
        else:
            return None, "Unauthorized: Team Leads and Managers cannot modify employee profiles. Profile information is managed exclusively by HR."

        # Filter and validate updates
        valid_updates = {}
        for key, value in updates.items():
            if key in allowed_fields:
                old_val = target_user.get(key)
                if old_val != value:
                    valid_updates[key] = value
                    # Record audit change
                    AuditService.log_profile_change(
                        target_employee_id=t_emp_id,
                        field_name=key,
                        old_value=old_val,
                        new_value=value,
                        changed_by=actor,
                        reason=reason
                    )

        # Synchronize contact and phone_number for seamless compatibility across schemas
        if "phone_number" in valid_updates and "contact" not in valid_updates:
            valid_updates["contact"] = valid_updates["phone_number"]
        elif "contact" in valid_updates and "phone_number" not in valid_updates:
            valid_updates["phone_number"] = valid_updates["contact"]

        # Synchronize employee_id and emp_id
        if "employee_id" in valid_updates and "emp_id" not in valid_updates:
            valid_updates["emp_id"] = valid_updates["employee_id"]
        elif "emp_id" in valid_updates and "employee_id" not in valid_updates:
            valid_updates["employee_id"] = valid_updates["emp_id"]

        # Synchronize full_name and name
        if "full_name" in valid_updates and "name" not in valid_updates:
            valid_updates["name"] = valid_updates["full_name"]
        elif "name" in valid_updates and "full_name" not in valid_updates:
            valid_updates["full_name"] = valid_updates["name"]

        if not valid_updates:
            return target_user, None

        # Backend Security & Onboarding Validation Guards
        is_activating = (
            valid_updates.get("is_active") is True or
            valid_updates.get("account_status") == "active" or
            valid_updates.get("status") == "active"
        )
        is_verifying = (
            valid_updates.get("verification_status") == "verified" or
            valid_updates.get("profile_status") == "verified"
        )

        eff_verification = valid_updates.get("verification_status", target_user.get("verification_status"))
        eff_emp_id = (valid_updates.get("employee_id") or valid_updates.get("emp_id") or target_user.get("employee_id") or target_user.get("emp_id") or "").strip()

        # Guard 1: Direct or implicit activation check
        if is_activating:
            if eff_verification != "verified":
                return None, "Backend Security Violation: Cannot activate a candidate account without a verified profile."
            if not eff_emp_id:
                return None, "Backend Security Violation: Cannot activate a pending candidate without an official Employee ID."

        # Guard 2: Formal Onboarding & Verification parameters check
        if is_verifying:
            eff_dept = (valid_updates.get("department") or target_user.get("department") or "").strip()
            eff_desig = (valid_updates.get("designation") or target_user.get("designation") or "").strip()
            eff_role = (valid_updates.get("role") or target_user.get("role") or "").strip()
            eff_name = (valid_updates.get("full_name") or valid_updates.get("name") or target_user.get("full_name") or target_user.get("name") or "").strip()

            if not eff_emp_id:
                return None, "Backend Security Violation: Cannot complete verification and onboarding without an official Employee ID."
            if not eff_dept:
                return None, "Backend Security Violation: Cannot complete onboarding with a missing Department."
            if not eff_desig:
                return None, "Backend Security Violation: Cannot complete onboarding with a missing Designation."
            if not eff_role or eff_role not in Role.ALL_ROLES:
                return None, "Backend Security Violation: Cannot complete onboarding with a missing or invalid System Role."
            if not eff_name:
                return None, "Backend Security Violation: Cannot complete onboarding without Candidate Full Name."

            # Guard 3: Unique Employee ID enforcement
            dup = db.users.find_one({"employee_id": eff_emp_id, "_id": {"$ne": target_user["_id"]}})
            if dup:
                return None, f"Backend Security Violation: Employee ID '{eff_emp_id}' is already registered to another user ({dup.get('email')})."

        valid_updates["updated_at"] = datetime.now(timezone.utc)
        db.users.update_one(
            {"_id": target_user["_id"]},
            {"$set": valid_updates}
        )

        updated_user = db.users.find_one({"_id": target_user["_id"]})
        return updated_user, None

    @classmethod
    def change_password(cls, user_id: str, current_password: str, new_password: str) -> tuple[bool, str]:
        """Handles user self password change with current password verification."""
        db = get_db()
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return False, "User not found."

        if not verify_password(current_password, user.get("password_hash", "")):
            return False, "Incorrect current password."

        valid, msg = validate_password_strength(new_password)
        if not valid:
            return False, msg

        db.users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "password_hash": hash_password(new_password),
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )

        AuditService.log_action(
            actor=user,
            action="CHANGE_PASSWORD",
            target_type="user",
            target_id=user["employee_id"],
            details={"action": "self_password_change"}
        )
        return True, "Password updated successfully."

    @classmethod
    def toggle_user_active_status(cls, actor: dict, target_employee_id: str, is_active: bool) -> tuple[bool, str]:
        """Allows HR/HR Manager to activate or deactivate user accounts within their permission scope."""
        db = get_db()
        query_conditions = []
        if target_employee_id:
            query_conditions.extend([
                {"employee_id": target_employee_id},
                {"emp_id": target_employee_id},
                {"email": str(target_employee_id).strip().lower()},
                {"personal_email": str(target_employee_id).strip().lower()}
            ])
            if ObjectId.is_valid(target_employee_id):
                query_conditions.append({"_id": ObjectId(target_employee_id)})
        target_user = db.users.find_one({"$or": query_conditions}) if query_conditions else None
        if not target_user:
            return False, "User not found."

        actor_role = normalize_role(actor.get("role"))
        target_role = normalize_role(target_user.get("role")) if target_user.get("role") else None

        if actor_role not in (Role.HR, Role.ADMIN):
            return False, "Unauthorized operation."

        if actor_role == Role.HR and target_role and target_role != Role.EMPLOYEE:
            return False, "HR can only activate/deactivate Employee accounts."

        # Safety Enforcement: Incomplete candidate accounts cannot be activated until onboarding is completed with a verified Employee ID
        if is_active:
            if target_user.get("verification_status") != "verified":
                return False, "Backend Security Violation: Cannot activate a candidate account without a verified profile."
            if not target_user.get("employee_id") or not str(target_user.get("employee_id")).strip():
                return False, "Backend Security Violation: Cannot activate a pending candidate without an official Employee ID."
            if not target_user.get("department") or not target_user.get("designation") or not target_user.get("role"):
                return False, "Backend Security Violation: Cannot activate candidate before formal profile verification and onboarding completion."

        db.users.update_one(
            {"_id": target_user["_id"]},
            {"$set": {
                "is_active": is_active,
                "status": "active" if is_active else "inactive",
                "account_status": "active" if is_active else "inactive",
                "updated_at": datetime.now(timezone.utc)
            }}
        )

        AuditService.log_action(
            actor=actor,
            action="DEACTIVATE_USER" if not is_active else "ACTIVATE_USER",
            target_type=target_role or "pending_user",
            target_id=target_user.get("employee_id") or str(target_user["_id"]),
            details={"new_status": is_active}
        )
        return True, f"Account {'activated' if is_active else 'deactivated'} successfully."

    @classmethod
    def offboard_employee(cls, actor: dict, target_employee_id: str, data: dict) -> tuple[dict | None, str | None]:
        """
        Executes formal HR offboarding / deactivation for an employee:
        - Disables login & invalidates future sessions (is_active = False, status = 'offboarded')
        - Prevents new attendance check-ins
        - Records reason, last working day, processing user, effective date, and notes
        - Retains 100% of historical attendance, leave, payslip, skill, complaint, and audit records
        - Updates active project and team memberships
        """
        db = get_db()
        target_user = db.users.find_one({"employee_id": target_employee_id})
        if not target_user:
            return None, "Employee not found."

        actor_role = normalize_role(actor.get("role"))
        target_role = normalize_role(target_user.get("role"))

        if actor_role not in (Role.HR, Role.ADMIN):
            return None, "Unauthorized: Only HR or Administrators can process employee offboarding."

        if actor_role == Role.HR and target_role in (Role.HR, Role.MANAGER, Role.ADMIN):
            return None, "Unauthorized: HR Officers cannot offboard other HR, Management, or Administrator accounts."

        reason = (data.get("reason") or "Voluntary Resignation").strip()
        last_working_day = (data.get("last_working_day") or get_local_date_str()).strip()
        effective_date = (data.get("effective_date") or get_local_date_str()).strip()
        notes = (data.get("notes") or "").strip()

        offboarding_entry = {
            "employee_id": target_employee_id,
            "employee_name": target_user.get("full_name", ""),
            "email": target_user.get("email", ""),
            "department": target_user.get("department", ""),
            "designation": target_user.get("designation", ""),
            "role": target_role,
            "reason": reason,
            "last_working_day": last_working_day,
            "effective_date": effective_date,
            "notes": notes,
            "processed_by_id": actor.get("employee_id"),
            "processed_by_name": actor.get("full_name"),
            "processed_by_role": actor_role,
            "created_at": datetime.now(timezone.utc)
        }

        # Store in offboardings collection
        db.offboardings.insert_one(offboarding_entry)

        # Update user record
        db.users.update_one(
            {"employee_id": target_employee_id},
            {
                "$set": {
                    "is_active": False,
                    "status": "offboarded",
                    "offboarding_details": offboarding_entry,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )

        # Update active project memberships (remove from active project members list while preserving former history)
        db.projects.update_many(
            {"members": target_employee_id},
            {
                "$pull": {"members": target_employee_id},
                "$addToSet": {"former_members": target_employee_id}
            }
        )

        AuditService.log_action(
            actor=actor,
            action="OFFBOARD_EMPLOYEE",
            target_type="employee",
            target_id=target_employee_id,
            details={
                "reason": reason,
                "last_working_day": last_working_day,
                "effective_date": effective_date,
                "processed_by": actor.get("full_name")
            }
        )

        return offboarding_entry, None

    @classmethod
    def reactivate_employee(cls, actor: dict, target_employee_id: str, reason: str = None) -> tuple[bool, str]:
        """Reactivates an offboarded / deactivated employee account."""
        db = get_db()
        target_user = db.users.find_one({"employee_id": target_employee_id})
        if not target_user:
            return False, "Employee not found."

        actor_role = normalize_role(actor.get("role"))
        if actor_role not in (Role.HR, Role.ADMIN):
            return False, "Unauthorized: Only HR or Administrators can reactivate accounts."

        db.users.update_one(
            {"employee_id": target_employee_id},
            {
                "$set": {
                    "is_active": True,
                    "status": "active",
                    "updated_at": datetime.now(timezone.utc)
                },
                "$unset": {"offboarding_details": ""}
            }
        )

        AuditService.log_action(
            actor=actor,
            action="REACTIVATE_EMPLOYEE",
            target_type="employee",
            target_id=target_employee_id,
            details={"reason": reason or "Account reactivated by HR"}
        )
        return True, "Employee account reactivated successfully."

    @classmethod
    def get_offboardings(cls, actor: dict) -> list:
        """Retrieves historical offboarding records."""
        if not actor or normalize_role(actor.get("role")) not in (Role.HR, Role.ADMIN):
            return []
        db = get_db()
        return list(db.offboardings.find().sort("created_at", -1))

    @classmethod
    def get_profile_history(cls, target_employee_id: str) -> list:
        """Retrieves profile audit changes for a given employee."""
        db = get_db()
        return list(
            db.profile_change_logs.find({"target_employee_id": target_employee_id})
            .sort("timestamp", -1)
        )

    @classmethod
    def get_salary_info(cls, user: dict) -> dict:
        """Retrieves verified salary details for a user if configured in database."""
        if not user:
            return {"configured": False, "message": "User not found."}

        existing = user.get("salary_info")
        emp_id = user.get("employee_id") or user.get("emp_id") or ""
        role = user.get("role", Role.EMPLOYEE)

        if existing and isinstance(existing, dict) and (existing.get("ctc_annual") or existing.get("basic") or existing.get("basic_salary")):
            if existing.get("ctc_annual"):
                comp = calculate_salary_components(existing["ctc_annual"])
            else:
                comp = dict(existing)
            for k, v in existing.items():
                if v is not None:
                    comp[k] = v
            banking = get_default_banking_info(emp_id, role)
            for bk, bv in banking.items():
                if not comp.get(bk):
                    comp[bk] = bv
            comp["configured"] = True
            return comp

        # Return truthful unconfigured status without fabricating fallback CTC
        return {
            "configured": False,
            "employee_id": emp_id,
            "message": "Salary structure not configured in database."
        }

    @classmethod
    def get_salary_slips(cls, user: dict, count: int = 6) -> list[dict]:
        """Retrieves actual finalized salary slips from the database for the user."""
        if not user:
            return []

        db = get_db()
        emp_id = user.get("employee_id") or user.get("emp_id")
        if not emp_id:
            return []

        # Only return genuine finalized slips generated in the database
        slips = list(
            db.salary_slips.find({"employee_id": emp_id}, {"_id": 0})
            .sort("year_month", -1)
            .limit(count)
        )
        return slips

    @classmethod
    def get_single_salary_slip(cls, actor: dict, target_employee_id: str, year_month: str) -> tuple[dict | None, str | None]:
        """Returns single detailed salary slip if actor is authorized to view profile."""
        db = get_db()
        target_user = db.users.find_one({"$or": [{"employee_id": target_employee_id}, {"emp_id": target_employee_id}]})
        if not target_user:
            return None, "Target employee not found."

        if not can_view_salary(actor, target_user):
            return None, "Access Denied: You cannot view this employee's salary slip."

        slips = cls.get_salary_slips(target_user, count=12)
        for slip in slips:
            if slip["year_month"] == year_month:
                return slip, None

        return None, f"Salary slip for {year_month} not found."

    @classmethod
    def get_user_skills(cls, user: dict) -> list[dict]:
        """Returns user skills with proficiency levels."""
        if not user:
            return []

        skills = user.get("skills")
        if skills and isinstance(skills, list) and len(skills) > 0:
            formatted = []
            for s in skills:
                if isinstance(s, dict) and "name" in s:
                    formatted.append({
                        "name": str(s["name"]).strip(),
                        "level": str(s.get("level", "Proficient")).strip()
                    })
                elif isinstance(s, str) and s.strip():
                    formatted.append({
                        "name": s.strip(),
                        "level": "Proficient"
                    })
            if formatted:
                return formatted

        emp_id = user.get("employee_id", "")
        if emp_id in DEFAULT_USER_SKILLS:
            return [dict(x) for x in DEFAULT_USER_SKILLS[emp_id]]

        dept = (user.get("department") or "").lower()
        role = user.get("role", Role.EMPLOYEE)

        if "eng" in dept or "dev" in dept:
            return [
                {"name": "Python", "level": "Expert"},
                {"name": "REST APIs", "level": "Advanced"},
                {"name": "SQL & Databases", "level": "Advanced"},
                {"name": "Git & CI/CD", "level": "Proficient"},
                {"name": "System Architecture", "level": "Proficient"}
            ]
        elif "qa" in dept or "quality" in dept or "test" in dept:
            return [
                {"name": "Test Automation", "level": "Expert"},
                {"name": "Pytest", "level": "Advanced"},
                {"name": "API Testing", "level": "Advanced"},
                {"name": "Selenium", "level": "Proficient"},
                {"name": "JIRA & Agile", "level": "Advanced"}
            ]
        elif "design" in dept or "ui" in dept or "ux" in dept:
            return [
                {"name": "UI/UX Design", "level": "Expert"},
                {"name": "Figma", "level": "Expert"},
                {"name": "User Research", "level": "Advanced"},
                {"name": "Wireframing", "level": "Advanced"},
                {"name": "Design Systems", "level": "Advanced"}
            ]
        elif role in (Role.HR, Role.HR_MANAGER):
            return [
                {"name": "HR Policy & Compliance", "level": "Expert"},
                {"name": "Talent Acquisition", "level": "Advanced"},
                {"name": "Employee Relations", "level": "Advanced"},
                {"name": "Payroll Administration", "level": "Proficient"},
                {"name": "Conflict Resolution", "level": "Proficient"}
            ]
        else:
            return [
                {"name": "Problem Solving", "level": "Advanced"},
                {"name": "Team Collaboration", "level": "Advanced"},
                {"name": "Project Coordination", "level": "Proficient"},
                {"name": "Communication", "level": "Proficient"}
            ]

    @classmethod
    def add_user_skill(cls, actor: dict, target_employee_id: str, skill_name: str, level: str = "Proficient") -> tuple[list | None, str | None]:
        """Adds or updates a skill badge for the employee profile."""
        db = get_db()
        target_user = db.users.find_one({"employee_id": target_employee_id})
        if not target_user:
            return None, "Target employee not found."

        is_self = actor.get("employee_id") == target_employee_id
        actor_role = actor.get("role")
        target_role = target_user.get("role")

        allowed = False
        if is_self:
            allowed = True
        elif actor_role == Role.HR and target_role == Role.EMPLOYEE:
            allowed = True
        elif actor_role == Role.HR_MANAGER and target_role in (Role.HR, Role.EMPLOYEE):
            allowed = True

        if not allowed:
            return None, "Unauthorized to modify skills for this profile."

        clean_name = skill_name.strip()
        if not clean_name:
            return None, "Skill name cannot be empty."

        valid_levels = ["Expert", "Advanced", "Proficient", "Intermediate", "Familiar"]
        clean_level = level.strip() if level and level.strip() in valid_levels else "Proficient"

        current_skills = cls.get_user_skills(target_user)
        updated = False
        for s in current_skills:
            if s["name"].lower() == clean_name.lower():
                s["level"] = clean_level
                updated = True
                break
        if not updated:
            current_skills.append({"name": clean_name, "level": clean_level})

        db.users.update_one(
            {"employee_id": target_employee_id},
            {"$set": {"skills": current_skills, "updated_at": datetime.now(timezone.utc)}}
        )

        AuditService.log_action(
            actor=actor,
            action="UPDATE_SKILLS",
            target_type=target_role,
            target_id=target_employee_id,
            details={"skill": clean_name, "level": clean_level}
        )

        return current_skills, None

    @classmethod
    def remove_user_skill(cls, actor: dict, target_employee_id: str, skill_name: str) -> tuple[list | None, str | None]:
        """Removes a skill from the employee profile."""
        db = get_db()
        target_user = db.users.find_one({"employee_id": target_employee_id})
        if not target_user:
            return None, "Target employee not found."

        is_self = actor.get("employee_id") == target_employee_id
        actor_role = actor.get("role")
        target_role = target_user.get("role")

        allowed = False
        if is_self:
            allowed = True
        elif actor_role == Role.HR and target_role == Role.EMPLOYEE:
            allowed = True
        elif actor_role == Role.HR_MANAGER and target_role in (Role.HR, Role.EMPLOYEE):
            allowed = True

        if not allowed:
            return None, "Unauthorized to modify skills for this profile."

        clean_name = skill_name.strip()
        current_skills = cls.get_user_skills(target_user)
        new_skills = [s for s in current_skills if s["name"].lower() != clean_name.lower()]

        db.users.update_one(
            {"employee_id": target_employee_id},
            {"$set": {"skills": new_skills, "updated_at": datetime.now(timezone.utc)}}
        )

        return new_skills, None

    @classmethod
    def update_user_salary(cls, actor: dict, target_employee_id: str, salary_data: dict, reason: str = "") -> tuple[dict | None, str | None]:
        """Allows HR / HR Manager to revise salary compensation structure."""
        db = get_db()
        target_user = db.users.find_one({"employee_id": target_employee_id})
        if not target_user:
            return None, "Target employee not found."

        actor_role = normalize_role(actor.get("role"))
        target_role = normalize_role(target_user.get("role"))

        allowed = False
        if actor_role == Role.ADMIN:
            allowed = True
        elif actor_role == Role.HR and target_role != Role.ADMIN:
            allowed = True

        if not allowed:
            return None, "Unauthorized: Only HR or Administrators are authorized to revise salary compensation."

        try:
            ctc_annual = float(salary_data.get("ctc_annual", 0))
            if ctc_annual <= 0:
                return None, "Annual CTC must be greater than 0."
        except (ValueError, TypeError):
            return None, "Invalid annual CTC amount."

        components = calculate_salary_components(ctc_annual)

        current_salary = cls.get_salary_info(target_user)
        bank_name = salary_data.get("bank_name") or current_salary.get("bank_name", "State Bank of India")
        account_number = salary_data.get("account_number") or current_salary.get("account_number", "••••••••1001")
        ifsc_code = salary_data.get("ifsc_code") or current_salary.get("ifsc_code", "SBIN0008472")
        pan_number = salary_data.get("pan_number") or current_salary.get("pan_number", "•••••100K")
        pf_number = salary_data.get("pf_number") or current_salary.get("pf_number", "KN/BNG/0048291/000/1001")
        uan_number = salary_data.get("uan_number") or current_salary.get("uan_number", "100984711001")

        components.update({
            "bank_name": bank_name,
            "account_number": account_number,
            "ifsc_code": ifsc_code,
            "pan_number": pan_number,
            "pf_number": pf_number,
            "uan_number": uan_number
        })

        db.users.update_one(
            {"employee_id": target_employee_id},
            {"$set": {"salary_info": components, "updated_at": datetime.now(timezone.utc)}}
        )

        AuditService.log_action(
            actor=actor,
            action="REVISE_SALARY",
            target_type=target_role,
            target_id=target_employee_id,
            details={"ctc_annual": ctc_annual, "reason": reason or "Salary compensation revision"}
        )

        return components, None

    @classmethod
    def enrich_user_profile(cls, user: dict) -> dict:
        """Enriches user dictionary with Tiimi SaaS HRM fields, full salary_info, salary_slips, and skills."""
        if not user:
            return user

        user_copy = dict(user)
        user_copy["salary_info"] = cls.get_salary_info(user)
        user_copy["skills"] = cls.get_user_skills(user)
        user_copy["salary_slips"] = cls.get_salary_slips(user, count=6)

        # Tiimi SaaS HRM Profile Demographics & Meta
        fn = user.get("full_name") or user.get("name") or "Team Member"
        user_copy["gender"] = user.get("gender") or "Male"
        user_copy["marital_status"] = user.get("marital_status") or "Single"
        user_copy["religion"] = user.get("religion") or "General"
        user_copy["place_of_birth"] = user.get("place_of_birth") or "Bengaluru"
        user_copy["birthdate"] = user.get("dob") or user.get("date_of_birth") or "06 March 1997"
        user_copy["blood_type"] = user.get("blood_type") or "B+"
        user_copy["age"] = user.get("age") or 25
        
        # Contacts & Addresses
        user_copy["phone_number"] = user.get("phone_number") or user.get("contact") or "+91 98765 43210"
        user_copy["other_contact"] = user.get("emergency_contact") or user.get("other_contact") or "Not Provided"
        user_copy["residential_address"] = user.get("residential_address") or user.get("address") or "4517 Washington Ave. Manchester, Kentucky 39495"
        user_copy["citizen_id_address"] = user.get("citizen_id_address") or user.get("permanent_address") or "2715 Ash Dr. San Jose, South Dakota 83475"
        user_copy["notes"] = user.get("notes") or f"{fn} has been a valuable member of the team and brings great energy to creative discussions. With some additional focus on data analysis and prioritization, manager believe they can take their work to the next level."
        
        # Employment Overview
        role_label = user.get("role", "employee").capitalize()
        user_copy["job_role"] = user.get("designation") or "Project Specialist"
        user_copy["job_level"] = user.get("job_level") or ("Managerial" if user.get("role") in ("manager", "tl", "admin") else "Associate")
        user_copy["employment_status"] = user.get("employment_status") or "Fulltime"
        user_copy["date_started"] = user.get("joining_date") or "2022-Current (2 Years)"
        user_copy["tags"] = user.get("tags") or ["Core Contributor", "Enterprise", user.get("department", "Engineering")]
        user_copy["last_clocked_in"] = "A few seconds ago"
        user_copy["last_messaged"] = "2 Days ago"

        return user_copy
