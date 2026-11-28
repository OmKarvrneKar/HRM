import os
import re
import logging
from datetime import datetime, timezone, timedelta
import pandas as pd
from werkzeug.security import generate_password_hash
from auth.security import hash_password, verify_password
from database.connection import DatabaseManager

logger = logging.getLogger("hrm_seeds")

# Pre-computed hash for password123 to ensure fast seeding without repetitive CPU work
DEFAULT_PASSWORD_HASH = generate_password_hash("password123")


# ============================================================================
# 100-PERSON ENTERPRISE ROSTER SPECIFICATION
# Distributed across Engineering, Product, Design, Operations, and HR
# ============================================================================

ENTERPRISE_USERS = [
    # ------------------------------------------------------------------------
    # 1. Authentic Corporate Leadership & Administration
    # ------------------------------------------------------------------------
    {
        "emp_id": "ADMIN-1001", "name": "System Administrator", "role": "admin",
        "email": "admin@aisamrat.com", "contact": "9876543214", "dob": "1985-09-10",
        "department": "IT & Infrastructure", "designation": "System Administrator",
        "team_id": "TEAM-EXEC", "assigned_tl_id": None, "manager_id": None, "joining_date": "2020-01-01"
    },
    {
        "emp_id": "HR-1001", "name": "Ramya", "role": "hr",
        "email": "ramya.hr@aisamrat.com", "contact": "9876543213", "dob": "1992-03-25",
        "department": "Human Resources", "designation": "HR Operations & People Lead",
        "team_id": "TEAM-HR-01", "assigned_tl_id": "HR-1001", "manager_id": "ADMIN-1001", "joining_date": "2021-01-01"
    },
    {
        "emp_id": "MGR-1001", "name": "Vikramaditya Roy", "role": "manager",
        "email": "manager@aisamrat.com", "contact": "9876543212", "dob": "1988-11-12",
        "department": "Engineering", "designation": "Engineering Director",
        "team_id": "TEAM-ENG-01", "assigned_tl_id": None, "manager_id": "ADMIN-1001", "joining_date": "2022-01-01"
    },
    {
        "emp_id": "TL-1001", "name": "Kavita Nair", "role": "tl",
        "email": "lead.kavita@aisamrat.com", "contact": "9876543211", "dob": "1994-08-20",
        "department": "Engineering", "designation": "Technical Team Lead",
        "team_id": "TEAM-ENG-01", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001", "joining_date": "2023-06-01"
    },

    # ------------------------------------------------------------------------
    # 2. All 34 Authentic Intern Records from Intern-Full-Details.xlsx
    # ------------------------------------------------------------------------
    {"emp_id": "AS-1001", "name": "Sneha K", "role": "employee", "email": "snehak2003k@gmail.com", "contact": "7899325378", "dob": "13-08-2003", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-01", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1002", "name": "Lakshmish K S", "role": "employee", "email": "lakshmish738@gmail.com", "contact": "9035426145", "dob": "07-10-2004", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-01", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1003", "name": "Bindu C Gowda", "role": "employee", "email": "binducgowda1947@gmail.com", "contact": "8147324190", "dob": "07-02-2004", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-01", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1004", "name": "Spandana Indira R", "role": "employee", "email": "spandanaindira19@gmail.com", "contact": "6361275189", "dob": "19-09-2002", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-01", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1005", "name": "Sanni kumar", "role": "employee", "email": "sannikumar1732003@gmail.com", "contact": "7542978310", "dob": "17-03-2003", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-01", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1006", "name": "Punith Pasupuleti", "role": "employee", "email": "punith.ncpc@gmail.com", "contact": "8296962311", "dob": "06-06-2006", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-01", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1007", "name": "Sai Sreekar", "role": "employee", "email": "saisreekar697@gmail.com", "contact": "9110321456", "dob": "27-10-2003", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-01", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1008", "name": "Shruthi Bhaskar", "role": "employee", "email": "shruthibhaskar2003@gmail.com", "contact": "9448606123", "dob": "11-03-2003", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-01", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1009", "name": "Salil Vijaykumar Madivala", "role": "employee", "email": "salilvmadivala24w@gmail.com", "contact": "8356897412", "dob": "24-11-2005", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-01", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1010", "name": "Raminaidu", "role": "employee", "email": "yarabatiraminaidu268@gmail.com", "contact": "8499937451", "dob": "14-06-2002", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-01", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1011", "name": "Darshan Naik", "role": "employee", "email": "darshannaik1305@gmail.com", "contact": "9742960124", "dob": "13-12-2005", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-01", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1012", "name": "Lekhana S N", "role": "employee", "email": "lekhanasn18@gmail.com", "contact": "8867032415", "dob": "05-08-2005", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-01", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1013", "name": "Sachin.V.Sagarnal", "role": "employee", "email": "sachinsagarnal2005@gmail.com", "contact": "9916924312", "dob": "09-02-2005", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-02", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1014", "name": "Swati Laxman Sunagar", "role": "employee", "email": "sunagarswati369@gmail.com", "contact": "6361357410", "dob": "01-06-2003", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-02", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1015", "name": "gurukiran", "role": "employee", "email": "giranguru322@gmail.com", "contact": "7338189421", "dob": "04-07-2002", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-02", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1016", "name": "Kethan Rao G", "role": "employee", "email": "kethanrao56@gmail.com", "contact": "7658940039", "dob": "07-10-2002", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-02", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1017", "name": "Y charan", "role": "employee", "email": "ycharan.mvjce@gmail.com", "contact": "9902220644", "dob": "04-09-2005", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-02", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1018", "name": "Sai Mahanth LN", "role": "employee", "email": "saimahanth07@gmail.com", "contact": "8971552949", "dob": "07-01-2005", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-02", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1019", "name": "Deepak S J", "role": "employee", "email": "deepaksj.in@gmail.com", "contact": "9380653985", "dob": "29-05-2002", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-02", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1020", "name": "Varshini R", "role": "employee", "email": "varshini772003@gmail.com", "contact": "8073313627", "dob": "15-08-2003", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-02", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1021", "name": "Nambu Aakas Narayan", "role": "employee", "email": "aakashnambunarayan@gmail.com", "contact": "9493481536", "dob": "06-05-2004", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-02", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1022", "name": "Nonisa chilur", "role": "employee", "email": "nonisarc@gmail.com", "contact": "8050016302", "dob": "08-06-1995", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-02", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1023", "name": "Aviraj Bhawrha", "role": "employee", "email": "avirajbhawrha@gmail.com", "contact": "9796838881", "dob": "29-08-2005", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-02", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1024", "name": "k.sanjana reddy", "role": "employee", "email": "sanjanakondireddy@gmail.com", "contact": "9000290109", "dob": "21-02-2004", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-02", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1025", "name": "Rahul S", "role": "employee", "email": "rahulr54071@gmail.com", "contact": "8310758489", "dob": "12-07-2004", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-03", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1026", "name": "Omkar  Vernekar", "role": "employee", "email": "omkarvernekar07@gmail.com", "contact": "8217071048", "dob": "02-12-2005", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-03", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1027", "name": "Dhanvish S J", "role": "employee", "email": "sjdhanvish@gmail.com", "contact": "8618340856", "dob": "23-08-2005", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-03", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1028", "name": "Fathima Zara A", "role": "employee", "email": "fathimazaraaa07@gmail.com", "contact": "8861053495", "dob": "25-02-2005", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-03", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1029", "name": "Kushi Kumari A", "role": "employee", "email": "kumarikushi055@gmail.com", "contact": "9353153667", "dob": "24-07-2004", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-03", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1030", "name": "Mangala Neelima", "role": "employee", "email": "neelimamangala18@gmail.com", "contact": "9550646715", "dob": "18-03-2003", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-03", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1031", "name": "Ganesh Vallabh M", "role": "employee", "email": "ganeshvallabhm7@gmail.com", "contact": "7676312256", "dob": "30-05-2005", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-03", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1032", "name": "Arjun Sharma", "role": "employee", "email": "arjunsentmail@gmail.com", "contact": "9119289604", "dob": "16-08-2004", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-03", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1033", "name": "Nikil H E", "role": "employee", "email": "nikilhe318@gmail.com", "contact": "9902846130", "dob": "11-04-2005", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-03", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"},
    {"emp_id": "AS-1034", "name": "Lakshmi E", "role": "employee", "email": "lakshmielakshmie38@gmail.com", "contact": "9945540276", "dob": "22-01-2006", "department": "Engineering", "designation": "Engineering Intern", "team_id": "TEAM-ENG-03", "assigned_tl_id": "TL-1001", "manager_id": "MGR-1001"}
]

ENTERPRISE_100_USERS = ENTERPRISE_USERS


# ============================================================================
# PREDEFINED SQUADS, ROOMS, POLICIES & ASSETS FOR ENTERPRISE
# ============================================================================

PREDEFINED_TEAMS = [
    {"team_id": "TEAM-ENG-01", "name": "Frontend & Web Experience Squad", "lead_employee_id": "TL-1001", "lead_id": "TL-1001", "department": "Engineering", "members": ["TL-1001"] + [f"AS-{1000+i}" for i in range(1, 13)]},
    {"team_id": "TEAM-ENG-02", "name": "Backend & Cloud Core Squad", "lead_employee_id": "TL-1001", "lead_id": "TL-1001", "department": "Engineering", "members": [f"AS-{1000+i}" for i in range(13, 25)]},
    {"team_id": "TEAM-ENG-03", "name": "AI, ML & Data Systems Squad", "lead_employee_id": "TL-1001", "lead_id": "TL-1001", "department": "Engineering", "members": [f"AS-{1000+i}" for i in range(25, 35)]},
    {"team_id": "TEAM-HR-01", "name": "Human Resources & People Operations", "lead_employee_id": "HR-1001", "lead_id": "HR-1001", "department": "Human Resources", "members": ["HR-1001"]},
    {"team_id": "TEAM-EXEC", "name": "Executive Leadership & Operations", "lead_employee_id": "ADMIN-1001", "lead_id": "ADMIN-1001", "department": "Operations", "members": ["ADMIN-1001", "MGR-1001"]}
]


def seed_real_and_dummy_users(db=None) -> int:
    """
    Seeds workforce accounts and squad teams into the target database without injecting fabricated facility/desk data.
    """
    if db is None:
        db = DatabaseManager.get_db()

    now = datetime.now(timezone.utc)
    enriched_users = []

    for u in ENTERPRISE_100_USERS:
        emp_id = u["emp_id"]
        role = u["role"]
        dept = u.get("department") or ("Engineering" if role in ["employee", "tl", "team_lead"] else ("Operations" if role == "manager" else ("Human Resources" if role == "hr" else "IT & Infrastructure")))
        desig = u.get("designation") or ("Engineering Intern" if emp_id.startswith("AS-") else ("Software Engineer" if role == "employee" else ("Technical Team Lead" if role in ["tl", "team_lead"] else ("Operations Manager" if role == "manager" else ("HR Administrator" if role == "hr" else "System Administrator")))))
        team = u.get("team_id") or ("TEAM-ENG-01" if role in ["employee", "tl", "team_lead"] else "TEAM-EXEC")
        tl_id = u.get("assigned_tl_id") or ("TL-1001" if role == "employee" else None)
        mgr_id = u.get("manager_id") or ("MGR-1001" if role in ["employee", "tl", "team_lead"] else ("ADMIN-1001" if role in ["manager", "hr"] else None))
        if role == "employee":
            tl_id = "TL-1001"
            mgr_id = "MGR-1001"

        doc = {
            "emp_id": emp_id,
            "employee_id": emp_id,
            "name": u["name"],
            "full_name": u["name"],
            "role": role,
            "email": u["email"],
            "personal_email": u["email"],
            "password_hash": u.get("password_hash") or DEFAULT_PASSWORD_HASH,
            "contact": u.get("contact", "9876543210"),
            "phone_number": u.get("contact", "9876543210"),
            "dob": u.get("dob", "1998-01-01"),
            "date_of_birth": u.get("dob", "1998-01-01"),
            "is_active": True,
            "is_email_verified": True,
            "account_status": "active",
            "status": "active",
            "department": dept,
            "designation": desig,
            "team_id": team,
            "assigned_tl_id": tl_id,
            "reporting_manager_id": mgr_id if role in ["employee", "tl", "team_lead"] else (tl_id or mgr_id),
            "manager_id": mgr_id,
            "joining_date": u.get("joining_date") or ("2024-06-01" if emp_id.startswith("AS-") else "2024-01-01"),
            "created_at": now,
            "updated_at": now
        }
        enriched_users.append(doc)

    inserted_users = 0
    for doc in enriched_users:
        existing_user = db.users.find_one(
            {"$or": [{"emp_id": doc["emp_id"]}, {"employee_id": doc["emp_id"]}, {"email": doc["email"]}]},
            {"_id": 1},
        )
        if not existing_user:
            db.users.update_one(
                {"$or": [{"emp_id": doc["emp_id"]}, {"employee_id": doc["emp_id"]}, {"email": doc["email"]}]},
                {"$setOnInsert": doc},
                upsert=True,
            )
            inserted_users += 1

    # Backfill missing reporting hierarchy fields only where unset; never overwrite existing assignments
    missing_emp_hierarchy_query = {
        "role": "employee",
        "$or": [
            {"assigned_tl_id": {"$in": [None, ""]}},
            {"assigned_tl_id": {"$exists": False}},
            {"manager_id": {"$in": [None, ""]}},
            {"manager_id": {"$exists": False}},
            {"reporting_manager_id": {"$in": [None, ""]}},
            {"reporting_manager_id": {"$exists": False}},
        ],
    }
    if db.users.find_one(missing_emp_hierarchy_query, {"_id": 1}):
        db.users.update_many(
            {"role": "employee", "$or": [{"assigned_tl_id": {"$in": [None, ""]}}, {"assigned_tl_id": {"$exists": False}}]},
            {"$set": {"assigned_tl_id": "TL-1001"}},
        )
        db.users.update_many(
            {"role": "employee", "$or": [{"manager_id": {"$in": [None, ""]}}, {"manager_id": {"$exists": False}}]},
            {"$set": {"manager_id": "MGR-1001"}},
        )
        db.users.update_many(
            {"role": "employee", "$or": [{"reporting_manager_id": {"$in": [None, ""]}}, {"reporting_manager_id": {"$exists": False}}]},
            {"$set": {"reporting_manager_id": "MGR-1001"}},
        )

    missing_tl_mgr_query = {
        "$and": [
            {"$or": [{"emp_id": "TL-1001"}, {"employee_id": "TL-1001"}]},
            {"$or": [{"reporting_manager_id": {"$in": [None, ""]}}, {"reporting_manager_id": {"$exists": False}}]},
        ]
    }
    if db.users.find_one(missing_tl_mgr_query, {"_id": 1}):
        db.users.update_one(
            {"$or": [{"emp_id": "TL-1001"}, {"employee_id": "TL-1001"}]},
            {"$set": {"reporting_manager_id": "MGR-1001"}},
        )

    employee_ids = [
        user.get("employee_id") or user.get("emp_id")
        for user in db.users.find({"role": "employee"}, {"employee_id": 1, "emp_id": 1})
        if user.get("employee_id") or user.get("emp_id")
    ]
    if employee_ids:
        employee_scope = {"employee_id": {"$in": employee_ids}}
        if db.leave_requests.find_one({
            **employee_scope,
            "status": {"$in": ["PENDING_TEAM_LEAD", "PENDING_MANAGER", "Pending"]},
            "$or": [
                {"assigned_tl_id": {"$in": [None, ""]}}, {"assigned_tl_id": {"$exists": False}},
                {"assigned_manager_id": {"$in": [None, ""]}}, {"assigned_manager_id": {"$exists": False}},
            ],
        }, {"_id": 1}):
            db.leave_requests.update_many(
                {**employee_scope, "status": {"$in": ["PENDING_TEAM_LEAD", "PENDING_MANAGER", "Pending"]}, "$or": [{"assigned_tl_id": {"$in": [None, ""]}}, {"assigned_tl_id": {"$exists": False}}]},
                {"$set": {"assigned_tl_id": "TL-1001"}},
            )
            db.leave_requests.update_many(
                {**employee_scope, "status": {"$in": ["PENDING_TEAM_LEAD", "PENDING_MANAGER", "Pending"]}, "$or": [{"assigned_manager_id": {"$in": [None, ""]}}, {"assigned_manager_id": {"$exists": False}}]},
                {"$set": {"assigned_manager_id": "MGR-1001"}},
            )

        if db.attendance_corrections.find_one({
            **employee_scope,
            "status": {"$in": ["PENDING_TEAM_LEAD", "PENDING_TEAM_LEAD_REVIEW", "PENDING_MANAGER"]},
            "$or": [
                {"assigned_tl_id": {"$in": [None, ""]}}, {"assigned_tl_id": {"$exists": False}},
                {"assigned_manager_id": {"$in": [None, ""]}}, {"assigned_manager_id": {"$exists": False}},
            ],
        }, {"_id": 1}):
            db.attendance_corrections.update_many(
                {**employee_scope, "status": {"$in": ["PENDING_TEAM_LEAD", "PENDING_TEAM_LEAD_REVIEW", "PENDING_MANAGER"]}, "$or": [{"assigned_tl_id": {"$in": [None, ""]}}, {"assigned_tl_id": {"$exists": False}}]},
                {"$set": {"assigned_tl_id": "TL-1001"}},
            )
            db.attendance_corrections.update_many(
                {**employee_scope, "status": {"$in": ["PENDING_TEAM_LEAD", "PENDING_TEAM_LEAD_REVIEW", "PENDING_MANAGER"]}, "$or": [{"assigned_manager_id": {"$in": [None, ""]}}, {"assigned_manager_id": {"$exists": False}}]},
                {"$set": {"assigned_manager_id": "MGR-1001"}},
            )

        if db.travel_requests.find_one({
            **employee_scope,
            "status": {"$in": ["PENDING_MANAGER", "Pending Endorsement", "PENDING ENDORSEMENT"]},
            "$or": [{"assigned_manager_id": {"$in": [None, ""]}}, {"assigned_manager_id": {"$exists": False}}],
        }, {"_id": 1}):
            db.travel_requests.update_many(
                {**employee_scope, "status": {"$in": ["PENDING_MANAGER", "Pending Endorsement", "PENDING ENDORSEMENT"]}, "$or": [{"assigned_manager_id": {"$in": [None, ""]}}, {"assigned_manager_id": {"$exists": False}}]},
                {"$set": {"assigned_manager_id": "MGR-1001"}},
            )

        if db.expense_claims.find_one({
            **employee_scope,
            "status": "Submitted",
            "$or": [{"assigned_manager_id": {"$in": [None, ""]}}, {"assigned_manager_id": {"$exists": False}}],
        }, {"_id": 1}):
            db.expense_claims.update_many(
                {**employee_scope, "status": "Submitted", "$or": [{"assigned_manager_id": {"$in": [None, ""]}}, {"assigned_manager_id": {"$exists": False}}]},
                {"$set": {"assigned_manager_id": "MGR-1001"}},
            )

        if db.asset_requests.find_one({
            **employee_scope,
            "status": "Pending Review",
            "$or": [
                {"assigned_manager_id": {"$in": [None, ""]}}, {"assigned_manager_id": {"$exists": False}},
                {"assigned_approver": {"$in": [None, ""]}}, {"assigned_approver": {"$exists": False}},
            ],
        }, {"_id": 1}):
            db.asset_requests.update_many(
                {**employee_scope, "status": "Pending Review", "$or": [{"assigned_manager_id": {"$in": [None, ""]}}, {"assigned_manager_id": {"$exists": False}}, {"assigned_approver": {"$in": [None, ""]}}, {"assigned_approver": {"$exists": False}}]},
                {"$set": {"assigned_manager_id": "MGR-1001", "assigned_approver": "MGR-1001"}},
            )

    # Seed Teams idempotently without modifying existing team docs
    inserted_teams = 0
    try:
        for team in PREDEFINED_TEAMS:
            if not db.teams.find_one({"team_id": team["team_id"]}, {"_id": 1}):
                db.teams.update_one(
                    {"team_id": team["team_id"]},
                    {"$setOnInsert": dict(team)},
                    upsert=True,
                )
                inserted_teams += 1
    except Exception as e:
        logger.warning(f"Failed to seed teams: {e}")

    # Seed baseline squad projects ONLY when genuinely missing; never overwrite or mutate timestamps of existing projects
    inserted_projects = 0
    try:
        baseline_projects = [
            {
                "project_id": "PRJ-ENG-01",
                "title": "NextGen AI Web & Experience Suite",
                "name": "NextGen AI Web & Experience Suite",
                "description": "Architecting the real-time AI assistant interface, modern component design system, and fluid employee experience.",
                "category": "Engineering",
                "priority": "High",
                "status": "Active",
                "team_id": "TEAM-ENG-01",
                "created_by": "TL-1001",
                "lead_id": "TL-1001",
                "lead_employee_id": "TL-1001",
                "manager_employee_id": "MGR-1001",
                "members": ["TL-1001", "AS-1001", "AS-1002", "AS-1003", "AS-1004"],
                "progress_percentage": 68,
                "is_approved": True,
                "created_at": now - timedelta(days=20),
                "updated_at": now
            },
            {
                "project_id": "PRJ-ENG-02",
                "title": "Distributed Cloud Core & Gateway",
                "name": "Distributed Cloud Core & Gateway",
                "description": "High-throughput API gateway, JWT session revocation cache, and enterprise database resilience.",
                "category": "Backend Infrastructure",
                "priority": "Critical",
                "status": "Active",
                "team_id": "TEAM-ENG-01",
                "created_by": "TL-1001",
                "lead_id": "TL-1001",
                "lead_employee_id": "TL-1001",
                "manager_employee_id": "MGR-1001",
                "members": ["TL-1001", "AS-1005", "AS-1006", "AS-1007"],
                "progress_percentage": 54,
                "is_approved": True,
                "created_at": now - timedelta(days=15),
                "updated_at": now
            }
        ]
        for p in baseline_projects:
            if not db.projects.find_one({"project_id": p["project_id"]}, {"_id": 1}):
                db.projects.update_one(
                    {"project_id": p["project_id"]},
                    {"$setOnInsert": p},
                    upsert=True,
                )
                inserted_projects += 1
    except Exception as e:
        logger.warning(f"Failed to seed baseline projects: {e}")

    # Baseline leaves: Empty state - no fake or sample leave requests
    try:
        legacy_fake_ids = ["LR-ENG-101", "LR-ENG-102", "LR-2026-BASELINE-01", "LR-2026-BASELINE-02"]
        if db.leave_requests.find_one({"request_id": {"$in": legacy_fake_ids}}, {"_id": 1}):
            db.leave_requests.delete_many({"request_id": {"$in": legacy_fake_ids}})
    except Exception as e:
        logger.warning(f"Failed to clean baseline leaves: {e}")

    # Facility meeting rooms and seating/locker allocations remain empty until verified by Administration.

    # Persist if custom disk persist hook exists
    persist_fn = getattr(db, "persist_to_disk", None)
    if callable(persist_fn) and not hasattr(persist_fn, "database") and (inserted_users or inserted_teams or inserted_projects):
        try:
            persist_fn()
        except Exception as e:
            logger.warning(f"Failed to persist mongomock db to disk: {e}")

    logger.info(
        "Database initialization verified (users_inserted=%d, teams_inserted=%d, projects_inserted=%d).",
        inserted_users,
        inserted_teams,
        inserted_projects,
    )
    return len(enriched_users)


# ---------------------------------------------------------------------------
# Default Test Accounts Definition & Idempotent Seeder for Unit Tests / Render
# ---------------------------------------------------------------------------

DEFAULT_USERS_TO_SEED = [
    user for user in ENTERPRISE_100_USERS
    if user["emp_id"] in {"AS-1001", "TL-1001", "MGR-1001", "HR-1001", "ADMIN-1001"}
]


def seed_default_users(db=None) -> int:
    """Seed the baseline employee/team lead/manager/hr accounts used for login tests."""
    if db is None:
        db = DatabaseManager.get_db()

    default_emps = {user["emp_id"] for user in DEFAULT_USERS_TO_SEED}
    existing = set()
    for user in DEFAULT_USERS_TO_SEED:
        existing_user = db.users.find_one({"$or": [{"emp_id": user["emp_id"]}, {"employee_id": user["emp_id"]}, {"email": user["email"]}]})
        if existing_user and existing_user.get("is_active") is True and existing_user.get("is_email_verified") is True:
            existing.add(user["emp_id"])

    if len(existing) == len(DEFAULT_USERS_TO_SEED):
        return 0

    seeded = 0
    for user in DEFAULT_USERS_TO_SEED:
        fill = {**user}
        fill["employee_id"] = fill.get("employee_id") or fill["emp_id"]
        fill["full_name"] = fill.get("full_name") or fill.get("name")
        fill["password_hash"] = fill.get("password_hash") or DEFAULT_PASSWORD_HASH
        fill["is_active"] = True
        fill["is_email_verified"] = True
        fill["account_status"] = "active"
        fill["status"] = "active"
        fill["created_at"] = datetime.now(timezone.utc)
        fill["updated_at"] = datetime.now(timezone.utc)

        existing_user = db.users.find_one({"$or": [{"emp_id": fill["emp_id"]}, {"employee_id": fill["emp_id"]}, {"email": fill["email"]}]})
        if existing_user and existing_user.get("password_hash") and verify_password("password123", existing_user["password_hash"]):
            continue

        db.users.replace_one(
            {"$or": [{"emp_id": fill["emp_id"]}, {"employee_id": fill["emp_id"]}, {"email": fill["email"]}]},
            fill,
            upsert=True,
        )
        seeded += 1

    return seeded


# Backward-compatible alias for initialize_users
initialize_users = seed_real_and_dummy_users
