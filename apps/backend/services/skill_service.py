import logging
import re
import secrets
from datetime import datetime, timezone
from database.connection import get_db
from permissions.rbac import Role
from services.audit_service import AuditService
from services.notification_service import NotificationService
from utils.serializers import serialize_doc

logger = logging.getLogger(__name__)

SKILL_CATEGORIES = [
    "Programming",
    "Web Development",
    "Database",
    "AI/ML",
    "Cloud & DevOps",
    "Tools",
    "Soft Skills"
]

PROFICIENCY_LEVELS = [
    "No Experience",
    "Beginner",
    "Basic",
    "Competent",
    "Advanced",
    "Expert"
]

PROFICIENCY_SCORES = {
    "No Experience": 0,
    "Beginner": 1,
    "Basic": 2,
    "Competent": 3,
    "Intermediate": 3,
    "Advanced": 4,
    "Expert": 5
}


class SkillService:
    """Enterprise Skill Matrix service supporting Employee self-reporting,
    Trainer assessments, Team Lead coverage and skill gap analyses, and HR oversight."""

    CATEGORIES = SKILL_CATEGORIES
    PROFICIENCY_LEVELS = PROFICIENCY_LEVELS
    PROFICIENCY_SCORES = PROFICIENCY_SCORES

    @classmethod
    def get_categories(cls) -> list[str]:
        """Loads company skill categories dynamically from the database."""
        db = get_db()
        docs = list(db.skill_categories.find({}, {"_id": 0, "name": 1}).sort("name", 1))
        if docs:
            return [d["name"] for d in docs if d.get("name")]
        return []

    @classmethod
    def add_category(cls, actor: dict, name: str) -> tuple[dict | None, str | None]:
        """Configures a new company skill category. Requires HR or Admin role."""
        actor_role = actor.get("role")
        if actor_role not in (Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN):
            return None, "Access Denied: Only HR or Admin may configure skill categories."

        clean_name = (name or "").strip()
        if not clean_name:
            return None, "Category name is required."

        db = get_db()
        existing = db.skill_categories.find_one({"name": {"$regex": f"^{re.escape(clean_name)}$", "$options": "i"}})
        if existing:
            return None, f"Category '{clean_name}' already exists in configuration."

        doc = {
            "category_id": f"CAT-{secrets.token_hex(4).upper()}",
            "name": clean_name,
            "created_by": actor.get("employee_id"),
            "created_at": datetime.now(timezone.utc)
        }
        db.skill_categories.insert_one(doc)
        doc.pop("_id", None)

        AuditService.log_action(
            actor=actor,
            action="ADD_SKILL_CATEGORY",
            target_type="skill_category",
            target_id=doc["category_id"],
            details={"category_name": clean_name}
        )
        return doc, None

    @classmethod
    def delete_category(cls, actor: dict, name: str) -> tuple[bool, str | None]:
        """Removes a company skill category. Requires HR or Admin role."""
        actor_role = actor.get("role")
        if actor_role not in (Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN):
            return False, "Access Denied: Only HR or Admin may remove skill categories."

        clean_name = (name or "").strip()
        db = get_db()
        res = db.skill_categories.delete_one({"name": clean_name})
        if res.deleted_count == 0:
            return False, f"Category '{clean_name}' not found."

        AuditService.log_action(
            actor=actor,
            action="DELETE_SKILL_CATEGORY",
            target_type="skill_category",
            target_id=clean_name,
            details={"category_name": clean_name}
        )
        return True, None

    @classmethod
    def get_proficiency_levels(cls) -> list[str]:
        return list(PROFICIENCY_LEVELS)

    @classmethod
    def get_user_skills(cls, employee_id: str) -> list[dict]:
        db = get_db()
        skills = list(db.skills.find({"employee_id": employee_id}, {"_id": 0}).sort("category", 1))
        
        # If no skills in collection, check user profile skills to backfill
        if not skills:
            user = db.users.find_one({"employee_id": employee_id})
            if user and user.get("skills"):
                for s in user["skills"]:
                    s_name = s.get("name") if isinstance(s, dict) else str(s)
                    s_level = s.get("level", "Intermediate") if isinstance(s, dict) else "Intermediate"
                    cat = cls._infer_category(s_name)
                    doc = {
                        "skill_id": f"SKL-{secrets.token_hex(4).upper()}",
                        "employee_id": employee_id,
                        "employee_name": user.get("full_name", ""),
                        "department": user.get("department", "Engineering"),
                        "team_id": user.get("team_id", ""),
                        "skill_name": s_name,
                        "category": cat,
                        "proficiency_level": s_level,
                        "proficiency_score": PROFICIENCY_SCORES.get(s_level, 2),
                        "experience_summary": f"Hands-on proficiency in {s_name} across production workloads.",
                        "years_of_experience": 2.0,
                        "learning_status": "Practicing",
                        "certification_name": "",
                        "verified_status": "Self-Reported",
                        "trainer_rating": None,
                        "trainer_feedback": "",
                        "assessor_name": "",
                        "created_at": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc)
                    }
                    db.skills.insert_one(doc)
                skills = list(db.skills.find({"employee_id": employee_id}, {"_id": 0}).sort("category", 1))
        
        return [serialize_doc(s) for s in skills]

    @classmethod
    def _infer_category(cls, skill_name: str) -> str:
        name_lower = skill_name.lower()
        if any(w in name_lower for w in ["python", "java", "c++", "golang", "rust", "typescript", "c#"]):
            return "Programming"
        if any(w in name_lower for w in ["react", "vue", "angular", "html", "css", "flask", "django", "node", "fastapi"]):
            return "Web Development"
        if any(w in name_lower for w in ["mongo", "sql", "postgres", "redis", "database"]):
            return "Database"
        if any(w in name_lower for w in ["ai", "ml", "neural", "pytorch", "tensorflow", "nlp", "llm", "langchain"]):
            return "AI/ML"
        if any(w in name_lower for w in ["docker", "kubernetes", "aws", "azure", "ci/cd", "devops", "cloud", "git"]):
            return "Cloud & DevOps"
        if any(w in name_lower for w in ["jira", "postman", "figma", "linux", "tools"]):
            return "Tools"
        return "Soft Skills"

    @classmethod
    def add_skill(cls, actor: dict, skill_data: dict) -> tuple[dict | None, str | None]:
        db = get_db()
        emp_id = skill_data.get("employee_id") or actor.get("employee_id")
        skill_name = (skill_data.get("skill_name") or "").strip()
        category = skill_data.get("category", "Programming")
        proficiency = skill_data.get("proficiency_level", "Intermediate")
        summary = (skill_data.get("experience_summary") or "").strip()
        years = float(skill_data.get("years_of_experience") or 1.0)
        learning_status = skill_data.get("learning_status", "Practicing")
        cert_name = (skill_data.get("certification_name") or "").strip()

        # Authorization check
        actor_role = actor.get("role")
        actor_id = actor.get("employee_id")
        if actor_role == Role.EMPLOYEE and actor_id != emp_id:
            return None, "Access Denied: You can only record skills for your own profile."

        target_user = db.users.find_one({"employee_id": emp_id})
        if not target_user:
            return None, "Target employee record not found."

        if not skill_name:
            return None, "Skill name is required."

        if category not in SKILL_CATEGORIES:
            category = "Programming"

        if proficiency not in PROFICIENCY_LEVELS:
            proficiency = "Intermediate"

        # Check if already exists for this employee (case-insensitive)
        existing = db.skills.find_one({
            "employee_id": emp_id,
            "skill_name": {"$regex": f"^{skill_name}$", "$options": "i"}
        })

        if existing:
            # Update existing skill entry
            update_fields = {
                "category": category,
                "proficiency_level": proficiency,
                "proficiency_score": PROFICIENCY_SCORES.get(proficiency, 2),
                "experience_summary": summary,
                "years_of_experience": years,
                "learning_status": learning_status,
                "certification_name": cert_name,
                "updated_at": datetime.now(timezone.utc)
            }
            db.skills.update_one({"_id": existing["_id"]}, {"$set": update_fields})
            existing.update(update_fields)
            cls._sync_user_skills(emp_id)
            return serialize_doc(existing), None

        skill_doc = {
            "skill_id": f"SKL-{secrets.token_hex(4).upper()}",
            "employee_id": emp_id,
            "employee_name": target_user.get("full_name", ""),
            "department": target_user.get("department", "Engineering"),
            "team_id": target_user.get("team_id", ""),
            "skill_name": skill_name,
            "category": category,
            "proficiency_level": proficiency,
            "proficiency_score": PROFICIENCY_SCORES.get(proficiency, 2),
            "experience_summary": summary,
            "years_of_experience": years,
            "learning_status": learning_status,
            "certification_name": cert_name,
            "verified_status": "Self-Reported",
            "trainer_rating": None,
            "trainer_feedback": "",
            "assessor_name": "",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }

        db.skills.insert_one(skill_doc)
        cls._sync_user_skills(emp_id)

        AuditService.log_action(
            actor=actor,
            action="ADD_SKILL",
            target_type="skill",
            target_id=skill_doc["skill_id"],
            details={"skill_name": skill_name, "category": category, "proficiency": proficiency}
        )

        return serialize_doc(skill_doc), None

    @classmethod
    def update_skill(cls, actor: dict, skill_id: str, updates: dict) -> tuple[dict | None, str | None]:
        db = get_db()
        skill = db.skills.find_one({"skill_id": skill_id})
        if not skill:
            return None, "Skill entry not found."

        actor_role = actor.get("role")
        actor_id = actor.get("employee_id")

        if actor_role == Role.EMPLOYEE and actor_id != skill["employee_id"]:
            return None, "Access Denied: You cannot modify another employee's skill."

        allowed_fields = [
            "category", "proficiency_level", "experience_summary",
            "years_of_experience", "learning_status", "certification_name"
        ]
        set_dict = {"updated_at": datetime.now(timezone.utc)}

        for f in allowed_fields:
            if f in updates:
                set_dict[f] = updates[f]

        if "proficiency_level" in set_dict:
            set_dict["proficiency_score"] = PROFICIENCY_SCORES.get(set_dict["proficiency_level"], 2)

        db.skills.update_one({"skill_id": skill_id}, {"$set": set_dict})
        updated = db.skills.find_one({"skill_id": skill_id})
        cls._sync_user_skills(skill["employee_id"])
        return serialize_doc(updated), None

    @classmethod
    def delete_skill(cls, actor: dict, skill_id: str) -> tuple[bool, str | None]:
        db = get_db()
        skill = db.skills.find_one({"skill_id": skill_id})
        if not skill:
            return False, "Skill entry not found."

        actor_role = actor.get("role")
        actor_id = actor.get("employee_id")

        if actor_role == Role.EMPLOYEE and actor_id != skill["employee_id"]:
            return False, "Access Denied: You cannot remove another employee's skill."

        db.skills.delete_one({"skill_id": skill_id})
        cls._sync_user_skills(skill["employee_id"])

        AuditService.log_action(
            actor=actor,
            action="DELETE_SKILL",
            target_type="skill",
            target_id=skill_id,
            details={"skill_name": skill.get("skill_name")}
        )
        return True, None

    @classmethod
    def assess_skill(cls, actor: dict, skill_id: str, assessment_data: dict) -> tuple[dict | None, str | None]:
        """Allows Corporate Trainers, Team Leads, and HR to verify and rate proficiency."""
        db = get_db()
        actor_role = actor.get("role")
        if actor_role not in (Role.TRAINER, Role.TEAM_LEAD, Role.HR, Role.HR_MANAGER):
            return None, "Access Denied: Only Trainers, Team Leads, or HR can evaluate employee skills."

        skill = db.skills.find_one({"skill_id": skill_id})
        if not skill:
            return None, "Skill record not found."

        rating = int(assessment_data.get("trainer_rating") or 4)
        rating = max(1, min(5, rating))
        feedback = (assessment_data.get("trainer_feedback") or "").strip()
        verified_status = assessment_data.get("verified_status") or "Verified"
        adjusted_level = assessment_data.get("proficiency_level")

        assessor_role = actor_role
        if assessor_role in (Role.TEAM_LEAD, "trainer") and (
            actor.get("department") == "Training"
            or actor.get("legacy_role") == "trainer"
            or actor.get("employee_id", "").startswith("TRN-")
            or "trainer" in actor.get("email", "").lower()
        ):
            assessor_role = "trainer"

        set_dict = {
            "trainer_rating": rating,
            "trainer_feedback": feedback,
            "verified_status": verified_status,
            "assessor_id": actor.get("employee_id"),
            "assessor_name": actor.get("full_name"),
            "assessor_role": assessor_role,
            "assessed_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }

        if adjusted_level and adjusted_level in PROFICIENCY_LEVELS:
            set_dict["proficiency_level"] = adjusted_level
            set_dict["proficiency_score"] = PROFICIENCY_SCORES.get(adjusted_level, 2)

        db.skills.update_one({"skill_id": skill_id}, {"$set": set_dict})
        updated = db.skills.find_one({"skill_id": skill_id})
        cls._sync_user_skills(skill["employee_id"])

        # Dispatch notification to employee
        NotificationService.create_notification(
            title=f"Skill Assessed: {skill.get('skill_name')}",
            message=f"{actor.get('full_name')} ({actor_role.replace('_', ' ').title()}) evaluated your skill with rating {rating}/5: '{feedback}'",
            category="SKILL_ASSESSMENT",
            recipient_id=skill["employee_id"],
            link="/skills"
        )

        AuditService.log_action(
            actor=actor,
            action="ASSESS_SKILL",
            target_type="skill",
            target_id=skill_id,
            details={"rating": rating, "verified_status": verified_status, "employee_id": skill["employee_id"]}
        )

        return serialize_doc(updated), None

    @classmethod
    def get_team_skill_matrix(cls, team_id: str) -> dict:
        """
        Calculates team skill coverage and identifies nuanced skill gaps for Team Leads.
        Strict requirements:
        - Counts active employee records only (excludes HR, Managers, or unrelated Team Leads).
        - Distinguishes missing skill records from zero proficiency.
        - Uses neutral indicators for ordinary skill gaps, reserving High/Red severity strictly for genuine critical technical risks.
        - Shows the actual number of employees possessing each skill.
        - Provides actionable training recommendations.
        - Never fabricates skill data.
        """
        db = get_db()
        team_member_ids = set()
        team_doc = db.teams.find_one({"team_id": team_id})
        if team_doc and team_doc.get("members"):
            team_member_ids.update([m for m in team_doc["members"] if m])

        # Query active employees assigned to this team (strictly role == Role.EMPLOYEE)
        query = {
            "$or": [
                {"team_id": team_id},
                {"employee_id": {"$in": list(team_member_ids)}}
            ],
            "role": Role.EMPLOYEE,
            "is_active": True
        }
        members = list(db.users.find(query))
        member_ids = [m["employee_id"] for m in members]

        skills = list(db.skills.find({"employee_id": {"$in": member_ids}})) if member_ids else []

        # Core critical technical categories for engineering/technical teams
        critical_categories = ["Programming", "AI/ML", "Web Development"]

        category_coverage = {}
        for cat in SKILL_CATEGORIES:
            cat_skills = [s for s in skills if s.get("category") == cat]
            
            # Count actual number of employees possessing each skill
            skill_counts = {}
            for s in cat_skills:
                s_name = s.get("skill_name")
                if s_name:
                    skill_counts[s_name] = skill_counts.get(s_name, 0) + 1

            distinct_skills = list(skill_counts.keys())
            employees_in_cat = len(set(s.get("employee_id") for s in cat_skills if s.get("employee_id")))
            
            avg_score = round(sum(s.get("proficiency_score", 2) for s in cat_skills) / len(cat_skills), 1) if cat_skills else 0.0
            
            if len(cat_skills) >= max(1, len(members) * 1.5):
                coverage_status = "Strong"
            elif cat_skills:
                coverage_status = "Moderate"
            else:
                coverage_status = "Missing Info" if len(members) > 0 else "Unassigned"

            category_coverage[cat] = {
                "total_skills": len(cat_skills),
                "distinct_skills": distinct_skills,
                "skill_breakdown": [{"skill_name": k, "employee_count": v} for k, v in sorted(skill_counts.items())],
                "employees_with_skill_count": employees_in_cat,
                "average_score": avg_score,
                "coverage_status": coverage_status
            }

        # Identify Gaps with neutral indicators vs genuine critical situations
        skill_gaps = []
        for cat, data in category_coverage.items():
            is_critical_domain = cat in critical_categories

            if data["coverage_status"] in ("Missing Info", "Unassigned") and len(members) > 0:
                # Distinguish between genuine critical technical stack vs normal peripheral domain
                if is_critical_domain:
                    skill_gaps.append({
                        "category": cat,
                        "severity": "High",  # Genuine critical engineering need
                        "type": "critical",
                        "employees_count": 0,
                        "badge_class": "bg-danger text-white",
                        "card_class": "border-danger-subtle bg-danger-subtle",
                        "reason": f"No team members currently have registered skills in core domain '{cat}'.",
                        "recommendation": f"Urgent technical upskilling or skill onboarding recommended for '{cat}'."
                    })
                else:
                    skill_gaps.append({
                        "category": cat,
                        "severity": "Normal",  # Neutral visual indicator
                        "type": "missing_info",
                        "employees_count": 0,
                        "badge_class": "bg-secondary-subtle text-secondary border",
                        "card_class": "border-secondary-subtle bg-body-tertiary",
                        "reason": f"No competency records logged yet for '{cat}'.",
                        "recommendation": f"Prompt team members to self-report any relevant experience in '{cat}'."
                    })
            elif data["total_skills"] > 0 and data["average_score"] < 2.0:
                skill_gaps.append({
                    "category": cat,
                    "severity": "Moderate",  # Neutral / informational
                    "type": "beginner_level",
                    "employees_count": data["employees_with_skill_count"],
                    "badge_class": "bg-info-subtle text-info border border-info-subtle",
                    "card_class": "border-info-subtle bg-info-subtle",
                    "reason": f"Team proficiency in '{cat}' is currently developing (Avg: {data['average_score']}/4.0 across {data['employees_with_skill_count']} member(s)).",
                    "recommendation": f"Schedule intermediate workshops or pair programming in '{cat}'."
                })

        return {
            "team_id": team_id,
            "total_members": len(members),
            "members": [serialize_doc(m) for m in members],
            "skills": [serialize_doc(s) for s in skills],
            "category_coverage": category_coverage,
            "skill_gaps": skill_gaps,
            "has_pending_assignment": (len(members) == 0)
        }

    @classmethod
    def get_team_skill_diagnostics(cls, lead_user: dict) -> dict:
        """
        Team Lead portal skill diagnostic report:
        Calculates team size strictly from active Role.EMPLOYEE members,
        identifies critical vs normal skill gaps with actionable recommendations,
        and never invents dummy data.
        """
        team_id = lead_user.get("team_id") or ""
        matrix = cls.get_team_skill_matrix(team_id)
        team_size = matrix["total_members"]
        has_pending = matrix["has_pending_assignment"]

        formatted_skills = []
        for gap in matrix.get("skill_gaps", []):
            sev = "critical" if gap.get("severity") == "High" else "normal"
            formatted_skills.append({
                "category": gap.get("category"),
                "severity": sev,
                "badge_class": gap.get("badge_class", ""),
                "actionable_recommendation": gap.get("recommendation", ""),
                "employee_count": gap.get("employees_count", 0),
                "reason": gap.get("reason", "")
            })

        if not formatted_skills and not has_pending:
            formatted_skills.append({
                "category": "All Tracked Domains",
                "severity": "covered",
                "badge_class": "bg-success-subtle text-success",
                "actionable_recommendation": "Maintain team skill proficiency with regular workshops.",
                "employee_count": team_size,
                "reason": "Adequate coverage across key capabilities."
            })

        has_critical = any(s["severity"] == "critical" for s in formatted_skills)
        is_healthy = True if has_pending else (not has_critical)

        return {
            "team_id": team_id,
            "team_size": team_size,
            "total_members": team_size,
            "has_pending_assignment": has_pending,
            "is_healthy": is_healthy,
            "skills": formatted_skills,
            "skill_gaps": matrix.get("skill_gaps", []),
            "category_coverage": matrix.get("category_coverage", {})
        }

    @classmethod
    def get_company_skill_matrix(cls, category: str = None, department: str = None) -> dict:
        """Company-wide overview for HR and executives."""
        db = get_db()
        query = {}
        if category and category != "ALL":
            query["category"] = category
        if department and department != "ALL":
            query["department"] = department

        skills = list(db.skills.find(query).sort("created_at", -1))
        total_skills = len(skills)
        verified_count = sum(1 for s in skills if s.get("verified_status") == "Verified")

        cat_distribution = {}
        for cat in SKILL_CATEGORIES:
            cat_distribution[cat] = sum(1 for s in skills if s.get("category") == cat)

        return {
            "total_skills": total_skills,
            "verified_count": verified_count,
            "verified_percentage": round((verified_count / total_skills * 100), 1) if total_skills > 0 else 0,
            "category_distribution": cat_distribution,
            "skills": [serialize_doc(s) for s in skills]
        }

    @classmethod
    def recommend_training(cls, actor: dict, rec_data: dict) -> tuple[dict | None, str | None]:
        db = get_db()
        actor_role = actor.get("role")
        if actor_role not in (Role.TRAINER, Role.TEAM_LEAD, Role.HR, Role.HR_MANAGER):
            return None, "Access Denied: Only Trainers, Team Leads, and HR can issue training recommendations."

        emp_id = rec_data.get("employee_id")
        target_skill = (rec_data.get("target_skill") or "").strip()
        reason = (rec_data.get("reason_or_gap") or "").strip()
        action_plan = (rec_data.get("action_plan") or "").strip()
        priority = rec_data.get("priority", "Medium")

        target_user = db.users.find_one({"employee_id": emp_id})
        if not target_user:
            return None, "Target employee not found."

        if not target_skill:
            return None, "Target skill is required."

        rec_doc = {
            "recommendation_id": f"REC-{secrets.token_hex(4).upper()}",
            "employee_id": emp_id,
            "employee_name": target_user.get("full_name", ""),
            "department": target_user.get("department", "Engineering"),
            "team_id": target_user.get("team_id", ""),
            "target_skill": target_skill,
            "category": rec_data.get("category", "Programming"),
            "priority": priority,
            "reason_or_gap": reason,
            "action_plan": action_plan,
            "status": "Recommended",
            "recommended_by_id": actor.get("employee_id"),
            "recommended_by_name": actor.get("full_name"),
            "recommended_by_role": actor_role,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }

        db.skill_recommendations.insert_one(rec_doc)

        NotificationService.create_notification(
            title=f"Training Recommended: {target_skill}",
            message=f"{actor.get('full_name')} recommended training in '{target_skill}' ({priority} Priority): {action_plan}",
            category="TRAINING_RECOMMENDATION",
            recipient_id=emp_id,
            link="/skills"
        )

        AuditService.log_action(
            actor=actor,
            action="RECOMMEND_TRAINING",
            target_type="recommendation",
            target_id=rec_doc["recommendation_id"],
            details={"target_skill": target_skill, "employee_id": emp_id, "priority": priority}
        )

        return serialize_doc(rec_doc), None

    @classmethod
    def get_recommendations(cls, employee_id: str = None, team_id: str = None) -> list[dict]:
        db = get_db()
        query = {}
        if employee_id:
            query["employee_id"] = employee_id
        elif team_id:
            query["team_id"] = team_id

        recs = list(db.skill_recommendations.find(query).sort("created_at", -1))
        return [serialize_doc(r) for r in recs]

    @classmethod
    def _sync_user_skills(cls, employee_id: str):
        """Keeps db.users[skills] synchronized with db.skills collection."""
        db = get_db()
        all_skills = list(db.skills.find({"employee_id": employee_id}))
        formatted = [{"name": s["skill_name"], "level": s["proficiency_level"]} for s in all_skills]
        db.users.update_one({"employee_id": employee_id}, {"$set": {"skills": formatted}})
