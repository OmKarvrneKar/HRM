import secrets
import logging
from datetime import datetime, timezone
from bson import ObjectId
from database.connection import get_db
from services.audit_service import AuditService
from permissions.rbac import Role

logger = logging.getLogger(__name__)


class ProjectService:
    @classmethod
    def create_project(cls, creator: dict, project_data: dict) -> tuple[dict | None, str | None]:
        """
        Creates a new project or project proposal.
        Team Leads create proposals with status 'PENDING_APPROVAL' (or 'DRAFT').
        Selected members are not activated and group chats are NOT created until Manager approval.
        Managers and Admins can create immediately active/approved projects.
        """
        db = get_db()
        project_id = project_data.get("project_id", "").strip().upper()
        if not project_id:
            count = db.projects.count_documents({})
            project_id = f"PRJ-{1001 + count}"

        if db.projects.find_one({"project_id": project_id}):
            return None, f"Project ID {project_id} already exists."

        title = (project_data.get("title") or project_data.get("name") or "").strip()
        if not title:
            return None, "Project title is required."

        # Parse and sanitize proposed members
        raw_members = project_data.get("selected_members") or project_data.get("members") or []
        if isinstance(raw_members, str):
            raw_members = [m.strip() for m in raw_members.split(",") if m.strip()]
        elif not isinstance(raw_members, list):
            raw_members = []

        selected_members = list(dict.fromkeys([str(m).strip().upper() for m in raw_members if str(m).strip()]))

        manager_id = project_data.get("manager_employee_id") or project_data.get("assigned_manager")
        if not manager_id:
            # Find default active operational manager
            mgr_user = db.users.find_one({"role": Role.MANAGER, "is_active": True})
            if mgr_user:
                manager_id = mgr_user.get("employee_id")

        if manager_id:
            manager_id = manager_id.strip().upper()

        due_date = project_data.get("due_date") or project_data.get("expected_completion_date")
        creator_role = creator.get("role")
        now = datetime.now(timezone.utc)

        if creator_role in (Role.HR, Role.HR_MANAGER):
            return None, "Unauthorized: HR personnel are restricted from project operations and project creation."
        if creator_role == Role.EMPLOYEE:
            return None, "Unauthorized: Regular employees cannot create project proposals."

        # Team Leads strictly create proposals requiring Manager approval
        is_tl = (creator_role == Role.TEAM_LEAD) or (creator.get("legacy_role") == "team_lead")
        requested_status = (project_data.get("status") or "").upper()
        is_draft = project_data.get("is_draft", False) or (requested_status == "DRAFT")

        if is_tl:
            if is_draft:
                status = "DRAFT"
            else:
                status = "PENDING_APPROVAL"
            is_approved = False
            active_members = []
        else:
            # Manager / Admin creation
            if requested_status in ("PENDING_APPROVAL", "DRAFT"):
                status = requested_status
                is_approved = False
                active_members = []
            else:
                status = "ACTIVE"
                is_approved = True
                active_members = selected_members

        # Parse proposed responsibilities and required skills
        responsibilities = project_data.get("responsibilities", {})
        if isinstance(responsibilities, str):
            responsibilities = {"general": responsibilities.strip()}
        elif not isinstance(responsibilities, dict):
            responsibilities = {}

        required_skills = project_data.get("required_skills", [])
        if isinstance(required_skills, str):
            required_skills = [s.strip() for s in required_skills.split(",") if s.strip()]
        elif not isinstance(required_skills, list):
            required_skills = []

        approval_history = [{
            "action": "SUBMITTED" if status == "PENDING_APPROVAL" else ("DRAFT" if status == "DRAFT" else "APPROVED"),
            "actor_id": creator.get("employee_id"),
            "actor_name": creator.get("full_name"),
            "actor_role": creator_role,
            "timestamp": now,
            "comments": "Project proposal submitted for Manager approval." if status == "PENDING_APPROVAL" else (
                "Proposal saved as draft." if status == "DRAFT" else "Project created by Management."
            )
        }]

        status_history = [{
            "status": status,
            "changed_by": creator.get("employee_id"),
            "changed_by_name": creator.get("full_name"),
            "timestamp": now,
            "notes": f"Initial state: {status}"
        }]

        new_project = {
            "project_id": project_id,
            "name": title,
            "title": title,
            "description": project_data.get("description", "").strip(),
            "objectives": project_data.get("objectives", project_data.get("description", "")).strip(),
            "deliverables": project_data.get("deliverables", project_data.get("objectives", "")).strip(),
            "department": project_data.get("department", "General"),
            "category": project_data.get("category", project_data.get("department", "General")),
            "client": project_data.get("client", "Internal"),
            "start_date": project_data.get("start_date"),
            "due_date": due_date,
            "expected_completion_date": due_date,
            "priority": project_data.get("priority", "Medium"),
            "status": status,
            "is_approved": is_approved,
            "team_id": project_data.get("team_id") or (creator.get("team_id") if creator else None),
            "manager_employee_id": manager_id,
            "assigned_manager": manager_id,
            "project_lead": project_data.get("project_lead") or creator.get("employee_id"),
            "lead_id": project_data.get("lead_id") or creator.get("employee_id"),
            "assigned_trainer_id": project_data.get("assigned_trainer_id"),
            "selected_members": selected_members,
            "proposed_members": selected_members,
            "members": active_members,
            "assigned_members": active_members,
            "responsibilities": responsibilities,
            "required_skills": required_skills,
            "notes": project_data.get("notes", "").strip(),
            "progress_percentage": 0,
            "created_by": creator.get("employee_id"),
            "created_at": now,
            "updated_at": now,
            "approval_history": approval_history,
            "status_history": status_history,
            "membership_change_requests": []
        }

        if is_approved:
            new_project["approved_by"] = creator.get("employee_id")
            new_project["approved_at"] = now

        db.projects.insert_one(new_project)

        # Chat creation & Notifications logic:
        if is_approved:
            new_project["conversation_id"] = f"PRJ-CHAT-{project_id}"
            try:
                from services.chat_service import ChatService
                ChatService.ensure_project_chat(new_project, creator)
            except Exception as e:
                logger.error(f"Error creating project chat: {e}")

            # Notify active members
            try:
                from services.notification_service import NotificationService
                for emp_id in active_members:
                    if emp_id != creator.get("employee_id"):
                        NotificationService.create_notification(
                            title=f"Assigned to Project: {title}",
                            message=f"You have been assigned to project '{title}' ({project_id}).",
                            recipient_id=emp_id,
                            category="PROJECT",
                            link=f"/projects/{project_id}",
                            priority="NORMAL"
                        )
            except Exception:
                pass
        else:
            # Under pending approval: notify Manager
            if status == "PENDING_APPROVAL" and manager_id and manager_id != creator.get("employee_id"):
                try:
                    from services.notification_service import NotificationService
                    NotificationService.create_notification(
                        title=f"New Project Proposal: {title}",
                        message=f"{creator.get('full_name')} submitted project proposal '{title}' ({project_id}) for your review and approval.",
                        recipient_id=manager_id,
                        category="PROJECT",
                        link=f"/projects?tab=approvals&project_id={project_id}",
                        priority="HIGH"
                    )
                except Exception as e:
                    logger.error(f"Error sending proposal notification to manager: {e}")

        AuditService.log_action(
            actor=creator,
            action="CREATE_PROJECT_PROPOSAL" if not is_approved else "CREATE_PROJECT",
            target_type="project",
            target_id=project_id,
            details={"title": title, "status": status, "selected_members_count": len(selected_members)}
        )
        return new_project, None

    @classmethod
    def approve_project(cls, manager: dict, project_id: str, review_notes: str = "") -> tuple[dict | None, str | None]:
        """
        Manager approval action:
        1. Activates project: status -> 'ACTIVE' (or 'APPROVED').
        2. Activates proposed members in project.members.
        3. Creates the single private group chat associated with the project.
        4. Notifies Team Lead and all approved members.
        5. Records approval history and audit trail.
        """
        db = get_db()
        project = db.projects.find_one({"project_id": project_id})
        if not project:
            return None, "Project not found."

        mgr_role = manager.get("role")
        is_assigned_mgr = (project.get("manager_employee_id") == manager.get("employee_id")) or (
            project.get("assigned_manager") == manager.get("employee_id")
        )
        if mgr_role not in (Role.MANAGER, Role.ADMIN) and not is_assigned_mgr:
            return None, "Unauthorized: Only an authorized Manager or Administrator can approve project proposals."

        if project.get("status") not in ("PENDING_APPROVAL", "CHANGES_REQUESTED", "DRAFT"):
            return None, f"Cannot approve project in status '{project.get('status')}'. Project must be PENDING_APPROVAL."

        now = datetime.now(timezone.utc)
        selected_members = project.get("selected_members") or project.get("proposed_members") or []
        clean_members = list(dict.fromkeys([str(m).strip().upper() for m in selected_members if str(m).strip()]))
        lead_id = project.get("project_lead") or project.get("created_by")

        approval_entry = {
            "action": "APPROVED",
            "actor_id": manager.get("employee_id"),
            "actor_name": manager.get("full_name"),
            "actor_role": mgr_role,
            "timestamp": now,
            "comments": review_notes or "Project proposal and team membership approved."
        }
        status_entry = {
            "status": "ACTIVE",
            "changed_by": manager.get("employee_id"),
            "changed_by_name": manager.get("full_name"),
            "timestamp": now,
            "notes": review_notes or "Approved by Manager; project activated."
        }

        db.projects.update_one(
            {"project_id": project_id},
            {
                "$set": {
                    "status": "ACTIVE",
                    "is_approved": True,
                    "approved_by": manager.get("employee_id"),
                    "approved_by_name": manager.get("full_name"),
                    "approved_at": now,
                    "members": clean_members,
                    "assigned_members": clean_members,
                    "conversation_id": f"PRJ-CHAT-{project_id}",
                    "updated_at": now
                },
                "$push": {
                    "approval_history": approval_entry,
                    "status_history": status_entry
                }
            }
        )

        updated_project = db.projects.find_one({"project_id": project_id})

        # 1. Automatic private group chat creation (idempotent)
        try:
            from services.chat_service import ChatService
            ChatService.ensure_project_chat(updated_project, manager)
        except Exception as e:
            logger.error(f"Error provisioning project group chat on approval: {e}")

        # 2. Notify Team Lead
        try:
            from services.notification_service import NotificationService
            if lead_id and lead_id != manager.get("employee_id"):
                NotificationService.create_notification(
                    title=f"Project Proposal Approved: {updated_project.get('title')}",
                    message=f"Manager {manager.get('full_name')} approved project proposal '{updated_project.get('title')}'. Collaboration workspace and group chat are now active.",
                    recipient_id=lead_id,
                    category="PROJECT",
                    link=f"/projects/{project_id}",
                    priority="HIGH"
                )

            # 3. Notify all approved project members
            for emp_id in clean_members:
                if emp_id != manager.get("employee_id"):
                    NotificationService.create_notification(
                        title=f"Assigned to Project: {updated_project.get('title')}",
                        message=f"You have been assigned to project '{updated_project.get('title')}' ({project_id}). Group chat and task deliverables are now open.",
                        recipient_id=emp_id,
                        category="PROJECT",
                        link=f"/projects/{project_id}",
                        priority="NORMAL"
                    )
        except Exception as e:
            logger.error(f"Error dispatching approval notifications: {e}")

        AuditService.log_action(
            actor=manager,
            action="APPROVE_PROJECT",
            target_type="project",
            target_id=project_id,
            details={"approved_members_count": len(clean_members), "review_notes": review_notes}
        )
        return updated_project, None

    @classmethod
    def reject_project(cls, manager: dict, project_id: str, rejection_reason: str) -> tuple[dict | None, str | None]:
        """
        Manager rejection action:
        Requires rejection reason. Keeps proposal and history intact for reference.
        No group chat is created.
        """
        if not rejection_reason or not rejection_reason.strip():
            return None, "Rejection reason is required."

        db = get_db()
        project = db.projects.find_one({"project_id": project_id})
        if not project:
            return None, "Project not found."

        mgr_role = manager.get("role")
        is_assigned_mgr = (project.get("manager_employee_id") == manager.get("employee_id")) or (
            project.get("assigned_manager") == manager.get("employee_id")
        )
        if mgr_role not in (Role.MANAGER, Role.ADMIN) and not is_assigned_mgr:
            return None, "Only an authorized Manager or Administrator can reject project proposals."

        if project.get("status") not in ("PENDING_APPROVAL", "CHANGES_REQUESTED"):
            return None, f"Cannot reject project in status '{project.get('status')}'. Project must be PENDING_APPROVAL."

        now = datetime.now(timezone.utc)
        lead_id = project.get("project_lead") or project.get("created_by")

        approval_entry = {
            "action": "REJECTED",
            "actor_id": manager.get("employee_id"),
            "actor_name": manager.get("full_name"),
            "actor_role": mgr_role,
            "timestamp": now,
            "comments": rejection_reason.strip()
        }
        status_entry = {
            "status": "REJECTED",
            "changed_by": manager.get("employee_id"),
            "changed_by_name": manager.get("full_name"),
            "timestamp": now,
            "notes": f"Rejected by Manager: {rejection_reason.strip()}"
        }

        db.projects.update_one(
            {"project_id": project_id},
            {
                "$set": {
                    "status": "REJECTED",
                    "is_approved": False,
                    "rejection_reason": rejection_reason.strip(),
                    "rejected_by": manager.get("employee_id"),
                    "rejected_by_name": manager.get("full_name"),
                    "rejected_at": now,
                    "updated_at": now
                },
                "$push": {
                    "approval_history": approval_entry,
                    "status_history": status_entry
                }
            }
        )

        updated_project = db.projects.find_one({"project_id": project_id})

        # Notify Team Lead
        try:
            from services.notification_service import NotificationService
            if lead_id:
                NotificationService.create_notification(
                    title=f"Project Proposal Rejected: {updated_project.get('title')}",
                    message=f"Manager {manager.get('full_name')} rejected proposal '{updated_project.get('title')}'. Reason: {rejection_reason.strip()}",
                    recipient_id=lead_id,
                    category="PROJECT",
                    link=f"/projects?tab=approvals&project_id={project_id}",
                    priority="HIGH"
                )
        except Exception:
            pass

        AuditService.log_action(
            actor=manager,
            action="REJECT_PROJECT",
            target_type="project",
            target_id=project_id,
            details={"rejection_reason": rejection_reason.strip()}
        )
        return updated_project, None

    @classmethod
    def request_changes_project(cls, manager: dict, project_id: str, comments: str) -> tuple[dict | None, str | None]:
        """
        Manager requests changes:
        Returns proposal to Team Lead with comments. Team Lead can edit and resubmit.
        """
        if not comments or not comments.strip():
            return None, "Comments detailing requested changes are required."

        db = get_db()
        project = db.projects.find_one({"project_id": project_id})
        if not project:
            return None, "Project not found."

        mgr_role = manager.get("role")
        is_assigned_mgr = (project.get("manager_employee_id") == manager.get("employee_id")) or (
            project.get("assigned_manager") == manager.get("employee_id")
        )
        if mgr_role not in (Role.MANAGER, Role.ADMIN) and not is_assigned_mgr:
            return None, "Only an authorized Manager or Administrator can request changes."

        if project.get("status") not in ("PENDING_APPROVAL",):
            return None, f"Cannot request changes on project in status '{project.get('status')}'. Project must be PENDING_APPROVAL."

        now = datetime.now(timezone.utc)
        lead_id = project.get("project_lead") or project.get("created_by")

        approval_entry = {
            "action": "CHANGES_REQUESTED",
            "actor_id": manager.get("employee_id"),
            "actor_name": manager.get("full_name"),
            "actor_role": mgr_role,
            "timestamp": now,
            "comments": comments.strip()
        }
        status_entry = {
            "status": "CHANGES_REQUESTED",
            "changed_by": manager.get("employee_id"),
            "changed_by_name": manager.get("full_name"),
            "timestamp": now,
            "notes": f"Changes requested by Manager: {comments.strip()}"
        }

        db.projects.update_one(
            {"project_id": project_id},
            {
                "$set": {
                    "status": "CHANGES_REQUESTED",
                    "change_comments": comments.strip(),
                    "change_request_comments": comments.strip(),
                    "reviewed_by": manager.get("employee_id"),
                    "reviewed_by_name": manager.get("full_name"),
                    "reviewed_at": now,
                    "updated_at": now
                },
                "$push": {
                    "approval_history": approval_entry,
                    "status_history": status_entry
                }
            }
        )

        updated_project = db.projects.find_one({"project_id": project_id})

        # Notify Team Lead
        try:
            from services.notification_service import NotificationService
            if lead_id:
                NotificationService.create_notification(
                    title=f"Changes Requested: {updated_project.get('title')}",
                    message=f"Manager {manager.get('full_name')} requested changes on proposal '{updated_project.get('title')}': {comments.strip()}",
                    recipient_id=lead_id,
                    category="PROJECT",
                    link=f"/projects?tab=approvals&project_id={project_id}",
                    priority="HIGH"
                )
        except Exception:
            pass

        AuditService.log_action(
            actor=manager,
            action="REQUEST_PROJECT_CHANGES",
            target_type="project",
            target_id=project_id,
            details={"comments": comments.strip()}
        )
        return updated_project, None

    @classmethod
    def update_project_proposal(cls, actor: dict, project_id: str, updates: dict, submit_for_approval: bool = True) -> tuple[dict | None, str | None]:
        """
        Allows Team Lead or Proposal Author to modify proposal details and resubmit for Manager approval.
        """
        db = get_db()
        project = db.projects.find_one({"project_id": project_id})
        if not project:
            return None, "Project not found."

        is_lead = (project.get("created_by") == actor.get("employee_id")) or (project.get("project_lead") == actor.get("employee_id"))
        is_mgr = actor.get("role") in (Role.MANAGER, Role.ADMIN)

        if not (is_lead or is_mgr):
            return None, "Unauthorized: Only the project lead or manager can edit this proposal."

        if project.get("status") not in ("DRAFT", "CHANGES_REQUESTED", "PENDING_APPROVAL"):
            return None, f"Cannot edit proposal in status '{project.get('status')}'. Proposal must be DRAFT, CHANGES_REQUESTED, or PENDING_APPROVAL."

        now = datetime.now(timezone.utc)
        set_dict = {"updated_at": now}

        for field in ["title", "name", "description", "objectives", "deliverables", "priority", "start_date", "due_date", "expected_completion_date", "category", "responsibilities", "required_skills", "notes", "assigned_manager"]:
            if field in updates:
                set_dict[field] = updates[field]
        if "title" in set_dict and "name" not in set_dict:
            set_dict["name"] = set_dict["title"]
        elif "name" in set_dict and "title" not in set_dict:
            set_dict["title"] = set_dict["name"]

        if "selected_members" in updates or "members" in updates:
            raw_members = updates.get("selected_members") or updates.get("members") or []
            if isinstance(raw_members, str):
                raw_members = [m.strip() for m in raw_members.split(",") if m.strip()]
            clean_members = list(dict.fromkeys([str(m).strip().upper() for m in raw_members if str(m).strip()]))
            set_dict["selected_members"] = clean_members
            set_dict["proposed_members"] = clean_members

        push_dict = {}
        if submit_for_approval:
            set_dict["status"] = "PENDING_APPROVAL"
            set_dict["is_approved"] = False
            approval_entry = {
                "action": "RESUBMITTED" if project.get("status") == "CHANGES_REQUESTED" else "SUBMITTED",
                "actor_id": actor.get("employee_id"),
                "actor_name": actor.get("full_name"),
                "actor_role": actor.get("role"),
                "timestamp": now,
                "comments": updates.get("resubmit_comments") or "Proposal resubmitted for Manager approval."
            }
            status_entry = {
                "status": "PENDING_APPROVAL",
                "changed_by": actor.get("employee_id"),
                "changed_by_name": actor.get("full_name"),
                "timestamp": now,
                "notes": "Proposal resubmitted for Manager approval"
            }
            push_dict["approval_history"] = approval_entry
            push_dict["status_history"] = status_entry

        update_op = {"$set": set_dict}
        if push_dict:
            update_op["$push"] = push_dict

        db.projects.update_one({"project_id": project_id}, update_op)
        updated_project = db.projects.find_one({"project_id": project_id})

        # Notify Manager if resubmitted
        if submit_for_approval:
            mgr_id = updated_project.get("assigned_manager") or updated_project.get("manager_employee_id")
            if mgr_id and mgr_id != actor.get("employee_id"):
                try:
                    from services.notification_service import NotificationService
                    NotificationService.create_notification(
                        title=f"Project Proposal Resubmitted: {updated_project.get('title')}",
                        message=f"{actor.get('full_name')} resubmitted proposal '{updated_project.get('title')}' ({project_id}) for your review and approval.",
                        recipient_id=mgr_id,
                        category="PROJECT",
                        link=f"/projects?tab=approvals&project_id={project_id}",
                        priority="HIGH"
                    )
                except Exception:
                    pass

        return updated_project, None

    @classmethod
    def submit_membership_change_request(
        cls,
        actor: dict,
        project_id: str,
        add_members: list,
        remove_members: list,
        reason: str
    ) -> tuple[dict | None, str | None]:
        """
        Team Lead submits a membership change request to add or remove members from an active project.
        Requires Manager approval before changes take effect.
        """
        db = get_db()
        project = db.projects.find_one({"project_id": project_id})
        if not project:
            return None, "Project not found."

        if not project.get("is_approved") or project.get("status") not in ("ACTIVE", "APPROVED", "IN_PROGRESS", "ON_HOLD"):
            return None, "Membership change requests can only be submitted for active approved projects."

        is_lead = (project.get("created_by") == actor.get("employee_id")) or (project.get("project_lead") == actor.get("employee_id"))
        is_mgr = actor.get("role") in (Role.MANAGER, Role.ADMIN)

        if not (is_lead or is_mgr):
            return None, "Unauthorized: Only the project lead or manager can submit membership change requests."

        clean_add = [str(m).strip().upper() for m in (add_members or []) if str(m).strip()]
        clean_remove = [str(m).strip().upper() for m in (remove_members or []) if str(m).strip()]

        if not clean_add and not clean_remove:
            return None, "At least one member must be specified to add or remove."

        now = datetime.now(timezone.utc)
        request_id = f"MCR-{secrets.token_hex(4).upper()}"
        change_request = {
            "request_id": request_id,
            "project_id": project_id,
            "project_title": project.get("title", ""),
            "requested_by": actor.get("employee_id"),
            "requested_by_name": actor.get("full_name"),
            "add_members": clean_add,
            "remove_members": clean_remove,
            "reason": (reason or "").strip(),
            "status": "PENDING",
            "created_at": now
        }

        db.projects.update_one(
            {"project_id": project_id},
            {"$push": {"membership_change_requests": change_request}}
        )

        # Notify Manager
        mgr_id = project.get("assigned_manager") or project.get("manager_employee_id")
        if mgr_id and mgr_id != actor.get("employee_id"):
            try:
                from services.notification_service import NotificationService
                NotificationService.create_notification(
                    title=f"Membership Change Request: {project.get('title')}",
                    message=f"{actor.get('full_name')} requested membership changes on '{project.get('title')}' (+{len(clean_add)}, -{len(clean_remove)}). Review required.",
                    recipient_id=mgr_id,
                    category="PROJECT",
                    link=f"/projects?tab=approvals&project_id={project_id}",
                    priority="HIGH"
                )
            except Exception:
                pass

        return change_request, None

    @classmethod
    def review_membership_change_request(
        cls,
        manager: dict,
        project_id: str,
        request_id: str,
        action: str,
        review_notes: str = ""
    ) -> tuple[dict | None, str | None]:
        """
        Manager reviews membership change request:
        - Approve: updates project.members, synchronizes project group chat participants, notifies added/removed members.
        - Reject: preserves original membership, records rejection reason, notifies lead.
        """
        db = get_db()
        project = db.projects.find_one({"project_id": project_id})
        if not project:
            return None, "Project not found."

        mgr_role = manager.get("role")
        is_assigned_mgr = (project.get("manager_employee_id") == manager.get("employee_id")) or (
            project.get("assigned_manager") == manager.get("employee_id")
        )
        if mgr_role not in (Role.MANAGER, Role.ADMIN) and not is_assigned_mgr:
            return None, "Only an authorized Manager or Administrator can review membership change requests."

        requests = project.get("membership_change_requests", [])
        req_match = next((r for r in requests if r.get("request_id") == request_id and r.get("status") == "PENDING"), None)
        if not req_match:
            return None, "Pending membership change request not found."

        action_upper = action.strip().upper()
        if action_upper not in ("APPROVE", "REJECT"):
            return None, "Action must be 'APPROVE' or 'REJECT'."

        now = datetime.now(timezone.utc)
        lead_id = project.get("project_lead") or project.get("created_by")

        if action_upper == "APPROVE":
            current_members = set(project.get("members", []))
            for m in req_match.get("add_members", []):
                current_members.add(m)
            for m in req_match.get("remove_members", []):
                current_members.discard(m)

            updated_members = sorted(list(current_members))

            # Update project document
            db.projects.update_one(
                {"project_id": project_id, "membership_change_requests.request_id": request_id},
                {
                    "$set": {
                        "members": updated_members,
                        "assigned_members": updated_members,
                        "selected_members": updated_members,
                        "membership_change_requests.$.status": "APPROVED",
                        "membership_change_requests.$.reviewed_by": manager.get("employee_id"),
                        "membership_change_requests.$.reviewed_by_name": manager.get("full_name"),
                        "membership_change_requests.$.reviewed_at": now,
                        "membership_change_requests.$.review_notes": review_notes or "Approved by Manager.",
                        "updated_at": now
                    }
                }
            )

            # Synchronize project chat participants
            updated_proj = db.projects.find_one({"project_id": project_id})
            try:
                from services.chat_service import ChatService
                ChatService.ensure_project_chat(updated_proj, manager)
            except Exception as e:
                logger.error(f"Error synchronizing chat on membership update: {e}")

            # Notify newly added members
            try:
                from services.notification_service import NotificationService
                for emp_id in req_match.get("add_members", []):
                    if emp_id != manager.get("employee_id"):
                        NotificationService.create_notification(
                            title=f"Added to Project: {project.get('title')}",
                            message=f"You have been added to project '{project.get('title')}' ({project_id}). Group chat and task access are now enabled.",
                            recipient_id=emp_id,
                            category="PROJECT",
                            link=f"/projects/{project_id}",
                            priority="NORMAL"
                        )

                # Notify removed members
                for emp_id in req_match.get("remove_members", []):
                    if emp_id != manager.get("employee_id"):
                        NotificationService.create_notification(
                            title=f"Removed from Project: {project.get('title')}",
                            message=f"You have been removed from project '{project.get('title')}' ({project_id}). Project access has been revoked.",
                            recipient_id=emp_id,
                            category="PROJECT",
                            link="/projects",
                            priority="NORMAL"
                        )

                # Notify Team Lead
                if lead_id and lead_id != manager.get("employee_id"):
                    NotificationService.create_notification(
                        title=f"Membership Change Approved: {project.get('title')}",
                        message=f"Manager {manager.get('full_name')} approved the requested membership changes on '{project.get('title')}'.",
                        recipient_id=lead_id,
                        category="PROJECT",
                        link=f"/projects/{project_id}",
                        priority="NORMAL"
                    )
            except Exception:
                pass

            req_match["status"] = "APPROVED"
            return req_match, None

        else:
            # Rejection
            db.projects.update_one(
                {"project_id": project_id, "membership_change_requests.request_id": request_id},
                {
                    "$set": {
                        "membership_change_requests.$.status": "REJECTED",
                        "membership_change_requests.$.reviewed_by": manager.get("employee_id"),
                        "membership_change_requests.$.reviewed_by_name": manager.get("full_name"),
                        "membership_change_requests.$.reviewed_at": now,
                        "membership_change_requests.$.review_notes": review_notes or "Rejected by Manager.",
                        "updated_at": now
                    }
                }
            )

            # Notify Team Lead
            try:
                from services.notification_service import NotificationService
                if lead_id:
                    NotificationService.create_notification(
                        title=f"Membership Change Rejected: {project.get('title')}",
                        message=f"Manager {manager.get('full_name')} rejected the membership change request on '{project.get('title')}'. Notes: {review_notes or 'No reason provided'}",
                        recipient_id=lead_id,
                        category="PROJECT",
                        link=f"/projects/{project_id}",
                        priority="NORMAL"
                    )
            except Exception:
                pass

            req_match["status"] = "REJECTED"
            return req_match, None

    @classmethod
    def update_project_status(cls, actor: dict, project_id: str, new_status: str, notes: str = "") -> tuple[dict | None, str | None]:
        """
        Manages the project status lifecycle with strict transition validation:
        DRAFT -> PENDING_APPROVAL -> APPROVED / ACTIVE -> IN_PROGRESS -> ON_HOLD -> COMPLETED.
        Also supports REJECTED, CHANGES_REQUESTED, CANCELLED.
        """
        valid_statuses = ("DRAFT", "PENDING_APPROVAL", "CHANGES_REQUESTED", "APPROVED", "ACTIVE", "IN_PROGRESS", "ON_HOLD", "COMPLETED", "REJECTED", "CANCELLED")
        target_status = new_status.strip().upper()
        if target_status not in valid_statuses:
            return None, f"Invalid status '{new_status}'. Allowed: {', '.join(valid_statuses)}"

        db = get_db()
        project = db.projects.find_one({"project_id": project_id})
        if not project:
            return None, "Project not found."

        current_status = project.get("status", "ACTIVE")
        actor_role = actor.get("role")
        is_lead = (project.get("created_by") == actor.get("employee_id")) or (project.get("project_lead") == actor.get("employee_id"))
        is_mgr = (actor_role in (Role.MANAGER, Role.ADMIN)) or (project.get("manager_employee_id") == actor.get("employee_id"))

        if not (is_lead or is_mgr):
            return None, "Unauthorized: Only the project lead or manager can transition project status."

        # Status transition rules
        VALID_TRANSITIONS = {
            "DRAFT": ["PENDING_APPROVAL", "CANCELLED"],
            "PENDING_APPROVAL": ["APPROVED", "ACTIVE", "CHANGES_REQUESTED", "REJECTED", "CANCELLED", "DRAFT"],
            "CHANGES_REQUESTED": ["PENDING_APPROVAL", "CANCELLED", "DRAFT"],
            "APPROVED": ["ACTIVE", "IN_PROGRESS", "ON_HOLD", "CANCELLED"],
            "ACTIVE": ["IN_PROGRESS", "ON_HOLD", "COMPLETED", "CANCELLED"],
            "IN_PROGRESS": ["ON_HOLD", "COMPLETED", "CANCELLED"],
            "ON_HOLD": ["IN_PROGRESS", "CANCELLED", "COMPLETED"],
            "COMPLETED": [],
            "REJECTED": ["DRAFT", "PENDING_APPROVAL"],
            "CANCELLED": []
        }
        if target_status != current_status and target_status not in VALID_TRANSITIONS.get(current_status, []):
            return None, f"Invalid status transition from '{current_status}' to '{target_status}'."

        if target_status in ("APPROVED", "ACTIVE") and current_status in ("PENDING_APPROVAL", "CHANGES_REQUESTED"):
            # Requires approve_project method
            return cls.approve_project(actor, project_id, notes)

        now = datetime.now(timezone.utc)
        status_entry = {
            "status": target_status,
            "changed_by": actor.get("employee_id"),
            "changed_by_name": actor.get("full_name"),
            "timestamp": now,
            "notes": notes or f"Status transitioned from {current_status} to {target_status}"
        }

        db.projects.update_one(
            {"project_id": project_id},
            {
                "$set": {"status": target_status, "updated_at": now},
                "$push": {"status_history": status_entry}
            }
        )

        updated_project = db.projects.find_one({"project_id": project_id})
        return updated_project, None

    @classmethod
    def get_pending_approvals(cls, user: dict) -> dict:
        """
        Returns pending project proposals and membership change requests for Manager or Team Lead review.
        """
        db = get_db()
        user_role = user.get("role")
        emp_id = user.get("employee_id")

        if user_role == Role.HR:
            return {"proposals": [], "membership_requests": [], "total_pending": 0}

        proposals = []
        membership_requests = []

        if user_role in (Role.MANAGER, Role.ADMIN):
            # All proposals awaiting manager approval
            query = {"status": {"$in": ["PENDING_APPROVAL", "CHANGES_REQUESTED"]}}
            proposals = list(db.projects.find(query).sort("created_at", -1))

            # All pending membership change requests
            mcr_projects = list(db.projects.find({"membership_change_requests.status": "PENDING"}))
            for p in mcr_projects:
                for req in p.get("membership_change_requests", []):
                    if req.get("status") == "PENDING":
                        membership_requests.append(req)

        elif user_role == Role.TEAM_LEAD:
            # Proposals created or led by this team lead
            query = {
                "$or": [{"created_by": emp_id}, {"project_lead": emp_id}],
                "status": {"$in": ["PENDING_APPROVAL", "CHANGES_REQUESTED", "DRAFT", "REJECTED"]}
            }
            proposals = list(db.projects.find(query).sort("created_at", -1))

            mcr_projects = list(db.projects.find({
                "$or": [{"created_by": emp_id}, {"project_lead": emp_id}],
                "membership_change_requests.status": "PENDING"
            }))
            for p in mcr_projects:
                for req in p.get("membership_change_requests", []):
                    if req.get("status") == "PENDING":
                        membership_requests.append(req)

        # Enrich proposals with employee info for review
        for p in proposals:
            sel_members = p.get("selected_members") or p.get("proposed_members") or []
            if sel_members:
                user_docs = list(db.users.find(
                    {"employee_id": {"$in": sel_members}},
                    {"employee_id": 1, "full_name": 1, "department": 1, "designation": 1, "skills": 1}
                ))
                for u in user_docs:
                    u_id = u.get("employee_id")
                    active_prjs = db.projects.count_documents({"members": u_id, "status": {"$in": ["ACTIVE", "APPROVED", "IN_PROGRESS"]}})
                    active_tsks = db.tasks.count_documents({"assigned_to": u_id, "status": {"$in": ["Pending", "In Progress"]}})
                    u["active_projects_count"] = active_prjs
                    u["active_tasks_count"] = active_tsks
                    u["availability"] = "Available (0 active)" if active_prjs == 0 else f"{active_prjs} active project(s)"
                p["selected_member_details"] = user_docs
            else:
                p["selected_member_details"] = []

        return {
            "proposals": proposals,
            "membership_requests": membership_requests,
            "total_pending": len(proposals) + len(membership_requests)
        }

    @classmethod
    def create_task(cls, actor: dict, task_data: dict) -> tuple[dict | None, str | None]:
        db = get_db()
        project_id = task_data.get("project_id")
        project = db.projects.find_one({"project_id": project_id})
        if not project:
            return None, "Project not found."

        if project.get("status") not in ("APPROVED", "ACTIVE", "IN_PROGRESS"):
            return None, f"Cannot create tasks on project with status '{project.get('status')}'. Project must be approved and active."

        task_id = task_data.get("task_id")
        if not task_id:
            count = db.tasks.count_documents({})
            task_id = f"TSK-{1001 + count}"

        title = task_data.get("title", "").strip()
        if not title:
            return None, "Task title is required."

        assigned_emp_id = task_data.get("assigned_employee_id")
        weight = float(task_data.get("weight", 1.0))
        if weight <= 0:
            weight = 1.0

        new_task = {
            "task_id": task_id,
            "project_id": project_id,
            "title": title,
            "description": task_data.get("description", "").strip(),
            "assigned_employee_id": assigned_emp_id,
            "due_date": task_data.get("due_date"),
            "status": "Pending",
            "progress_percentage": 0,
            "weight": weight,
            "notes": task_data.get("notes", ""),
            "created_by": actor.get("employee_id"),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }

        db.tasks.insert_one(new_task)

        if assigned_emp_id and assigned_emp_id not in project.get("members", []):
            db.projects.update_one(
                {"project_id": project_id},
                {"$addToSet": {"members": assigned_emp_id}}
            )

        cls.recalculate_project_progress(project_id)

        AuditService.log_action(
            actor=actor,
            action="CREATE_TASK",
            target_type="task",
            target_id=task_id,
            details={"project_id": project_id, "assigned_to": assigned_emp_id}
        )
        return new_task, None

    @classmethod
    def update_task_progress(
        cls,
        actor: dict,
        task_id: str,
        progress_percentage: int,
        status: str = None,
        notes: str = None
    ) -> tuple[dict | None, str | None]:
        db = get_db()
        task = db.tasks.find_one({"task_id": task_id})
        if not task:
            return None, "Task not found."

        is_assigned = task.get("assigned_employee_id") == actor.get("employee_id")
        is_hr = actor.get("role") in (Role.HR, Role.HR_MANAGER, Role.ORGANIZATION, Role.ADMIN)

        if not (is_assigned or is_hr):
            return None, "You are not authorized to update this task."

        progress = max(0, min(100, int(progress_percentage)))
        updates = {
            "progress_percentage": progress,
            "updated_at": datetime.now(timezone.utc)
        }
        if status:
            updates["status"] = status
        elif progress == 100:
            updates["status"] = "Completed"
        elif progress > 0:
            updates["status"] = "In Progress"

        if notes is not None:
            updates["notes"] = notes.strip()

        db.tasks.update_one({"task_id": task_id}, {"$set": updates})
        cls.recalculate_project_progress(task["project_id"])

        updated_task = db.tasks.find_one({"task_id": task_id})
        return updated_task, None

    @classmethod
    def recalculate_project_progress(cls, project_id: str) -> int:
        db = get_db()
        tasks = list(db.tasks.find({"project_id": project_id}))
        if not tasks:
            return 0

        total_weight = sum(t.get("weight", 1.0) for t in tasks)
        if total_weight <= 0:
            return 0

        weighted_progress = sum(
            (t.get("progress_percentage", 0) * t.get("weight", 1.0))
            for t in tasks
        )
        overall_progress = int(round(weighted_progress / total_weight))

        all_completed = all(t.get("status") == "Completed" for t in tasks)
        status_update = {}
        if all_completed and len(tasks) > 0:
            status_update["status"] = "Completed"

        status_update["progress_percentage"] = overall_progress
        status_update["updated_at"] = datetime.now(timezone.utc)

        db.projects.update_one({"project_id": project_id}, {"$set": status_update})
        return overall_progress

    @classmethod
    def edit_project(cls, actor: dict, project_id: str, updates: dict) -> tuple[dict | None, str | None]:
        """
        Allows authorized Team Leads and Managers to edit project details:
        name, description, objectives, dates, priority, tasks, progress, blockers.
        Enforces authorization scopes:
        - HR cannot edit projects (403)
        - Employees cannot edit projects (403)
        - Team Leads can only edit projects assigned to them or created by them
        - Managers can edit projects within their scope
        """
        db = get_db()
        actor_role = actor.get("role")
        actor_id = actor.get("employee_id")

        if actor_role == Role.HR:
            return None, "Unauthorized: HR personnel do not manage projects."
        if actor_role == Role.EMPLOYEE:
            return None, "Unauthorized: Employees cannot edit project settings."

        project = db.projects.find_one({"project_id": project_id, "is_deleted": {"$ne": True}})
        if not project:
            return None, "Project not found."

        is_lead = (project.get("created_by") == actor_id) or (project.get("project_lead") == actor_id) or (project.get("lead_id") == actor_id)
        is_mgr = actor_role in (Role.MANAGER, Role.ADMIN, Role.HR_MANAGER, Role.ORGANIZATION) or (project.get("manager_employee_id") == actor_id)

        if not (is_lead or is_mgr):
            return None, "Unauthorized: You do not have permission to edit this project."

        now = datetime.now(timezone.utc)
        allowed_fields = [
            "title", "name", "description", "objectives", "deliverables",
            "priority", "start_date", "due_date", "expected_completion_date",
            "category", "responsibilities", "progress_percentage", "blockers", "notes"
        ]
        set_dict = {"updated_at": now}
        for field in allowed_fields:
            if field in updates:
                set_dict[field] = updates[field]

        if "title" in set_dict and "name" not in set_dict:
            set_dict["name"] = set_dict["title"]
        elif "name" in set_dict and "title" not in set_dict:
            set_dict["title"] = set_dict["name"]

        # Manager can update members directly; TL must use membership change request
        if is_mgr and ("members" in updates or "selected_members" in updates):
            raw_members = updates.get("members") or updates.get("selected_members") or []
            if isinstance(raw_members, str):
                raw_members = [m.strip() for m in raw_members.split(",") if m.strip()]
            clean_members = list(dict.fromkeys([str(m).strip().upper() for m in raw_members if str(m).strip()]))
            set_dict["members"] = clean_members
            set_dict["selected_members"] = clean_members

        db.projects.update_one({"project_id": project_id}, {"$set": set_dict})

        AuditService.log_action(
            actor=actor,
            action="PROJECT_EDITED",
            target_type="project",
            target_id=project_id,
            details={"updated_fields": list(set_dict.keys())}
        )

        return db.projects.find_one({"project_id": project_id}), None

    @classmethod
    def delete_or_archive_project(cls, actor: dict, project_id: str, reason: str = "") -> tuple[bool, str]:
        """
        Soft deletes or archives a project while preserving audit records, chat history,
        and employee work diaries.
        - Team Lead can delete/cancel draft or pending proposals they created.
        - Manager can archive/soft-delete active projects or clean up confirmed dummy/test projects.
        - Prevents accidental deletion of active projects with dependent work without Manager confirmation.
        - Does NOT delete employee accounts, attendance, or unrelated conversations.
        """
        db = get_db()
        actor_role = actor.get("role")
        actor_id = actor.get("employee_id")

        if actor_role == Role.HR:
            return False, "Unauthorized: HR personnel cannot delete projects."
        if actor_role == Role.EMPLOYEE:
            return False, "Unauthorized: Employees cannot delete projects."

        project = db.projects.find_one({"project_id": project_id})
        if not project:
            return False, "Project not found."

        is_lead = (project.get("created_by") == actor_id) or (project.get("project_lead") == actor_id) or (project.get("lead_id") == actor_id)
        is_mgr = actor_role in (Role.MANAGER, Role.ADMIN, Role.ORGANIZATION) or (project.get("manager_employee_id") == actor_id)

        if not (is_lead or is_mgr):
            return False, "Unauthorized: You do not have permission to delete this project."

        current_status = (project.get("status") or "").upper()
        now = datetime.now(timezone.utc)

        # Team Lead can only delete DRAFT, PENDING_APPROVAL, or REJECTED proposals they created
        if is_lead and not is_mgr:
            if current_status not in ("DRAFT", "PENDING_APPROVAL", "CHANGES_REQUESTED", "REJECTED"):
                return False, "Unauthorized: Active or approved projects require Manager authorization to archive or delete."

        # Check dependent work diaries
        diary_count = db.work_diaries.count_documents({"project_id": project_id})
        task_count = db.tasks.count_documents({"project_id": project_id})

        # Soft delete / archival
        db.projects.update_one(
            {"project_id": project_id},
            {
                "$set": {
                    "is_deleted": True,
                    "deleted_at": now,
                    "deleted_by": actor_id,
                    "delete_reason": reason or "Project archived by authorized manager/lead.",
                    "status": "ARCHIVED",
                    "updated_at": now
                },
                "$push": {
                    "status_history": {
                        "status": "ARCHIVED",
                        "changed_by": actor_id,
                        "changed_by_name": actor.get("full_name"),
                        "timestamp": now,
                        "notes": f"Project soft-deleted/archived. Reason: {reason or 'Cleanup'}"
                    }
                }
            }
        )

        AuditService.log_action(
            actor=actor,
            action="PROJECT_ARCHIVED",
            target_type="project",
            target_id=project_id,
            details={
                "reason": reason,
                "had_tasks": task_count,
                "had_diaries": diary_count,
                "previous_status": current_status
            }
        )

        return True, f"Project {project_id} has been safely archived."

    @classmethod
    def get_dummy_projects_for_review(cls, manager: dict) -> list:
        """
        Identifies confirmed test/demo or empty placeholder projects for safe review by authorized Managers.
        Does NOT auto-delete anything.
        """
        db = get_db()
        if manager.get("role") not in (Role.MANAGER, Role.ADMIN, Role.ORGANIZATION):
            return []

        all_projects = list(db.projects.find({"is_deleted": {"$ne": True}}).sort("created_at", -1))
        candidates = []
        for p in all_projects:
            pid = p.get("project_id", "")
            title = p.get("title") or p.get("name") or ""
            tasks_count = db.tasks.count_documents({"project_id": pid})
            diary_count = db.work_diaries.count_documents({"project_id": pid})
            members = p.get("members", []) or p.get("selected_members", [])

            is_test_id = "TEST" in pid or "DEMO" in pid or "DUMMY" in pid
            is_test_title = any(term in title.lower() for term in ["test", "demo", "sandbox", "sample", "placeholder"])
            is_empty = (len(members) == 0 and tasks_count == 0 and diary_count == 0)

            if is_test_id or is_test_title or (is_empty and p.get("status") in ("DRAFT", "CANCELLED")):
                reason = []
                if is_test_id:
                    reason.append(f"Project ID contains test identifier ({pid})")
                if is_test_title:
                    reason.append(f"Title indicates test/sandbox ({title})")
                if is_empty:
                    reason.append("No members, tasks, or work diaries recorded")

                candidates.append({
                    "project_id": pid,
                    "title": title,
                    "status": p.get("status"),
                    "created_at": p.get("created_at"),
                    "members_count": len(members),
                    "tasks_count": tasks_count,
                    "work_diaries_count": diary_count,
                    "flag_reason": ", ".join(reason)
                })

        return candidates

    @classmethod
    def get_user_projects(cls, user: dict) -> list:
        db = get_db()
        role = user.get("role")
        emp_id = user.get("employee_id")

        if role == Role.HR:
            return []

        if role in (Role.MANAGER, Role.ADMIN, Role.ORGANIZATION, Role.HR_MANAGER):
            return list(db.projects.find({"is_deleted": {"$ne": True}}).sort("created_at", -1))
        
        if role in (Role.TEAM_LEAD, Role.TRAINER) or user.get("legacy_role") == "team_lead":
            query = {
                "is_deleted": {"$ne": True},
                "$or": [
                    {"project_lead": emp_id},
                    {"lead_id": emp_id},
                    {"created_by": emp_id},
                    {"members": emp_id},
                    {"selected_members": emp_id}
                ]
            }
            return list(db.projects.find(query).sort("created_at", -1))

        # Role.EMPLOYEE: strictly approved/active projects where employee is an active member
        query = {
            "is_deleted": {"$ne": True},
            "members": emp_id,
            "status": {"$in": ["APPROVED", "ACTIVE", "IN_PROGRESS", "ON_HOLD", "COMPLETED"]}
        }
        return list(db.projects.find(query).sort("created_at", -1))

    @classmethod
    def get_user_tasks(cls, user: dict) -> list:
        db = get_db()
        emp_id = user.get("employee_id")
        return list(db.tasks.find({"assigned_employee_id": emp_id}).sort("due_date", 1))

    @classmethod
    def create_team(cls, creator: dict, team_data: dict) -> tuple[dict | None, str | None]:
        db = get_db()
        team_id = team_data.get("team_id")
        if not team_id:
            count = db.teams.count_documents({})
            team_id = f"TEAM-{101 + count}"

        if db.teams.find_one({"team_id": team_id}):
            return None, f"Team ID {team_id} already exists."

        name = team_data.get("name", "").strip()
        if not name:
            return None, "Team name is required."

        new_team = {
            "team_id": team_id,
            "name": name,
            "department": team_data.get("department", "Engineering"),
            "lead_employee_id": team_data.get("lead_employee_id"),
            "members": team_data.get("members", []),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        db.teams.insert_one(new_team)
        return new_team, None
