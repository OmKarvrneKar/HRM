import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database.connection import get_db
from backend.database.indexes import setup_indexes
from backend.auth.security import hash_password
from backend.permissions.rbac import Role
from backend.services.attendance_service import AttendanceService
from backend.services.project_service import ProjectService
from backend.services.complaint_service import ComplaintService
from backend.services.notification_service import NotificationService
from backend.services.user_service import UserService
from backend.utils.timezone import get_app_timezone, get_local_date_str


def seed_database(force_reset: bool = False):
    print("Initializing database collections and indexes...")
    db = get_db()
    setup_indexes(db)

    from backend.database.connection import DatabaseManager

    if force_reset:
        print("[BACKUP] Creating snapshot of current database before reset...")
        DatabaseManager.backup_database(getattr(db, "name", "office_hrm"))
        print("[RESET] Wiping existing collections as force_reset=True was requested...")
        for col in [
            "users", "attendance_events", "attendance_daily", "projects",
            "teams", "tasks", "notifications", "complaints", "profile_change_logs",
            "audit_logs", "organization_settings", "holidays", "skills", "skill_recommendations",
            "leave_requests", "work_diary", "conversations", "messages", "login_attempts"
        ]:
            db[col].delete_many({})
    else:
        print("[SAFE SEED] Preserving existing records. Only inserting missing demo baseline data...")

    from backend.services.holiday_service import HolidayService
    HolidayService.seed_default_holidays(db)

    tz = get_app_timezone()
    today_str = get_local_date_str()
    y, m, d = map(int, today_str.split("-"))

    print("Seeding Users...")
    users_data = [
        {
            "employee_id": "ADM-1001",
            "full_name": "System Administrator",
            "email": "admin@aisamrat.com",
            "password_hash": hash_password("Admin@Samrat2026!"),
            "role": Role.MANAGER,
            "department": "IT & Infrastructure",
            "designation": "Principal Infrastructure & Operations Manager",
            "team_id": "TEAM-EXEC",
            "joining_date": "2020-01-01",
            "date_of_birth": "1984-06-15",
            "employment_status": "Active",
            "phone_number": "+91 9811100001",
            "address": "AI Samrat HQ, Bengaluru",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "employee_id": "ORG-1001",
            "full_name": "Operations Director",
            "email": "org@aisamrat.com",
            "password_hash": hash_password("Org@Samrat2026!"),
            "role": Role.MANAGER,
            "department": "Corporate Operations",
            "designation": "Director of Corporate Operations",
            "team_id": "TEAM-EXEC",
            "joining_date": "2021-01-01",
            "date_of_birth": "1983-09-10",
            "employment_status": "Active",
            "phone_number": "+91 9811100002",
            "address": "AI Samrat Corporate Tower, Bengaluru",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "employee_id": "MGR-1001",
            "full_name": "Vikramaditya Roy",
            "email": "mgr@aisamrat.com",
            "password_hash": hash_password("Admin@Nexus2026!"),
            "role": Role.HR,
            "department": "Human Resources Executive",
            "designation": "Head of HR Operations & People Lead",
            "team_id": "TEAM-HR-OPS",
            "joining_date": "2021-01-15",
            "date_of_birth": "1985-04-12",
            "employment_status": "Active",
            "phone_number": "+91 9811122233",
            "address": "402 Royal Palms, Bangalore",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "employee_id": "HR-1000",
            "full_name": "AI Samrat HR",
            "email": "hr@aisamrat.com",
            "password_hash": hash_password("Hr@Samrat2026!"),
            "role": Role.HR,
            "department": "Human Resources",
            "designation": "HR Administrator",
            "team_id": "TEAM-HR-OPS",
            "joining_date": "2022-01-01",
            "date_of_birth": "1990-01-01",
            "employment_status": "Active",
            "phone_number": "+91 9800011122",
            "address": "AI Samrat Corporate Tower, Bangalore",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "employee_id": "HR-1001",
            "full_name": "Priya Sharma",
            "email": "hr.priya@aisamrat.com",
            "password_hash": hash_password("Hr@Priya2026!"),
            "role": Role.HR,
            "department": "Human Resources",
            "designation": "Senior HR Generalist",
            "team_id": "TEAM-HR-OPS",
            "joining_date": "2022-03-01",
            "date_of_birth": "1992-08-20",
            "employment_status": "Active",
            "phone_number": "+91 9822233344",
            "address": "15 Green Valley, Indiranagar, Bangalore",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "employee_id": "HR-1002",
            "full_name": "Amit Patel",
            "email": "hr.amit@aisamrat.com",
            "password_hash": hash_password("Hr@Amit2026!"),
            "role": Role.HR,
            "department": "Human Resources",
            "designation": "HR Operations Specialist",
            "team_id": "TEAM-HR-OPS",
            "joining_date": "2023-06-15",
            "date_of_birth": "1994-11-05",
            "employment_status": "Active",
            "phone_number": "+91 9833344455",
            "address": "88 Lakeview Road, Koramangala, Bangalore",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "employee_id": "EMP-1001",
            "full_name": "Rahul Verma",
            "email": "emp.rahul@aisamrat.com",
            "password_hash": hash_password("Emp@Rahul2026!"),
            "role": Role.EMPLOYEE,
            "department": "Engineering",
            "designation": "AI/ML Engineering Intern",
            "team_id": "TEAM-CORE-ENG",
            "joining_date": "2023-01-10",
            "date_of_birth": "1995-05-18",
            "employment_status": "Active",
            "phone_number": "+91 9844455566",
            "address": "120 Whitefield Tech Zone, Bangalore",
            "emergency_contact": "+91 9844455500 (Spouse)",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "employee_id": "EMP-1002",
            "full_name": "Sneha Reddy",
            "email": "emp.sneha@aisamrat.com",
            "password_hash": hash_password("Emp@Sneha2026!"),
            "role": Role.EMPLOYEE,
            "department": "Engineering",
            "designation": "AI Systems & LLM Intern",
            "team_id": "TEAM-CORE-ENG",
            "joining_date": "2023-04-12",
            "date_of_birth": "1996-09-25",
            "employment_status": "Active",
            "phone_number": "+91 9855566677",
            "address": "77 Cyber City, HSR Layout, Bangalore",
            "emergency_contact": "+91 9855566600 (Parent)",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "employee_id": "EMP-1003",
            "full_name": "Karan Mehta",
            "email": "emp.karan@aisamrat.com",
            "password_hash": hash_password("Emp@Karan2026!"),
            "role": Role.EMPLOYEE,
            "department": "Quality Assurance",
            "designation": "AI/ML QA & Testing Intern",
            "team_id": "TEAM-QA",
            "joining_date": "2024-02-01",
            "date_of_birth": "1997-12-14",
            "employment_status": "Active",
            "phone_number": "+91 9866677788",
            "address": "204 BTM 2nd Stage, Bangalore",
            "emergency_contact": "+91 9866677700 (Sibling)",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "employee_id": "EMP-1004",
            "full_name": "Ananya Sen",
            "email": "emp.ananya@aisamrat.com",
            "password_hash": hash_password("Emp@Ananya2026!"),
            "role": Role.EMPLOYEE,
            "department": "Product & Design",
            "designation": "AI Product & UI/UX Design Intern",
            "team_id": "TEAM-DESIGN",
            "joining_date": "2024-05-15",
            "date_of_birth": f"1998-{m:02d}-{d:02d}",
            "employment_status": "Active",
            "phone_number": "+91 9877788899",
            "address": "55 Domlur Heights, Bangalore",
            "emergency_contact": "+91 9877788800 (Parent)",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "employee_id": "LEAD-1001",
            "full_name": "Kavita Nair",
            "email": "lead.kavita@aisamrat.com",
            "password_hash": hash_password("Lead@Kavita2026!"),
            "role": Role.TEAM_LEAD,
            "department": "Engineering & Upskilling",
            "designation": "Staff AI Engineering Lead & Technical Trainer",
            "team_id": "TEAM-CORE-ENG",
            "joining_date": "2022-02-15",
            "date_of_birth": "1990-07-11",
            "employment_status": "Active",
            "phone_number": "+91 9888899900",
            "address": "104 Palm Grove, Indiranagar, Bangalore",
            "emergency_contact": "+91 9888899911 (Spouse)",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "employee_id": "TRN-1001",
            "full_name": "Rajesh Sharma",
            "email": "trainer.rajesh@aisamrat.com",
            "password_hash": hash_password("Trainer@Rajesh2026!"),
            "role": Role.TEAM_LEAD,
            "department": "Engineering & Learning",
            "designation": "Technical Training & Competency Lead",
            "team_id": "TEAM-CORE-ENG",
            "joining_date": "2022-08-01",
            "date_of_birth": "1988-03-22",
            "employment_status": "Active",
            "phone_number": "+91 9899900011",
            "address": "22 Silicon Terraces, Electronic City, Bangalore",
            "emergency_contact": "+91 9899900022 (Sibling)",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
    ]

    inserted_users = 0
    for u in users_data:
        if not db.users.find_one({"$or": [{"email": u["email"]}, {"employee_id": u.get("employee_id")}]}):
            u["salary_info"] = UserService.get_salary_info(u)
            u["skills"] = UserService.get_user_skills(u)
            db.users.insert_one(u)
            inserted_users += 1
    if inserted_users > 0:
        print(f"Inserted {inserted_users} baseline demo users.")

    if db.organization_settings.count_documents({"key": "attendance_policy"}) == 0:
        print("Seeding Organization Settings...")
        db.organization_settings.insert_one({
            "key": "attendance_policy",
            "value": {
                "office_start_time": "10:00",
                "office_end_time": "18:00",
                "late_grace_minutes": 0,
                "timezone": "Asia/Kolkata",
                "leap_day_policy": "Feb 28 in non-leap years"
            },
            "updated_at": datetime.now(timezone.utc)
        })

    print("Checking Teams & Projects...")
    teams = [
        {"team_id": "TEAM-CORE-ENG", "name": "Core Platform Engineering", "department": "Engineering", "lead_employee_id": "LEAD-1001", "members": ["LEAD-1001", "EMP-1001", "EMP-1002"]},
        {"team_id": "TEAM-QA", "name": "Quality Assurance", "department": "Quality Assurance", "lead_employee_id": "EMP-1003", "members": ["EMP-1003"]},
        {"team_id": "TEAM-DESIGN", "name": "Product Design", "department": "Product & Design", "lead_employee_id": "EMP-1004", "members": ["EMP-1004"]},
        {"team_id": "TEAM-HR-OPS", "name": "HR People Operations", "department": "Human Resources", "lead_employee_id": "HR-1001", "members": ["HR-1001", "HR-1002", "TRN-1001"]}
    ]
    for t in teams:
        if not db.teams.find_one({"team_id": t["team_id"]}):
            t["created_at"] = datetime.now(timezone.utc)
            t["updated_at"] = datetime.now(timezone.utc)
            db.teams.insert_one(t)

    projects = [
        {
            "project_id": "PRJ-1001",
            "title": "Enterprise Cloud Migration & Microservices",
            "description": "Migrating legacy monolithic infrastructure to scalable containerized microservices on AWS.",
            "department": "Engineering",
            "client": "Internal Infrastructure",
            "start_date": "2026-08-01",
            "due_date": "2026-12-15",
            "priority": "High",
            "status": "In Progress",
            "team_id": "TEAM-CORE-ENG",
            "manager_employee_id": "HR-1001",
            "members": ["EMP-1001", "EMP-1002"],
            "progress_percentage": 65,
            "created_by": "HR-1001",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "project_id": "PRJ-1002",
            "title": "Next-Gen Design System & Accessibility",
            "description": "Revamping component libraries with WCAG 2.1 AA accessibility compliance and micro-interactions.",
            "department": "Product & Design",
            "client": "Design Ops",
            "start_date": "2026-09-10",
            "due_date": "2026-11-30",
            "priority": "Medium",
            "status": "In Progress",
            "team_id": "TEAM-DESIGN",
            "manager_employee_id": "HR-1001",
            "members": ["EMP-1004", "EMP-1003"],
            "progress_percentage": 40,
            "created_by": "HR-1001",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
    ]
    for p in projects:
        if not db.projects.find_one({"project_id": p["project_id"]}):
            db.projects.insert_one(p)

    tasks = [
        {
            "task_id": "TSK-1001",
            "project_id": "PRJ-1001",
            "title": "Containerize core API services and configure health checks",
            "assigned_employee_id": "EMP-1001",
            "due_date": "2026-10-25",
            "status": "Completed",
            "progress_percentage": 100,
            "weight": 2.0,
            "notes": "Dockerfiles and compose specs reviewed.",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "task_id": "TSK-1002",
            "project_id": "PRJ-1001",
            "title": "Implement distributed session caching with Redis/Mongo cluster",
            "assigned_employee_id": "EMP-1002",
            "due_date": "2026-11-05",
            "status": "In Progress",
            "progress_percentage": 50,
            "weight": 3.0,
            "notes": "Benchmarked failover latency under 20ms.",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "task_id": "TSK-1003",
            "project_id": "PRJ-1002",
            "title": "Design token definitions and high-contrast color palette",
            "assigned_employee_id": "EMP-1004",
            "due_date": "2026-10-20",
            "status": "In Progress",
            "progress_percentage": 60,
            "weight": 2.0,
            "notes": "Color contrast verified for AAA ratings.",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
    ]
    for t in tasks:
        if not db.tasks.find_one({"task_id": t["task_id"]}):
            db.tasks.insert_one(t)

    def make_event(emp_id, emp_name, local_h, local_m, event_type, sid, is_closed=None):
        local_dt = datetime(y, m, d, local_h, local_m, 0, tzinfo=tz)
        utc_dt = local_dt.astimezone(timezone.utc)
        closed_flag = (event_type == "LOGOUT") if is_closed is None else is_closed
        return {
            "employee_id": emp_id,
            "employee_name": emp_name,
            "date": today_str,
            "session_id": sid,
            "event_type": event_type,
            "timestamp": utc_dt,
            "is_closed": closed_flag,
            "event_source": "WEB",
            "created_at": utc_dt,
            "updated_at": utc_dt
        }

    events = [
        make_event("EMP-1001", "Rahul Verma", 9, 45, "LOGIN", "sess-rahul-1", is_closed=True),
        make_event("EMP-1001", "Rahul Verma", 12, 30, "LOGOUT", "sess-rahul-1"),
        make_event("EMP-1001", "Rahul Verma", 13, 30, "LOGIN", "sess-rahul-2", is_closed=True),
        make_event("EMP-1001", "Rahul Verma", 18, 30, "LOGOUT", "sess-rahul-2"),

        make_event("EMP-1002", "Sneha Reddy", 10, 25, "LOGIN", "sess-sneha-1", is_closed=False),

        make_event("EMP-1003", "Karan Mehta", 9, 55, "LOGIN", "sess-karan-1", is_closed=True),
        make_event("EMP-1003", "Karan Mehta", 16, 30, "LOGOUT", "sess-karan-1"),

        make_event("HR-1001", "Priya Sharma", 9, 30, "LOGIN", "sess-priya-1", is_closed=True),
        make_event("HR-1001", "Priya Sharma", 18, 15, "LOGOUT", "sess-priya-1")
    ]

    if db.attendance_events.count_documents({}) == 0:
        print("Seeding Attendance Events illustrating core rules...")
        for ev in events:
            db.attendance_events.insert_one(ev)

        print("Recalculating attendance daily summaries...")
        AttendanceService.recalculate_daily_summary("EMP-1001", today_str)
        AttendanceService.recalculate_daily_summary("EMP-1002", today_str)
        AttendanceService.recalculate_daily_summary("EMP-1003", today_str)
        AttendanceService.recalculate_daily_summary("HR-1001", today_str)

    print("Seeding Complaints...")
    complaints = [
        {
            "complaint_id": "CMP-1001",
            "complainant_id": "EMP-1002",
            "complainant_name": "Sneha Reddy",
            "complainant_email": "emp.sneha@aisamrat.com",
            "category": "Workplace Harassment",
            "subject": "Inappropriate comments during off-site sprint retrospective",
            "description": "During yesterday's offsite team event, inappropriate remarks regarding gender roles were repeatedly directed at junior members.",
            "priority": "Urgent",
            "status": "Under Review",
            "assigned_hr_id": "HR-1001",
            "responses": [
                {
                    "sender_id": "HR-1001",
                    "sender_name": "Priya Sharma",
                    "sender_role": "hr",
                    "message": "Thank you for bringing this forward Sneha. We treat workplace conduct very seriously. I have scheduled an initial confidential discovery session.",
                    "timestamp": datetime.now(timezone.utc) - timedelta(hours=2)
                }
            ],
            "created_at": datetime.now(timezone.utc) - timedelta(days=1),
            "updated_at": datetime.now(timezone.utc) - timedelta(hours=2),
            "closed_at": None
        },
        {
            "complaint_id": "CMP-1002",
            "complainant_id": "EMP-1001",
            "complainant_name": "Rahul Verma",
            "complainant_email": "emp.rahul@aisamrat.com",
            "category": "Salary or Benefits Query",
            "subject": "Tax exemption certificate on health insurance premium",
            "description": "Need the Form 16 Annexure for annual medical insurance tax deduction.",
            "priority": "Medium",
            "status": "Resolved",
            "assigned_hr_id": "HR-1002",
            "responses": [
                {
                    "sender_id": "HR-1002",
                    "sender_name": "Amit Patel",
                    "sender_role": "hr",
                    "message": "The tax exemption receipt has been forwarded to your official email and uploaded to the payroll repository.",
                    "timestamp": datetime.now(timezone.utc) - timedelta(days=3)
                }
            ],
            "created_at": datetime.now(timezone.utc) - timedelta(days=5),
            "updated_at": datetime.now(timezone.utc) - timedelta(days=3),
            "closed_at": datetime.now(timezone.utc) - timedelta(days=3)
        }
    ]
    if db.complaints.count_documents({}) == 0:
        print("Seeding Complaints...")
        for c in complaints:
            db.complaints.insert_one(c)

    notifs = [
        {
            "title": "Welcome to AI Samrat Pvt Ltd",
            "message": "Your enterprise HR portal is active. Please review your profile and project allocations.",
            "category": "ANNOUNCEMENT",
            "recipient_group": "ALL",
            "link": "/attendance",
            "is_read": False,
            "read_by": [],
            "created_at": datetime.now(timezone.utc) - timedelta(hours=10)
        },
        {
            "title": "Q4 Performance & Appraisal Cycle Kickoff",
            "message": "HR has initiated the annual appraisal cycle. Please update task contributions by month end.",
            "category": "ANNOUNCEMENT",
            "recipient_group": "EMPLOYEES",
            "link": "/projects",
            "is_read": False,
            "read_by": [],
            "created_at": datetime.now(timezone.utc) - timedelta(hours=4)
        }
    ]
    if db.notifications.count_documents({}) == 0:
        print("Seeding Notifications & Announcements...")
        for n in notifs:
            db.notifications.insert_one(n)
    print("Seeding Skills & Competency Matrix...")
    initial_skills = [
        {
            "skill_id": "SKL-1001",
            "employee_id": "EMP-1001",
            "employee_name": "Rahul Verma",
            "department": "Engineering",
            "team_id": "TEAM-CORE-ENG",
            "skill_name": "Python",
            "category": "Programming",
            "proficiency_level": "Expert",
            "proficiency_score": 4,
            "years_of_experience": 4.5,
            "experience_summary": "Extensive core backend architecture with asyncio, Flask, and performance optimizations.",
            "learning_status": "Practicing",
            "certification_name": "Python Institute Certified PCAP",
            "verified_status": "Verified",
            "trainer_rating": 5,
            "trainer_feedback": "Outstanding architectural mastery and clean code design.",
            "assessor_name": "Rajesh Sharma",
            "assessor_id": "TRN-1001",
            "assessor_role": "trainer",
            "created_at": datetime.now(timezone.utc) - timedelta(days=60),
            "updated_at": datetime.now(timezone.utc) - timedelta(days=10)
        },
        {
            "skill_id": "SKL-1002",
            "employee_id": "EMP-1001",
            "employee_name": "Rahul Verma",
            "department": "Engineering",
            "team_id": "TEAM-CORE-ENG",
            "skill_name": "Flask & FastAPI",
            "category": "Web Development",
            "proficiency_level": "Expert",
            "proficiency_score": 4,
            "years_of_experience": 4.0,
            "experience_summary": "Shipped high-throughput microservices handling millions of events daily.",
            "learning_status": "Practicing",
            "certification_name": "",
            "verified_status": "Verified",
            "trainer_rating": 5,
            "trainer_feedback": "Industry-grade REST API design and secure middleware development.",
            "assessor_name": "Rajesh Sharma",
            "assessor_id": "TRN-1001",
            "assessor_role": "trainer",
            "created_at": datetime.now(timezone.utc) - timedelta(days=60),
            "updated_at": datetime.now(timezone.utc) - timedelta(days=10)
        },
        {
            "skill_id": "SKL-1003",
            "employee_id": "EMP-1001",
            "employee_name": "Rahul Verma",
            "department": "Engineering",
            "team_id": "TEAM-CORE-ENG",
            "skill_name": "MongoDB",
            "category": "Database",
            "proficiency_level": "Advanced",
            "proficiency_score": 3,
            "years_of_experience": 3.5,
            "experience_summary": "Query indexing, aggregation pipelines, replica sets, and distributed locks.",
            "learning_status": "Practicing",
            "certification_name": "MongoDB Certified Associate Developer",
            "verified_status": "Verified",
            "trainer_rating": 4,
            "trainer_feedback": "Solid grasp of compound indexes and schema design.",
            "assessor_name": "Rajesh Sharma",
            "assessor_id": "TRN-1001",
            "assessor_role": "trainer",
            "created_at": datetime.now(timezone.utc) - timedelta(days=60),
            "updated_at": datetime.now(timezone.utc) - timedelta(days=10)
        },
        {
            "skill_id": "SKL-1004",
            "employee_id": "EMP-1001",
            "employee_name": "Rahul Verma",
            "department": "Engineering",
            "team_id": "TEAM-CORE-ENG",
            "skill_name": "Docker & Containerization",
            "category": "Cloud & DevOps",
            "proficiency_level": "Advanced",
            "proficiency_score": 3,
            "years_of_experience": 3.0,
            "experience_summary": "Multi-stage Docker builds, compose stacks, container hardening.",
            "learning_status": "Practicing",
            "certification_name": "Docker Certified Associate",
            "verified_status": "Self-Reported",
            "trainer_rating": None,
            "trainer_feedback": "",
            "assessor_name": "",
            "created_at": datetime.now(timezone.utc) - timedelta(days=30),
            "updated_at": datetime.now(timezone.utc) - timedelta(days=30)
        },
        {
            "skill_id": "SKL-1005",
            "employee_id": "EMP-1002",
            "employee_name": "Sneha Reddy",
            "department": "Engineering",
            "team_id": "TEAM-CORE-ENG",
            "skill_name": "PostgreSQL",
            "category": "Database",
            "proficiency_level": "Expert",
            "proficiency_score": 4,
            "years_of_experience": 4.0,
            "experience_summary": "Relational schema modeling, query optimization, ACID transactions.",
            "learning_status": "Practicing",
            "certification_name": "",
            "verified_status": "Verified",
            "trainer_rating": 5,
            "trainer_feedback": "Exceptional database tuning and indexing skills.",
            "assessor_name": "Rajesh Sharma",
            "assessor_id": "TRN-1001",
            "assessor_role": "trainer",
            "created_at": datetime.now(timezone.utc) - timedelta(days=50),
            "updated_at": datetime.now(timezone.utc) - timedelta(days=15)
        },
        {
            "skill_id": "SKL-1006",
            "employee_id": "EMP-1003",
            "employee_name": "Karan Mehta",
            "department": "Quality Assurance",
            "team_id": "TEAM-QA",
            "skill_name": "PyTest & Automation",
            "category": "Tools",
            "proficiency_level": "Expert",
            "proficiency_score": 4,
            "years_of_experience": 4.5,
            "experience_summary": "End-to-end integration and security test suites with mock engines.",
            "learning_status": "Certified",
            "certification_name": "ISTQB Advanced Test Automation",
            "verified_status": "Verified",
            "trainer_rating": 5,
            "trainer_feedback": "Comprehensive automated testing suites and CI integration.",
            "assessor_name": "Rajesh Sharma",
            "assessor_id": "TRN-1001",
            "assessor_role": "trainer",
            "created_at": datetime.now(timezone.utc) - timedelta(days=40),
            "updated_at": datetime.now(timezone.utc) - timedelta(days=8)
        },
        {
            "skill_id": "SKL-1007",
            "employee_id": "EMP-1004",
            "employee_name": "Ananya Sen",
            "department": "Product & Design",
            "team_id": "TEAM-DESIGN",
            "skill_name": "Figma & Design Systems",
            "category": "Tools",
            "proficiency_level": "Expert",
            "proficiency_score": 4,
            "years_of_experience": 4.0,
            "experience_summary": "Commercial SaaS component libraries, responsive design tokens, and user journeys.",
            "learning_status": "Practicing",
            "certification_name": "Interaction Design Specialist",
            "verified_status": "Verified",
            "trainer_rating": 5,
            "trainer_feedback": "World-class aesthetic sensibilities and component system design.",
            "assessor_name": "Rajesh Sharma",
            "assessor_id": "TRN-1001",
            "assessor_role": "trainer",
            "created_at": datetime.now(timezone.utc) - timedelta(days=35),
            "updated_at": datetime.now(timezone.utc) - timedelta(days=5)
        },
        {
            "skill_id": "SKL-1008",
            "employee_id": "LEAD-1001",
            "employee_name": "Kavita Nair",
            "department": "Engineering",
            "team_id": "TEAM-CORE-ENG",
            "skill_name": "Cloud Infrastructure & Distributed Systems",
            "category": "Cloud & DevOps",
            "proficiency_level": "Expert",
            "proficiency_score": 4,
            "years_of_experience": 7.0,
            "experience_summary": "High-availability multi-region architectures, microservices decoupling, and fault tolerance.",
            "learning_status": "Mentoring",
            "certification_name": "AWS Certified Solutions Architect - Professional",
            "verified_status": "Verified",
            "trainer_rating": 5,
            "trainer_feedback": "Pillar of engineering leadership and resilient system design.",
            "assessor_name": "Rajesh Sharma",
            "assessor_id": "TRN-1001",
            "assessor_role": "trainer",
            "created_at": datetime.now(timezone.utc) - timedelta(days=90),
            "updated_at": datetime.now(timezone.utc) - timedelta(days=20)
        }
    ]
    if db.skills.count_documents({}) == 0:
        for s in initial_skills:
            db.skills.insert_one(s)

    recs = [
        {
            "recommendation_id": "REC-1001",
            "employee_id": "EMP-1001",
            "employee_name": "Rahul Verma",
            "department": "Engineering",
            "team_id": "TEAM-CORE-ENG",
            "target_skill": "Kubernetes Orchestration",
            "category": "Cloud & DevOps",
            "priority": "High",
            "reason_or_gap": "Identified gap for upcoming Q4 enterprise cloud migration sprint.",
            "action_plan": "Enroll in the Certified Kubernetes Administrator (CKA) practical training track.",
            "status": "Recommended",
            "recommended_by_id": "LEAD-1001",
            "recommended_by_name": "Kavita Nair",
            "recommended_by_role": "team_lead",
            "created_at": datetime.now(timezone.utc) - timedelta(days=4),
            "updated_at": datetime.now(timezone.utc) - timedelta(days=4)
        },
        {
            "recommendation_id": "REC-1002",
            "employee_id": "EMP-1002",
            "employee_name": "Sneha Reddy",
            "department": "Engineering",
            "team_id": "TEAM-CORE-ENG",
            "target_skill": "GraphQL Federation",
            "category": "Web Development",
            "priority": "Medium",
            "reason_or_gap": "Preparation for unified frontend API gateway rollout.",
            "action_plan": "Complete corporate GraphQL hands-on workshop by end of month.",
            "status": "Recommended",
            "recommended_by_id": "TRN-1001",
            "recommended_by_name": "Rajesh Sharma",
            "recommended_by_role": "trainer",
            "created_at": datetime.now(timezone.utc) - timedelta(days=2),
            "updated_at": datetime.now(timezone.utc) - timedelta(days=2)
        }
    ]
    if db.skill_recommendations.count_documents({}) == 0:
        print("Seeding Training Recommendations...")
        for r in recs:
            db.skill_recommendations.insert_one(r)

    if db.leave_requests.count_documents({}) == 0:
        print("Seeding Sample Leave Requests...")
        sample_leaves = [
            {
                "request_id": "LR-1001",
                "request_type": "LEAVE",
                "employee_id": "EMP-1001",
                "employee_name": "Rahul Verma",
                "department": "Engineering",
                "leave_type": "Casual Leave",
                "start_date": (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d"),
                "end_date": (datetime.now(timezone.utc) + timedelta(days=6)).strftime("%Y-%m-%d"),
                "days_count": 2.0,
                "is_half_day": False,
                "reason": "Attending family function out of station.",
                "status": "Pending",
                "reviewed_by_id": None,
                "reviewed_by_name": None,
                "review_remarks": None,
                "reviewed_at": None,
                "created_at": datetime.now(timezone.utc) - timedelta(days=1),
                "updated_at": datetime.now(timezone.utc) - timedelta(days=1)
            },
            {
                "request_id": "LR-1002",
                "request_type": "LEAVE",
                "employee_id": "EMP-1002",
                "employee_name": "Sneha Reddy",
                "department": "Engineering",
                "leave_type": "Sick Leave",
                "start_date": (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d"),
                "end_date": (datetime.now(timezone.utc) - timedelta(days=9)).strftime("%Y-%m-%d"),
                "days_count": 2.0,
                "is_half_day": False,
                "reason": "Viral fever and doctor consultation.",
                "status": "Approved",
                "reviewed_by_id": "HR-1001",
                "reviewed_by_name": "Priya Sharma",
                "review_remarks": "Medical certificate verified. Approved.",
                "reviewed_at": datetime.now(timezone.utc) - timedelta(days=10),
                "created_at": datetime.now(timezone.utc) - timedelta(days=11),
                "updated_at": datetime.now(timezone.utc) - timedelta(days=10)
            }
        ]
        for lr in sample_leaves:
            db.leave_requests.insert_one(lr)

    if db.work_diary.count_documents({}) == 0:
        print("Seeding Sample Work Diary Entries...")
        sample_diaries = [
            {
                "diary_id": "WD-1001",
                "employee_id": "EMP-1001",
                "employee_name": "Rahul Verma",
                "department": "Engineering",
                "diary_date": today_str,
                "category": "Development",
                "activity_title": "API Gateway Authentication & JWT Verification",
                "description": "Refactored JWT signature verification and session timeout middleware.",
                "start_time": "10:15",
                "end_time": "12:30",
                "duration_minutes": 135,
                "project_id": "PRJ-1001",
                "project_name": "Enterprise Cloud Migration & Microservices",
                "task_id": "TSK-1001",
                "task_title": "Containerize core API services and configure health checks",
                "blockers": "None",
                "status": "Completed",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            },
            {
                "diary_id": "WD-1002",
                "employee_id": "EMP-1001",
                "employee_name": "Rahul Verma",
                "department": "Engineering",
                "diary_date": today_str,
                "category": "Code Review",
                "activity_title": "PR Review for Database Persistence Layer",
                "description": "Reviewed disk snapshot proxy and atomic rename locking mechanism.",
                "start_time": "14:00",
                "end_time": "16:00",
                "duration_minutes": 120,
                "project_id": "PRJ-1001",
                "project_name": "Enterprise Cloud Migration & Microservices",
                "task_id": "TSK-1002",
                "task_title": "Implement distributed session caching with Redis/Mongo cluster",
                "blockers": "None",
                "status": "Completed",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
        ]
        for wd in sample_diaries:
            db.work_diary.insert_one(wd)

    print("\n[SUCCESS] Seed data check completed!")


if __name__ == "__main__":
    force_reset = "--reset" in sys.argv or "--force" in sys.argv or "-f" in sys.argv
    seed_database(force_reset=force_reset)
