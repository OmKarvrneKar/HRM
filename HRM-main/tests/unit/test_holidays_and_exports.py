import pytest
import zipfile
from backend.services.holiday_service import HolidayService
from backend.services.export_service import ExportService
from backend.services.salary_pdf_service import SalaryPDFService
from backend.services.user_service import UserService
from backend.permissions.rbac import Role


def test_standard_holidays_seeded(db):
    """Verifies that standard Indian public and national holidays are automatically seeded."""
    holidays = HolidayService.get_all_holidays(year=2026)
    assert len(holidays) >= 7
    holiday_names = [h["name"] for h in holidays]
    assert any("Republic Day" in n for n in holiday_names)
    assert any("Independence Day" in n for n in holiday_names)
    assert any("Gandhi Jayanti" in n for n in holiday_names)


def test_upcoming_holidays(db):
    """Verifies fetching upcoming organization holidays."""
    upcoming = HolidayService.get_upcoming_holidays(limit=5)
    assert isinstance(upcoming, list)


def test_hr_can_add_and_delete_holiday(db, seeded_users):
    """Authorized HR can declare a new organization holiday and remove it."""
    hr = seeded_users["hr"]
    holiday, err = HolidayService.add_holiday(
        actor=hr,
        date_str="2026-11-15",
        name="AI Samrat Foundation Day",
        holiday_type="Corporate"
    )
    assert err is None
    assert holiday["name"] == "AI Samrat Foundation Day"
    assert holiday["date"] == "2026-11-15"

    # Verify holiday appears in list
    all_h = HolidayService.get_all_holidays(year=2026)
    assert any(h["holiday_id"] == holiday["holiday_id"] for h in all_h)

    # Delete holiday
    deleted, del_err = HolidayService.delete_holiday(hr, holiday["holiday_id"])
    assert deleted is True
    assert del_err is None

    # Verify removed
    all_h_after = HolidayService.get_all_holidays(year=2026)
    assert not any(h["holiday_id"] == holiday["holiday_id"] for h in all_h_after)


def test_employee_cannot_add_holiday(db, seeded_users):
    """Regular employee is restricted from declaring organization holidays."""
    emp = seeded_users["emp1"]
    holiday, err = HolidayService.add_holiday(
        actor=emp,
        date_str="2026-07-20",
        name="Employee Unauthorized Holiday",
        holiday_type="Corporate"
    )
    assert holiday is None
    assert "Access Denied" in err


def test_salary_pdf_generation(seeded_users):
    """ReportLab payslip generator creates valid PDF stream with company seal."""
    emp = seeded_users["emp1"]
    slips = UserService.get_salary_slips(emp, count=1)
    assert len(slips) == 1

    pdf_buffer = SalaryPDFService.generate_payslip_pdf(slips[0])
    content = pdf_buffer.getvalue()
    assert len(content) > 1000
    assert content.startswith(b"%PDF")


def test_admin_zip_export(db, seeded_users):
    """ExportService creates a comprehensive ZIP file containing all major registers."""
    hr = seeded_users["hr"]
    zip_buffer = ExportService.export_administrative_zip(hr)
    assert zip_buffer is not None

    with zipfile.ZipFile(zip_buffer, "r") as z:
        names = z.namelist()
        assert "Attendance_Summary.xlsx" in names
        assert "Staff_Directory.xlsx" in names
        assert "Projects_Report.xlsx" in names
        assert "Leave_Requests.xlsx" in names
        assert "Holidays_Schedule.xlsx" in names
