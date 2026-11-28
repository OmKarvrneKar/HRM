import io
import pytest
from datetime import datetime, timezone
from bson import ObjectId
from werkzeug.datastructures import FileStorage
from services.chat_service import ChatService
from services.project_service import ProjectService
from permissions.rbac import Role


def create_approved_test_project(db, creator, manager, members):
    """Helper to create and approve an isolated test project with an active group chat."""
    payload = {
        "title": "Quantum Gateway Migration",
        "description": "Enterprise cloud security migration",
        "objectives": "Zero-downtime cluster switchover",
        "deliverables": "Configuration templates and test suites",
        "start_date": "2026-11-15",
        "expected_completion_date": "2026-12-15",
        "priority": "High",
        "manager_employee_id": manager["employee_id"],
        "selected_members": [m["employee_id"] for m in members]
    }
    project, err = ProjectService.create_project(creator, payload)
    assert err is None
    project_id = project["project_id"]

    # Manager approves project
    approved_project, approve_err = ProjectService.approve_project(manager, project_id, review_notes="Approved for execution")
    assert approve_err is None
    assert approved_project["status"] == "ACTIVE"

    conv = ChatService.ensure_project_chat(approved_project, manager)
    assert conv is not None
    return approved_project, conv


def test_1_employee_deletes_own_direct_chat_preserves_other_user_view(db, seeded_users, client, tokens):
    """
    Test 1: Employee deletes their own direct chat.
    - Removes conversation from requesting employee's view.
    - The other participant retains their conversation history and view.
    - Underlying messages and attachments are preserved.
    - Audit log is created.
    """
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    # Create DM and exchange messages
    conv = ChatService.get_or_create_direct_chat(emp1, emp2)
    cid = conv["conversation_id"]

    msg1, _ = ChatService.send_message(emp1, cid, "Hello Employee Two, this is Rahul.")
    msg2, _ = ChatService.send_message(emp2, cid, "Acknowledged, Rahul. Good to connect.")

    # Both see 1 conversation
    convs_emp1 = ChatService.get_user_conversations(emp1)
    convs_emp2 = ChatService.get_user_conversations(emp2)
    assert any(c["conversation_id"] == cid for c in convs_emp1)
    assert any(c["conversation_id"] == cid for c in convs_emp2)

    # Employee 1 deletes their direct chat via API
    res = client.delete(f"/api/conversations/{cid}", headers={"Authorization": f"Bearer {tokens['emp1']}"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["scope"] == "user_view"

    # Verify Employee 1 no longer sees the conversation in their inbox
    convs_emp1_after = ChatService.get_user_conversations(emp1)
    assert not any(c["conversation_id"] == cid for c in convs_emp1_after)

    # Verify Employee 2 STILL sees the conversation and its full history intact
    convs_emp2_after = ChatService.get_user_conversations(emp2)
    assert any(c["conversation_id"] == cid for c in convs_emp2_after)

    msgs_emp2, err2 = ChatService.get_messages(emp2, cid)
    assert err2 is None
    assert len(msgs_emp2) >= 2
    assert any(m["content"] == "Hello Employee Two, this is Rahul." for m in msgs_emp2)

    # Verify audit record exists
    audit = db.audit_logs.find_one({"action": "CHAT_DIRECT_DELETED", "target_id": cid})
    assert audit is not None
    assert audit["actor_id"] == emp1["employee_id"]


def test_2_employee_cannot_delete_approved_project_group_chat(db, seeded_users, client, tokens):
    """
    Test 2: Normal employee cannot delete an approved project group chat.
    Direct API request returns 403 Forbidden.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    project, conv = create_approved_test_project(db, tl, mgr, [emp1, emp2])
    cid = conv["conversation_id"]

    # Employee 1 attempts to delete project chat
    res = client.delete(f"/api/conversations/{cid}", headers={"Authorization": f"Bearer {tokens['emp1']}"})
    assert res.status_code == 403
    data = res.get_json()
    assert "Access Denied" in data["error"]
    assert "Project group chats cannot be deleted by employees" in data["error"]

    # Conversation remains active in database
    db_conv = db.conversations.find_one({"conversation_id": cid})
    assert db_conv["status"] == "active"


def test_3_employee_can_hide_and_unhide_protected_project_chat(db, seeded_users, client, tokens):
    """
    Test 3: Employee can hide a protected project chat from their personal list.
    - Hiding removes it from default conversation list.
    - It remains active and accessible to other members.
    - Employee can view it under ?type=hidden and unhide it.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    project, conv = create_approved_test_project(db, tl, mgr, [emp1, emp2])
    cid = conv["conversation_id"]

    # Initial check: emp1 sees project chat
    initial_convs = ChatService.get_user_conversations(emp1)
    assert any(c["conversation_id"] == cid for c in initial_convs)

    # emp1 hides project chat via API
    hide_res = client.post(f"/api/conversations/{cid}/hide", headers={"Authorization": f"Bearer {tokens['emp1']}"})
    assert hide_res.status_code == 200
    assert hide_res.get_json()["success"] is True

    # emp1 no longer sees it in default list
    active_convs = ChatService.get_user_conversations(emp1)
    assert not any(c["conversation_id"] == cid for c in active_convs)

    # But emp1 CAN see it under type=hidden
    hidden_convs = ChatService.get_user_conversations(emp1, filter_type="hidden")
    assert any(c["conversation_id"] == cid for c in hidden_convs)

    # emp2 and manager still see it in their default active list
    emp2_convs = ChatService.get_user_conversations(emp2)
    assert any(c["conversation_id"] == cid for c in emp2_convs)

    # emp1 unhides it
    unhide_res = client.post(f"/api/conversations/{cid}/unhide", headers={"Authorization": f"Bearer {tokens['emp1']}"})
    assert unhide_res.status_code == 200

    # Restored to emp1's default list
    restored_convs = ChatService.get_user_conversations(emp1)
    assert any(c["conversation_id"] == cid for c in restored_convs)


def test_4_employee_cannot_bypass_restrictions_via_api(db, seeded_users, client, tokens):
    """
    Test 4: Employee cannot bypass project chat deletion via query params or payload manipulation.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]

    project, conv = create_approved_test_project(db, tl, mgr, [emp1])
    cid = conv["conversation_id"]

    # Attempt delete with forced confirm_permanent flags
    res = client.delete(
        f"/api/conversations/{cid}?confirm=true&confirm_permanent=true",
        json={"confirm_permanent": True, "confirm": True},
        headers={"Authorization": f"Bearer {tokens['emp1']}"}
    )
    assert res.status_code == 403
    assert "Access Denied" in res.get_json()["error"]


def test_5_team_lead_cannot_permanently_delete_approved_project_chat(db, seeded_users, client, tokens):
    """
    Test 5: Team Lead who proposed the project cannot delete the approved project chat.
    Follows existing Manager approval and project lifecycle rules.
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]

    project, conv = create_approved_test_project(db, tl, mgr, [emp1])
    cid = conv["conversation_id"]

    # Team Lead attempts deletion
    res = client.delete(
        f"/api/conversations/{cid}",
        json={"confirm_permanent": True},
        headers={"Authorization": f"Bearer {tokens['team_lead']}"}
    )
    assert res.status_code == 403
    data = res.get_json()
    assert "Access Denied" in data["error"]
    assert "Team Leads cannot delete approved project group chats" in data["error"]

    # Verify conversation and message history remain intact
    db_conv = db.conversations.find_one({"conversation_id": cid})
    assert db_conv["status"] == "active"


def test_6_manager_controls_archival_and_deletion(db, seeded_users, client, tokens):
    """
    Test 6: Manager's authorized lifecycle controls:
    - Manager CANNOT archive or delete while active project depends on it.
    - Once project is COMPLETED or CANCELLED, Manager can archive.
    - Archival restricts new messages.
    - Manager can delete with explicit confirmation (soft deletion, preserving compliance records).
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]

    project, conv = create_approved_test_project(db, tl, mgr, [emp1])
    cid = conv["conversation_id"]
    pid = project["project_id"]

    # 1. Project is ACTIVE -> Manager cannot delete or archive
    del_active = client.delete(
        f"/api/conversations/{cid}",
        json={"confirm_permanent": True},
        headers={"Authorization": f"Bearer {tokens['manager']}"}
    )
    assert del_active.status_code == 400
    assert "Active project dependencies exist" in del_active.get_json()["error"]

    arch_active = client.post(
        f"/api/conversations/{cid}/archive",
        headers={"Authorization": f"Bearer {tokens['manager']}"}
    )
    assert arch_active.status_code == 400
    assert "Active project dependencies exist" in arch_active.get_json()["error"]

    # 2. Transition project to COMPLETED
    db.projects.update_one({"project_id": pid}, {"$set": {"status": "COMPLETED"}})

    # 3. Manager archives the completed project chat
    arch_res = client.post(
        f"/api/conversations/{cid}/archive",
        headers={"Authorization": f"Bearer {tokens['manager']}"}
    )
    assert arch_res.status_code == 200
    assert arch_res.get_json()["status"] == "archived"

    # Verify conversation status is archived
    db_conv = db.conversations.find_one({"conversation_id": cid})
    assert db_conv["status"] == "archived"

    # Verify new messages are restricted in archived chat
    msg_res, msg_err = ChatService.send_message(emp1, cid, "Can we still post here?")
    assert msg_res is None
    assert "archived" in msg_err.lower()

    # 4. Manager permanent deletion without confirmation is rejected
    del_unconfirmed = client.delete(
        f"/api/conversations/{cid}",
        json={"confirm_permanent": False},
        headers={"Authorization": f"Bearer {tokens['manager']}"}
    )
    assert del_unconfirmed.status_code == 400
    assert "Explicit confirmation required" in del_unconfirmed.get_json()["error"]

    # 5. Manager permanent deletion with explicit confirmation succeeds
    del_confirmed = client.delete(
        f"/api/conversations/{cid}",
        json={"confirm_permanent": True, "confirm": True},
        headers={"Authorization": f"Bearer {tokens['manager']}"}
    )
    assert del_confirmed.status_code == 200
    assert del_confirmed.get_json()["status"] == "deleted"

    # Verify soft-deletion: status='deleted', but message history and audit records are preserved
    db_conv_del = db.conversations.find_one({"conversation_id": cid})
    assert db_conv_del["status"] == "deleted"

    audit_del = db.audit_logs.find_one({"action": "PROJECT_CHAT_DELETED", "target_id": cid})
    assert audit_del is not None
    assert audit_del["actor_id"] == mgr["employee_id"]


def test_7_hr_cannot_access_or_manage_project_chats(db, seeded_users, client, tokens):
    """
    Test 7: HR is strictly restricted from project chats (view, delete, archive, hide).
    """
    tl = seeded_users["team_lead"]
    mgr = seeded_users["manager"]
    emp1 = seeded_users["emp1"]
    hr = seeded_users["hr"]

    project, conv = create_approved_test_project(db, tl, mgr, [emp1])
    cid = conv["conversation_id"]
    pid = project["project_id"]

    # HR cannot view project chat
    get_res = client.get(f"/api/conversations/project/{pid}", headers={"Authorization": f"Bearer {tokens['hr']}"})
    assert get_res.status_code == 403

    # HR cannot fetch detail of project conversation
    detail_res = client.get(f"/api/conversations/{cid}", headers={"Authorization": f"Bearer {tokens['hr']}"})
    assert detail_res.status_code == 403

    # HR cannot delete project conversation
    del_res = client.delete(f"/api/conversations/{cid}", headers={"Authorization": f"Bearer {tokens['hr']}"})
    assert del_res.status_code == 403

    # HR cannot archive project conversation
    arch_res = client.post(f"/api/conversations/{cid}/archive", headers={"Authorization": f"Bearer {tokens['hr']}"})
    assert arch_res.status_code == 403

    # HR cannot hide project conversation
    hide_res = client.post(f"/api/conversations/{cid}/hide", headers={"Authorization": f"Bearer {tokens['hr']}"})
    assert hide_res.status_code == 403


def test_8_other_users_conversations_remain_intact(db, seeded_users, client, tokens):
    """
    Test 8: Deleting a conversation does not impact unrelated conversations of other users.
    """
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]
    mgr = seeded_users["manager"]

    # Conv A: emp1 & emp2
    convA = ChatService.get_or_create_direct_chat(emp1, emp2)
    cidA = convA["conversation_id"]
    ChatService.send_message(emp1, cidA, "Message in Conv A")

    # Conv B: emp1 & mgr
    convB = ChatService.get_or_create_direct_chat(emp1, mgr)
    cidB = convB["conversation_id"]
    ChatService.send_message(emp1, cidB, "Message in Conv B")

    # Conv C: emp2 & mgr
    convC = ChatService.get_or_create_direct_chat(emp2, mgr)
    cidC = convC["conversation_id"]
    ChatService.send_message(emp2, cidC, "Message in Conv C")

    # emp1 deletes Conv A
    client.delete(f"/api/conversations/{cidA}", headers={"Authorization": f"Bearer {tokens['emp1']}"})

    # Conv B for emp1 is unaffected
    emp1_convs = ChatService.get_user_conversations(emp1)
    assert not any(c["conversation_id"] == cidA for c in emp1_convs)
    assert any(c["conversation_id"] == cidB for c in emp1_convs)

    # Conv A and Conv C for emp2 are completely intact
    emp2_convs = ChatService.get_user_conversations(emp2)
    assert any(c["conversation_id"] == cidA for c in emp2_convs)
    assert any(c["conversation_id"] == cidC for c in emp2_convs)


def test_9_cannot_delete_unrelated_conversation(db, seeded_users, client, tokens):
    """
    Test 9: A user cannot delete another person's unrelated direct conversation (RBAC guard).
    """
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]
    mgr = seeded_users["manager"]

    # DM between emp1 and emp2
    conv = ChatService.get_or_create_direct_chat(emp1, emp2)
    cid = conv["conversation_id"]

    # Manager (who is not a participant) attempts to delete emp1-emp2 direct chat
    res = client.delete(f"/api/conversations/{cid}", headers={"Authorization": f"Bearer {tokens['manager']}"})
    assert res.status_code == 403
    assert "Access Denied" in res.get_json()["error"]


def test_10_incoming_message_restores_direct_chat_for_recipient(db, seeded_users, client, tokens):
    """
    Test 10: Existing messaging and unsending continue working normally.
    If emp1 deleted the chat, but emp2 sends a new message to emp1, the chat
    reappears in emp1's list with the new message.
    """
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    conv = ChatService.get_or_create_direct_chat(emp1, emp2)
    cid = conv["conversation_id"]

    # emp1 deletes the chat
    client.delete(f"/api/conversations/{cid}", headers={"Authorization": f"Bearer {tokens['emp1']}"})
    assert not any(c["conversation_id"] == cid for c in ChatService.get_user_conversations(emp1))

    # emp2 sends a new message to emp1
    new_msg, err = ChatService.send_message(emp2, cid, "Hey Rahul, are you available for a quick sync?")
    assert err is None

    # Chat reappears in emp1's conversation list
    emp1_convs = ChatService.get_user_conversations(emp1)
    assert any(c["conversation_id"] == cid for c in emp1_convs)

    # In emp1's view of messages, old history prior to delete is cleared, but new message is present
    emp1_msgs, _ = ChatService.get_messages(emp1, cid)
    assert len(emp1_msgs) == 1
    assert emp1_msgs[0]["content"] == "Hey Rahul, are you available for a quick sync?"
