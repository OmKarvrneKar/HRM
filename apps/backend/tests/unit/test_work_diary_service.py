import pytest
import io
import openpyxl
from backend.services.work_diary_service import WorkDiaryService


def test_calculate_duration():
    """Test duration calculation for various time intervals."""
    h, d = WorkDiaryService.calculate_duration("09:00", "11:30")
    assert h == 2.5
    assert d == "2h 30m"

    h, d = WorkDiaryService.calculate_duration("10:15", "11:45")
    assert h == 1.5
    assert d == "1h 30m"

    # Invalid / overnight / empty
    h, d = WorkDiaryService.calculate_duration("17:00", "09:00")
    assert h == 0.0
    assert d == "0h 0m"

    h, d = WorkDiaryService.calculate_duration("", "")
    assert h == 0.0
    assert d == "0h 0m"


def test_work_diary_crud_and_privacy(db, seeded_users):
    """Test creating, updating, deleting entries and privacy boundary enforcement."""
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    # 1. Create entry for emp1
    entry = WorkDiaryService.create_entry(
        employee_id=emp1["employee_id"],
        employee_name=emp1["full_name"],
        payload={
            "diary_date": "2026-10-16",
            "start_time": "09:30",
            "end_time": "12:30",
            "activity_title": "Core Module Refactoring",
            "work_description": "Cleaned up database queries and added caching layer.",
            "category": "Development",
            "status": "Completed"
        }
    )
    assert entry["diary_id"].startswith("WD-")
    assert entry["duration_hours"] == 3.0
    assert entry["duration_display"] == "3h 0m"
    assert entry["employee_id"] == emp1["employee_id"]

    diary_id = entry["diary_id"]

    # 2. Strict Privacy: emp2 cannot update emp1's entry
    with pytest.raises(PermissionError):
        WorkDiaryService.update_entry(
            employee_id=emp2["employee_id"],
            diary_id=diary_id,
            payload={"activity_title": "Hacked title"}
        )

    # 3. emp1 can update their own entry
    updated = WorkDiaryService.update_entry(
        employee_id=emp1["employee_id"],
        diary_id=diary_id,
        payload={
            "start_time": "09:30",
            "end_time": "13:30",
            "activity_title": "Core Module Refactoring & Testing"
        }
    )
    assert updated["duration_hours"] == 4.0
    assert updated["duration_display"] == "4h 0m"
    assert updated["activity_title"] == "Core Module Refactoring & Testing"

    # 4. Strict Privacy: emp2 cannot delete emp1's entry
    with pytest.raises(PermissionError):
        WorkDiaryService.delete_entry(
            employee_id=emp2["employee_id"],
            diary_id=diary_id
        )

    # 5. emp1 can delete their own entry
    deleted = WorkDiaryService.delete_entry(
        employee_id=emp1["employee_id"],
        diary_id=diary_id
    )
    assert deleted is True

    # Confirm it's gone
    daily = WorkDiaryService.get_daily_diary(emp1["employee_id"], "2026-10-16")
    assert daily["summary"]["entry_count"] == 0


def test_work_diary_monthly_aggregation_and_privacy(db, seeded_users):
    """Test monthly aggregation and ensuring emp2 sees none of emp1's data."""
    emp1 = seeded_users["emp1"]
    emp2 = seeded_users["emp2"]

    # Create entries on two different days for emp1
    WorkDiaryService.create_entry(emp1["employee_id"], emp1["full_name"], {
        "diary_date": "2026-10-10",
        "start_time": "10:00",
        "end_time": "12:00",
        "activity_title": "Task A",
        "work_description": "Did Task A",
        "category": "Development"
    })
    WorkDiaryService.create_entry(emp1["employee_id"], emp1["full_name"], {
        "diary_date": "2026-10-11",
        "start_time": "14:00",
        "end_time": "17:00",
        "activity_title": "Task B",
        "work_description": "Did Task B",
        "category": "Testing & QA"
    })

    # emp1 monthly query
    m_emp1 = WorkDiaryService.get_monthly_diary(emp1["employee_id"], "2026-10")
    assert m_emp1["summary"]["entry_count"] == 2
    assert m_emp1["summary"]["days_logged_count"] == 2
    assert m_emp1["summary"]["total_hours"] == 5.0

    # emp2 monthly query must return 0 (strict privacy)
    m_emp2 = WorkDiaryService.get_monthly_diary(emp2["employee_id"], "2026-10")
    assert m_emp2["summary"]["entry_count"] == 0
    assert m_emp2["summary"]["days_logged_count"] == 0
    assert m_emp2["summary"]["total_hours"] == 0.0


def test_work_diary_excel_export_daily_and_monthly(db, seeded_users):
    """Test generating valid Excel spreadsheets for daily and monthly logs."""
    emp1 = seeded_users["emp1"]

    WorkDiaryService.create_entry(emp1["employee_id"], emp1["full_name"], {
        "diary_date": "2026-10-16",
        "start_time": "09:00",
        "end_time": "12:00",
        "activity_title": "API Development",
        "work_description": "Designed work diary endpoints",
        "category": "Development",
        "status": "Completed"
    })
    WorkDiaryService.create_entry(emp1["employee_id"], emp1["full_name"], {
        "diary_date": "2026-10-16",
        "start_time": "13:00",
        "end_time": "15:30",
        "activity_title": "Excel Generator Integration",
        "work_description": "Wrote openpyxl styling and summary rows",
        "category": "Development",
        "status": "Completed"
    })

    # 1. Daily Excel export
    daily_stream = WorkDiaryService.export_diary_excel(
        employee_id=emp1["employee_id"],
        employee_name=emp1["full_name"],
        filter_type="daily",
        date_or_month="2026-10-16"
    )
    assert isinstance(daily_stream, io.BytesIO)
    daily_wb = openpyxl.load_workbook(daily_stream)
    assert len(daily_wb.sheetnames) >= 1
    sheet = daily_wb.active
    # Check Title and Headers
    assert "AI Samrat Pvt Ltd" in sheet["A1"].value
    assert "Date" in sheet["A5"].value
    assert "Task / Activity Title" in sheet["F5"].value
    # Check row 6 and row 7 data
    assert sheet["A6"].value == "2026-10-16"
    assert "API Development" in sheet["F6"].value
    assert "Excel Generator Integration" in sheet["F7"].value

    # 2. Monthly Excel export
    monthly_stream = WorkDiaryService.export_diary_excel(
        employee_id=emp1["employee_id"],
        employee_name=emp1["full_name"],
        filter_type="monthly",
        date_or_month="2026-10"
    )
    assert isinstance(monthly_stream, io.BytesIO)
    monthly_wb = openpyxl.load_workbook(monthly_stream)
    sheet_m = monthly_wb.active
    assert "AI Samrat Pvt Ltd" in sheet_m["A1"].value
    assert "CONFIDENTIAL EMPLOYEE WORK DIARY REPORT" in sheet_m["A2"].value
    assert emp1["employee_id"] in sheet_m["A3"].value
