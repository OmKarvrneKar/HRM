import logging
import uuid
import re
from datetime import datetime, timezone
from database.connection import get_db
from utils.serializers import serialize_doc, serialize_docs
from utils.timezone import now_utc

logger = logging.getLogger(__name__)


class FeedbackService:
    """
    Smart Feedback & Bug Reporting Service for AISamrat HRMS:
    Collects employee feedback & bug reports across all dashboards,
    routes them directly to Admin / Super Admin console, and uses
    intelligent deduplication & clustering to group repetitive issues
    by Department and Dashboard Source without exposing employee names.
    """

    @classmethod
    def submit_feedback(cls, user: dict, data: dict) -> tuple[dict | None, str | None]:
        summary = (data.get("summary") or "").strip()
        details = (data.get("details") or "").strip()
        if not summary:
            return None, "Feedback summary / title is required."
        if not details:
            return None, "Detailed description of the issue or feedback is required."

        category = (data.get("category") or "Bug").strip()
        severity = (data.get("severity") or "Medium").capitalize()
        if severity not in ("Low", "Medium", "High", "Critical"):
            severity = "Medium"

        department = user.get("department") or data.get("department") or "Engineering"
        dashboard_source = (data.get("dashboard_source") or "Workspace Dashboard").strip()

        feedback_id = f"FB-{uuid.uuid4().hex[:10].upper()}"

        doc = {
            "feedback_id": feedback_id,
            # employee_id is stored strictly for internal DB indexing, but is NEVER returned in triage responses
            "employee_id": user.get("employee_id"),
            "department": department,
            "dashboard_source": dashboard_source,
            "category": category,
            "severity": severity,
            "summary": summary,
            "details": details,
            "status": "Open",
            "admin_notes": "",
            "created_at": now_utc(),
            "updated_at": now_utc()
        }

        db = get_db()
        db.system_feedback.insert_one(doc)
        logger.info("Submitted feedback %s from %s for %s", feedback_id, department, dashboard_source)

        # Return safe acknowledgement object (without sensitive fields)
        safe_response = {
            "feedback_id": feedback_id,
            "category": category,
            "severity": severity,
            "department": department,
            "dashboard_source": dashboard_source,
            "status": "Open",
            "message": "Feedback submitted successfully to Administrator triage."
        }
        return safe_response, None

    @classmethod
    def _extract_bullets(cls, text: str) -> list[str]:
        """Extracts unique descriptive bullet items from free-form details."""
        if not text:
            return []
        lines = [re.sub(r"^[\s\-\*\•\d\.\)]+", "", line).strip() for line in text.splitlines()]
        cleaned = [line for line in lines if len(line) >= 8]
        return list(dict.fromkeys(cleaned))

    @classmethod
    def _normalize_title_key(cls, summary: str) -> str:
        """Strips common stop words and punctuation to cluster similar reports into canonical signatures."""
        words = re.findall(r"\b[a-zA-Z0-9]{3,}\b", summary.lower())
        stop_words = {
            "the", "and", "for", "with", "not", "issue", "bug", "error", "problem",
            "when", "while", "clicking", "button", "page", "failed", "fails", "is",
            "are", "was", "were", "this", "that", "there", "some", "any", "got",
            "getting", "please", "fix", "very", "my", "our", "screen", "view"
        }
        filtered = [w for w in words if w not in stop_words]
        if not filtered:
            return summary.lower().strip()[:24]
        # Sort top 4 significant keywords alphabetically to eliminate word-order sensitivity
        sorted_keywords = sorted(filtered[:5])
        return " ".join(sorted_keywords)

    @classmethod
    def get_triaged_feedback(cls, status_filter: str = None) -> dict:
        """
        Groups and deduplicates repetitive feedback reports into consolidated master ticket clusters.
        STRICT PRIVACY GUARANTEE: Does not return employee names, employee IDs, or personal emails.
        Clusters identical/similar bug submissions across users with occurrence counts.
        """
        db = get_db()
        query = {}
        if status_filter and status_filter.upper() != "ALL":
            query["status"] = status_filter

        records = list(db.system_feedback.find(query).sort("created_at", -1))

        # Clustering dictionary keyed by canonical topic signature
        clusters = {}
        severity_rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}

        for rec in records:
            dept = rec.get("department") or "General"
            source = rec.get("dashboard_source") or "Workspace"
            cat = rec.get("category") or "Bug"
            emp_id = rec.get("employee_id")
            norm_key = cls._normalize_title_key(rec.get("summary", ""))

            # If normalized key has specific keywords, cluster across departments; otherwise include dept
            cluster_key = f"{cat}::{norm_key}" if len(norm_key.split()) >= 2 else f"{dept}::{cat}::{norm_key}"

            if cluster_key not in clusters:
                clusters[cluster_key] = {
                    "cluster_id": f"CLUST-{abs(hash(cluster_key)) % 100000:05d}",
                    "department": dept,
                    "departments": [dept],
                    "dashboard_source": source,
                    "category": cat,
                    "title": rec.get("summary"),
                    "highest_severity": rec.get("severity", "Medium"),
                    "status": rec.get("status", "Open"),
                    "report_count": 0,
                    "reporters_set": set(),
                    "feedback_ids": [],
                    "unique_bullets": [],
                    "first_reported_at": rec.get("created_at"),
                    "latest_reported_at": rec.get("created_at")
                }

            c = clusters[cluster_key]
            c["report_count"] += 1
            if emp_id:
                c["reporters_set"].add(emp_id)
            c["feedback_ids"].append(rec.get("feedback_id"))

            if dept not in c["departments"]:
                c["departments"].append(dept)

            # Elevate severity if a higher severity report joined this cluster
            if severity_rank.get(rec.get("severity"), 0) > severity_rank.get(c["highest_severity"], 0):
                c["highest_severity"] = rec.get("severity")

            # Accumulate unique descriptive bullet points
            bullets = cls._extract_bullets(rec.get("details", ""))
            for b in bullets:
                if b not in c["unique_bullets"] and len(c["unique_bullets"]) < 6:
                    c["unique_bullets"].append(b)

            if not c["unique_bullets"]:
                summary_text = rec.get("summary")
                if summary_text and summary_text not in c["unique_bullets"]:
                    c["unique_bullets"].append(summary_text)

            # Track latest timestamp
            if rec.get("created_at") and (not c["latest_reported_at"] or rec["created_at"] > c["latest_reported_at"]):
                c["latest_reported_at"] = rec.get("created_at")

        triaged_list = []
        for c in clusters.values():
            c["reporters_count"] = len(c["reporters_set"])
            del c["reporters_set"]
            if len(c["departments"]) > 1:
                c["department"] = f"Multi-Dept ({', '.join(c['departments'][:2])})"
            triaged_list.append(c)

        # Sort by highest severity rank desc, then report_count desc
        triaged_list.sort(
            key=lambda x: (severity_rank.get(x["highest_severity"], 0), x["report_count"]),
            reverse=True
        )

        return {
            "total_reports": len(records),
            "total_clusters": len(triaged_list),
            "clusters": serialize_docs(triaged_list)
        }

    @classmethod
    def update_cluster_status(cls, admin_user: dict, feedback_ids: list[str], new_status: str, notes: str = "") -> tuple[bool, str | None]:
        db = get_db()
        if not feedback_ids:
            return False, "No feedback IDs provided."
        if new_status not in ("Open", "Under Investigation", "Resolved"):
            return False, "Invalid status. Must be 'Open', 'Under Investigation', or 'Resolved'."

        db.system_feedback.update_many(
            {"feedback_id": {"$in": feedback_ids}},
            {"$set": {
                "status": new_status,
                "admin_notes": notes,
                "updated_at": now_utc()
            }}
        )
        return True, None

