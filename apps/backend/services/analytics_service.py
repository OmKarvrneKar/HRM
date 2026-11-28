import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from database.connection import get_db
from permissions.rbac import Role
from utils.timezone import now_local, get_local_date_str

logger = logging.getLogger("analytics_service")


class AnalyticsService:
    """
    Centralized analytics and operational visualization service.
    Aggregates real database records for Employee, Team Lead, Manager, and HR roles.
    Strictly enforces role-based boundaries (e.g. HR blocked from project analytics).
    """

    @classmethod
    def get_date_range(cls, period: str = "this_month") -> tuple[str, str]:
        """Calculates start and end date strings (YYYY-MM-DD) based on period filter."""
        today = now_local()
        today_str = today.strftime("%Y-%m-%d")

        if period == "today":
            return today_str, today_str
        elif period == "this_week":
            start = today - timedelta(days=today.weekday())
            return start.strftime("%Y-%m-%d"), today_str
        elif period == "last_month":
            first_this_month = today.replace(day=1)
            last_month_end = first_this_month - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            return last_month_start.strftime("%Y-%m-%d"), last_month_end.strftime("%Y-%m-%d")
        elif period == "this_quarter":
            quarter = (today.month - 1) // 3
            first_month_of_quarter = quarter * 3 + 1
            start = today.replace(month=first_month_of_quarter, day=1)
            return start.strftime("%Y-%m-%d"), today_str
        elif period == "all_time":
            return "2020-01-01", today_str
        else:  # "this_month" (default)
            start = today.replace(day=1)
            return start.strftime("%Y-%m-%d"), today_str

    @classmethod
    def get_analytics_for_user(cls, user: dict, period: str = "this_month", filters: dict = None) -> dict:
        """Route analytics generation strictly according to the authenticated user's role."""
        role = user.get("role")
        start_date, end_date = cls.get_date_range(period)
        filters = filters or {}

        base_meta = {
            "period": period,
            "start_date": start_date,
            "end_date": end_date,
            "role": role,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

        if role == Role.HR:
            return {
                **base_meta,
                "scope": "hr_operations",
                "data": cls._get_hr_analytics(user, start_date, end_date, filters)
            }
        elif role == Role.MANAGER:
            return {
                **base_meta,
                "scope": "operations_oversight",
                "data": cls._get_manager_analytics(user, start_date, end_date, filters)
            }
        elif role == Role.TEAM_LEAD:
            return {
                **base_meta,
                "scope": "team_engineering",
                "data": cls._get_team_lead_analytics(user, start_date, end_date, filters)
            }
        else:
            return {
                **base_meta,
                "scope": "personal_workplace",
                "data": cls._get_employee_analytics(user, start_date, end_date, filters)
            }

    # =========================================================================
    # 1. EMPLOYEE PERSONAL ANALYTICS
    # =========================================================================
    @classmethod
    def _get_employee_analytics(cls, user: dict, start_date: str, end_date: str, filters: dict) -> dict:
        db = get_db()
        emp_id = user["employee_id"]

        # Attendance stats
        att_records = list(db.attendance_daily.find({
            "employee_id": emp_id,
            "date": {"$gte": start_date, "$lte": end_date}
        }))

        present_days = sum(1 for r in att_records if r.get("status") in ("PRESENT", "ON_TIME", "LATE"))
        late_days = sum(1 for r in att_records if r.get("status") == "LATE" or r.get("is_late"))
        on_time_days = present_days - late_days
        total_hours = sum(r.get("total_hours", 0) or 0 for r in att_records)

        # Leave stats
        leave_requests = list(db.leave_requests.find({"employee_id": emp_id}))
        approved_leaves = sum(r.get("days_count", 0) for r in leave_requests if r.get("status") == "Approved")
        pending_leaves = sum(1 for r in leave_requests if r.get("status") == "Pending")

        # Tasks stats
        tasks = list(db.tasks.find({"assigned_to": emp_id}))
        total_tasks = len(tasks)
        completed_tasks = sum(1 for t in tasks if t.get("status") in ("COMPLETED", "Done"))
        in_progress_tasks = sum(1 for t in tasks if t.get("status") in ("IN_PROGRESS", "In Progress"))
        pending_tasks = total_tasks - completed_tasks - in_progress_tasks

        # Skills stats
        skills = list(db.skills.find({"employee_id": emp_id}))
        skill_categories = {}
        for s in skills:
            cat = s.get("category", "General")
            skill_categories[cat] = skill_categories.get(cat, 0) + 1

        return {
            "summary_kpis": {
                "present_days": present_days,
                "total_hours": round(total_hours, 1),
                "on_time_ratio": round((on_time_days / present_days * 100), 1) if present_days > 0 else 100.0,
                "completed_tasks": completed_tasks,
                "pending_tasks": pending_tasks,
                "approved_leave_days": approved_leaves,
                "skills_count": len(skills)
            },
            "attendance_breakdown": {
                "labels": ["On-Time", "Late", "Leaves / Off"],
                "values": [on_time_days, late_days, approved_leaves]
            },
            "task_status_distribution": {
                "labels": ["Completed", "In Progress", "Pending"],
                "values": [completed_tasks, in_progress_tasks, max(0, pending_tasks)]
            },
            "skill_category_distribution": {
                "labels": list(skill_categories.keys()) or ["General"],
                "values": list(skill_categories.values()) or [0]
            }
        }

    # =========================================================================
    # 2. TEAM LEAD ANALYTICS
    # =========================================================================
    @classmethod
    def _get_team_lead_analytics(cls, user: dict, start_date: str, end_date: str, filters: dict) -> dict:
        db = get_db()
        emp_id = user["employee_id"]
        team_id = filters.get("team_id") or user.get("team_id")

        # Team members
        team_query = {"team_id": team_id} if team_id else {"team_lead_id": emp_id}
        team_members = list(db.users.find(team_query, {"employee_id": 1, "full_name": 1}))
        member_ids = [m["employee_id"] for m in team_members]
        if emp_id not in member_ids:
            member_ids.append(emp_id)

        # Team projects
        projects = list(db.projects.find({
            "$or": [
                {"lead_id": emp_id},
                {"team_id": team_id},
                {"assigned_employee_ids": emp_id}
            ]
        }))

        total_projects = len(projects)
        active_projects = sum(1 for p in projects if p.get("status") in ("ACTIVE", "In Progress"))
        completed_projects = sum(1 for p in projects if p.get("status") in ("COMPLETED", "Completed"))

        # Team Tasks & Workload
        tasks = list(db.tasks.find({"assigned_to": {"$in": member_ids}}))
        workload_by_member = {}
        for m in team_members:
            workload_by_member[m["full_name"]] = 0

        for t in tasks:
            assignee = t.get("assigned_to")
            # find name
            name = next((m["full_name"] for m in team_members if m["employee_id"] == assignee), assignee)
            workload_by_member[name] = workload_by_member.get(name, 0) + 1

        total_tasks = len(tasks)
        completed_tasks = sum(1 for t in tasks if t.get("status") in ("COMPLETED", "Done"))
        overdue_tasks = sum(1 for t in tasks if t.get("is_overdue") or (t.get("due_date", "9999") < get_local_date_str() and t.get("status") not in ("COMPLETED", "Done")))

        # Team Attendance
        att_records = list(db.attendance_daily.find({
            "employee_id": {"$in": member_ids},
            "date": {"$gte": start_date, "$lte": end_date}
        }))
        present_count = sum(1 for r in att_records if r.get("status") in ("PRESENT", "ON_TIME", "LATE"))
        total_possible = max(1, len(member_ids) * max(1, len(set(r.get("date") for r in att_records)) or 1))
        att_rate = min(100.0, round((present_count / total_possible) * 100, 1))

        # Team Skills
        skills = list(db.skills.find({"employee_id": {"$in": member_ids}}))
        skill_breakdown = {}
        for s in skills:
            cat = s.get("category", "Engineering")
            skill_breakdown[cat] = skill_breakdown.get(cat, 0) + 1

        return {
            "summary_kpis": {
                "team_members_count": len(team_members),
                "active_projects": active_projects,
                "total_team_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "overdue_tasks": overdue_tasks,
                "team_attendance_rate": att_rate
            },
            "project_status_distribution": {
                "labels": ["Active / In Progress", "Completed", "Planning / On Hold"],
                "values": [active_projects, completed_projects, max(0, total_projects - active_projects - completed_projects)]
            },
            "member_workload": {
                "labels": list(workload_by_member.keys()) or ["No Members"],
                "values": list(workload_by_member.values()) or [0]
            },
            "team_skill_categories": {
                "labels": list(skill_breakdown.keys()) or ["Technical"],
                "values": list(skill_breakdown.values()) or [0]
            }
        }

    # =========================================================================
    # 3. MANAGER OPERATIONS ANALYTICS
    # =========================================================================
    @classmethod
    def _get_manager_analytics(cls, user: dict, start_date: str, end_date: str, filters: dict) -> dict:
        db = get_db()

        # Cross-team projects
        projects = list(db.projects.find({}))
        total_projects = len(projects)
        active_projects = sum(1 for p in projects if p.get("status") in ("ACTIVE", "In Progress", "In Development"))
        completed_projects = sum(1 for p in projects if p.get("status") in ("COMPLETED", "Completed"))
        delayed_projects = sum(1 for p in projects if p.get("is_delayed") or p.get("status") == "DELAYED")

        # Project Progress list
        project_progress = []
        for p in projects[:6]:
            project_progress.append({
                "project_id": p.get("project_id"),
                "title": p.get("title", p.get("project_id")),
                "progress_percentage": p.get("progress_percentage", 0) or 0,
                "status": p.get("status", "ACTIVE")
            })

        # All Tasks
        tasks = list(db.tasks.find({}))
        total_tasks = len(tasks)
        completed_tasks = sum(1 for t in tasks if t.get("status") in ("COMPLETED", "Done"))
        in_progress_tasks = sum(1 for t in tasks if t.get("status") in ("IN_PROGRESS", "In Progress"))
        overdue_tasks = sum(1 for t in tasks if t.get("is_overdue") or (t.get("due_date", "9999") < get_local_date_str() and t.get("status") not in ("COMPLETED", "Done")))

        # Organization Attendance trend
        att_records = list(db.attendance_daily.find({
            "date": {"$gte": start_date, "$lte": end_date}
        }))
        daily_trends = {}
        for r in att_records:
            d = r.get("date")
            if d:
                daily_trends[d] = daily_trends.get(d, 0) + 1

        sorted_dates = sorted(daily_trends.keys())
        trend_labels = sorted_dates[-14:] if len(sorted_dates) > 14 else sorted_dates
        trend_values = [daily_trends[d] for d in trend_labels]

        # Workforce distribution
        users = list(db.users.find({"is_active": True}))
        dept_dist = {}
        for u in users:
            dept = u.get("department", "Operations")
            dept_dist[dept] = dept_dist.get(dept, 0) + 1

        return {
            "summary_kpis": {
                "total_projects": total_projects,
                "active_projects": active_projects,
                "completed_projects": completed_projects,
                "delayed_projects": delayed_projects,
                "total_tasks": total_tasks,
                "task_completion_rate": round((completed_tasks / max(1, total_tasks)) * 100, 1),
                "overdue_tasks": overdue_tasks,
                "active_workforce": len(users)
            },
            "project_status_distribution": {
                "labels": ["Active", "Completed", "Delayed", "Planning"],
                "values": [
                    active_projects,
                    completed_projects,
                    delayed_projects,
                    max(0, total_projects - active_projects - completed_projects - delayed_projects)
                ]
            },
            "task_stage_distribution": {
                "labels": ["Completed", "In Progress", "Pending", "Overdue"],
                "values": [completed_tasks, in_progress_tasks, max(0, total_tasks - completed_tasks - in_progress_tasks), overdue_tasks]
            },
            "attendance_trend": {
                "labels": trend_labels or ["Today"],
                "values": trend_values or [len(att_records)]
            },
            "department_headcount": {
                "labels": list(dept_dist.keys()) or ["General"],
                "values": list(dept_dist.values()) or [len(users)]
            },
            "top_projects": project_progress
        }

    # =========================================================================
    # 4. HR WORKFORCE & ADMINISTRATION ANALYTICS (NO PROJECTS!)
    # =========================================================================
    @classmethod
    def _get_hr_analytics(cls, user: dict, start_date: str, end_date: str, filters: dict) -> dict:
        db = get_db()

        # All Users
        users = list(db.users.find({}))
        active_users = [u for u in users if u.get("is_active", True) and u.get("status") not in ("offboarded", "deactivated")]
        offboarded_users = [u for u in users if not u.get("is_active", True) or u.get("status") in ("offboarded", "deactivated")]

        # Department Breakdown
        dept_dist = {}
        for u in active_users:
            dept = u.get("department", "Operations")
            dept_dist[dept] = dept_dist.get(dept, 0) + 1

        # Monthly Joining / Hiring trends
        hiring_by_month = {}
        for u in users:
            join_date = u.get("joining_date", "")
            if len(join_date) >= 7:
                ym = join_date[:7]
                hiring_by_month[ym] = hiring_by_month.get(ym, 0) + 1

        sorted_ym = sorted(hiring_by_month.keys())[-6:] if hiring_by_month else []
        hiring_labels = sorted_ym or [start_date[:7]]
        hiring_values = [hiring_by_month.get(ym, 0) for ym in hiring_labels]

        # Leaves administration
        leave_requests = list(db.leave_requests.find({}))
        leave_by_status = {"Approved": 0, "Pending": 0, "Rejected": 0}
        leave_by_type = {}
        for r in leave_requests:
            st = r.get("status", "Pending")
            leave_by_status[st] = leave_by_status.get(st, 0) + 1
            l_type = r.get("leave_type", "Casual Leave")
            leave_by_type[l_type] = leave_by_type.get(l_type, 0) + 1

        # Attendance exceptions in date range
        att_records = list(db.attendance_daily.find({
            "date": {"$gte": start_date, "$lte": end_date}
        }))
        late_instances = sum(1 for r in att_records if r.get("status") == "LATE" or r.get("is_late"))
        total_present = sum(1 for r in att_records if r.get("status") in ("PRESENT", "ON_TIME", "LATE"))

        # Confidential HR Complaints
        complaints = list(db.complaints.find({}))
        open_complaints = sum(1 for c in complaints if c.get("status") in ("Open", "Under Review", "PENDING"))
        resolved_complaints = sum(1 for c in complaints if c.get("status") in ("Resolved", "CLOSED"))

        return {
            "summary_kpis": {
                "total_active_employees": len(active_users),
                "total_offboarded": len(offboarded_users),
                "pending_leave_approvals": leave_by_status.get("Pending", 0),
                "attendance_late_exceptions": late_instances,
                "total_attendance_logs": total_present,
                "open_hr_complaints": open_complaints,
                "resolved_hr_complaints": resolved_complaints
            },
            "department_distribution": {
                "labels": list(dept_dist.keys()) or ["General"],
                "values": list(dept_dist.values()) or [len(active_users)]
            },
            "hiring_trends": {
                "labels": hiring_labels,
                "values": hiring_values
            },
            "leave_status_distribution": {
                "labels": ["Approved", "Pending", "Rejected"],
                "values": [
                    leave_by_status.get("Approved", 0),
                    leave_by_status.get("Pending", 0),
                    leave_by_status.get("Rejected", 0)
                ]
            },
            "leave_type_distribution": {
                "labels": list(leave_by_type.keys()) or ["Casual Leave"],
                "values": list(leave_by_type.values()) or [0]
            }
        }

    # =========================================================================
    # 5. CSV EXPORT UTILITY
    # =========================================================================
    @classmethod
    def export_analytics_csv(cls, user: dict, period: str = "this_month", filters: dict = None) -> tuple[str, str]:
        """Generates authorized CSV stream based on the caller's role."""
        data = cls.get_analytics_for_user(user, period=period, filters=filters)
        output = io.StringIO()
        writer = csv.writer(output)

        role = user.get("role")
        today_str = get_local_date_str()
        filename = f"ai_samrat_analytics_{role}_{period}_{today_str}.csv"

        writer.writerow(["AI SAMRAT HRMS — OPERATIONAL METRICS REPORT"])
        writer.writerow(["Report Scope", data.get("scope")])
        writer.writerow(["Period", data.get("period")])
        writer.writerow(["Start Date", data.get("start_date")])
        writer.writerow(["End Date", data.get("end_date")])
        writer.writerow(["Generated By", f"{user.get('full_name')} ({user.get('employee_id')})"])
        writer.writerow(["Role", role.upper()])
        writer.writerow([])

        # Write KPIs
        writer.writerow(["KEY PERFORMANCE INDICATORS (KPIS)"])
        writer.writerow(["Metric", "Value"])
        kpis = data.get("data", {}).get("summary_kpis", {})
        for k, v in kpis.items():
            metric_label = k.replace("_", " ").title()
            writer.writerow([metric_label, v])
        writer.writerow([])

        # Write Distributions
        d = data.get("data", {})
        for section_key, section_data in d.items():
            if isinstance(section_data, dict) and "labels" in section_data and "values" in section_data:
                section_title = section_key.replace("_", " ").title()
                writer.writerow([f"DISTRIBUTION: {section_title.upper()}"])
                writer.writerow(["Category / Label", "Count / Value"])
                for label, val in zip(section_data["labels"], section_data["values"]):
                    writer.writerow([label, val])
                writer.writerow([])

        return output.getvalue(), filename
