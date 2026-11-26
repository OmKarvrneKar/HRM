import io
import pytest
from backend.services.chat_service import ChatService
from backend.permissions.rbac import Role
from werkzeug.datastructures import FileStorage


def test_direct_chat_and_unsend_by_author(db, seeded_users):
    """Sender can unsend their own message, replacing content and updating last_message."""
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    # 1. Create DM
    conv = ChatService.get_or_create_direct_chat(emp1, emp2)
    cid = conv["conversation_id"]

    # 2. Send message
    msg, err = ChatService.send_message(emp1, cid, "Hello Sneha, please review the latest PR.")
    assert err is None
    assert msg["content"] == "Hello Sneha, please review the latest PR."
    msg_id = str(msg["_id"])

    # 3. Unsend message by author (emp1)
    unsent_msg, unsend_err = ChatService.unsend_message(emp1, msg_id)
    assert unsend_err is None
    assert unsent_msg["content"] == "This message was unsent"
    assert unsent_msg["is_unsent"] is True

    # 4. Fetch messages from view: must display redacted content
    messages, fetch_err = ChatService.get_messages(emp2, cid)
    assert fetch_err is None
    m_in_view = [m for m in messages if str(m["_id"]) == msg_id][0]
    assert m_in_view["content"] == "This message was unsent"

    # 5. Check audit log
    audit = db.audit_logs.find_one({"action": "CHAT_MESSAGE_UNSENT", "target_id": msg_id})
    assert audit is not None
    assert audit["actor_id"] == emp1["employee_id"]


def test_unsend_rejected_for_non_author(db, seeded_users):
    """An unauthorized employee cannot unsend another user's message."""
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    conv = ChatService.get_or_create_direct_chat(emp1, emp2)
    cid = conv["conversation_id"]

    msg, _ = ChatService.send_message(emp1, cid, "Confidential note from Rahul.")
    msg_id = str(msg["_id"])

    # emp2 attempts to unsend emp1's message
    res, err = ChatService.unsend_message(emp2, msg_id)
    assert res is None
    assert "Access Denied" in err

    # Verify message remains intact
    db_msg = db.messages.find_one({"_id": msg["_id"]})
    assert db_msg["content"] == "Confidential note from Rahul."
    assert db_msg.get("is_unsent") is not True


def test_chat_file_attachment_upload_and_security(db, seeded_users):
    """Authorized participant can upload allowed file types; dangerous executables are rejected."""
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    conv = ChatService.get_or_create_direct_chat(emp1, emp2)
    cid = conv["conversation_id"]

    # 1. Valid document attachment (.pdf)
    pdf_content = b"%PDF-1.4 test document content for AI Samrat HRMS"
    pdf_file = FileStorage(
        stream=io.BytesIO(pdf_content),
        filename="project_architecture.pdf",
        content_type="application/pdf"
    )

    msg, err = ChatService.save_attachment(emp1, cid, pdf_file, caption="Architecture Draft")
    assert err is None
    assert msg["attachment"] is not None
    assert msg["attachment"]["filename"] == "project_architecture.pdf"
    att_id = msg["attachment"]["attachment_id"]

    # 2. Verify attachment record in database
    att_doc = db.chat_attachments.find_one({"attachment_id": att_id})
    assert att_doc is not None
    assert "static" not in att_doc["file_path"]  # Stored outside static public path

    # 3. Reject dangerous executable (.exe)
    exe_file = FileStorage(
        stream=io.BytesIO(b"malicious executable"),
        filename="trojan.exe",
        content_type="application/x-msdownload"
    )
    bad_msg, bad_err = ChatService.save_attachment(emp1, cid, exe_file)
    assert bad_msg is None
    assert "not permitted" in bad_err.lower()

    # 4. Reject binary executable disguised as document (.pdf with MZ header)
    disguised_file = FileStorage(
        stream=io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00disguised binary"),
        filename="report.pdf",
        content_type="application/pdf"
    )
    disguised_msg, disguised_err = ChatService.save_attachment(emp1, cid, disguised_file)
    assert disguised_msg is None
    assert "Executable binaries cannot be uploaded" in disguised_err


def test_attachment_download_authorization(db, seeded_users):
    """Only conversation participants can download chat attachments; outsiders receive 403."""
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]
    lead = seeded_users["team_lead"]

    conv = ChatService.get_or_create_direct_chat(emp1, emp2)
    cid = conv["conversation_id"]

    valid_file = FileStorage(
        stream=io.BytesIO(b"Meeting Notes and Minutes"),
        filename="notes.txt",
        content_type="text/plain"
    )
    msg, _ = ChatService.save_attachment(emp1, cid, valid_file)
    att_id = msg["attachment"]["attachment_id"]

    # Participant (emp2) can access attachment
    att_info, err = ChatService.get_attachment_for_download(emp2, cid, att_id)
    assert err is None
    assert att_info["original_filename"] == "notes.txt"

    # Outsider (lead) cannot access attachment
    outsider_att, outsider_err = ChatService.get_attachment_for_download(lead, cid, att_id)
    assert outsider_att is None
    assert "Access Denied" in outsider_err


def test_unsend_message_with_attachment_removes_attachment(db, seeded_users):
    """Unsending an attachment message permanently redacts the attachment from active chat views."""
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    conv = ChatService.get_or_create_direct_chat(emp1, emp2)
    cid = conv["conversation_id"]

    file_obj = FileStorage(
        stream=io.BytesIO(b"Financial spreadsheet data"),
        filename="budget.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    msg, _ = ChatService.save_attachment(emp1, cid, file_obj, caption="Confidential budget")
    msg_id = str(msg["_id"])
    att_id = msg["attachment"]["attachment_id"]

    # Unsend
    unsent, err = ChatService.unsend_message(emp1, msg_id)
    assert err is None
    assert unsent["content"] == "This message was unsent"
    assert unsent["attachment"] is None

    # Database attachment record marked deleted
    att_rec = db.chat_attachments.find_one({"attachment_id": att_id})
    assert att_rec["is_deleted"] is True

    # Attempting to download now fails
    dl, dl_err = ChatService.get_attachment_for_download(emp2, cid, att_id)
    assert dl is None
    assert "removed" in dl_err.lower()
