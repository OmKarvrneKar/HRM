import os
import sys
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = r"C:\Users\Omkar\.gemini\antigravity\brain\d03ec726-4c17-48f4-862a-49cb371f8a5b\screenshots_task4"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://localhost:5173"

def run_task4_verification():
    print(f"=== Starting Task 4 Live Browser Verification ===")
    print(f"Screenshots directory: {OUTPUT_DIR}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME_PATH,
            headless=True,
            args=["--disable-web-security", "--no-sandbox"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # ----------------------------------------------------
        # 1. LOGIN AS EMPLOYEE (AS-1019) & PAYROLL AUDIT
        # ----------------------------------------------------
        print("\n1. Logging in as Employee Deepak S J (AS-1019)...")
        page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        time.sleep(1)
        page.fill("input[type='text']", "AS-1019")
        page.fill("input[type='password']", "password123")
        page.click("button[type='submit']")
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=15000)
        time.sleep(1.5)

        print("2. Verifying Payroll (/payroll) - Honest Empty States & No Fallback Numbers...")
        page.goto(f"{BASE_URL}/payroll", wait_until="networkidle")
        time.sleep(2)
        shot1 = os.path.join(OUTPUT_DIR, "task4_01_payroll_unconfigured.png")
        page.screenshot(path=shot1, full_page=True)
        print(f"   [Saved]: {shot1}")

        # ----------------------------------------------------
        # 2. CELEBRATIONS & HOLIDAY CALENDAR (HONEST EMPTY STATE)
        # ----------------------------------------------------
        print("3. Verifying Celebrations & Holiday Calendar (/celebrations)...")
        page.goto(f"{BASE_URL}/celebrations", wait_until="networkidle")
        time.sleep(2)
        shot2 = os.path.join(OUTPUT_DIR, "task4_02_celebrations_honest_holidays.png")
        page.screenshot(path=shot2, full_page=True)
        print(f"   [Saved]: {shot2}")

        # ----------------------------------------------------
        # 3. ASSETS & FACILITIES: HARDWARE (UNVERIFIED BASELINE BADGES)
        # ----------------------------------------------------
        print("4. Verifying Assets Inventory (/enterprise) - Hardware Tab...")
        page.goto(f"{BASE_URL}/enterprise", wait_until="networkidle")
        time.sleep(2)
        page.click("button:has-text('Hardware Inventory')")
        time.sleep(1)
        shot3 = os.path.join(OUTPUT_DIR, "task4_03_assets_hardware_unverified_baseline.png")
        page.screenshot(path=shot3, full_page=True)
        print(f"   [Saved]: {shot3}")

        # ----------------------------------------------------
        # 4. ASSETS & FACILITIES: SOFTWARE (UNVERIFIED BASELINE BADGES)
        # ----------------------------------------------------
        print("5. Verifying Assets Inventory (/enterprise) - Software Tab...")
        page.click("button:has-text('Software Licenses')")
        time.sleep(1)
        shot4 = os.path.join(OUTPUT_DIR, "task4_04_assets_software_unverified_baseline.png")
        page.screenshot(path=shot4, full_page=True)
        print(f"   [Saved]: {shot4}")

        # ----------------------------------------------------
        # 5. ASSETS & FACILITIES: SEATING ALLOCATIONS (ALGORITHMIC)
        # ----------------------------------------------------
        print("6. Verifying Assets Inventory (/enterprise) - Desk & Locker Bay Tab...")
        page.click("button:has-text('Desk & Locker Bay')")
        time.sleep(1)
        shot5 = os.path.join(OUTPUT_DIR, "task4_05_assets_seating_algorithmic.png")
        page.screenshot(path=shot5, full_page=True)
        print(f"   [Saved]: {shot5}")

        # ----------------------------------------------------
        # 6. SKILL MATRIX VIEW (DYNAMIC TAXONOMY)
        # ----------------------------------------------------
        print("7. Verifying Skill Matrix (/skills)...")
        page.goto(f"{BASE_URL}/skills", wait_until="networkidle")
        time.sleep(2)
        shot6 = os.path.join(OUTPUT_DIR, "task4_06_skills_matrix_dynamic.png")
        page.screenshot(path=shot6, full_page=True)
        print(f"   [Saved]: {shot6}")

        # Clear session
        context.clear_cookies()

        # ----------------------------------------------------
        # 7. MANAGER DASHBOARD (MGR-1001) - SPRINT VELOCITY & TEAM ATTENDANCE
        # ----------------------------------------------------
        print("\n8. Logging in as Manager Vikramaditya Roy (MGR-1001)...")
        page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        time.sleep(1)
        # Switch to Leadership tab
        tabs = page.query_selector_all("button")
        for t in tabs:
            if "Leadership" in (t.text_content() or ""):
                t.click()
                break
        time.sleep(0.5)

        page.fill("input[type='text']", "MGR-1001")
        page.fill("input[type='password']", "password123")
        page.click("button[type='submit']")
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=15000)
        time.sleep(2)
        shot7 = os.path.join(OUTPUT_DIR, "task4_07_manager_dashboard_real_metrics.png")
        page.screenshot(path=shot7, full_page=True)
        print(f"   [Saved]: {shot7}")

        # Clear session
        context.clear_cookies()

        # ----------------------------------------------------
        # 8. HR DASHBOARD (HR-1001) - REAL DAILY ATTENDANCE PERCENTAGE
        # ----------------------------------------------------
        print("\n9. Logging in as HR Ramya (HR-1001)...")
        page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        time.sleep(1)
        tabs = page.query_selector_all("button")
        for t in tabs:
            if "Leadership" in (t.text_content() or ""):
                t.click()
                break
        time.sleep(0.5)

        page.fill("input[type='text']", "HR-1001")
        page.fill("input[type='password']", "password123")
        page.click("button[type='submit']")
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=15000)
        time.sleep(2)
        shot8 = os.path.join(OUTPUT_DIR, "task4_08_hr_dashboard_real_attendance.png")
        page.screenshot(path=shot8, full_page=True)
        print(f"   [Saved]: {shot8}")

        # Clear session
        context.clear_cookies()

        # ----------------------------------------------------
        # 9. ADMIN CONTROL CENTER (ADMIN-1001) - ALL 5 TABS
        # ----------------------------------------------------
        print("\n10. Logging in as System Administrator (ADMIN-1001)...")
        page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        time.sleep(1)
        tabs = page.query_selector_all("button")
        for t in tabs:
            if "Leadership" in (t.text_content() or ""):
                t.click()
                break
        time.sleep(0.5)

        page.fill("input[type='text']", "ADMIN-1001")
        page.fill("input[type='password']", "password123")
        page.click("button[type='submit']")
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=15000)
        time.sleep(1.5)

        print("11. Navigating to Admin Control Center (/admin)...")
        page.goto(f"{BASE_URL}/admin", wait_until="networkidle")
        time.sleep(2)

        # Tab 1: Workforce Accounts
        page.click("button:has-text('Workforce Accounts')")
        time.sleep(1)
        shot9 = os.path.join(OUTPUT_DIR, "task4_09_admin_accounts_governance.png")
        page.screenshot(path=shot9, full_page=True)
        print(f"   [Saved]: {shot9}")

        # Tab 2: Holiday Calendar Configuration
        page.click("button:has-text('Holiday Calendar')")
        time.sleep(1)
        shot10 = os.path.join(OUTPUT_DIR, "task4_10_admin_holiday_calendar_mgmt.png")
        page.screenshot(path=shot10, full_page=True)
        print(f"   [Saved]: {shot10}")

        # Tab 3: Skill Matrix Tracks Configuration
        page.click("button:has-text('Skill Matrix Tracks')")
        time.sleep(1)
        shot11 = os.path.join(OUTPUT_DIR, "task4_11_admin_skill_matrix_mgmt.png")
        page.screenshot(path=shot11, full_page=True)
        print(f"   [Saved]: {shot11}")

        # Tab 4: Compensation Setup
        page.click("button:has-text('Compensation Setup')")
        time.sleep(1)
        shot12 = os.path.join(OUTPUT_DIR, "task4_12_admin_compensation_setup.png")
        page.screenshot(path=shot12, full_page=True)
        print(f"   [Saved]: {shot12}")

        # Tab 5: Real vs Baseline Audit
        page.click("button:has-text('Real vs Baseline Audit')")
        time.sleep(1)
        shot13 = os.path.join(OUTPUT_DIR, "task4_13_admin_data_audit_overview.png")
        page.screenshot(path=shot13, full_page=True)
        print(f"   [Saved]: {shot13}")

        browser.close()
        print("\n=== Task 4 Live Browser Verification Complete! ===")
        print(f"All 13 screenshots successfully generated in: {OUTPUT_DIR}")

if __name__ == "__main__":
    run_task4_verification()

