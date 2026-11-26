import io
import csv
from openpyxl import Workbook
from backend.services.attendance_service import AttendanceService
from backend.services.project_service import ProjectService
from backend.database.connection import get_db
from backend.permissions.rbac import Role, normalize_role


class ExportService:
    @classmethod
    def export_attendance_csv(cls, records: list) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Employee ID",
            "Name",
            "Department",
            "Date",
            "First Login (UTC)",
            "Final Qualifying Logout (UTC)",
            "Status",
            "Late Status",
            "Delay (Minutes)",
            "Official Working Duration",
            "Active Session Duration",
            "Sessions Count"
        ])

        for r in records:
            writer.writerow([
                r.get("employee_id"),
                r.get("employee_name"),
                r.get("department"),
                r.get("attendance_date"),
                r.get("first_login"),
                r.get("final_qualifying_logout"),
                r.get("status"),
                r.get("late_arrival_status"),
                r.get("delay_minutes", 0),
                r.get("official_working_duration_display", "0h 0m"),
                r.get("total_active_session_display", "0h 0m"),
                r.get("session_count", 0)
            ])

        return output.getvalue()

    @classmethod
    def export_attendance_excel(cls, records: list) -> io.BytesIO:
        wb = Workbook()
        ws = wb.active
        ws.title = "Attendance Report"

        headers = [
            "Employee ID", "Name", "Department", "Date",
            "First Login", "Final Qualifying Logout", "Status",
            "Late Status", "Delay (Mins)", "Official Working Duration",
            "Active Session Duration", "Sessions Count"
        ]
        ws.append(headers)

        for r in records:
            ws.append([
                r.get("employee_id"),
                r.get("employee_name"),
                r.get("department"),
                r.get("attendance_date"),
                str(r.get("first_login")) if r.get("first_login") else "-",
                str(r.get("final_qualifying_logout")) if r.get("final_qualifying_logout") else "-",
                r.get("status"),
                r.get("late_arrival_status"),
                r.get("delay_minutes", 0),
                r.get("official_working_duration_display", "0h 0m"),
                r.get("total_active_session_display", "0h 0m"),
                r.get("session_count", 0)
            ])

        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        return stream

    @classmethod
    def export_administrative_zip(cls, actor: dict) -> io.BytesIO:
        """Packages all organizational records into a comprehensive administrative ZIP archive."""
        if not actor or normalize_role(actor.get("role")) not in (Role.HR, Role.ADMIN):
            raise PermissionError("Unauthorized: Only HR and Administrators can export administrative archives.")
        import zipfile
        db = get_db()
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # 1. Attendance Daily Summary
            wb_att = Workbook()
            ws_att = wb_att.active
            ws_att.title = "Attendance Summary"
            att_headers = [
                "Employee ID", "Employee Name", "Date", "First Login (UTC)",
                "Final Qualifying Logout", "Status", "Late Status", "Delay (Mins)",
                "Official Working Duration", "Active Duration"
            ]
            ws_att.append(att_headers)
            for r in db.attendance_daily.find({}).sort("attendance_date", -1):
                ws_att.append([
                    r.get("employee_id"), r.get("employee_name"), r.get("attendance_date"),
                    str(r.get("first_login")) if r.get("first_login") else "-",
                    str(r.get("final_qualifying_logout")) if r.get("final_qualifying_logout") else "-",
                    r.get("status"), r.get("late_arrival_status"), r.get("delay_minutes", 0),
                    r.get("official_working_duration_display", "0h 0m"),
                    r.get("total_active_session_display", "0h 0m")
                ])
            buf_att = io.BytesIO()
            wb_att.save(buf_att)
            zip_file.writestr("Attendance_Summary.xlsx", buf_att.getvalue())

            # 2. Staff Directory
            wb_usr = Workbook()
            ws_usr = wb_usr.active
            ws_usr.title = "Staff Roster"
            usr_headers = [
                "Employee ID", "Full Name", "Email", "Role", "Department",
                "Designation", "Joining Date", "Status", "Phone Number", "PAN"
            ]
            ws_usr.append(usr_headers)
            for u in db.users.find({}, {"password_hash": 0}).sort("employee_id", 1):
                sal = u.get("salary_info") or {}
                ws_usr.append([
                    u.get("employee_id"), u.get("full_name"), u.get("email"),
                    u.get("role"), u.get("department"), u.get("designation"),
                    u.get("joining_date"), "Active" if u.get("is_active", True) else "Inactive",
                    u.get("phone_number", "-"), sal.get("pan_number", "-")
                ])
            buf_usr = io.BytesIO()
            wb_usr.save(buf_usr)
            zip_file.writestr("Staff_Directory.xlsx", buf_usr.getvalue())

            # 3. Projects and Tasks
            wb_prj = Workbook()
            ws_prj = wb_prj.active
            ws_prj.title = "Projects"
            prj_headers = [
                "Project ID", "Title", "Department", "Status", "Priority",
                "Progress (%)", "Manager", "Due Date"
            ]
            ws_prj.append(prj_headers)
            for p in db.projects.find({}).sort("project_id", 1):
                ws_prj.append([
                    p.get("project_id"), p.get("title"), p.get("department"),
                    p.get("status"), p.get("priority"), p.get("progress_percentage", 0),
                    p.get("manager_employee_id"), p.get("due_date")
                ])
            buf_prj = io.BytesIO()
            wb_prj.save(buf_prj)
            zip_file.writestr("Projects_Report.xlsx", buf_prj.getvalue())

            # 4. Leave & Permission Requests
            wb_lve = Workbook()
            ws_lve = wb_lve.active
            ws_lve.title = "Leave Requests"
            lve_headers = [
                "Request ID", "Employee ID", "Type", "From Date", "To Date",
                "Status", "Reason", "Decided By"
            ]
            ws_lve.append(lve_headers)
            for l in db.leave_requests.find({}).sort("created_at", -1):
                ws_lve.append([
                    l.get("request_id"), l.get("employee_id"), l.get("request_type"),
                    l.get("start_date") or l.get("from_date"), l.get("end_date") or l.get("to_date"),
                    l.get("status"), l.get("reason"), l.get("decided_by")
                ])
            buf_lve = io.BytesIO()
            wb_lve.save(buf_lve)
            zip_file.writestr("Leave_Requests.xlsx", buf_lve.getvalue())

            # 5. Organization Holidays
            from backend.services.holiday_service import HolidayService
            holidays = HolidayService.get_all_holidays()
            wb_hol = Workbook()
            ws_hol = wb_hol.active
            ws_hol.title = "Holidays"
            ws_hol.append(["Holiday ID", "Date", "Name", "Type"])
            for h in holidays:
                ws_hol.append([h.get("holiday_id"), h.get("date"), h.get("name"), h.get("type")])
            buf_hol = io.BytesIO()
            wb_hol.save(buf_hol)
            zip_file.writestr("Holidays_Schedule.xlsx", buf_hol.getvalue())

        zip_buffer.seek(0)
        return zip_buffer
