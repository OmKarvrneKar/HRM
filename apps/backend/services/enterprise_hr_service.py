"""
AI Samrat HRMS — Enterprise Full-Stack Modules Service Suite (R1-R29)
=======================================================================
Architecture:
- Bulletproof multi-tenant persistence layer across MongoDB & Mongomock
- Production-grade service classes covering:
  1. NomineeManagementService (Nominee share registry with 100% total validation)
  2. AssetSoftwareService (Hardware allocation, software license keys, global inventory)
  3. FacilityBookingService (Verified meeting room management and collision-free booking)
  4. PerformanceLearningService (KRA/KPI goal tracker & mandatory compliance courses: InfoSec, DPDP Act 2023)
  5. EngagementSupportService (Community feed, birthday kudos points leaderboard, IT/HR ticketing, travel & expense claims, policy vault)
  6. SeparationService (Resignation workflow, tenure tracker, 4-way departmental clearance)
  7. RecruitmentTalentService (Interview candidate scorecards, ATS resume match scoring, MRF manpower requisition workflows)
  8. SecureDocumentViewerService (PII redaction, Aadhaar XXXX-XXXX-1234, PAN, bank records)
  9. EnterprisePayrollService (Monthly payroll cycles, statutory PF/ESI/TDS calculations, batch vector slip links)
"""

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Any, Optional
from bson import ObjectId

from database.connection import get_db
from services.audit_service import AuditService
from services.notification_service import NotificationService
from permissions.rbac import Role, normalize_role
from utils.serializers import serialize_doc, serialize_docs

logger = logging.getLogger(__name__)


def _utc_now():
    return datetime.now(timezone.utc)


def _persist_if_proxy(db):
    persist_fn = getattr(db, "persist_to_disk", None)
    if callable(persist_fn) and not hasattr(persist_fn, "database"):
        try:
            persist_fn()
        except Exception:
            pass


# ============================================================================
# 1. NOMINEE MANAGEMENT SERVICE
# ============================================================================
class NomineeManagementService:
    @classmethod
    def get_nominees(cls, employee_id: str) -> List[Dict]:
        db = get_db()
        nominees = list(db.nominees.find({"employee_id": employee_id}))
        return serialize_docs(nominees)

    @classmethod
    def save_nominees(cls, actor: dict, employee_id: str, nominees_data: List[Dict]) -> Tuple[bool, str]:
        db = get_db()
        if not nominees_data:
            return False, "At least one nominee is required."

        total_share = 0
        cleaned_nominees = []
        for idx, item in enumerate(nominees_data, start=1):
            name = (item.get("name") or "").strip()
            relationship = (item.get("relationship") or "").strip()
            contact = (item.get("contact") or "").strip()
            address = (item.get("address") or "").strip()
            try:
                share = float(item.get("share_percentage", 0))
            except (ValueError, TypeError):
                return False, f"Invalid share percentage for nominee '{name}'."

            if not name or not relationship:
                return False, f"Nominee #{idx} must have a valid full name and relationship."
            if share <= 0 or share > 100:
                return False, f"Nominee '{name}' share percentage must be between 1% and 100%."

            total_share += share
            cleaned_nominees.append({
                "nominee_id": f"NOM-{employee_id}-{idx}",
                "employee_id": employee_id,
                "name": name,
                "relationship": relationship,
                "date_of_birth": (item.get("date_of_birth") or "").strip(),
                "contact": contact,
                "address": address,
                "share_percentage": share,
                "guardian_name": (item.get("guardian_name") or "").strip(),
                "updated_at": _utc_now()
            })

        if round(total_share, 2) != 100.0:
            return False, f"Total nominee allocation must equal exactly 100%. Current sum: {total_share}%."

        # Atomically replace employee's nominees
        db.nominees.delete_many({"employee_id": employee_id})
        db.nominees.insert_many(cleaned_nominees)

        # Update in user document for quick profile display
        db.users.update_one(
            {"employee_id": employee_id},
            {"$set": {
                "nominees_count": len(cleaned_nominees),
                "nominees_summary": f"{len(cleaned_nominees)} registered (100% allocated)",
                "updated_at": _utc_now()
            }}
        )

        AuditService.log_action(
            actor=actor,
            action="UPDATE_NOMINEE_REGISTRY",
            target_type="user",
            target_id=employee_id,
            details=f"Updated {len(cleaned_nominees)} nominees totaling 100% share allocation."
        )
        return True, "Nominee registry updated successfully."


# ============================================================================
# 2. ASSETS & SOFTWARE MANAGEMENT SERVICE
# ============================================================================
class AssetSoftwareService:
    @classmethod
    def get_employee_assets(cls, employee_id: str) -> Dict[str, Any]:
        db = get_db()
        hardware = list(db.hardware_assets.find({"assigned_to": employee_id, "status": "Assigned", "is_verified": True}))
        software = list(db.software_licenses.find({"assigned_to": employee_id, "status": "Active", "is_verified": True}))
        requests = list(db.asset_requests.find({"employee_id": employee_id}).sort("created_at", -1))
        seating = SeatingLockerService.get_employee_seating(employee_id)

        return {
            "hardware": serialize_docs(hardware),
            "software": serialize_docs(software),
            "requests": serialize_docs(requests),
            "seating": seating
        }

    @classmethod
    def request_asset(cls, actor: dict, data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        cat = (data.get("category") or "Hardware").strip()
        item_name = (data.get("item_name") or "").strip()
        justification = (data.get("justification") or "").strip()
        urgency = (data.get("urgency") or "Medium").strip()

        if not item_name or not justification:
            return None, "Item name and business justification are mandatory."

        count = db.asset_requests.count_documents({})
        req_id = f"AST-REQ-{1001 + count}"

        doc = {
            "request_id": req_id,
            "employee_id": actor["employee_id"],
            "employee_name": actor.get("full_name", ""),
            "department": actor.get("department", "Engineering"),
            "category": cat,
            "item_name": item_name,
            "justification": justification,
            "urgency": urgency,
            "status": "Pending Review",
            "assigned_approver": actor.get("manager_id") or "MGR-1001",
            "assigned_manager_id": actor.get("manager_id") or "MGR-1001",
            "created_at": _utc_now(),
            "updated_at": _utc_now()
        }
        db.asset_requests.insert_one(doc)
        try:
            NotificationService.create_notification(
                title=f"Asset Request: {item_name}",
                message=f"{doc['employee_name']} requested {item_name}. Please review the request.",
                category="ASSET",
                recipient_id=doc["assigned_manager_id"],
                link="/dashboard/manager"
            )
        except Exception as exc:
            logger.warning("Failed to notify the assigned manager about asset request %s: %s", req_id, exc)

        AuditService.log_action(
            actor=actor,
            action="SUBMIT_ASSET_REQUEST",
            target_type="asset_request",
            target_id=req_id,
            details=f"Requested {cat}: {item_name} (Urgency: {urgency})"
        )
        return serialize_doc(doc), None

    @classmethod
    def get_global_inventory(cls, actor: dict = None) -> Dict[str, Any]:
        db = get_db()
        # Only expose verified enterprise hardware/software records; exclude any unverified baseline drafts
        all_hw = list(db.hardware_assets.find({"is_verified": True}))
        all_sw = list(db.software_licenses.find({"is_verified": True}))
        request_query = {}
        if actor and normalize_role(actor.get("role")) == Role.MANAGER:
            actor_id = actor.get("employee_id") or actor.get("emp_id")
            request_query = {"$or": [
                {"assigned_manager_id": actor_id},
                {"assigned_manager_id": {"$exists": False}, "department": actor.get("department")}
            ]}
        all_reqs = list(db.asset_requests.find(request_query).sort("created_at", -1))

        in_use_hw = sum(1 for h in all_hw if h.get("status") == "Assigned")
        in_stock_hw = sum(1 for h in all_hw if h.get("status") == "In Stock")

        actor_role = normalize_role(actor.get("role")) if actor else Role.ADMIN
        all_seating = (
            SeatingLockerService.get_all_seating_allocations()
            if actor_role in (Role.HR, Role.MANAGER, Role.ADMIN)
            else []
        )

        return {
            "total_hardware": len(all_hw),
            "hardware_assigned": in_use_hw,
            "hardware_in_stock": in_stock_hw,
            "total_software_licenses": len(all_sw),
            "total_seating_allocated": len(all_seating),
            "pending_requests_count": sum(1 for r in all_reqs if r.get("status") == "Pending Review"),
            "hardware": serialize_docs(all_hw),
            "software": serialize_docs(all_sw),
            "requests": serialize_docs(all_reqs),
            "seating_allocations": all_seating
        }

    @classmethod
    def review_asset_request(
        cls,
        actor: dict,
        request_id: str,
        decision: str,
        remarks: str = "",
        assigned_asset_tag: str = None
    ) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        req = db.asset_requests.find_one({"request_id": request_id})
        if not req:
            return None, f"Asset request '{request_id}' not found."

        role = normalize_role(actor.get("role"))
        if role == Role.MANAGER and req.get("assigned_manager_id") != actor.get("employee_id") and not (
            not req.get("assigned_manager_id") and req.get("department") == actor.get("department")
        ):
            return None, "Access denied: this asset request is assigned to another manager."
        if req.get("status") != "Pending Review":
            return None, f"Asset request is already in '{req.get('status')}' status."

        dec = decision.strip().title()
        if dec not in ("Approved", "Rejected"):
            return None, "Decision must be 'Approved' or 'Rejected'."

        now = _utc_now()
        updates = {
            "status": dec,
            "reviewed_by_id": actor["employee_id"],
            "reviewed_by_name": actor.get("full_name", ""),
            "review_remarks": remarks.strip(),
            "reviewed_at": now,
            "updated_at": now
        }

        if dec == "Approved" and assigned_asset_tag:
            updates["assigned_asset_tag"] = assigned_asset_tag
            emp_id = req["employee_id"]
            emp_name = req.get("employee_name", "")
            hw = db.hardware_assets.find_one({"asset_tag": assigned_asset_tag})
            if hw:
                db.hardware_assets.update_one(
                    {"asset_tag": assigned_asset_tag},
                    {"$set": {
                        "status": "Assigned",
                        "assigned_to": emp_id,
                        "assigned_name": emp_name,
                        "assigned_date": datetime.now().strftime("%Y-%m-%d")
                    }}
                )
            else:
                sw = db.software_licenses.find_one({"license_id": assigned_asset_tag})
                if sw:
                    db.software_licenses.update_one(
                        {"license_id": assigned_asset_tag},
                        {"$set": {
                            "status": "Active",
                            "assigned_to": emp_id
                        }}
                    )

        result = db.asset_requests.update_one(
            {"request_id": request_id, "status": "Pending Review"},
            {"$set": updates}
        )
        if result.matched_count != 1:
            return None, "Asset request was already reviewed. Refresh and try again."

        AuditService.log_action(
            actor=actor,
            action=f"ASSET_REQUEST_{dec.upper()}",
            target_type="asset_request",
            target_id=request_id,
            details=f"Decision: {dec}, Tag: {assigned_asset_tag}, Remarks: {remarks}"
        )
        try:
            NotificationService.create_notification(
                title=f"Asset Request {dec}",
                message=f"Your asset request for {req.get('item_name')} was {dec.lower()}.",
                category="ASSET",
                recipient_id=req["employee_id"],
                link="/assets"
            )
        except Exception as exc:
            logger.warning("Failed to notify employee about asset request %s: %s", request_id, exc)
        return serialize_doc(db.asset_requests.find_one({"request_id": request_id})), None

    @classmethod
    def allocate_asset(cls, actor: dict, employee_id: str, asset_data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        target_user = db.users.find_one({"$or": [{"emp_id": employee_id}, {"employee_id": employee_id}]})
        if not target_user:
            return None, f"Employee '{employee_id}' not found."

        cat = (asset_data.get("category") or "Hardware").strip()
        now = _utc_now()
        today_str = datetime.now().strftime("%Y-%m-%d")
        import uuid

        if cat.lower() == "hardware":
            asset_tag = (asset_data.get("asset_tag") or f"AIS-LAP-{uuid.uuid4().hex[:4].upper()}").strip()
            doc = {
                "asset_tag": asset_tag,
                "type": asset_data.get("type", "Laptop"),
                "model": asset_data.get("model", "Company Hardware"),
                "serial": asset_data.get("serial", f"SN-{uuid.uuid4().hex[:6].upper()}"),
                "status": "Assigned",
                "assigned_to": target_user.get("emp_id") or target_user.get("employee_id"),
                "assigned_name": target_user.get("full_name") or target_user.get("name"),
                "assigned_date": today_str,
                "allocated_by": actor["employee_id"],
                "is_verified": True,
                "verification_status": "Verified Asset Allocation",
                "created_at": now
            }
            db.hardware_assets.replace_one({"asset_tag": asset_tag}, doc, upsert=True)
            allocated = doc
        else:
            license_id = (asset_data.get("license_id") or f"SW-LIC-{uuid.uuid4().hex[:4].upper()}").strip()
            doc = {
                "license_id": license_id,
                "software_name": asset_data.get("software_name", "Enterprise Software"),
                "edition": asset_data.get("edition", "Enterprise Seat"),
                "seat_key": asset_data.get("seat_key", f"KEY-{uuid.uuid4().hex[:8].upper()}"),
                "status": "Active",
                "assigned_to": target_user.get("emp_id") or target_user.get("employee_id"),
                "expiry_date": asset_data.get("expiry_date", "2027-12-31"),
                "allocated_by": actor["employee_id"],
                "is_verified": True,
                "verification_status": "Verified Asset Allocation",
                "created_at": now
            }
            db.software_licenses.replace_one({"license_id": license_id}, doc, upsert=True)
            allocated = doc

        AuditService.log_action(
            actor=actor,
            action="ALLOCATE_ASSET",
            target_type="asset_inventory",
            target_id=allocated.get("asset_tag") or allocated.get("license_id"),
            details=f"Allocated to {employee_id}"
        )
        return serialize_doc(allocated), None

    @classmethod
    def cancel_or_delete_asset_request(cls, actor: dict, request_id: str) -> Tuple[bool, Optional[str]]:
        db = get_db()
        req = db.asset_requests.find_one({"request_id": request_id})
        if not req:
            return False, f"Asset request '{request_id}' not found."

        is_owner = req.get("employee_id") == actor.get("employee_id")
        is_admin_or_hr = actor.get("role") in (Role.ADMIN, Role.HR, Role.HR_MANAGER, Role.ORGANIZATION)

        if is_owner and not is_admin_or_hr:
            if req.get("status") not in ("Pending Review", "Draft"):
                return False, "Cannot cancel request once it has been processed."
        elif not is_admin_or_hr:
            return False, "Unauthorized to cancel or delete this asset request."

        db.asset_requests.delete_one({"request_id": request_id})
        AuditService.log_action(
            actor=actor,
            action="DELETE_ASSET_REQUEST",
            target_type="asset_request",
            target_id=request_id,
            details=f"Asset request {request_id} deleted."
        )
        return True, None

    @classmethod
    def delete_asset_inventory(cls, actor: dict, asset_type: str, item_id: str) -> Tuple[bool, Optional[str]]:
        if actor.get("role") not in (Role.ADMIN, Role.HR, Role.HR_MANAGER, Role.ORGANIZATION):
            return False, "Unauthorized: Only HR or Admin can decommission or delete assets."

        db = get_db()
        if asset_type.lower() in ("hardware", "hw"):
            res = db.hardware_assets.delete_one({"asset_tag": item_id})
            if res.deleted_count == 0:
                return False, f"Hardware asset '{item_id}' not found."
        else:
            res = db.software_licenses.delete_one({"license_id": item_id})
            if res.deleted_count == 0:
                return False, f"Software license '{item_id}' not found."

        AuditService.log_action(
            actor=actor,
            action="DECOMMISSION_ASSET",
            target_type="asset_inventory",
            target_id=item_id,
            details=f"{asset_type} item {item_id} decommissioned/deleted."
        )
        return True, None



# ============================================================================
# 2.1 OFFICE SEATING & PERSONAL LOCKER ALLOCATION SERVICE
# ============================================================================
class SeatingLockerService:
    @classmethod
    def get_employee_seating(cls, employee_id: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        alloc = db.seating_allocations.find_one({
            "$or": [{"employee_id": employee_id}, {"emp_id": employee_id}],
            "is_verified": True,
        })
        if not alloc:
            return None
        alloc["is_verified"] = True
        return serialize_doc(alloc)

    @classmethod
    def get_all_seating_allocations(cls) -> List[Dict[str, Any]]:
        db = get_db()
        active_users = {
            (u.get("employee_id") or u.get("emp_id")): u
            for u in db.users.find({"is_active": True}, {"employee_id": 1, "emp_id": 1, "full_name": 1, "name": 1})
            if (u.get("employee_id") or u.get("emp_id"))
        }
        # Never expose generated or unverified provisional baseline desk layouts in production
        allocs = list(db.seating_allocations.find({"is_verified": True}).sort("desk_number", 1))
        visible = []
        for a in allocs:
            eid = a.get("employee_id") or a.get("emp_id")
            if eid in active_users:
                a["is_verified"] = True
                a["status"] = a.get("status") or "Allocated"
                a["verification_status"] = a.get("verification_status") or "Verified Official Allocation"
                visible.append(a)
        return serialize_docs(visible)

    @classmethod
    def verify_allocation(cls, actor: dict, allocation_id: str, verified_data: dict = None) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        actor_role = normalize_role(actor.get("role"))
        if actor_role not in (Role.HR, Role.ADMIN):
            return None, "Unauthorized: Only HR and Administrators can verify and confirm workstation allocations."

        alloc = db.seating_allocations.find_one({"allocation_id": allocation_id})
        if not alloc:
            alloc = db.seating_allocations.find_one({"$or": [{"employee_id": allocation_id}, {"emp_id": allocation_id}]})
        if not alloc:
            return None, f"Seating allocation '{allocation_id}' not found."

        data = verified_data or {}
        notes = (data.get("notes") or "").strip()
        if not notes:
            return None, "Verification notes describing physical inspection evidence are strictly required."

        desk_no = (data.get("desk_number") or "").strip().upper()
        if not desk_no:
            return None, "Official desk number is required for verification."

        now_iso = datetime.now(timezone.utc).isoformat()
        actor_id = actor.get("employee_id") or actor.get("emp_id") or "ADMIN"
        actor_name = actor.get("full_name") or actor.get("name") or "Administrator"

        updates = {
            "is_verified": True,
            "verification_status": "Verified Official Allocation",
            "allocation_type": "Official Physical Assignment",
            "status": "Allocated",
            "verified_by_id": actor_id,
            "verified_by_name": actor_name,
            "verified_at": now_iso,
            "verification_notes": notes,
            "desk_number": desk_no,
            "updated_at": _utc_now()
        }
        if data.get("locker_number") is not None:
            updates["locker_number"] = data["locker_number"].strip().upper()
        if data.get("locker_location") is not None:
            updates["locker_location"] = data["locker_location"].strip()
        if data.get("floor") is not None:
            updates["floor"] = data["floor"].strip()
        if data.get("bay") is not None:
            updates["bay"] = data["bay"].strip()
        if data.get("amenities") is not None:
            updates["amenities"] = data["amenities"].strip()

        db.seating_allocations.update_one({"_id": alloc["_id"]}, {"$set": updates})

        AuditService.log_action(
            actor=actor,
            action="VERIFY_SEATING_ALLOCATION",
            target_type="seating_allocation",
            target_id=alloc.get("allocation_id") or allocation_id,
            details=f"Verified official seating assignment for {alloc.get('employee_name')} ({alloc.get('employee_id')})"
        )

        updated = db.seating_allocations.find_one({"_id": alloc["_id"]})
        _persist_if_proxy(db)
        return serialize_doc(updated), None

    @classmethod
    def allocate_or_update(cls, actor: dict, data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        actor_role = normalize_role(actor.get("role"))
        if actor_role not in (Role.HR, Role.ADMIN):
            return None, "Unauthorized: Only HR and Administrators can create or assign workstation allocations."

        emp_id = (data.get("employee_id") or "").strip().upper()
        if not emp_id:
            return None, "Employee ID is required."

        u = db.users.find_one({"$or": [{"employee_id": emp_id}, {"emp_id": emp_id}]})
        if not u:
            return None, f"Employee '{emp_id}' not found."

        floor = (data.get("floor") or "").strip()
        bay = (data.get("bay") or "").strip()
        desk = (data.get("desk_number") or "").strip().upper()
        notes = (data.get("notes") or data.get("verification_notes") or "").strip()

        if not floor or not bay or not desk:
            return None, "Physical floor, zone/bay, and official desk number are required (no placeholder defaults permitted)."
        if not notes:
            return None, "Physical verification audit notes are required to confirm a genuine workstation allocation."

        emp_name = u.get("full_name") or u.get("name") or emp_id
        dept = u.get("department") or (data.get("department") or "").strip()
        locker = (data.get("locker_number") or "").strip().upper()
        lck_loc = (data.get("locker_location") or "").strip()
        key_type = (data.get("key_type") or "").strip()
        amenities = (data.get("amenities") or "").strip()
        now_date = datetime.now().strftime("%Y-%m-%d")
        now_iso = datetime.now(timezone.utc).isoformat()
        actor_id = actor.get("employee_id") or actor.get("emp_id") or "ADMIN"
        actor_name = actor.get("full_name") or actor.get("name") or "Administrator"

        doc = {
            "allocation_id": f"SL-{emp_id}",
            "employee_id": emp_id,
            "employee_name": emp_name,
            "department": dept,
            "role": u.get("role", "employee"),
            "floor": floor,
            "bay": bay,
            "desk_number": desk,
            "locker_number": locker,
            "locker_location": lck_loc,
            "key_type": key_type,
            "amenities": amenities,
            "status": "Allocated",
            "is_verified": True,
            "verification_status": "Verified Official Allocation",
            "allocation_type": "Official Physical Assignment",
            "verified_by_id": actor_id,
            "verified_by_name": actor_name,
            "verified_at": now_iso,
            "verification_notes": notes,
            "allocated_date": data.get("allocated_date") or now_date,
            "updated_at": _utc_now()
        }

        db.seating_allocations.update_one(
            {"employee_id": emp_id},
            {"$set": doc, "$setOnInsert": {"created_at": _utc_now()}},
            upsert=True
        )

        AuditService.log_action(
            actor=actor,
            action="ALLOCATE_SEATING_LOCKER",
            target_type="seating_allocation",
            target_id=emp_id,
            details=f"Verified and allocated Desk {desk}" + (f" and Locker {locker}" if locker else "") + f" to {emp_name} ({emp_id})"
        )

        _persist_if_proxy(db)
        saved = db.seating_allocations.find_one({"employee_id": emp_id})
        return serialize_doc(saved), None


# ============================================================================
# 3. FACILITY & MEETING ROOM BOOKING SERVICE
# ============================================================================
class FacilityBookingService:
    @classmethod
    def get_rooms_and_bookings(cls, target_date: str) -> Dict[str, Any]:
        db = get_db()
        # Only return formally verified company rooms; exclude unverified baseline templates
        rooms = list(db.facility_rooms.find({"is_verified": True}))
        for r in rooms:
            r["is_verified"] = True
            r["verification_status"] = r.get("verification_status") or "Verified Company Facility"
            r["status"] = r.get("status") or "Available"
        bookings = list(db.facility_bookings.find({"booking_date": target_date}).sort("start_time", 1))

        return {
            "target_date": target_date,
            "rooms": serialize_docs(rooms),
            "bookings": serialize_docs(bookings),
            "verified_rooms_count": len(rooms),
            "unverified_rooms_count": 0,
            "total_rooms": len(rooms)
        }

    @classmethod
    def verify_room(cls, actor: dict, room_id: str, verified_data: dict = None) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        actor_role = normalize_role(actor.get("role"))
        if actor_role not in (Role.HR, Role.ADMIN):
            return None, "Unauthorized: Only HR and Facility Administrators can verify meeting room information."

        room = db.facility_rooms.find_one({"room_id": room_id})
        if not room:
            return None, f"Facility room '{room_id}' not found."

        data = verified_data or {}
        notes = (data.get("notes") or "").strip()
        if not notes:
            return None, "Verification notes describing physical inspection evidence are strictly required."

        name = (data.get("name") or "").strip()
        floor = (data.get("floor") or "").strip()
        if not name:
            return None, "Confirmed room name is required for verification."
        if not floor:
            return None, "Audited physical floor location is required for verification."

        try:
            capacity_val = int(data.get("capacity"))
            if capacity_val <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            return None, "Confirmed positive seat capacity is required for verification."

        now_iso = datetime.now(timezone.utc).isoformat()
        actor_id = actor.get("employee_id") or actor.get("emp_id") or "ADMIN"
        actor_name = actor.get("full_name") or actor.get("name") or "Administrator"

        updates = {
            "is_verified": True,
            "verification_status": "Verified Company Facility",
            "status": "Available",
            "verified_by_id": actor_id,
            "verified_by_name": actor_name,
            "verified_at": now_iso,
            "verification_notes": notes,
            "name": name,
            "floor": floor,
            "capacity": capacity_val,
            "updated_at": _utc_now()
        }
        if "features" in data and isinstance(data["features"], list):
            updates["features"] = data["features"]

        db.facility_rooms.update_one({"_id": room["_id"]}, {"$set": updates})

        AuditService.log_action(
            actor=actor,
            action="VERIFY_FACILITY_ROOM",
            target_type="facility_room",
            target_id=room_id,
            details=f"Verified facility room {name} ({room_id})"
        )

        updated = db.facility_rooms.find_one({"_id": room["_id"]})
        _persist_if_proxy(db)
        return serialize_doc(updated), None

    @classmethod
    def create_booking(cls, actor: dict, data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        room_id = (data.get("room_id") or "").strip()
        b_date = (data.get("booking_date") or "").strip()
        start_t = (data.get("start_time") or "").strip()
        end_t = (data.get("end_time") or "").strip()
        title = (data.get("title") or "").strip()
        attendees = int(data.get("attendees_count") or 1)

        if not room_id or not b_date or not start_t or not end_t or not title:
            return None, "All booking details (room, date, start time, end time, and meeting title) are required."

        if start_t >= end_t:
            return None, "Meeting start time must precede end time."

        room = db.facility_rooms.find_one({"room_id": room_id})
        if not room:
            return None, f"Facility room '{room_id}' not found."
        if not room.get("is_verified"):
            return None, f"Facility room '{room.get('name') or room_id}' must be formally verified before booking."

        # Check for time overlap conflict
        conflict = db.facility_bookings.find_one({
            "room_id": room_id,
            "booking_date": b_date,
            "$or": [
                {"start_time": {"$lt": end_t}, "end_time": {"$gt": start_t}}
            ]
        })
        if conflict:
            return None, f"Slot conflict: '{room['name']}' is already booked from {conflict['start_time']} to {conflict['end_time']} by {conflict['organizer_name']}."

        count = db.facility_bookings.count_documents({})
        b_id = f"FCL-{1001 + count}"

        booking = {
            "booking_id": b_id,
            "room_id": room_id,
            "room_name": room["name"],
            "booking_date": b_date,
            "start_time": start_t,
            "end_time": end_t,
            "title": title,
            "organizer_id": actor["employee_id"],
            "organizer_name": actor.get("full_name", ""),
            "attendees_count": attendees,
            "created_at": _utc_now()
        }
        db.facility_bookings.insert_one(booking)

        AuditService.log_action(
            actor=actor,
            action="BOOK_FACILITY_ROOM",
            target_type="facility_booking",
            target_id=b_id,
            details=f"Booked {room['name']} on {b_date} ({start_t}–{end_t}) for '{title}'"
        )
        _persist_if_proxy(db)
        return serialize_doc(booking), None

    @classmethod
    def cancel_booking(cls, actor: dict, booking_id: str) -> Tuple[bool, str]:
        db = get_db()
        booking = db.facility_bookings.find_one({"booking_id": booking_id})
        if not booking:
            return False, "Booking not found."

        is_owner = booking.get("organizer_id") == actor.get("employee_id")
        is_admin = normalize_role(actor.get("role")) in (Role.ADMIN, Role.HR)
        if not is_owner and not is_admin:
            return False, "Unauthorized: Only the meeting organizer or Administrator can cancel this booking."

        db.facility_bookings.delete_one({"booking_id": booking_id})
        _persist_if_proxy(db)
        return True, "Meeting room booking cancelled successfully."

    @classmethod
    def create_room(cls, actor: dict, data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        if normalize_role(actor.get("role")) not in (Role.ADMIN, Role.HR):
            return None, "Unauthorized: Only HR or Admin can add and verify facility meeting rooms."

        db = get_db()
        name = (data.get("name") or "").strip()
        floor = (data.get("floor") or "").strip()
        notes = (data.get("notes") or data.get("verification_notes") or "").strip()

        if not name or not floor:
            return None, "Confirmed room name and physical floor are required (no placeholder defaults permitted)."

        try:
            capacity = int(data.get("capacity"))
            if capacity <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            return None, "Confirmed positive seat capacity is required."

        if not notes:
            return None, "Verification notes describing physical inspection evidence are strictly required."

        raw_features = data.get("features")
        if isinstance(raw_features, str):
            features = [f.strip() for f in raw_features.split(",") if f.strip()]
        elif isinstance(raw_features, list):
            features = [str(f).strip() for f in raw_features if str(f).strip()]
        else:
            features = []

        import uuid
        room_id = f"ROOM-{uuid.uuid4().hex[:6].upper()}"
        now_iso = datetime.now(timezone.utc).isoformat()
        actor_id = actor.get("employee_id") or actor.get("emp_id") or "ADMIN"
        actor_name = actor.get("full_name") or actor.get("name") or "Administrator"

        doc = {
            "room_id": room_id,
            "name": name,
            "floor": floor,
            "capacity": capacity,
            "features": features,
            "image_badge": (data.get("image_badge") or "Conference Room").strip(),
            "color": (data.get("color") or "primary").strip(),
            "is_verified": True,
            "verification_status": "Verified Company Facility",
            "status": "Available",
            "verified_by_id": actor_id,
            "verified_by_name": actor_name,
            "verified_at": now_iso,
            "verification_notes": notes,
            "created_by": actor_id,
            "created_at": _utc_now(),
            "updated_at": _utc_now()
        }
        db.facility_rooms.insert_one(doc)
        AuditService.log_action(
            actor=actor,
            action="CREATE_VERIFIED_FACILITY_ROOM",
            target_type="facility_room",
            target_id=room_id,
            details=f"Registered verified room '{name}' on {floor} (capacity {capacity})"
        )
        _persist_if_proxy(db)
        return serialize_doc(doc), None

    @classmethod
    def delete_room(cls, actor: dict, room_id: str) -> Tuple[bool, Optional[str]]:
        if normalize_role(actor.get("role")) not in (Role.ADMIN, Role.HR):
            return False, "Unauthorized: Only HR or Admin can delete facility meeting rooms."

        db = get_db()
        res = db.facility_rooms.delete_one({"room_id": room_id})
        if res.deleted_count == 0:
            return False, f"Meeting room '{room_id}' not found."

        db.facility_bookings.delete_many({"room_id": room_id})
        AuditService.log_action(
            actor=actor,
            action="DELETE_FACILITY_ROOM",
            target_type="facility_room",
            target_id=room_id,
            details=f"Deleted facility room {room_id}"
        )
        _persist_if_proxy(db)
        return True, None


# ============================================================================
# 4. PERFORMANCE & COMPLIANCE LEARNING SERVICE (L&D)
# ============================================================================
class PerformanceLearningService:
    MANDATORY_COURSES = [
        {
            "course_id": "CRS-SEC-101",
            "title": "Information Security & ISO 27001 Essentials",
            "category": "Mandatory Statutory",
            "duration": "45 mins",
            "modules_count": 4,
            "compliance_code": "ISO-27001-A.7",
            "description": "Enterprise hygiene, phishing defense, zero-trust endpoint rules, credential encryption, and incident reporting protocols.",
            "pass_score": 80
        },
        {
            "course_id": "CRS-DPDP-201",
            "title": "Digital Personal Data Protection (DPDP) Act 2023",
            "category": "Statutory Law",
            "duration": "60 mins",
            "modules_count": 5,
            "compliance_code": "DPDP-ACT-SEC-6",
            "description": "Indian statutory data fiduciary responsibilities, consent lifecycle, data principal grievances, and multi-crore penalty deterrence.",
            "pass_score": 85
        },
        {
            "course_id": "CRS-POSH-301",
            "title": "Prevention of Sexual Harassment (PoSH) Governance",
            "category": "Mandatory Governance",
            "duration": "30 mins",
            "modules_count": 3,
            "compliance_code": "POSH-ACT-2013",
            "description": "Zero tolerance workplace mandate, Internal Committee (IC) grievance workflow, confidentiality protection, and safe office standards.",
            "pass_score": 80
        },
        {
            "course_id": "CRS-ETH-401",
            "title": "Corporate Code of Conduct & Anti-Bribery Standards",
            "category": "Ethics & Integrity",
            "duration": "30 mins",
            "modules_count": 3,
            "compliance_code": "FCPA-PCA-2026",
            "description": "Conflict of interest disclosure, vendor transparency, gift policies, intellectual property security, and whistleblower protections.",
            "pass_score": 80
        }
    ]

    @classmethod
    def get_employee_performance_hub(cls, employee_id: str) -> Dict[str, Any]:
        db = get_db()
        goals = list(db.kpi_goals.find({"employee_id": employee_id}))
        completions = {c["course_id"]: c for c in db.compliance_completions.find({"employee_id": employee_id})}

        # Build dynamic course list with employee status
        courses_with_status = []
        for c in cls.MANDATORY_COURSES:
            rec = completions.get(c["course_id"])
            item = dict(c)
            if rec:
                item["status"] = rec.get("status", "Completed")
                item["score"] = rec.get("score", 100)
                item["completed_at"] = rec.get("completed_at")
                item["certificate_id"] = rec.get("certificate_id")
            else:
                item["status"] = "Pending"
                item["score"] = 0
                item["completed_at"] = None
                item["certificate_id"] = None
            courses_with_status.append(item)

        # Baseline seed sample goals if none exist
        if not goals:
            sample_goals = [
                {"goal_id": f"KRA-{employee_id}-01", "employee_id": employee_id, "title": "Quarterly Sprint Velocity & High Code Quality", "weightage": 35, "target": "Maintain <0.5 bug escape rate and 95%+ sprint commitment delivery", "progress": 88, "status": "On Track"},
                {"goal_id": f"KRA-{employee_id}-02", "employee_id": employee_id, "title": "Enterprise System Architecture Upgrades", "weightage": 35, "target": "Execute zero-downtime database resilience & enterprise modules upgrade", "progress": 95, "status": "Exceeding Target"},
                {"goal_id": f"KRA-{employee_id}-03", "employee_id": employee_id, "title": "Mandatory Compliance & Team Mentorship", "weightage": 30, "target": "100% on-time completion of DPDP & ISO 27001 training modules", "progress": 100, "status": "Completed"},
            ]
            db.kpi_goals.insert_many(sample_goals)
            goals = sample_goals

        # Query employee tasks
        tasks = list(db.employee_tasks.find({"$or": [{"employee_id": employee_id}, {"assignee_id": employee_id}]}).sort("created_at", -1))
        if not tasks:
            sample_tasks = [
                {
                    "task_id": f"TSK-{employee_id}-01",
                    "employee_id": employee_id,
                    "assignee_id": employee_id,
                    "title": "Implement Enterprise RBAC Clearance Gates",
                    "project": "HRMS Core Platform",
                    "priority": "High",
                    "due_date": (datetime.now().date() + timedelta(days=7)).strftime("%Y-%m-%d"),
                    "status": "In Progress",
                    "description": "Implement 4-way departmental clearances for separation workflow.",
                    "created_at": _utc_now()
                },
                {
                    "task_id": f"TSK-{employee_id}-02",
                    "employee_id": employee_id,
                    "assignee_id": employee_id,
                    "title": "Audit Biometric Attendance Log Synchronization",
                    "project": "Attendance Engine",
                    "priority": "Critical",
                    "due_date": (datetime.now().date() + timedelta(days=3)).strftime("%Y-%m-%d"),
                    "status": "To Do",
                    "description": "Ensure punch-in telemetry matches server timestamp with zero deviation.",
                    "created_at": _utc_now()
                },
                {
                    "task_id": f"TSK-{employee_id}-03",
                    "employee_id": employee_id,
                    "assignee_id": employee_id,
                    "title": "PoSH & DPDP Compliance Certificate Issuance",
                    "project": "Governance & Compliance",
                    "priority": "Medium",
                    "due_date": (datetime.now().date() + timedelta(days=12)).strftime("%Y-%m-%d"),
                    "status": "Completed",
                    "description": "Issue signed digital certification on passing statutory evaluation.",
                    "created_at": _utc_now()
                },
                {
                    "task_id": f"TSK-{employee_id}-04",
                    "employee_id": employee_id,
                    "assignee_id": employee_id,
                    "title": "Review Squad Sprint Work Diaries",
                    "project": "Sprint Management",
                    "priority": "Low",
                    "due_date": (datetime.now().date() + timedelta(days=5)).strftime("%Y-%m-%d"),
                    "status": "In Progress",
                    "description": "Verify team velocity and task status updates before retrospective.",
                    "created_at": _utc_now()
                }
            ]
            db.employee_tasks.insert_many(sample_tasks)
            tasks = sample_tasks

        completed_count = sum(1 for c in courses_with_status if c["status"] == "Completed")
        compliance_pct = int((completed_count / len(cls.MANDATORY_COURSES)) * 100) if cls.MANDATORY_COURSES else 100

        return {
            "employee_id": employee_id,
            "compliance_percentage": compliance_pct,
            "completed_courses_count": completed_count,
            "total_mandatory_courses": len(cls.MANDATORY_COURSES),
            "goals": serialize_docs(goals),
            "courses": courses_with_status,
            "tasks": serialize_docs(tasks)
        }

    @classmethod
    def create_task(cls, actor: dict, data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        emp_id = actor["employee_id"]
        title = (data.get("title") or "").strip()
        if not title:
            return None, "Task title is required."
        project = (data.get("project") or "General Enterprise").strip()
        priority = (data.get("priority") or "Medium").strip()
        due_date = (data.get("due_date") or "").strip()
        description = (data.get("description") or "").strip()

        count = db.employee_tasks.count_documents({})
        task_id = f"TSK-{emp_id}-{101 + count}"
        now_dt = _utc_now()

        doc = {
            "task_id": task_id,
            "employee_id": emp_id,
            "assignee_id": data.get("assignee_id") or emp_id,
            "created_by": emp_id,
            "created_by_name": actor.get("full_name") or actor.get("name") or emp_id,
            "title": title,
            "project": project,
            "priority": priority,
            "due_date": due_date or (datetime.now().date() + timedelta(days=7)).strftime("%Y-%m-%d"),
            "status": data.get("status") or "To Do",
            "description": description,
            "created_at": now_dt,
            "updated_at": now_dt
        }
        db.employee_tasks.insert_one(doc)
        return serialize_doc(doc), None

    @classmethod
    def update_task_status(cls, actor: dict, task_id: str, new_status: str) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        valid_statuses = ["To Do", "In Progress", "In Review", "Completed"]
        if new_status not in valid_statuses:
            return None, f"Invalid status '{new_status}'. Allowed: {', '.join(valid_statuses)}"

        task = db.employee_tasks.find_one({"task_id": task_id})
        if not task and ObjectId.is_valid(task_id):
            task = db.employee_tasks.find_one({"_id": ObjectId(task_id)})
        if not task:
            return None, f"Task '{task_id}' not found."

        db.employee_tasks.update_one(
            {"_id": task["_id"]},
            {"$set": {"status": new_status, "updated_at": _utc_now()}}
        )
        updated = db.employee_tasks.find_one({"_id": task["_id"]})
        return serialize_doc(updated), None

    @classmethod
    def complete_course(cls, actor: dict, course_id: str, score: int = 95) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        course = next((c for c in cls.MANDATORY_COURSES if c["course_id"] == course_id), None)
        if not course:
            return None, "Invalid compliance course identifier."

        try:
            score = int(score)
        except (TypeError, ValueError):
            return None, "Assessment score must be an integer from 0 to 100."
        if not 0 <= score <= 100:
            return None, "Assessment score must be between 0 and 100."
        if score < course["pass_score"]:
            return None, f"Assessment score must be at least {course['pass_score']}% to complete this course."

        emp_id = actor["employee_id"]
        cert_id = f"CERT-{course_id.split('-')[1]}-{emp_id}-{int(datetime.now().timestamp())}"

        doc = {
            "employee_id": emp_id,
            "employee_name": actor.get("full_name", ""),
            "course_id": course_id,
            "course_title": course["title"],
            "score": score,
            "status": "Completed",
            "certificate_id": cert_id,
            "completed_at": _utc_now()
        }
        db.compliance_completions.update_one(
            {"employee_id": emp_id, "course_id": course_id},
            {"$set": doc},
            upsert=True
        )

        AuditService.log_action(
            actor=actor,
            action="COMPLETE_COMPLIANCE_COURSE",
            target_type="compliance_course",
            target_id=course_id,
            details=f"Completed '{course['title']}' with score {score}%. Certificate: {cert_id}"
        )
        return doc, None


# ============================================================================
# 5. ENGAGEMENT, COMMUNITY, KUDOS, TICKETS & TRAVEL CLAIMS
# ============================================================================
class EngagementSupportService:
    @classmethod
    def get_community_feed(cls) -> List[Dict]:
        db = get_db()
        posts = list(db.community_posts.find({}).sort("created_at", -1).limit(20))
        if not posts:
            seed_posts = [
                {
                    "post_id": "POST-101",
                    "author_name": "Deepak S J",
                    "author_role": "Employee / Tech Lead",
                    "author_initial": "D",
                    "badge": "Engineering Spotlight",
                    "content": "Excited to announce that the AI Samrat HRMS platform has just been upgraded to enterprise-grade with automated database resilience, multi-pad notes, and 29 integrated enterprise modules! 🚀",
                    "likes_count": 18,
                    "liked_by": ["AS-1019", "TL-1001", "HR-1001"],
                    "created_at": _utc_now()
                },
                {
                    "post_id": "POST-102",
                    "author_name": "Ramya",
                    "author_role": "HR Operations Center",
                    "author_initial": "R",
                    "badge": "Company Milestone",
                    "content": "Happy Birthday to all team members celebrating this month! Check out the Kudos Leaderboard and send peer appreciation points to your colleagues. 🎉",
                    "likes_count": 24,
                    "liked_by": ["AS-1019", "AS-1012", "MGR-1001"],
                    "created_at": _utc_now()
                }
            ]
            db.community_posts.insert_many(seed_posts)
            posts = seed_posts

        return serialize_docs(posts)

    @classmethod
    def create_post(cls, actor: dict, content: str, badge: str = "Team Update") -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        content = content.strip()
        if not content:
            return None, "Post content cannot be empty."

        count = db.community_posts.count_documents({})
        post = {
            "post_id": f"POST-{1001 + count}",
            "author_id": actor["employee_id"],
            "author_name": actor.get("full_name", ""),
            "author_role": actor.get("role", "employee").capitalize(),
            "author_initial": (actor.get("full_name") or "U")[:1].upper(),
            "badge": badge,
            "content": content,
            "likes_count": 0,
            "liked_by": [],
            "created_at": _utc_now()
        }
        db.community_posts.insert_one(post)
        return serialize_doc(post), None

    @classmethod
    def toggle_like(cls, actor: dict, post_id: str) -> Tuple[bool, int]:
        db = get_db()
        post = db.community_posts.find_one({"post_id": post_id})
        if not post:
            return False, 0

        emp_id = actor["employee_id"]
        liked_by = post.get("liked_by", [])
        if emp_id in liked_by:
            liked_by.remove(emp_id)
        else:
            liked_by.append(emp_id)

        new_count = len(liked_by)
        db.community_posts.update_one(
            {"post_id": post_id},
            {"$set": {"liked_by": liked_by, "likes_count": new_count}}
        )
        return True, new_count

    @classmethod
    def get_kudos_leaderboard(cls) -> Dict[str, Any]:
        db = get_db()
        kudos_records = list(db.kudos_ledger.find({}))
        # Do not silently insert fake kudos on read if empty
        if not kudos_records:
            return {
                "leaderboard": [],
                "recent_kudos": [],
                "total_kudos_count": 0,
                "top_recognizers": []
            }

        # Aggregate points per recipient
        points_map = {}
        for k in kudos_records:
            rid = k["recipient_id"]
            if rid not in points_map:
                points_map[rid] = {
                    "employee_id": rid,
                    "name": k["recipient_name"],
                    "total_points": 0,
                    "kudos_count": 0,
                    "top_category": k["category"]
                }
            points_map[rid]["total_points"] += k["points"]
            points_map[rid]["kudos_count"] += 1

        leaderboard = sorted(points_map.values(), key=lambda x: x["total_points"], reverse=True)
        for idx, item in enumerate(leaderboard, start=1):
            item["rank"] = idx

        return {
            "leaderboard": leaderboard,
            "recent_kudos": serialize_docs(kudos_records[-10:])
        }

    @classmethod
    def send_kudos(cls, actor: dict, recipient_id: str, points: int, category: str, message: str) -> Tuple[bool, str]:
        import re
        db = get_db()
        recipient = db.users.find_one({
            "$or": [
                {"employee_id": recipient_id},
                {"emp_id": recipient_id},
                {"full_name": {"$regex": f"^{re.escape(recipient_id)}$", "$options": "i"}},
                {"name": {"$regex": f"^{re.escape(recipient_id)}$", "$options": "i"}}
            ]
        })
        if not recipient:
            return False, f"Recipient employee '{recipient_id}' not found."

        actual_rid = recipient.get("employee_id") or recipient.get("emp_id")
        actor_id = actor.get("employee_id") or actor.get("emp_id")
        if actor_id == actual_rid:
            return False, "You cannot send kudos points to yourself."

        if points < 10 or points > 150:
            return False, "Kudos points must be between 10 and 150 points."

        count = db.kudos_ledger.count_documents({})
        doc = {
            "kudos_id": f"KUD-{1001 + count}",
            "sender_id": actor_id,
            "sender_name": actor.get("full_name") or actor.get("name") or actor_id,
            "recipient_id": actual_rid,
            "recipient_name": recipient.get("full_name") or recipient.get("name") or actual_rid,
            "points": points,
            "category": category or "Teamwork",
            "message": message.strip() or "Great job!",
            "created_at": _utc_now()
        }
        db.kudos_ledger.insert_one(doc)

        NotificationService.create_notification(
            recipient_id=actual_rid,
            title="Kudos Points Received! 🌟",
            message=f"{doc['sender_name']} awarded you {points} Kudos points for '{category}': {message}",
            category="KUDOS"
        )
        return True, f"Successfully awarded {points} Kudos points to {doc['recipient_name']}."

    @classmethod
    def get_support_tickets(cls, employee_id: str = None) -> List[Dict]:
        db = get_db()
        query = {"employee_id": employee_id} if employee_id else {}
        tickets = list(db.support_tickets.find(query).sort("created_at", -1))
        if not tickets and employee_id:
            # Seed sample ticket
            seed = {
                "ticket_id": f"TCK-{employee_id}-01",
                "employee_id": employee_id,
                "category": "Hardware & Peripherals",
                "subject": "Secondary 4K Monitor Display Cable Request",
                "description": "Requesting an extra USB-C to DisplayPort cable for the dual monitor workstation setup.",
                "priority": "Medium",
                "status": "Resolved",
                "resolution_notes": "Cable provided by IT Helpdesk Floor 2.",
                "created_at": _utc_now() - timedelta(days=2),
                "resolved_at": _utc_now() - timedelta(days=1)
            }
            db.support_tickets.insert_one(seed)
            tickets = [seed]
        return serialize_docs(tickets)

    @classmethod
    def create_support_ticket(cls, actor: dict, data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        subject = (data.get("subject") or "").strip()
        description = (data.get("description") or "").strip()
        category = (data.get("category") or "IT & Systems Support").strip()
        priority = (data.get("priority") or "Medium").strip()

        if not subject or not description:
            return None, "Subject and ticket description are mandatory."

        count = db.support_tickets.count_documents({})
        ticket_id = f"TCK-{1001 + count}"

        assigned_role = (data.get("assigned_role") or data.get("target_role") or "auto").lower()
        if assigned_role == "auto":
            cat_lower = (category + " " + subject).lower()
            if any(k in cat_lower for k in ["hr", "policy", "benefit", "payroll", "salary", "compensation", "leave", "welfare"]):
                assigned_role = "hr"
            elif any(k in cat_lower for k in ["project", "sprint", "task", "team", "approval", "workload", "manager"]):
                assigned_role = "manager"
            else:
                assigned_role = "admin"

        assigned_role_name = "Human Resources Desk" if assigned_role == "hr" else ("Department Manager Desk" if assigned_role == "manager" else "System & IT Administrator")

        ticket = {
            "ticket_id": ticket_id,
            "employee_id": actor["employee_id"],
            "employee_name": actor.get("full_name") or actor.get("name") or actor["employee_id"],
            "department": actor.get("department", "Engineering"),
            "category": category,
            "subject": subject,
            "description": description,
            "priority": priority,
            "assigned_role": assigned_role,
            "assigned_role_name": assigned_role_name,
            "status": "Open",
            "resolution_notes": None,
            "created_at": _utc_now()
        }
        db.support_tickets.insert_one(ticket)

        # Notify the targeted authority
        try:
            target_user = db.users.find_one({"role": assigned_role, "is_active": True})
            if target_user:
                NotificationService.create_notification(
                    title=f"New {category} Ticket: {ticket_id}",
                    message=f"Staff member {ticket['employee_name']} logged ticket '{subject}' routed to {assigned_role_name}.",
                    category="SUPPORT",
                    recipient_id=target_user["employee_id"],
                    link="/kudos-support"
                )
        except Exception:
            pass

        return serialize_doc(ticket), None

    @classmethod
    def get_expense_claims(cls, employee_id: str = None, actor: dict = None) -> List[Dict]:
        db = get_db()
        query = {"employee_id": employee_id} if employee_id else {}
        if actor:
            role = normalize_role(actor.get("role"))
            actor_id = actor.get("employee_id") or actor.get("emp_id")
            if role == Role.MANAGER:
                query = {"$or": [
                    {"assigned_manager_id": actor_id},
                    {"assigned_manager_id": {"$exists": False}, "department": actor.get("department")}
                ]}
            elif role not in (Role.HR, Role.ADMIN):
                query = {"employee_id": actor_id}
        claims = list(db.expense_claims.find(query).sort("created_at", -1))
        return serialize_docs(claims)

    @classmethod
    def submit_expense_claim(cls, actor: dict, data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        purpose = (data.get("trip_purpose") or "").strip()
        items = data.get("items") or []

        if not purpose or not items:
            return None, "Trip purpose and at least one expense item are required."

        total = 0.0
        cleaned_items = []
        for i in items:
            if not isinstance(i, dict):
                return None, "Each expense item must include a category, description, and amount."
            cat = i.get("category", "General Expense")
            desc = i.get("description", "")
            try:
                amt = float(i.get("amount", 0))
            except (TypeError, ValueError):
                return None, "Expense amounts must be valid numbers."
            if not math.isfinite(amt) or amt < 0:
                return None, "Expense amounts must be finite and cannot be negative."
            if amt <= 0:
                continue
            total += amt
            cleaned_items.append({"category": cat, "description": desc, "amount": amt})

        if total <= 0:
            return None, "Total expense claim amount must be greater than zero."

        count = db.expense_claims.count_documents({})
        claim_id = f"EXP-{1001 + count}"
        doc = {
            "claim_id": claim_id,
            "employee_id": actor["employee_id"],
            "employee_name": actor.get("full_name", ""),
            "department": actor.get("department", "Engineering"),
            "trip_purpose": purpose,
            "travel_dates": data.get("travel_dates", "Current Month"),
            "items": cleaned_items,
            "total_amount": round(total, 2),
            "currency": "INR",
            "status": "Submitted",
            "assigned_manager_id": actor.get("manager_id") or "MGR-1001",
            "created_at": _utc_now()
        }
        db.expense_claims.insert_one(doc)
        try:
            NotificationService.create_notification(
                title=f"Expense Claim Submitted: {claim_id}",
                message=f"{doc['employee_name']} submitted an expense claim of INR {doc['total_amount']:.2f} for manager review.",
                category="EXPENSE",
                recipient_id=doc["assigned_manager_id"],
                link="/dashboard/manager"
            )
        except Exception as exc:
            logger.warning("Failed to notify manager about expense claim %s: %s", claim_id, exc)
        return serialize_doc(doc), None

    @classmethod
    def get_company_policy_vault(cls) -> List[Dict]:
        db = get_db()
        policies = list(db.company_policies.find({}))
        if not policies:
            default_policies = [
                {
                    "policy_id": "POL-WFH-01",
                    "title": "Hybrid & Remote Work Architecture Policy 2026",
                    "category": "Workplace Governance",
                    "version": "v3.2",
                    "effective_date": "2026-04-01",
                    "summary": "Governs progressive WFA, MHL, and neutral-gender emergency permissions with automated manager approval routing.",
                    "content": "Official policy regarding remote work and hybrid working days.",
                    "download_url": "/api/policies/download/wfh"
                },
                {
                    "policy_id": "POL-POSH-02",
                    "title": "Prevention of Sexual Harassment (PoSH) Statutory Guidelines",
                    "category": "Statutory & Legal",
                    "version": "v4.0",
                    "effective_date": "2026-01-01",
                    "summary": "Mandatory workplace safety, Internal Committee composition, confidential reporting mechanisms, and 24h SLA guarantees.",
                    "content": "Guidelines and statutory standards under PoSH regulations.",
                    "download_url": "/api/policies/download/posh"
                },
                {
                    "policy_id": "POL-EXP-03",
                    "title": "Travel & Official Expense Reimbursement Policy",
                    "category": "Finance & Operations",
                    "version": "v2.5",
                    "effective_date": "2026-06-01",
                    "summary": "Daily subsistence allowances, travel class limits, client dinner protocol, and fast-track 5-day bank disbursement.",
                    "content": "Reimbursement procedures, limits, and submission timelines.",
                    "download_url": "/api/policies/download/expenses"
                },
                {
                    "policy_id": "POL-SEC-04",
                    "title": "Information Security, DPDP Act & Clean Desk Standards",
                    "category": "Cybersecurity & Compliance",
                    "version": "v5.1",
                    "effective_date": "2026-05-15",
                    "summary": "Mandatory 2FA authentication, endpoint encryption, restricted data movement, and privacy rights under DPDP 2023.",
                    "content": "Compliance requirements, cyber defense, and DPDP mandates.",
                    "download_url": "/api/policies/download/infosec"
                }
            ]
            for p in default_policies:
                db.company_policies.insert_one(p)
            policies = default_policies
        return serialize_docs(policies)

    @classmethod
    def create_policy(cls, actor: dict, data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        role = actor.get("role")
        if role not in (Role.HR, Role.HR_MANAGER, Role.ADMIN, Role.ORGANIZATION):
            return None, "Access Denied: Only HR or Administrators can create corporate policies."

        title = (data.get("title") or "").strip()
        if not title:
            return None, "Policy title is required."

        db = get_db()
        count = db.company_policies.count_documents({})
        policy_id = (data.get("policy_id") or f"POL-{101 + count}").strip().upper()

        doc = {
            "policy_id": policy_id,
            "title": title,
            "category": data.get("category", "Workplace Governance"),
            "version": data.get("version", "v1.0"),
            "effective_date": data.get("effective_date", datetime.now().strftime("%Y-%m-%d")),
            "summary": data.get("summary", ""),
            "content": data.get("content", ""),
            "created_by": actor["employee_id"],
            "created_at": _utc_now(),
            "updated_at": _utc_now()
        }
        db.company_policies.update_one({"policy_id": policy_id}, {"$set": doc}, upsert=True)
        return serialize_doc(doc), None

    @classmethod
    def update_policy(cls, actor: dict, policy_id: str, data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        role = actor.get("role")
        if role not in (Role.HR, Role.HR_MANAGER, Role.ADMIN, Role.ORGANIZATION):
            return None, "Access Denied: Only HR or Administrators can modify corporate policies."

        db = get_db()
        existing = db.company_policies.find_one({"policy_id": policy_id})
        if not existing:
            return None, f"Policy '{policy_id}' not found."

        update_fields = {"updated_at": _utc_now()}
        for k in ["title", "category", "version", "effective_date", "summary", "content"]:
            if k in data and data[k] is not None:
                update_fields[k] = data[k]

        db.company_policies.update_one({"policy_id": policy_id}, {"$set": update_fields})
        updated = db.company_policies.find_one({"policy_id": policy_id})
        return serialize_doc(updated), None

    @classmethod
    def delete_policy(cls, actor: dict, policy_id: str) -> Tuple[bool, Optional[str]]:
        role = actor.get("role")
        if role not in (Role.HR, Role.HR_MANAGER, Role.ADMIN, Role.ORGANIZATION):
            return False, "Access Denied: Only HR or Administrators can delete corporate policies."

        db = get_db()
        res = db.company_policies.delete_one({"policy_id": policy_id})
        if res.deleted_count == 0:
            return False, f"Policy '{policy_id}' not found."
        return True, None


# ============================================================================
# TRAVEL ALLOCATION & LOGISTICS SERVICE
# ============================================================================
class TravelAllocationService:
    """
    Corporate Travel Requisition & Logistics Allocation:
    1. Employee submits Travel Request (destination, dates, mode, budget, lodging).
    2. Manager reviews & endorses (PENDING_MANAGER -> APPROVED / REJECTED).
    3. HR / Facilities allocates tickets, PNR, hotel vouchers, and per-diem (ALLOCATED / DISBURSED).
    4. Employee can cancel their own pending request.
    5. Manager and HR can review all requests across their jurisdiction.
    """

    @classmethod
    def submit_travel_request(cls, actor: dict, data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        destination = (data.get("destination") or "").strip()
        trip_purpose = (data.get("trip_purpose") or data.get("purpose") or "").strip()
        start_date = (data.get("start_date") or data.get("departure_date") or "").strip()
        end_date = (data.get("end_date") or data.get("return_date") or "").strip()

        if not destination or not trip_purpose or not start_date or not end_date:
            return None, "Destination, trip purpose, start date, and end date are required."

        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d").date()
            ed = datetime.strptime(end_date, "%Y-%m-%d").date()
            if ed < sd:
                return None, "Trip end date cannot be earlier than start date."
        except ValueError:
            return None, "Invalid date format. Please use YYYY-MM-DD."

        db = get_db()
        count = db.travel_requests.count_documents({})
        request_id = f"TRV-{1001 + count}"
        try:
            estimated_cost = float(data.get("estimated_cost", 0.0) or 0.0)
            advance_requested = float(data.get("advance_requested") or data.get("per_diem_advance") or 0.0)
        except (TypeError, ValueError):
            return None, "Estimated cost and requested advance must be valid numbers."
        if not math.isfinite(estimated_cost) or not math.isfinite(advance_requested):
            return None, "Estimated cost and requested advance must be finite numbers."
        if estimated_cost < 0 or advance_requested < 0:
            return None, "Estimated cost and requested advance cannot be negative."

        manager_id = actor.get("manager_id")
        if not manager_id:
            manager = db.users.find_one(
                {"role": Role.MANAGER, "is_active": True},
                {"employee_id": 1, "emp_id": 1}
            )
            manager_id = (manager or {}).get("employee_id") or (manager or {}).get("emp_id")

        doc = {
            "request_id": request_id,
            "employee_id": actor["employee_id"],
            "employee_name": actor.get("full_name") or actor.get("name") or actor["employee_id"],
            "department": actor.get("department", "Engineering"),
            "destination": destination,
            "trip_purpose": trip_purpose,
            "purpose": trip_purpose,
            "start_date": start_date,
            "end_date": end_date,
            "departure_date": start_date,
            "return_date": end_date,
            "travel_mode": data.get("travel_mode", "Flight"),
            "estimated_cost": estimated_cost,
            "hotel_required": bool(data.get("hotel_required", True)),
            "per_diem_advance": advance_requested,
            "advance_requested": advance_requested,
            "status": "PENDING_MANAGER",
            "assigned_manager_id": manager_id,
            "manager_decision": None,
            "manager_remarks": None,
            "allocation_details": None,
            "created_at": _utc_now(),
            "updated_at": _utc_now()
        }
        db.travel_requests.insert_one(doc)

        # Notify Manager
        if manager_id:
            try:
                NotificationService.create_notification(
                    title=f"New Travel Requisition: {actor.get('name', actor['employee_id'])}",
                    message=f"Travel request {request_id} to {destination} submitted for manager review.",
                    category="TRAVEL",
                    recipient_id=manager_id,
                    link="/facilities?tab=travel"
                )
            except Exception as exc:
                logger.warning("Failed to notify manager about travel request %s: %s", request_id, exc)

        return serialize_doc(doc), None

    @classmethod
    def get_travel_requests(cls, actor: dict, status_filter: str = "ALL") -> List[Dict]:
        db = get_db()
        role = normalize_role(actor.get("role"))
        query = {}

        if role == Role.EMPLOYEE:
            query["employee_id"] = actor["employee_id"]
        elif role == Role.TL:
            query["employee_id"] = actor["employee_id"]
        elif role == Role.MANAGER:
            manager_id = actor.get("employee_id") or actor.get("emp_id")
            query["$or"] = [
                {"assigned_manager_id": manager_id},
                {"assigned_manager_id": {"$exists": False}, "department": actor.get("department")}
            ]

        if status_filter and status_filter.upper() != "ALL":
            query["status"] = status_filter.upper()

        records = list(db.travel_requests.find(query).sort("created_at", -1))
        return serialize_docs(records)

    @classmethod
    def review_travel_request(cls, reviewer: dict, request_id: str, decision: str, remarks: str = "") -> Tuple[Optional[Dict], Optional[str]]:
        decision = decision.upper().strip()
        if decision in ("ENDORSED", "APPROVE"):
            decision = "APPROVED"
        elif decision in ("REJECT",):
            decision = "REJECTED"

        if decision not in ("APPROVED", "REJECTED"):
            return None, "Invalid decision. Must be 'APPROVED' or 'REJECTED'."

        role = normalize_role(reviewer.get("role"))
        if role not in (Role.MANAGER, Role.ADMIN):
            return None, "Access Denied: Only the assigned Manager or an Administrator can approve/reject travel requisitions."

        db = get_db()
        req = db.travel_requests.find_one({"request_id": request_id})
        if not req:
            return None, f"Travel request '{request_id}' not found."

        reviewer_id = reviewer.get("employee_id") or reviewer.get("emp_id")
        if role == Role.MANAGER and req.get("assigned_manager_id") != reviewer_id and not (
            not req.get("assigned_manager_id") and req.get("department") == reviewer.get("department")
        ):
            return None, "Access denied: this travel request is assigned to another manager."
        pending_statuses = ("PENDING_MANAGER", "Pending Endorsement", "PENDING ENDORSEMENT")
        if req.get("status") not in pending_statuses:
            return None, f"Request is already in '{req.get('status')}' status."

        next_status = "APPROVED" if decision == "APPROVED" else "REJECTED"
        update_doc = {
            "status": next_status,
            "reviewed_by_id": reviewer["employee_id"],
            "reviewed_by_name": reviewer.get("full_name") or reviewer.get("name") or reviewer["employee_id"],
            "reviewed_by_role": role,
            "manager_remarks": (remarks or "").strip(),
            "reviewed_at": _utc_now(),
            "updated_at": _utc_now()
        }
        result = db.travel_requests.update_one(
            {"request_id": request_id, "status": {"$in": pending_statuses}},
            {"$set": update_doc}
        )
        if result.matched_count != 1:
            return None, "Travel request was already reviewed. Refresh and try again."

        try:
            NotificationService.create_notification(
                title=f"Travel Request {next_status}",
                message=f"Your travel request {request_id} to {req.get('destination')} has been {next_status.lower()}.",
                category="TRAVEL",
                recipient_id=req["employee_id"],
                link="/facilities?tab=travel"
            )
        except Exception as exc:
            logger.warning("Failed to notify employee about travel request %s: %s", request_id, exc)

        updated = db.travel_requests.find_one({"request_id": request_id})
        return serialize_doc(updated), None

    @classmethod
    def allocate_travel(cls, actor: dict, request_id: str, allocation_data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        role = normalize_role(actor.get("role"))
        if role not in (Role.HR, Role.ADMIN):
            return None, "Access Denied: Only HR or Facilities Administration can allocate travel tickets."

        db = get_db()
        req = db.travel_requests.find_one({"request_id": request_id})
        if not req:
            return None, f"Travel request '{request_id}' not found."
        if str(req.get("status") or "").upper() not in ("APPROVED", "ENDORSED"):
            return None, "Travel logistics can only be allocated after Manager approval."

        pnr = (allocation_data.get("pnr_or_ticket") or "CONFIRMED-TKT").strip()
        hotel_details = (allocation_data.get("hotel_details") or "Arranged by Corporate Desk").strip()
        try:
            advance_paid = float(allocation_data.get("advance_paid", 0.0) or 0.0)
        except (TypeError, ValueError):
            return None, "Travel advance paid must be a valid number."
        if not math.isfinite(advance_paid) or advance_paid < 0:
            return None, "Travel advance paid must be finite and cannot be negative."

        allocation_doc = {
            "pnr_or_ticket": pnr,
            "hotel_details": hotel_details,
            "advance_paid": advance_paid,
            "allocated_by": actor["employee_id"],
            "allocated_at": _utc_now()
        }

        db.travel_requests.update_one(
            {"request_id": request_id},
            {
                "$set": {
                    "status": "ALLOCATED",
                    "allocation_details": allocation_doc,
                    "updated_at": _utc_now()
                }
            }
        )

        try:
            NotificationService.create_notification(
                title="Travel Tickets & Logistics Allocated",
                message=f"Logistics allocated for trip {request_id}. PNR/Ticket: {pnr}.",
                category="TRAVEL",
                recipient_id=req["employee_id"],
                link="/facilities?tab=travel"
            )
        except Exception:
            pass

        updated = db.travel_requests.find_one({"request_id": request_id})
        return serialize_doc(updated), None

    @classmethod
    def cancel_travel_request(cls, actor: dict, request_id: str) -> Tuple[bool, Optional[str]]:
        db = get_db()
        req = db.travel_requests.find_one({"request_id": request_id})
        if not req:
            return False, f"Travel request '{request_id}' not found."

        emp_id = actor["employee_id"]
        role = actor.get("role")

        if req.get("employee_id") != emp_id and role not in (Role.HR, Role.HR_MANAGER, Role.ADMIN, Role.ORGANIZATION):
            return False, "Access Denied: You cannot cancel another employee's travel request."

        if req.get("status") in ("ALLOCATED", "COMPLETED") and role not in (Role.HR, Role.HR_MANAGER, Role.ADMIN, Role.ORGANIZATION):
            return False, "Cannot cancel a travel request that has already been ticketed and allocated. Contact Facilities."

        if role in (Role.HR, Role.HR_MANAGER, Role.ADMIN, Role.ORGANIZATION):
            db.travel_requests.delete_one({"request_id": request_id})
            return True, None

        db.travel_requests.update_one(
            {"request_id": request_id},
            {
                "$set": {
                    "status": "CANCELLED",
                    "cancelled_by": emp_id,
                    "cancelled_at": _utc_now(),
                    "updated_at": _utc_now()
                }
            }
        )
        return True, None


# ============================================================================
# 6. EXIT & SEPARATION MANAGEMENT SERVICE
# ============================================================================
class SeparationService:
    @classmethod
    def get_tenure_and_status(cls, employee_id: str) -> Dict[str, Any]:
        db = get_db()
        user = db.users.find_one({"employee_id": employee_id})
        resignation = db.resignations.find_one({"employee_id": employee_id})

        # Calculate exact tenure
        doj_str = (user.get("date_of_joining") or "2024-06-01") if user else "2024-06-01"
        try:
            doj = datetime.strptime(doj_str, "%Y-%m-%d").date()
        except ValueError:
            doj = datetime(2024, 6, 1).date()

        today = datetime.now().date()
        total_days = max(1, (today - doj).days)
        years = total_days // 365
        rem_days = total_days % 365
        months = rem_days // 30
        days = rem_days % 30

        tenure_display = f"{years} Year(s), {months} Month(s), {days} Day(s)"

        if resignation:
            res_doc = serialize_doc(resignation)
            res_doc["proposed_lwd"] = res_doc.get("proposed_lwd") or res_doc.get("requested_lwd")
            res_doc["handover_notes"] = res_doc.get("handover_notes") or res_doc.get("comments")
            if not res_doc.get("submitted_at") and res_doc.get("created_at"):
                c_at = res_doc.get("created_at")
                res_doc["submitted_at"] = c_at.strftime("%d %b %Y") if hasattr(c_at, "strftime") else str(c_at)[:10]
            clearances = res_doc.get("clearances") or {}
            c_mgr = bool(res_doc.get("manager_approval") or clearances.get("project_handover_signed"))
            c_it = bool(res_doc.get("it_clearance") or clearances.get("it_hardware_returned"))
            c_fin = bool(res_doc.get("finance_clearance") or clearances.get("finance_settlement_cleared"))
            c_hr = bool(res_doc.get("hr_clearance") or clearances.get("hr_exit_interview_completed"))
            current_status = res_doc.get("status", "Submitted")
            if c_mgr and c_it and c_fin and c_hr:
                current_status = "Cleared & Ready for FnF"
            elif c_mgr:
                current_status = "In Notice"
        else:
            res_doc = None
            c_mgr = c_it = c_fin = c_hr = False
            current_status = "Active"

        return {
            "employee_id": employee_id,
            "date_of_joining": doj_str,
            "tenure_display": tenure_display,
            "tenure": {
                "years": years,
                "months": months,
                "days": days,
                "joining_date": doj_str
            },
            "total_days_served": total_days,
            "notice_period_standard_days": 60,
            "resignation": res_doc,
            "has_active_resignation": bool(res_doc and res_doc.get("status") not in ("Withdrawn", "Rejected")),
            "clearance_stages": {
                "manager": c_mgr,
                "it": c_it,
                "finance": c_fin,
                "hr": c_hr
            },
            "status": current_status
        }

    @classmethod
    def initiate_resignation(cls, actor: dict, data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        emp_id = actor["employee_id"]
        existing = db.resignations.find_one({
            "employee_id": emp_id,
            "status": {"$in": ["Submitted", "Manager Approved", "HR Verification", "In Notice", "Under Clearance"]}
        })
        if existing:
            return None, "You already have an active separation request under review."

        reason = (data.get("reason") or "").strip()
        comments = (data.get("comments") or data.get("handover_notes") or "").strip()
        requested_lwd = (data.get("requested_lwd") or data.get("proposed_lwd") or "").strip()

        if not reason:
            return None, "Primary reason for separation is required."
        if not comments:
            comments = "Transition and knowledge transfer plan initiated."
        if not requested_lwd:
            requested_lwd = (datetime.now().date() + timedelta(days=60)).strftime("%Y-%m-%d")

        count = db.resignations.count_documents({})
        res_id = f"RES-{1001 + count}"
        now_dt = _utc_now()

        doc = {
            "resignation_id": res_id,
            "employee_id": emp_id,
            "employee_name": actor.get("full_name") or actor.get("name") or emp_id,
            "department": actor.get("department", "Engineering"),
            "reason": reason,
            "comments": comments,
            "handover_notes": comments,
            "requested_lwd": requested_lwd,
            "proposed_lwd": requested_lwd,
            "status": "Submitted",
            "submitted_at": datetime.now().strftime("%d %b %Y"),
            "manager_approval": False,
            "it_clearance": False,
            "finance_clearance": False,
            "hr_clearance": False,
            "clearances": {
                "it_hardware_returned": False,
                "project_handover_signed": False,
                "finance_settlement_cleared": False,
                "hr_exit_interview_completed": False
            },
            "created_at": now_dt,
            "updated_at": now_dt
        }
        db.resignations.insert_one(doc)

        # Notify Reporting Manager & HR
        try:
            rep_mgr = actor.get("reporting_manager_id") or "MGR-001"
            NotificationService.send_notification(
                user_id=rep_mgr,
                title=f"Resignation Notice: {actor.get('full_name', emp_id)}",
                message=f"{actor.get('full_name', emp_id)} ({actor.get('department')}) has submitted formal resignation with proposed LWD {requested_lwd}.",
                category="SEPARATION",
                link="/exit-tenure"
            )
            NotificationService.send_notification(
                user_id="HR-001",
                title=f"Separation Case Initiated: {actor.get('full_name', emp_id)}",
                message=f"New exit request initiated by {actor.get('full_name', emp_id)}. Reason: {reason}.",
                category="SEPARATION",
                link="/exit-tenure"
            )
        except Exception as e:
            logger.warning(f"Failed to dispatch resignation notifications: {e}")

        AuditService.log_action(
            actor=actor,
            action="INITIATE_RESIGNATION",
            target_type="resignation",
            target_id=res_id,
            details=f"Initiated voluntary resignation. Reason: {reason}"
        )
        return serialize_doc(doc), None

    @classmethod
    def approve_clearance_stage(cls, actor: dict, resignation_id: str, stage: str, remarks: str = "") -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        res = db.resignations.find_one({"resignation_id": resignation_id})
        if not res and ObjectId.is_valid(resignation_id):
            res = db.resignations.find_one({"_id": ObjectId(resignation_id)})
        if not res:
            return None, f"Resignation docket '{resignation_id}' not found."

        stage_norm = stage.strip().lower()
        actor_role = actor.get("role", "").lower()
        now_dt = _utc_now()
        now_str = datetime.now().strftime("%d %b %Y %I:%M %p")
        reviewer_name = actor.get("full_name") or actor.get("name") or actor["employee_id"]

        update_fields: Dict[str, Any] = {"updated_at": now_dt}

        if stage_norm in ("manager", "project_handover", "handover"):
            if actor_role not in (Role.MANAGER, Role.TEAM_LEAD, Role.TL, Role.ADMIN, "manager", "team_lead", "tl", "admin"):
                return None, "Access Denied: Only Reporting Manager or Team Lead can sign off on Project Handover clearance."
            update_fields["manager_approval"] = True
            update_fields["clearances.project_handover_signed"] = True
            update_fields["manager_cleared_by"] = reviewer_name
            update_fields["manager_cleared_at"] = now_str
            update_fields["manager_remarks"] = remarks or "Project handover confirmed."
            if res.get("status") == "Submitted":
                update_fields["status"] = "Manager Approved"

        elif stage_norm in ("it", "it_infrastructure", "hardware"):
            if actor_role not in (Role.HR, Role.ADMIN, "it", "it_admin", "admin", "hr"):
                return None, "Access Denied: Only IT Administrator or HR can sign off on IT hardware & asset clearance."
            update_fields["it_clearance"] = True
            update_fields["clearances.it_hardware_returned"] = True
            update_fields["it_cleared_by"] = reviewer_name
            update_fields["it_cleared_at"] = now_str
            update_fields["it_remarks"] = remarks or "Hardware and access credentials surrendered."

        elif stage_norm in ("finance", "finance_accounts", "accounts"):
            if actor_role not in (Role.HR, Role.ADMIN, "finance", "accounts", "admin", "hr"):
                return None, "Access Denied: Only Finance & Accounts or HR can sign off on Finance settlement."
            update_fields["finance_clearance"] = True
            update_fields["clearances.finance_settlement_cleared"] = True
            update_fields["finance_cleared_by"] = reviewer_name
            update_fields["finance_cleared_at"] = now_str
            update_fields["finance_remarks"] = remarks or "No dues or pending salary advances."

        elif stage_norm in ("hr", "hr_exit", "exit_interview"):
            if actor_role not in (Role.HR, Role.ADMIN, "hr", "admin", "hr_manager"):
                return None, "Access Denied: Only HR Administration can sign off on Exit Interview & Relieving status."
            update_fields["hr_clearance"] = True
            update_fields["clearances.hr_exit_interview_completed"] = True
            update_fields["hr_cleared_by"] = reviewer_name
            update_fields["hr_cleared_at"] = now_str
            update_fields["hr_remarks"] = remarks or "Formal exit interview completed and relieving docket authorized."

        else:
            return None, f"Invalid clearance stage '{stage}'. Must be one of: manager, it, finance, hr."

        db.resignations.update_one({"_id": res["_id"]}, {"$set": update_fields})
        updated = db.resignations.find_one({"_id": res["_id"]})

        c = updated.get("clearances", {})
        if (c.get("project_handover_signed") or updated.get("manager_approval")) and \
           (c.get("it_hardware_returned") or updated.get("it_clearance")) and \
           (c.get("finance_settlement_cleared") or updated.get("finance_clearance")) and \
           (c.get("hr_exit_interview_completed") or updated.get("hr_clearance")):
            db.resignations.update_one({"_id": res["_id"]}, {"$set": {"status": "Cleared & Ready for FnF"}})
            updated["status"] = "Cleared & Ready for FnF"

        AuditService.log_action(
            actor=actor,
            action="APPROVE_SEPARATION_CLEARANCE",
            target_type="resignation",
            target_id=res.get("resignation_id"),
            details=f"Cleared stage '{stage_norm}' for employee {res.get('employee_id')}"
        )
        return serialize_doc(updated), None

    @classmethod
    def get_all_resignations(cls, actor: dict) -> List[Dict]:
        db = get_db()
        # Clean any legacy dummy sample resignations if present
        db.resignations.delete_many({"resignation_id": "RES-1001"})

        role = actor.get("role", "").lower()
        if role in (Role.ADMIN, Role.HR, "admin", "hr", "hr_manager", "organization"):
            records = list(db.resignations.find({}).sort("created_at", -1))
        elif role in (Role.MANAGER, "manager"):
            dept = actor.get("department")
            records = list(db.resignations.find({"$or": [{"department": dept}, {"reporting_manager_id": actor["employee_id"]}]}).sort("created_at", -1))
        elif role in (Role.TEAM_LEAD, Role.TL, "tl", "team_lead", "trainer"):
            team_id = actor.get("team_id")
            dept = actor.get("department")
            squad_ids = [u["employee_id"] for u in db.users.find({"team_id": team_id})] if team_id else []
            or_clauses = [{"employee_id": {"$in": squad_ids}}, {"assigned_tl": actor["employee_id"]}]
            if dept:
                or_clauses.append({"department": dept})
            records = list(db.resignations.find({"$or": or_clauses}).sort("created_at", -1))
        else:
            records = list(db.resignations.find({"employee_id": actor["employee_id"]}))
        return serialize_docs(records)


# ============================================================================
# 7. RECRUITMENT & TALENT MANAGEMENT (TL, MANAGER, HR/ADMIN)
# ============================================================================
class RecruitmentTalentService:
    @classmethod
    def get_candidate_scorecards(cls, interviewer_id: str = None) -> List[Dict]:
        db = get_db()
        query = {"interviewer_id": interviewer_id} if interviewer_id else {}
        cards = list(db.interview_scorecards.find(query).sort("created_at", -1))
        if not cards:
            seed = [
                {
                    "scorecard_id": "SCR-101",
                    "candidate_name": "Aditya Varma",
                    "candidate_email": "aditya.v@gmail.com",
                    "position": "Senior Backend Architect (Python/Distributed Systems)",
                    "round_name": "Round 2: System Design & Resilience",
                    "interviewer_id": "AS-1019",
                    "interviewer_name": "Deepak S J",
                    "technical_rating": 4.8,
                    "problem_solving_rating": 4.5,
                    "culture_fit_rating": 5.0,
                    "overall_score": 4.8,
                    "recommendation": "Strong Hire",
                    "feedback": "Deep expertise in MongoDB sharding, microservices architecture, and clean Flask modular design.",
                    "created_at": _utc_now() - timedelta(days=3)
                },
                {
                    "scorecard_id": "SCR-102",
                    "candidate_name": "Meera Krishnan",
                    "candidate_email": "meera.k@gmail.com",
                    "position": "Frontend UI/UX Specialist (Bootstrap 5 & Micro-interactions)",
                    "round_name": "Round 1: Practical Frontend Coding",
                    "interviewer_id": "TL-1001",
                    "interviewer_name": "Kavita Nair",
                    "technical_rating": 4.2,
                    "problem_solving_rating": 4.0,
                    "culture_fit_rating": 4.5,
                    "overall_score": 4.2,
                    "recommendation": "Hire",
                    "feedback": "Strong command of accessible UI tokens, CSS responsive grids, and clean DOM manipulation.",
                    "created_at": _utc_now() - timedelta(days=1)
                }
            ]
            db.interview_scorecards.insert_many(seed)
            cards = seed
        return serialize_docs(cards)

    @classmethod
    def submit_scorecard(cls, actor: dict, data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        c_name = (data.get("candidate_name") or "").strip()
        pos = (data.get("position") or "").strip()
        round_name = (data.get("round_name") or "Technical Evaluation").strip()
        rec = (data.get("recommendation") or "Hire").strip()
        feedback = (data.get("feedback") or "").strip()

        if not c_name or not pos or not feedback:
            return None, "Candidate name, target position, and interview feedback are mandatory."

        tech = float(data.get("technical_rating", 4.0))
        prob = float(data.get("problem_solving_rating", 4.0))
        cult = float(data.get("culture_fit_rating", 4.0))
        overall = round((tech + prob + cult) / 3.0, 1)

        count = db.interview_scorecards.count_documents({})
        sc_id = f"SCR-{1001 + count}"
        doc = {
            "scorecard_id": sc_id,
            "candidate_name": c_name,
            "candidate_email": (data.get("candidate_email") or "").strip(),
            "position": pos,
            "round_name": round_name,
            "interviewer_id": actor["employee_id"],
            "interviewer_name": actor.get("full_name", ""),
            "technical_rating": tech,
            "problem_solving_rating": prob,
            "culture_fit_rating": cult,
            "overall_score": overall,
            "recommendation": rec,
            "feedback": feedback,
            "created_at": _utc_now()
        }
        db.interview_scorecards.insert_one(doc)
        return serialize_doc(doc), None

    @classmethod
    def get_ats_pipeline(cls) -> Dict[str, Any]:
        db = get_db()
        candidates = list(db.ats_candidates.find({}).sort("match_score", -1))
        if not candidates:
            seed = [
                {"candidate_id": "CAN-01", "name": "Aditya Varma", "role": "Senior Backend Architect", "experience_years": 7.5, "match_score": 94, "stage": "Offer Extended", "skills": ["Python", "Flask", "MongoDB", "Distributed Systems", "Docker"]},
                {"candidate_id": "CAN-02", "name": "Meera Krishnan", "role": "Frontend UI/UX Specialist", "experience_years": 4.5, "match_score": 89, "stage": "Technical Interview", "skills": ["Bootstrap 5", "JavaScript", "HTML5", "CSS3", "Figma"]},
                {"candidate_id": "CAN-03", "name": "Rohan Deshmukh", "role": "DevOps & Cloud Engineer", "experience_years": 5.0, "match_score": 85, "stage": "Screening", "skills": ["Kubernetes", "AWS", "Terraform", "CI/CD", "Linux"]},
                {"candidate_id": "CAN-04", "name": "Pooja Hegde", "role": "Quality Assurance Automation Lead", "experience_years": 6.0, "match_score": 78, "stage": "Applied", "skills": ["Pytest", "Selenium", "Playwright", "API Testing"]}
            ]
            db.ats_candidates.insert_many(seed)
            candidates = seed

        mrf_reqs = list(db.mrf_requisitions.find({}).sort("created_at", -1))
        if not mrf_reqs:
            seed_mrf = [
                {"mrf_id": "MRF-2026-01", "department": "AI & Engineering", "title": "Staff Cloud Architect", "headcount": 2, "budget_ctc": "₹28L – ₹35L", "justification": "Scale multi-tenant HRMS cluster & real-time telemetry", "status": "Approved", "initiator": "Vikramaditya Roy", "created_at": _utc_now()},
                {"mrf_id": "MRF-2026-02", "department": "Product & Design", "title": "Lead UI Systems Designer", "headcount": 1, "budget_ctc": "₹18L – ₹24L", "justification": "Design token standardization across web and mobile", "status": "Pending HR", "initiator": "Kavita Nair", "created_at": _utc_now()}
            ]
            db.mrf_requisitions.insert_many(seed_mrf)
            mrf_reqs = seed_mrf

        return {
            "candidates": serialize_docs(candidates),
            "mrf_requisitions": serialize_docs(mrf_reqs),
            "total_open_requisitions": sum(m.get("headcount", 1) for m in mrf_reqs if m.get("status") == "Approved")
        }

    @classmethod
    def extract_text_from_file(cls, file_storage, filename: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extracts plain text content from uploaded resume documents:
        - PDF: pypdf.PdfReader
        - DOCX: docx.Document
        - TXT / Markdown: UTF-8 / latin-1 decoding
        Returns (text, error).
        """
        if not file_storage or not filename:
            return None, "No resume file provided for upload."

        fn_lower = filename.lower()
        try:
            import io
            file_bytes = file_storage.read()
            if not file_bytes:
                return None, "Uploaded resume file is empty (0 bytes)."

            if fn_lower.endswith(".pdf"):
                try:
                    import pypdf
                    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                    extracted = []
                    for page in reader.pages:
                        t = page.extract_text()
                        if t:
                            extracted.append(t)
                    text = "\n".join(extracted).strip()
                    if not text:
                        return None, "Could not extract readable text from PDF (it may contain scanned image pages without OCR or have security protection)."
                    return text, None
                except Exception as e:
                    return None, f"PDF extraction failed: {str(e)}"

            elif fn_lower.endswith(".docx"):
                try:
                    import docx
                    doc = docx.Document(io.BytesIO(file_bytes))
                    paras = [p.text for p in doc.paragraphs if p.text.strip()]
                    for table in doc.tables:
                        for row in table.rows:
                            for cell in row.cells:
                                if cell.text.strip():
                                    paras.append(cell.text.strip())
                    text = "\n".join(paras).strip()
                    if not text:
                        return None, "Could not extract text from DOCX file."
                    return text, None
                except Exception as e:
                    return None, f"DOCX extraction failed: {str(e)}"

            elif fn_lower.endswith((".txt", ".md", ".rtf", ".csv")):
                try:
                    text = file_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    text = file_bytes.decode("latin-1", errors="ignore")
                return text.strip(), None
            else:
                try:
                    text = file_bytes.decode("utf-8")
                    return text.strip(), None
                except Exception:
                    return None, f"Unsupported file format '{filename}'. Please upload a PDF, DOCX, or TXT file."
        except Exception as e:
            return None, f"Failed to process uploaded file: {str(e)}"

    @classmethod
    def scan_resume(cls, resume_text: str, target_role: str, required_skills: list = None) -> Dict[str, Any]:
        """
        Parses resume text against target role requirements, extracts matched skills,
        computes an automated ATS match score %, and returns comprehensive match telemetry.
        """
        text_lower = (resume_text or "").lower()
        if not required_skills:
            role_lower = (target_role or "").lower()
            if "backend" in role_lower or "python" in role_lower:
                required_skills = ["Python", "Flask", "Django", "MongoDB", "PostgreSQL", "REST APIs", "Docker", "Git", "Microservices", "Redis"]
            elif "frontend" in role_lower or "ui" in role_lower or "react" in role_lower:
                required_skills = ["JavaScript", "TypeScript", "React", "Bootstrap 5", "HTML5", "CSS3", "Figma", "REST APIs", "Responsive Design"]
            elif "devops" in role_lower or "cloud" in role_lower:
                required_skills = ["Kubernetes", "Docker", "AWS", "CI/CD", "Terraform", "Linux", "Python", "Monitoring", "Bash"]
            elif "qa" in role_lower or "test" in role_lower:
                required_skills = ["Pytest", "Selenium", "Playwright", "API Testing", "Postman", "CI/CD", "Python", "Bug Tracking"]
            else:
                required_skills = ["Python", "Flask", "MongoDB", "Bootstrap 5", "REST APIs", "Git", "Problem Solving", "Agile"]

        matched_skills = []
        missing_skills = []
        for skill in required_skills:
            s_clean = skill.lower().replace(" ", "")
            if skill.lower() in text_lower or s_clean in text_lower.replace(" ", ""):
                matched_skills.append(skill)
            else:
                missing_skills.append(skill)

        total_req = max(1, len(required_skills))
        base_ratio = len(matched_skills) / total_req
        match_score = min(98, max(38, int(round(base_ratio * 100))))

        if match_score >= 85:
            fit_tier = "High Match (Recommended for Technical Round)"
            fit_badge = "success"
        elif match_score >= 65:
            fit_tier = "Moderate Match (Recommended for Screening Round)"
            fit_badge = "warning"
        else:
            fit_tier = "Low Match (Skill Deficiencies Identified)"
            fit_badge = "danger"

        # Detect experience years if mentioned
        exp_years = 3.5
        import re
        exp_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:\+|\s+)?(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)', text_lower)
        if exp_match:
            try:
                exp_years = float(exp_match.group(1))
            except Exception:
                pass

        return {
            "target_role": target_role,
            "match_score": match_score,
            "fit_tier": fit_tier,
            "fit_badge": fit_badge,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "total_required": len(required_skills),
            "total_matched": len(matched_skills),
            "detected_experience_years": exp_years
        }



# ============================================================================
# 8. SECURE DOCUMENT VIEWER & PII REDACTION (HR & ADMIN)
# ============================================================================
class SecureDocumentViewerService:
    @classmethod
    def get_employee_secure_docket(cls, target_employee_id: str, actor: dict = None) -> Dict[str, Any]:
        if actor is not None and normalize_role(actor.get("role")) not in (Role.HR, Role.ADMIN):
            return {"error": "Unauthorized: Only HR and Administrators can access secure employee dockets.", "status_code": 403}
        db = get_db()
        emp = db.users.find_one({"$or": [{"employee_id": target_employee_id}, {"emp_id": target_employee_id}]})
        if not emp:
            return {"error": f"Employee '{target_employee_id}' not found."}

        # Redact Aadhaar & Bank Accounts for strict DPDP 2023 compliance
        raw_aadhaar = str(emp.get("aadhaar_number") or "987654321234")
        masked_aadhaar = f"XXXX-XXXX-{raw_aadhaar[-4:]}"

        raw_pan = str(emp.get("pan_number") or "ABCDE1234F")
        masked_pan = f"{raw_pan[:2]}XXX{raw_pan[-2:]}"

        raw_bank = str(emp.get("bank_account_number") or "918237465012")
        masked_bank = f"XXXXXXXX{raw_bank[-4:]}"

        docket_records = [
            {"doc_type": "PAN Card (Identity Verification)", "doc_number": masked_pan, "verification_status": "Verified by NSDL", "verified_date": "2024-06-05", "preview_type": "pdf", "file_name": f"PAN_{target_employee_id}.pdf"},
            {"doc_type": "Aadhaar Card (UIDAI Redacted)", "doc_number": masked_aadhaar, "verification_status": "Masked e-Aadhaar Verified", "verified_date": "2024-06-05", "preview_type": "pdf", "file_name": f"Aadhaar_Redacted_{target_employee_id}.pdf"},
            {"doc_type": "Bank Passbook / Cancelled Cheque", "doc_number": masked_bank, "verification_status": "Penny Drop Bank Verified", "verified_date": "2024-06-06", "preview_type": "image", "file_name": f"Cancelled_Cheque_{target_employee_id}.png"},
            {"doc_type": "Degree / Educational Credentials", "doc_number": "B.Tech / MCA Verified", "verification_status": "Background Checked (Green)", "verified_date": "2024-06-10", "preview_type": "pdf", "file_name": f"Degree_Cert_{target_employee_id}.pdf"}
        ]

        return {
            "employee_id": target_employee_id,
            "full_name": emp.get("full_name", ""),
            "department": emp.get("department", ""),
            "role": emp.get("role", ""),
            "docket_records": docket_records
        }

    @classmethod
    def get_secure_document_preview(cls, target_employee_id: str, doc_query: str, actor: dict = None) -> Dict[str, Any]:
        docket = cls.get_employee_secure_docket(target_employee_id, actor=actor)
        if "error" in docket:
            return docket
        emp_name = docket.get("full_name", target_employee_id)
        records = docket.get("docket_records", [])

        # Match specific doc or default to first
        matched = records[0] if records else {}
        if doc_query:
            dq = doc_query.lower()
            for r in records:
                if dq in r.get("doc_type", "").lower() or dq in r.get("file_name", "").lower():
                    matched = r
                    break

        preview_html = f"""
        <div class="secure-doc-preview-container border rounded-3 p-4 bg-white shadow-sm position-relative overflow-hidden" style="min-height: 280px;">
            <div class="position-absolute top-50 start-50 translate-middle text-muted opacity-10 fw-bold font-mono" style="font-size: 1.8rem; transform: translate(-50%, -50%) rotate(-25deg); pointer-events: none; white-space: nowrap;">
                CONFIDENTIAL • AI SAMRAT HR AUDIT • {datetime.now().strftime('%Y-%m-%d')}
            </div>
            <div class="d-flex justify-content-between align-items-center mb-3">
                <span class="badge bg-primary-subtle text-primary border border-primary-subtle font-mono">{matched.get('verification_status')}</span>
                <span class="badge bg-light text-dark border font-mono">Verified: {matched.get('verified_date')}</span>
            </div>
            <div class="text-center my-4 py-2">
                <i class="bi bi-file-earmark-lock2 text-primary display-4"></i>
                <h5 class="fw-bold mt-3 mb-1 text-dark">{matched.get('doc_type')}</h5>
                <div class="fs-4 font-mono fw-bold text-dark my-2 tracking-wider">{matched.get('doc_number')}</div>
                <div class="text-muted small">Employee: <span class="fw-semibold text-dark">{emp_name}</span> ({target_employee_id})</div>
            </div>
            <div class="border-top pt-3 d-flex justify-content-between align-items-center">
                <small class="text-success"><i class="bi bi-shield-fill-check me-1"></i>DPDP Act 2023 Redacted &amp; Protected</small>
                <span class="badge bg-dark font-mono">{matched.get('file_name')}</span>
            </div>
        </div>
        """
        return {
            "success": True,
            "employee_id": target_employee_id,
            "full_name": emp_name,
            "record": matched,
            "preview_html": preview_html
        }



# ============================================================================
# 9. ENTERPRISE PAYROLL GENERATION (HR & ADMIN)
# ============================================================================
class EnterprisePayrollService:
    @classmethod
    def get_payroll_overview(cls) -> Dict[str, Any]:
        db = get_db()
        now = datetime.now()
        current_cycle = f"{now.strftime('%B %Y')}"

        total_employees = db.users.count_documents({"is_active": True})
        processed_records = list(db.payroll_records.find({"cycle": current_cycle}))

        gross = sum(r.get("gross", 0) for r in processed_records)
        deductions = sum(r.get("deductions", 0) for r in processed_records)
        net = gross - deductions

        return {
            "cycle": current_cycle,
            "total_eligible_employees": total_employees,
            "processed_count": len(processed_records),
            "status": "Ready for Processing" if not processed_records else "Completed",
            "total_gross_outlay": f"₹ {gross:,.2f}" if processed_records else "₹ 0.00",
            "total_statutory_deductions": f"₹ {deductions:,.2f}" if processed_records else "₹ 0.00",
            "net_disbursement": f"₹ {net:,.2f}" if processed_records else "₹ 0.00",
            "statutory_breakdown": {
                "provident_fund_pf": "12% Employee + 12% Employer Match",
                "employee_state_insurance_esi": "0.75% / 3.25% Threshold",
                "professional_tax_pt": "₹200 Standard (Karnataka)",
                "tax_deducted_at_source_tds": "Regime Option Applied"
            }
        }


# ============================================================================
# 10. ENTERPRISE OFFICIAL MAILBOX & STATUTORY NOTICES (WORKDAY STANDARD)
# ============================================================================
class EnterpriseMailboxService:
    """
    Manages dedicated official communications: Appointment letters, payslip
    notifications, statutory directives, and executive memoranda.
    Provides complete separation from project team chat.
    """
    CATEGORIES = {
        "all": "All Official Mail",
        "letters": "Letters & Contracts",
        "payslips": "Statutory & Payslips",
        "memos": "Administrative Memos",
        "alerts": "Approval & Compliance Alerts"
    }

    @classmethod
    def get_user_mailbox(cls, user: dict, folder: str = "all", search: str = None) -> Dict[str, Any]:
        db = get_db()
        emp_id = user["employee_id"]
        role = user.get("role")

        query = {
            "$and": [
                {
                    "$or": [
                        {"recipient_id": emp_id},
                        {"recipient_group": "ALL_EMPLOYEES"},
                        {"recipient_group": role.upper() if role else "EMPLOYEE"},
                        {"sender_id": emp_id}
                    ]
                },
                {"deleted_for": {"$ne": emp_id}},
                {"is_deleted": {"$ne": True}}
            ]
        }
        if folder == "letters":
            query["$and"].append({"category": "OFFICIAL_LETTER"})
        elif folder == "payslips":
            query["$and"].append({"category": "PAYSLIP_STATUTORY"})
        elif folder == "memos":
            query["$and"].append({"category": "ADMIN_MEMO"})
        elif folder == "alerts":
            query["$and"].append({"category": {"$in": ["APPROVAL_ALERT", "COMPLIANCE_ALERT"]}})
        elif folder == "sent":
            query["$and"].append({"sender_id": emp_id})

        mails = list(db.official_mailbox.find(query).sort("created_at", -1))
        if not mails and folder == "all":
            # Seed foundational corporate letters for this user
            seed = [
                {
                    "mail_id": f"MAIL-{emp_id}-01",
                    "recipient_id": emp_id,
                    "recipient_name": user.get("full_name", emp_id),
                    "sender_name": "Executive HR Directorate",
                    "sender_title": "Head of People Operations",
                    "category": "OFFICIAL_LETTER",
                    "subject": "Official Letter of Employment & Standard Compensation Annexure",
                    "ref_no": f"AIS/HR/OFF/{emp_id}/2026",
                    "date": "2026-01-15",
                    "preview": "We are pleased to confirm your appointment at AI Samrat HRMS. Please retain this official docket for regulatory and statutory records.",
                    "content": f"Dear {user.get('full_name', emp_id)},\n\nWe are pleased to formally confirm your continuous tenure and employment terms at AI Samrat Technologies. Your position is categorized under the standard enterprise engineering cadre with all associated statutory benefits (PF, ESI, Gratuity, Health Coverage).\n\nThis communication constitutes an official company record and remains verified under our central digital credentials repository.",
                    "read_by": [emp_id],
                    "is_confidential": True,
                    "has_attachment": True,
                    "attachment_name": f"Appointment_Contract_{emp_id}.pdf",
                    "created_at": _utc_now() - timedelta(days=60)
                },
                {
                    "mail_id": f"MAIL-{emp_id}-02",
                    "recipient_id": emp_id,
                    "recipient_name": user.get("full_name", emp_id),
                    "sender_name": "Corporate Payroll Cell",
                    "sender_title": "Chief Financial Controller",
                    "category": "PAYSLIP_STATUTORY",
                    "subject": "Monthly Compensation Statement & Statutory Deduction Advice (October 2026)",
                    "ref_no": f"AIS/PAY/2026-10/{emp_id}",
                    "date": "2026-10-31",
                    "preview": "Your electronic salary statement for the payroll period October 2026 is published. Statutory deductions: PF 12%, ESI, PT.",
                    "content": f"Dear {user.get('full_name', emp_id)},\n\nYour net monthly remuneration for October 2026 has been credited via direct NEFT transaction to your registered salary account. Provident Fund (PF) and Professional Tax (PT) contributions have been remitted to statutory authorities.\n\nYou may view or download your password-protected Form 16 / Payslip directly from this official docket.",
                    "read_by": [emp_id],
                    "is_confidential": True,
                    "has_attachment": True,
                    "attachment_name": f"Payslip_Oct2026_{emp_id}.pdf",
                    "created_at": _utc_now() - timedelta(days=7)
                },
                {
                    "mail_id": f"MAIL-{emp_id}-03",
                    "recipient_id": "ALL",
                    "recipient_group": "ALL_EMPLOYEES",
                    "sender_name": "Office of Chief Information Security Officer (CISO)",
                    "sender_title": "CISO & Compliance Head",
                    "category": "ADMIN_MEMO",
                    "subject": "Mandatory Directive: Annual Information Security, ISO 27001 & DPDP Act Compliance",
                    "ref_no": "AIS/SEC/CIRC/2026-04",
                    "date": "2026-11-01",
                    "preview": "All employees must complete mandatory compliance refresher modules and observe clean desk and strict credential isolation policies.",
                    "content": "To All Personnel,\n\nIn accordance with ISO/IEC 27001:2022 standards and the Digital Personal Data Protection (DPDP) Act 2023, all employees are reminded to uphold zero-trust principles. Do not share credentials, avoid unencrypted transmission of customer identifiers, and report any suspicious activities directly via the Feedback/Triage portal.\n\nMandatory compliance coursework is available under the Training & Performance portal.",
                    "read_by": [emp_id],
                    "is_confidential": False,
                    "has_attachment": False,
                    "attachment_name": None,
                    "created_at": _utc_now() - timedelta(days=6)
                }
            ]
            db.official_mailbox.insert_many(seed)
            mails = seed

        unread_count = sum(1 for m in mails if emp_id not in m.get("read_by", []))

        # Filter by search term if provided
        if search:
            s = search.lower().strip()
            mails = [
                m for m in mails
                if s in m.get("subject", "").lower()
                or s in m.get("sender_name", "").lower()
                or s in m.get("ref_no", "").lower()
                or s in m.get("preview", "").lower()
            ]

        counts = {
            "all": db.official_mailbox.count_documents({"$or": [{"recipient_id": emp_id}, {"recipient_group": "ALL_EMPLOYEES"}]}),
            "letters": db.official_mailbox.count_documents({"$or": [{"recipient_id": emp_id}, {"recipient_group": "ALL_EMPLOYEES"}], "category": "OFFICIAL_LETTER"}),
            "payslips": db.official_mailbox.count_documents({"$or": [{"recipient_id": emp_id}, {"recipient_group": "ALL_EMPLOYEES"}], "category": "PAYSLIP_STATUTORY"}),
            "memos": db.official_mailbox.count_documents({"$or": [{"recipient_id": emp_id}, {"recipient_group": "ALL_EMPLOYEES"}], "category": "ADMIN_MEMO"}),
            "alerts": db.official_mailbox.count_documents({"$or": [{"recipient_id": emp_id}, {"recipient_group": "ALL_EMPLOYEES"}], "category": {"$in": ["APPROVAL_ALERT", "COMPLIANCE_ALERT"]}})
        }

        return {
            "folder": folder,
            "unread_count": unread_count,
            "counts": counts,
            "items": serialize_docs(mails)
        }

    @classmethod
    def get_mail_item(cls, user: dict, mail_id: str) -> Optional[Dict]:
        db = get_db()
        emp_id = user["employee_id"]
        role = user.get("role")
        mail = db.official_mailbox.find_one({"mail_id": mail_id})
        if not mail:
            return None

        # RBAC Check: Ensure user is authorized to read this official mail
        rec_id = mail.get("recipient_id")
        rec_grp = mail.get("recipient_group")
        if rec_id != emp_id and rec_grp != "ALL_EMPLOYEES" and rec_grp != (role.upper() if role else "") and role not in (Role.ADMIN, Role.HR):
            return None

        # Mark read
        if emp_id not in mail.get("read_by", []):
            db.official_mailbox.update_one({"mail_id": mail_id}, {"$addToSet": {"read_by": emp_id}})
            mail["read_by"].append(emp_id)

        return serialize_doc(mail)

    @classmethod
    def dispatch_official_notice(cls, actor: dict, data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_db()
        subject = (data.get("subject") or "").strip()
        content = (data.get("content") or "").strip()
        category = (data.get("category") or "ADMIN_MEMO").strip()
        recipient_group = (data.get("recipient_group") or "ALL_EMPLOYEES").strip()
        recipient_id = (data.get("recipient_id") or "").strip().upper()

        if not subject or not content:
            return None, "Subject and official content body are mandatory."

        count = db.official_mailbox.count_documents({})
        mail_id = f"MAIL-PUB-{1001 + count}"
        ref_no = f"AIS/OFF/{datetime.now().strftime('%Y%m')}/{1001 + count}"

        doc = {
            "mail_id": mail_id,
            "recipient_id": recipient_id or "ALL",
            "recipient_group": recipient_group,
            "sender_name": actor.get("full_name", "Corporate Administration"),
            "sender_title": f"{actor.get('role', 'Admin').title()} Authority",
            "category": category,
            "subject": subject,
            "ref_no": ref_no,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "preview": content[:140] + ("..." if len(content) > 140 else ""),
            "content": content,
            "read_by": [actor.get("employee_id")],
            "is_confidential": data.get("is_confidential", False),
            "has_attachment": False,
            "attachment_name": None,
            "created_at": _utc_now()
        }
        db.official_mailbox.insert_one(doc)
        return serialize_doc(doc), None

    @classmethod
    def send_user_mail(cls, actor: dict, data: dict) -> Tuple[Optional[Dict], Optional[str]]:
        """Sends an internal official mail or direct corporate memo between employees with attachment support."""
        db = get_db()
        sender_id = (actor.get("employee_id") or actor.get("emp_id") or "").strip().upper()
        sender_name = actor.get("full_name") or actor.get("name") or sender_id

        recipient_id = (data.get("recipient_id") or "").strip().upper()
        recipient_email = (data.get("recipient_email") or "").strip().lower()
        subject = (data.get("subject") or "").strip()
        content = (data.get("content") or "").strip()
        category = (data.get("category") or "OFFICIAL_LETTER").strip()

        if not recipient_id and not recipient_email:
            return None, "Recipient employee ID or email is required."
        if not subject:
            return None, "Subject line is required."
        if not content:
            return None, "Mail content message is required."

        rec_user = None
        if recipient_id:
            rec_user = db.users.find_one({"$or": [{"employee_id": recipient_id}, {"emp_id": recipient_id}]})
        if not rec_user and recipient_email:
            rec_user = db.users.find_one({"email": recipient_email})

        if not rec_user:
            return None, f"Recipient '{recipient_id or recipient_email}' not found."

        rec_id = rec_user.get("employee_id") or rec_user.get("emp_id")
        rec_name = rec_user.get("full_name") or rec_user.get("name") or rec_id

        count = db.official_mailbox.count_documents({}) + 1
        now_dt = datetime.now()
        mail_id = f"MAIL-{now_dt.year}-{count:04d}"
        ref_no = f"AIS/MAIL/{now_dt.strftime('%Y%m')}/{count:04d}"

        has_att = bool(data.get("attachment_name") or data.get("has_attachment"))
        att_name = data.get("attachment_name") or (f"Attachment_{count}.pdf" if has_att else None)

        doc = {
            "mail_id": mail_id,
            "recipient_id": rec_id,
            "recipient_name": rec_name,
            "recipient_email": rec_user.get("email"),
            "recipient_group": None,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "sender_title": f"{actor.get('designation') or actor.get('role', 'Staff').title()}",
            "category": category,
            "subject": subject,
            "ref_no": ref_no,
            "date": now_dt.strftime("%Y-%m-%d"),
            "preview": content[:140] + ("..." if len(content) > 140 else ""),
            "content": content,
            "read_by": [sender_id],
            "is_confidential": data.get("is_confidential", False),
            "has_attachment": has_att,
            "attachment_name": att_name,
            "attachment_url": data.get("attachment_url"),
            "created_at": _utc_now()
        }

        db.official_mailbox.insert_one(doc)

        try:
            from services.notification_service import NotificationService
            NotificationService.create_notification(
                title=f"New Official Mail: {subject[:40]}",
                message=f"{sender_name} sent you an official communication: '{subject}'.",
                category="COMMUNICATION",
                recipient_id=rec_id,
                link="/communication?tab=mail",
                priority="HIGH"
            )
        except Exception as e:
            logger.warning(f"Could not dispatch notification: {e}")

        return serialize_doc(doc), None

    @classmethod
    def delete_mail(cls, user: dict, mail_id: str) -> Tuple[bool, str]:
        """
        Deletes or removes an official mail / memo:
        - Announcements / company broadcasts: Only higher officials (Admin, HR, Manager) can delete for everyone.
          Employees can only remove from their personal view.
        - Personal mail / direct memos: Soft-deletes for the requesting user.
        """
        db = get_db()
        emp_id = user["employee_id"]
        role = user.get("role")
        is_higher_official = role in (Role.ADMIN, Role.HR, Role.HR_MANAGER, Role.MANAGER, Role.ORGANIZATION)

        mail = db.official_mailbox.find_one({"mail_id": mail_id})
        if not mail:
            return False, "Official mail not found."

        is_announcement = mail.get("recipient_group") in ("ALL_EMPLOYEES", "ALL") or mail.get("category") == "ADMIN_MEMO"

        if is_announcement:
            if is_higher_official:
                db.official_mailbox.delete_one({"mail_id": mail_id})
                AuditService.log_action(
                    actor=user,
                    action="OFFICIAL_CIRCULAR_DELETED",
                    target_type="mailbox",
                    target_id=mail_id,
                    details={"subject": mail.get("subject"), "deleted_by": emp_id}
                )
                return True, "Official corporate circular/announcement removed."
            else:
                db.official_mailbox.update_one(
                    {"mail_id": mail_id},
                    {"$addToSet": {"deleted_for": emp_id}}
                )
                return True, "Announcement dismissed from your view."

        # Personal mail / direct memos
        db.official_mailbox.update_one(
            {"mail_id": mail_id},
            {"$addToSet": {"deleted_for": emp_id}}
        )
        AuditService.log_action(
            actor=user,
            action="MAIL_ITEM_DELETED",
            target_type="mailbox",
            target_id=mail_id,
            details={"subject": mail.get("subject"), "deleted_by": emp_id}
        )
        return True, "Mail item removed from your mailbox."
