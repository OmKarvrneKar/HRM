import openpyxl
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

from database.connection import DatabaseManager, get_db
from permissions.rbac import Role
from auth.security import hash_password
from services.audit_service import AuditService
from utils.validators import validate_email, validate_phone

class EmployeeImportService:
    DEFAULT_EXCEL_PATH = "data/Intern-Full-Details(1).xlsx"

    @classmethod
    def get_next_employee_id(cls, db) -> str:
        """Finds highest numeric EMP-xxxx ID in db and increments."""
        existing_emp_ids = db.users.find({"employee_id": {"$regex": r"^EMP-\d+$"}}, {"employee_id": 1})
        highest = 1004
        for u in existing_emp_ids:
            try:
                num = int(u["employee_id"].split("-")[1])
                if num > highest:
                    highest = num
            except Exception:
                pass
        return f"EMP-{highest + 1}"

    @classmethod
    def inspect_and_validate_file(cls, file_path: str = None) -> List[Dict[str, Any]]:
        """
        Reads all employee rows from the Excel spreadsheet and validates every field.
        Returns a list of parsed record dictionaries with validation status and issues.
        """
        path = file_path or cls.DEFAULT_EXCEL_PATH
        if not Path(path).exists():
            # Fallback check
            alt_path = Path("C:/Users/Deepak/Documents/Deepak/Intern-Full-Details.xlsx")
            if alt_path.exists():
                path = str(alt_path)
            else:
                raise FileNotFoundError(f"Excel file not found at: {path}")

        wb = openpyxl.load_workbook(path)
        ws = wb.active

        db = get_db()
        existing_users = list(db.users.find({}))
        existing_emails = {u.get("email", "").strip().lower(): u for u in existing_users if u.get("email")}
        existing_phones = {re.sub(r"[^0-9]", "", str(u.get("phone_number", ""))): u for u in existing_users if u.get("phone_number")}

        records = []
        # Row 1 is header, Row 2 is blank, data starts from Row 3 to 36
        for r in range(3, ws.max_row + 1):
            sno_val = ws.cell(r, 1).value
            name_val = ws.cell(r, 2).value
            contact_val = ws.cell(r, 3).value
            email_val = ws.cell(r, 4).value
            dob_val = ws.cell(r, 5).value

            if not any([sno_val, name_val, contact_val, email_val, dob_val]):
                continue

            sno = int(sno_val) if isinstance(sno_val, (int, float)) else sno_val
            name_clean = str(name_val).strip() if name_val is not None else ""

            # Phone processing
            phone_digits = ""
            if contact_val is not None:
                if isinstance(contact_val, float):
                    phone_digits = str(int(contact_val)).strip()
                else:
                    phone_digits = re.sub(r"[^0-9]", "", str(contact_val)).strip()

            phone_display = f"+91 {phone_digits}" if len(phone_digits) == 10 else phone_digits

            # Email processing
            email_raw = str(email_val) if email_val is not None else ""
            email_clean = email_raw.strip()

            # Date of Birth processing
            dob_clean = None
            dob_err = None
            if isinstance(dob_val, datetime):
                dob_clean = dob_val.strftime("%Y-%m-%d")
            elif isinstance(dob_val, str):
                s = dob_val.strip()
                m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", s)
                if m:
                    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    try:
                        dt = datetime(y, mo, d)
                        dob_clean = dt.strftime("%Y-%m-%d")
                    except ValueError:
                        dob_err = f"Invalid calendar date values: {s}"
                else:
                    try:
                        dt = datetime.strptime(s, "%Y-%m-%d")
                        dob_clean = dt.strftime("%Y-%m-%d")
                    except Exception:
                        dob_err = f"Unrecognized date format: '{s}' (expected DD-MM-YYYY or YYYY-MM-DD)"
            else:
                dob_err = "Missing Date of Birth"

            rec = {
                "row_num": r,
                "sno": sno,
                "name": name_clean,
                "phone_raw": contact_val,
                "phone_digits": phone_digits,
                "phone_display": phone_display,
                "email_raw": email_raw,
                "email_clean": email_clean,
                "dob_raw": dob_val,
                "dob_clean": dob_clean,
                "dob_err": dob_err,
                "issues": [],
                "status": "READY",
                "db_match": None
            }

            # Field-level validations
            if not name_clean:
                rec["issues"].append("Missing employee name")
            if not phone_digits or len(phone_digits) != 10:
                rec["issues"].append(f"Invalid 10-digit phone number: '{phone_digits}'")

            # Email validation
            if " " in email_clean:
                rec["issues"].append(f"Whitespace detected inside email address: '{email_clean}'")
                rec["status"] = "PENDING_REVIEW"
            elif not validate_email(email_clean):
                rec["issues"].append(f"Malformed email syntax: '{email_clean}'")
                rec["status"] = "INVALID"

            if dob_err:
                rec["issues"].append(dob_err)
                if rec["status"] == "READY":
                    rec["status"] = "INVALID"

            # Check DB match / collisions
            email_key = email_clean.lower().replace(" ", "")
            if email_key in existing_emails:
                matched_u = existing_emails[email_key]
                rec["db_match"] = f"Email matches existing employee {matched_u.get('employee_id')} ({matched_u.get('full_name')})"
                rec["status"] = "EXISTING_MATCH"
            elif phone_digits in existing_phones:
                matched_u = existing_phones[phone_digits]
                rec["db_match"] = f"Phone matches existing employee {matched_u.get('employee_id')} ({matched_u.get('full_name')})"
                rec["status"] = "EXISTING_MATCH"

            records.append(rec)

        # Check internal duplicate checks within spreadsheet
        seen_emails: Dict[str, int] = {}
        seen_phones: Dict[str, int] = {}
        for rec in records:
            e_key = rec["email_clean"].lower().replace(" ", "")
            p_key = rec["phone_digits"]

            if e_key in seen_emails:
                rec["issues"].append(f"Duplicate email within spreadsheet (matches row {seen_emails[e_key]})")
                rec["status"] = "DUPLICATE"
            else:
                seen_emails[e_key] = rec["row_num"]

            if p_key:
                if p_key in seen_phones:
                    rec["issues"].append(f"Duplicate phone within spreadsheet (matches row {seen_phones[p_key]})")
                    rec["status"] = "DUPLICATE"
                else:
                    seen_phones[p_key] = rec["row_num"]

        return records

    @classmethod
    def generate_preview(cls, file_path: str = None) -> Dict[str, Any]:
        """
        Generates comprehensive pre-import summary report without altering database state.
        """
        records = cls.inspect_and_validate_file(file_path)

        ready_records = [r for r in records if r["status"] == "READY"]
        existing_matches = [r for r in records if r["status"] == "EXISTING_MATCH"]
        duplicate_records = [r for r in records if r["status"] == "DUPLICATE"]
        invalid_records = [r for r in records if r["status"] == "INVALID"]
        pending_review = [r for r in records if r["status"] == "PENDING_REVIEW"]

        return {
            "total_records": len(records),
            "ready_count": len(ready_records),
            "existing_match_count": len(existing_matches),
            "duplicate_count": len(duplicate_records),
            "invalid_count": len(invalid_records),
            "pending_review_count": len(pending_review),
            "records": records,
            "ready_records": ready_records,
            "pending_review_records": pending_review,
            "existing_match_records": existing_matches,
            "duplicate_records": duplicate_records,
            "invalid_records": invalid_records
        }

    @classmethod
    def execute_import(
        cls,
        actor: dict,
        file_path: str = None,
        auto_sanitize_whitespace: bool = False
    ) -> Dict[str, Any]:
        """
        Executes safe database import of validated employee records into persistent MongoDB.
        Enforces:
        - Automatic database backup prior to insertion
        - Role strictly set to Role.EMPLOYEE
        - Unique EMP-XXXX sequential IDs
        - Distinct, cryptographically generated activation tokens/hashes (no shared default password)
        - Audit trail logging
        """
        # 1. Back up database before any changes
        backup_dir = DatabaseManager.backup_database()

        # 2. Inspect and validate
        preview = cls.generate_preview(file_path)
        records = preview["records"]

        db = get_db()
        imported = []
        skipped = []
        pending_review = []
        duplicates = []
        invalids = []

        # Find starting ID sequence
        next_id_counter = 1005
        existing_emp_ids = db.users.find({"employee_id": {"$regex": r"^EMP-\d+$"}}, {"employee_id": 1})
        for u in existing_emp_ids:
            try:
                num = int(u["employee_id"].split("-")[1])
                if num >= next_id_counter:
                    next_id_counter = num + 1
            except Exception:
                pass

        for rec in records:
            status = rec["status"]

            # If auto_sanitize_whitespace is enabled and issue is only whitespace in email:
            if status == "PENDING_REVIEW" and auto_sanitize_whitespace:
                cleaned_email = rec["email_clean"].replace(" ", "")
                if validate_email(cleaned_email):
                    rec["email_clean"] = cleaned_email
                    rec["issues"] = []
                    status = "READY"

            if status == "EXISTING_MATCH":
                skipped.append({
                    "sno": rec["sno"],
                    "name": rec["name"],
                    "reason": rec["db_match"]
                })
            elif status == "DUPLICATE":
                duplicates.append({
                    "sno": rec["sno"],
                    "name": rec["name"],
                    "issues": rec["issues"]
                })
            elif status == "INVALID":
                invalids.append({
                    "sno": rec["sno"],
                    "name": rec["name"],
                    "issues": rec["issues"]
                })
            elif status == "PENDING_REVIEW":
                pending_review.append({
                    "sno": rec["sno"],
                    "name": rec["name"],
                    "issues": rec["issues"],
                    "raw_email": rec["email_raw"]
                })
            elif status == "READY":
                emp_id = f"EMP-{next_id_counter}"
                next_id_counter += 1

                # Generate individual cryptographically secure activation token
                activation_token = secrets.token_urlsafe(18)
                # Password hash for pending activation
                initial_password_hash = hash_password(activation_token)

                now = datetime.now(timezone.utc)
                doc = {
                    "employee_id": emp_id,
                    "full_name": rec["name"],
                    "email": rec["email_clean"].lower(),
                    "phone_number": rec["phone_display"],
                    "date_of_birth": rec["dob_clean"],
                    "role": Role.EMPLOYEE,  # Strictly EMPLOYEE
                    "department": "Engineering",
                    "designation": "AI/ML Engineering Intern",
                    "team_id": None,               # Unassigned per prompt rules
                    "reporting_manager_id": None, # Unassigned per prompt rules
                    "joining_date": now.strftime("%Y-%m-%d"),
                    "employment_status": "Active",
                    "is_active": True,
                    "account_status": "pending_activation",
                    "needs_password_setup": True,
                    "activation_token": activation_token,
                    "password_hash": initial_password_hash,
                    "import_source": "Intern-Full-Details(1).xlsx",
                    "import_sno": rec["sno"],
                    "created_by": actor.get("employee_id", "SYSTEM_IMPORT"),
                    "created_at": now,
                    "updated_at": now
                }

                res = db.users.insert_one(doc)
                doc["_id"] = res.inserted_id

                AuditService.log_action(
                    actor=actor,
                    action="IMPORT_EMPLOYEE_RECORD",
                    target_type=Role.EMPLOYEE,
                    target_id=emp_id,
                    details={
                        "name": rec["name"],
                        "email": rec["email_clean"].lower(),
                        "phone": rec["phone_display"],
                        "import_sno": rec["sno"],
                        "source": "Intern-Full-Details(1).xlsx"
                    }
                )

                imported.append({
                    "sno": rec["sno"],
                    "employee_id": emp_id,
                    "name": rec["name"],
                    "email": rec["email_clean"].lower(),
                    "phone": rec["phone_display"],
                    "date_of_birth": rec["dob_clean"],
                    "role": Role.EMPLOYEE,
                    "account_status": "pending_activation"
                })

        return {
            "backup_path": str(backup_dir) if backup_dir else None,
            "total_excel_records": len(records),
            "imported_count": len(imported),
            "skipped_count": len(skipped),
            "duplicate_count": len(duplicates),
            "invalid_count": len(invalids),
            "pending_review_count": len(pending_review),
            "imported_records": imported,
            "skipped_records": skipped,
            "duplicate_records": duplicates,
            "invalid_records": invalids,
            "pending_review_records": pending_review
        }
