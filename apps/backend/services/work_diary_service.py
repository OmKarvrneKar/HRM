import io
import uuid
import logging
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from database.connection import get_db
from utils.timezone import now_utc, get_local_date_str, now_local
from utils.serializers import serialize_doc, serialize_docs

logger = logging.getLogger(__name__)


class WorkDiaryService:
    """
    Manages daily work diary logs for users.
    Each user can select any date, log time slots and descriptions of work done.
    Strict privacy rule: Work diary logs are strictly private to each individual user.
    """

    @classmethod
    def calculate_duration(cls, start_time: str, end_time: str) -> tuple[float, str]:
        """
        Calculates decimal hours and human-readable duration from start_time and end_time (HH:MM).
        Returns (hours_float, 'Xh Ym').
        """
        if not start_time or not end_time:
            return 0.0, "0h 0m"

        try:
            sh, sm = map(int, start_time.strip().split(":"))
            eh, em = map(int, end_time.strip().split(":"))
            start_mins = sh * 60 + sm
            end_mins = eh * 60 + em

            diff_mins = end_mins - start_mins
            if diff_mins < 0:
                # If overnight or invalid, return 0
                return 0.0, "0h 0m"

            hours = round(diff_mins / 60.0, 2)
            display = f"{diff_mins // 60}h {diff_mins % 60}m"
            return hours, display
        except Exception as e:
            logger.debug("Failed to calculate duration: %s", str(e))
            return 0.0, "0h 0m"

    @classmethod
    def create_entry(cls, employee_id: str, employee_name: str, payload: dict) -> dict:
        """
        Creates a new work diary entry for an employee.
        """
        db = get_db()
        diary_date = payload.get("diary_date") or get_local_date_str()
        start_time = (payload.get("start_time") or "").strip()
        end_time = (payload.get("end_time") or "").strip()
        activity_title = (payload.get("activity_title") or payload.get("title") or "").strip()
        work_description = (payload.get("work_description") or payload.get("description") or "").strip()
        category = (payload.get("category") or "General").strip()
        status = (payload.get("status") or "Completed").strip()

        if not activity_title:
            activity_title = work_description[:60] if work_description else "Daily Work Task"
        if not work_description:
            work_description = activity_title

        # Calculate duration
        hours_spent = 0.0
        duration_display = "0h 0m"
        if start_time and end_time:
            hours_spent, duration_display = cls.calculate_duration(start_time, end_time)
        elif payload.get("hours_spent"):
            try:
                hours_spent = round(float(payload.get("hours_spent")), 2)
                mins = int(round(hours_spent * 60))
                duration_display = f"{mins // 60}h {mins % 60}m"
            except (ValueError, TypeError):
                hours_spent = 0.0

        diary_id = f"WD-{uuid.uuid4().hex[:8].upper()}"
        project_id = (payload.get("project_id") or "").strip()
        project_name = (payload.get("project_name") or payload.get("project") or "").strip()
        task_id = (payload.get("task_id") or "").strip()
        task_title = (payload.get("task_title") or payload.get("task") or "").strip()
        tasks_handled = (payload.get("tasks_handled") or task_title).strip()
        blockers = (payload.get("blockers") or payload.get("notes") or "").strip()
        planned_next = (payload.get("planned_next") or "").strip()

        doc = {
            "diary_id": diary_id,
            "employee_id": employee_id,
            "employee_name": employee_name,
            "diary_date": diary_date,
            "start_time": start_time,
            "end_time": end_time,
            "duration_hours": hours_spent,
            "duration_minutes": int(round(hours_spent * 60)),
            "duration_display": duration_display,
            "activity_title": activity_title,
            "title": activity_title,
            "work_description": work_description,
            "description": work_description,
            "category": category,
            "status": status,
            "project_id": project_id,
            "project_name": project_name,
            "task_id": task_id,
            "task_title": task_title,
            "tasks_handled": tasks_handled,
            "blockers": blockers,
            "notes": blockers,
            "planned_next": planned_next,
            "comments": [],
            "created_at": now_utc(),
            "updated_at": now_utc()
        }

        db.work_diary.insert_one(doc)
        logger.info("Created work diary entry '%s' for employee '%s' on %s", diary_id, employee_id, diary_date)
        return serialize_doc(doc)

    @classmethod
    def update_entry(cls, employee_id: str, diary_id: str, payload: dict) -> dict:
        """
        Updates an existing work diary entry.
        Strict privacy check: Ensures entry belongs to employee_id.
        """
        db = get_db()
        entry = db.work_diary.find_one({"diary_id": diary_id})
        if not entry:
            raise KeyError(f"Work diary entry '{diary_id}' not found.")

        if entry.get("employee_id") != employee_id:
            raise PermissionError("Access denied: You can only edit your own work diary entries.")

        update_fields = {"updated_at": now_utc()}

        if "diary_date" in payload and payload["diary_date"]:
            update_fields["diary_date"] = payload["diary_date"].strip()

        start_time = payload.get("start_time", entry.get("start_time", ""))
        end_time = payload.get("end_time", entry.get("end_time", ""))
        if "start_time" in payload:
            update_fields["start_time"] = (start_time or "").strip()
        if "end_time" in payload:
            update_fields["end_time"] = (end_time or "").strip()

        if "activity_title" in payload:
            title = (payload.get("activity_title") or "").strip()
            if title:
                update_fields["activity_title"] = title

        if "work_description" in payload:
            update_fields["work_description"] = (payload.get("work_description") or "").strip()

        if "category" in payload:
            update_fields["category"] = (payload.get("category") or "General").strip()

        if "status" in payload:
            update_fields["status"] = (payload.get("status") or "Completed").strip()

        if "project_id" in payload:
            update_fields["project_id"] = (payload.get("project_id") or "").strip()

        if "project_name" in payload or "project" in payload:
            update_fields["project_name"] = (payload.get("project_name") or payload.get("project") or "").strip()

        if "task_id" in payload:
            update_fields["task_id"] = (payload.get("task_id") or "").strip()

        if "task_title" in payload or "task" in payload:
            update_fields["task_title"] = (payload.get("task_title") or payload.get("task") or "").strip()

        if "tasks_handled" in payload:
            update_fields["tasks_handled"] = (payload.get("tasks_handled") or "").strip()
        elif "task_title" in update_fields:
            update_fields["tasks_handled"] = update_fields["task_title"]

        if "blockers" in payload:
            update_fields["blockers"] = (payload.get("blockers") or "").strip()

        if "planned_next" in payload:
            update_fields["planned_next"] = (payload.get("planned_next") or "").strip()

        # Recalculate duration if time changed
        effective_start = update_fields.get("start_time", entry.get("start_time", ""))
        effective_end = update_fields.get("end_time", entry.get("end_time", ""))
        if effective_start and effective_end:
            h, d = cls.calculate_duration(effective_start, effective_end)
            update_fields["duration_hours"] = h
            update_fields["duration_display"] = d
        elif "hours_spent" in payload:
            try:
                h = round(float(payload.get("hours_spent")), 2)
                mins = int(round(h * 60))
                update_fields["duration_hours"] = h
                update_fields["duration_display"] = f"{mins // 60}h {mins % 60}m"
            except (ValueError, TypeError):
                pass

        db.work_diary.update_one({"diary_id": diary_id}, {"$set": update_fields})
        updated_doc = db.work_diary.find_one({"diary_id": diary_id})
        return serialize_doc(updated_doc)

    @classmethod
    def delete_entry(cls, employee_id: str, diary_id: str) -> bool:
        """
        Deletes a work diary entry.
        Strict privacy check: Ensures entry belongs to employee_id.
        """
        db = get_db()
        entry = db.work_diary.find_one({"diary_id": diary_id})
        if not entry:
            raise KeyError(f"Work diary entry '{diary_id}' not found.")

        if entry.get("employee_id") != employee_id:
            raise PermissionError("Access denied: You can only delete your own work diary entries.")

        db.work_diary.delete_one({"diary_id": diary_id})
        logger.info("Deleted work diary entry '%s' for employee '%s'", diary_id, employee_id)
        return True

    @classmethod
    def get_daily_diary(cls, employee_id: str, diary_date: str) -> dict:
        """
        Retrieves all work diary entries for an employee on a specific date.
        Strict privacy check: Only returns entries for employee_id.
        """
        db = get_db()
        cursor = db.work_diary.find({
            "employee_id": employee_id,
            "diary_date": diary_date
        }).sort([("start_time", 1), ("created_at", 1)])

        entries = list(cursor)
        total_hours = sum(e.get("duration_hours", 0.0) or 0.0 for e in entries)
        total_mins = int(round(total_hours * 60))
        total_time_str = f"{total_mins // 60}h {total_mins % 60}m"
        completed_count = sum(1 for e in entries if e.get("status") == "Completed")

        return {
            "date": diary_date,
            "employee_id": employee_id,
            "entries": serialize_docs(entries),
            "summary": {
                "total_hours": round(total_hours, 2),
                "total_time_str": total_time_str,
                "entry_count": len(entries),
                "completed_count": completed_count
            }
        }

    @classmethod
    def get_monthly_diary(cls, employee_id: str, year_month: str) -> dict:
        """
        Retrieves all work diary entries for an employee across a given month (YYYY-MM).
        Strict privacy check: Only returns entries for employee_id.
        """
        db = get_db()
        regex_pattern = f"^{year_month}"
        cursor = db.work_diary.find({
            "employee_id": employee_id,
            "diary_date": {"$regex": regex_pattern}
        }).sort([("diary_date", -1), ("start_time", 1)])

        entries = list(cursor)
        total_hours = sum(e.get("duration_hours", 0.0) or 0.0 for e in entries)
        total_mins = int(round(total_hours * 60))
        total_time_str = f"{total_mins // 60}h {total_mins % 60}m"
        unique_dates = sorted(list(set(e.get("diary_date") for e in entries if e.get("diary_date"))), reverse=True)

        # Group entries by date
        grouped = {}
        for d in unique_dates:
            grouped[d] = []
        for e in entries:
            d = e.get("diary_date")
            if d:
                grouped[d].append(serialize_doc(e))

        daily_summaries = []
        for d in unique_dates:
            d_entries = grouped[d]
            d_hours = sum(item.get("duration_hours", 0.0) or 0.0 for item in d_entries)
            d_mins = int(round(d_hours * 60))
            daily_summaries.append({
                "date": d,
                "entry_count": len(d_entries),
                "total_hours": round(d_hours, 2),
                "total_time_str": f"{d_mins // 60}h {d_mins % 60}m",
                "entries": d_entries
            })

        avg_hours_per_active_day = round(total_hours / len(unique_dates), 2) if unique_dates else 0.0

        return {
            "year_month": year_month,
            "employee_id": employee_id,
            "entries": serialize_docs(entries),
            "daily_summaries": daily_summaries,
            "summary": {
                "total_hours": round(total_hours, 2),
                "total_time_str": total_time_str,
                "days_logged_count": len(unique_dates),
                "entry_count": len(entries),
                "avg_hours_per_active_day": avg_hours_per_active_day
            }
        }

    @classmethod
    def export_diary_excel(cls, employee_id: str, employee_name: str, filter_type: str, date_or_month: str) -> io.BytesIO:
        """
        Generates a beautifully formatted Excel (.xlsx) report for daily or monthly work diary.
        Strict privacy: Exports ONLY the requesting user's records.
        """
        if filter_type == "daily":
            report_data = cls.get_daily_diary(employee_id, date_or_month)
            entries = report_data["entries"]
            period_label = f"Daily Log: {date_or_month}"
            sheet_title = f"Diary {date_or_month}"
        else:
            report_data = cls.get_monthly_diary(employee_id, date_or_month)
            entries = report_data["entries"]
            period_label = f"Monthly Log: {date_or_month}"
            sheet_title = f"Diary {date_or_month}"

        wb = Workbook()
        ws = wb.active
        ws.title = sheet_title[:31]  # Excel limits sheet name to 31 chars

        # Palette & Styles
        navy_dark = "1E293B"       # Slate 800
        blue_brand = "1D4ED8"      # Brand Primary
        blue_light = "EFF6FF"      # Brand Subtle
        gray_border = "CBD5E1"     # Slate 300
        zebra_fill = "F8FAFC"      # Slate 50
        text_dark = "0F172A"       # Slate 900

        font_company = Font(name="Calibri", size=15, bold=True, color="1E3A8A")
        font_title = Font(name="Calibri", size=12, bold=True, color="334155")
        font_meta = Font(name="Calibri", size=10, bold=False, color="475569")
        font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        font_row = Font(name="Calibri", size=10, bold=False, color="1E293B")
        font_total = Font(name="Calibri", size=11, bold=True, color="0F172A")

        fill_header = PatternFill(start_color=navy_dark, end_color=navy_dark, fill_type="solid")
        fill_zebra = PatternFill(start_color=zebra_fill, end_color=zebra_fill, fill_type="solid")
        fill_total = PatternFill(start_color=blue_light, end_color=blue_light, fill_type="solid")

        thin_side = Side(border_style="thin", color=gray_border)
        cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
        double_bottom = Border(left=thin_side, right=thin_side, top=thin_side, bottom=Side(border_style="double", color="0F172A"))

        align_center = Alignment(horizontal="center", vertical="center")
        align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
        align_right = Alignment(horizontal="right", vertical="center")

        # 1. Title & Metadata Block
        ws.merge_cells("A1:H1")
        ws["A1"] = "AI Samrat Pvt Ltd"
        ws["A1"].font = font_company
        ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 24

        ws.merge_cells("A2:H2")
        ws["A2"] = "CONFIDENTIAL EMPLOYEE WORK DIARY REPORT"
        ws["A2"].font = font_title
        ws["A2"].alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[2].height = 20

        ws.merge_cells("A3:H3")
        gen_time = now_local().strftime("%Y-%m-%d %I:%M %p")
        ws["A3"] = f"Employee: {employee_name} ({employee_id})  |  Period: {period_label}  |  Generated: {gen_time} IST"
        ws["A3"].font = font_meta
        ws["A3"].alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[3].height = 18

        # Blank row 4
        ws.row_dimensions[4].height = 10

        # 2. Table Headers (Row 5)
        headers = [
            "Date",
            "Day",
            "Time Slot",
            "Duration",
            "Category",
            "Task / Activity Title",
            "Detailed Work Accomplished",
            "Status"
        ]
        ws.row_dimensions[5].height = 26

        for col_idx, h_text in enumerate(headers, start=1):
            cell = ws.cell(row=5, column=col_idx, value=h_text)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = align_center
            cell.border = cell_border

        # 3. Data Rows
        current_row = 6
        total_hours_sum = 0.0

        for idx, entry in enumerate(entries):
            d_str = entry.get("diary_date", "")
            day_name = ""
            if d_str:
                try:
                    dt = datetime.strptime(d_str, "%Y-%m-%d")
                    day_name = dt.strftime("%A")
                except Exception:
                    pass

            start_t = entry.get("start_time") or ""
            end_t = entry.get("end_time") or ""
            time_slot = f"{start_t} - {end_t}" if start_t and end_t else (start_t or "-")
            duration_disp = entry.get("duration_display") or f"{entry.get('duration_hours', 0)}h"
            duration_val = float(entry.get("duration_hours", 0.0) or 0.0)
            total_hours_sum += duration_val

            row_data = [
                d_str,
                day_name,
                time_slot,
                duration_disp,
                entry.get("category", "General"),
                entry.get("activity_title", ""),
                entry.get("work_description", ""),
                entry.get("status", "Completed")
            ]
            ws.row_dimensions[current_row].height = 24

            # Apply row styling
            is_zebra = (idx % 2 == 1)
            for col_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=current_row, column=col_idx, value=val)
                cell.font = font_row
                cell.border = cell_border
                if is_zebra:
                    cell.fill = fill_zebra

                if col_idx in (1, 2, 3, 4, 5, 8):
                    cell.alignment = align_center
                elif col_idx in (6, 7):
                    cell.alignment = align_left

            current_row += 1

        # Empty state handling
        if not entries:
            ws.merge_cells(f"A6:H6")
            no_cell = ws.cell(row=6, column=1)
            no_cell.value = "No work diary entries found for this period."
            no_cell.font = font_meta
            no_cell.alignment = align_center
            no_cell.border = cell_border
            ws.row_dimensions[6].height = 24
            current_row = 7

        # 4. Summary Row
        ws.row_dimensions[current_row].height = 24
        ws.merge_cells(f"A{current_row}:C{current_row}")
        sum_label_cell = ws.cell(row=current_row, column=1)
        sum_label_cell.value = f"TOTAL ({len(entries)} Entries)"
        sum_label_cell.font = font_total
        sum_label_cell.alignment = Alignment(horizontal="right", vertical="center")

        total_hours_mins = int(round(total_hours_sum * 60))
        total_time_disp = f"{total_hours_mins // 60}h {total_hours_mins % 60}m ({round(total_hours_sum, 2)} hrs)"

        dur_cell = ws.cell(row=current_row, column=4)
        dur_cell.value = total_time_disp
        dur_cell.font = font_total
        dur_cell.alignment = align_center

        ws.merge_cells(f"E{current_row}:H{current_row}")
        status_sum_cell = ws.cell(row=current_row, column=5)
        completed_ct = sum(1 for e in entries if e.get("status") == "Completed")
        status_sum_cell.value = f"{completed_ct} Tasks Completed"
        status_sum_cell.font = font_total
        status_sum_cell.alignment = align_left

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=current_row, column=col_idx)
            cell.fill = fill_total
            cell.border = double_bottom

        # Auto-fit Column Widths
        column_min_widths = {
            1: 14,  # Date
            2: 12,  # Day
            3: 16,  # Time Slot
            4: 18,  # Duration
            5: 18,  # Category
            6: 28,  # Task Title
            7: 45,  # Description
            8: 14   # Status
        }
        for col_idx in range(1, len(headers) + 1):
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = column_min_widths.get(col_idx, 20)

        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        return stream

    @classmethod
    def add_review_comment(cls, reviewer: dict, diary_id: str, comment_text: str) -> dict:
        """
        Team Lead, Manager, or HR adds a review comment / feedback note to an employee's work diary.
        Preserves original submission while recording feedback author, role, and timestamp.
        """
        comment_text = (comment_text or "").strip()
        if not comment_text:
            raise ValueError("Comment text cannot be empty.")

        role = reviewer.get("role")
        from permissions.rbac import Role
        if role not in (Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN, "trainer", "organization", "hr_manager"):
            raise PermissionError("Access denied: You do not have permission to review work diaries.")

        db = get_db()
        entry = db.work_diary.find_one({"diary_id": diary_id})
        if not entry:
            raise KeyError(f"Work diary entry '{diary_id}' not found.")

        # If reviewer is Team Lead, ensure target employee is within scope
        if role in (Role.TEAM_LEAD, "trainer"):
            lead_id = reviewer.get("employee_id")
            lead_team = reviewer.get("team_id")
            target_emp = db.users.find_one({"employee_id": entry.get("employee_id")})
            is_authorized = False
            if lead_team and target_emp and target_emp.get("team_id") == lead_team:
                is_authorized = True
            else:
                lead_teams = list(db.teams.find({"$or": [{"lead_id": lead_id}, {"lead_email": reviewer.get("email")}]}))
                for t in lead_teams:
                    if entry.get("employee_id") in t.get("members", []):
                        is_authorized = True
                        break
            if not is_authorized:
                raise PermissionError("Access denied: You can only review work diaries of your assigned team members.")

        comment_obj = {
            "comment_id": f"CMT-{uuid.uuid4().hex[:6].upper()}",
            "author_id": reviewer.get("employee_id"),
            "author_name": reviewer.get("full_name", reviewer.get("employee_id")),
            "author_role": role,
            "comment": comment_text,
            "created_at": now_utc()
        }

        db.work_diary.update_one(
            {"diary_id": diary_id},
            {
                "$push": {"comments": comment_obj},
                "$set": {"updated_at": now_utc()}
            }
        )

        # Notify employee
        try:
            from services.notification_service import NotificationService
            NotificationService.create_notification(
                title=f"Work Diary Feedback from {reviewer.get('full_name')}",
                message=f"{reviewer.get('full_name')} reviewed your work diary entry '{entry.get('activity_title')}': {comment_text}",
                category="WORK_DIARY",
                recipient_id=entry.get("employee_id"),
                link=f"/work-diary?date={entry.get('diary_date')}"
            )
        except Exception as e:
            logger.warning("Failed to notify employee of work diary comment: %s", str(e))

        updated = db.work_diary.find_one({"diary_id": diary_id})
        return serialize_doc(updated)

    @classmethod
    def get_team_work_diaries(cls, reviewer: dict, diary_date: str) -> dict:
        """
        Fetches daily work diary submissions and progress metrics for the authorized team or department.
        For Team Leads: shows assigned active team members.
        For Managers: shows cross-team summaries, project updates, and blockers.
        """
        db = get_db()
        from permissions.rbac import Role
        role = reviewer.get("role")
        reviewer_id = reviewer.get("employee_id")

        if role not in (Role.TEAM_LEAD, Role.MANAGER, Role.HR, Role.ADMIN, "trainer", "organization", "hr_manager"):
            raise PermissionError("Access denied: You do not have permission to view team work diaries.")

        members_list = []
        if role in (Role.TEAM_LEAD, "trainer"):
            team_id = reviewer.get("team_id")
            member_ids = set()
            if team_id:
                for u in db.users.find({"team_id": team_id, "role": Role.EMPLOYEE, "is_active": True}):
                    member_ids.add(u["employee_id"])
            for t in db.teams.find({"$or": [{"lead_id": reviewer_id}, {"lead_email": reviewer.get("email")}]}):
                for m in t.get("members", []):
                    member_ids.add(m)
            for p in db.projects.find({"$or": [{"created_by": reviewer_id}, {"lead_id": reviewer_id}]}):
                for m in p.get("members", []):
                    member_ids.add(m)
            member_ids.discard(reviewer_id)
            if member_ids:
                members_list = list(db.users.find({"employee_id": {"$in": list(member_ids)}, "is_active": True}))
        elif role in (Role.MANAGER, "organization", "admin"):
            dept = reviewer.get("department")
            query = {"role": Role.EMPLOYEE, "is_active": True}
            if dept and dept != "General":
                query["department"] = dept
            members_list = list(db.users.find(query))
        else:
            members_list = list(db.users.find({"role": Role.EMPLOYEE, "is_active": True}))

        # Sort members by name
        members_list.sort(key=lambda x: x.get("full_name", ""))

        team_records = []
        total_hours = 0.0
        submitted_count = 0
        total_tasks = 0
        all_blockers = []
        all_projects = set()

        for mem in members_list:
            emp_id = mem["employee_id"]
            entries = list(db.work_diary.find({"employee_id": emp_id, "diary_date": diary_date}).sort("start_time", 1))
            mem_hours = sum(e.get("duration_hours", 0.0) or 0.0 for e in entries)
            mem_mins = int(round(mem_hours * 60))
            mem_completed = sum(1 for e in entries if e.get("status") == "Completed")
            mem_blockers = [e.get("blockers") for e in entries if e.get("blockers")]
            mem_planned = [e.get("planned_next") for e in entries if e.get("planned_next")]
            mem_projects = list(set([e.get("project_name") for e in entries if e.get("project_name")]))

            if entries:
                submitted_count += 1
                total_hours += mem_hours
                total_tasks += len(entries)
                for b in mem_blockers:
                    all_blockers.append({"employee_name": mem.get("full_name"), "blocker": b})
                for pr in mem_projects:
                    all_projects.add(pr)

            team_records.append({
                "employee_id": emp_id,
                "full_name": mem.get("full_name"),
                "email": mem.get("email"),
                "designation": mem.get("designation", "Employee"),
                "department": mem.get("department", "General"),
                "is_submitted": len(entries) > 0,
                "entry_count": len(entries),
                "completed_count": mem_completed,
                "total_hours": round(mem_hours, 2),
                "total_time_str": f"{mem_mins // 60}h {mem_mins % 60}m",
                "entries": serialize_docs(entries),
                "blockers": mem_blockers,
                "planned_next": mem_planned,
                "projects": mem_projects
            })

        pending_count = len(members_list) - submitted_count
        total_mins = int(round(total_hours * 60))

        return {
            "date": diary_date,
            "members": team_records,
            "summary": {
                "total_team_members": len(members_list),
                "submitted_count": submitted_count,
                "pending_count": pending_count,
                "submission_rate": round((submitted_count / len(members_list) * 100) if members_list else 0.0, 1),
                "total_hours": round(total_hours, 2),
                "total_time_str": f"{total_mins // 60}h {total_mins % 60}m",
                "total_tasks_logged": total_tasks,
                "blockers_count": len(all_blockers),
                "blockers_list": all_blockers,
                "active_projects": list(all_projects)
            }
        }

