import os
import sys
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = r"C:\Users\Omkar\.gemini\antigravity\brain\d03ec726-4c17-48f4-862a-49cb371f8a5b\screenshots"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://localhost:5173"

def run_verification():
    print(f"=== Starting Task 3 Live Playwright Verification ===")
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
        # 1. LOGIN SCREEN
        # ----------------------------------------------------
        print("\n1. Navigating to Login Page...")
        page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        time.sleep(1)
        login_shot = os.path.join(OUTPUT_DIR, "01_login_screen.png")
        page.screenshot(path=login_shot, full_page=True)
        print(f"   [Screenshot saved]: {login_shot}")

        # ----------------------------------------------------
        # 2. LOGIN AS EMPLOYEE (AS-1019) & EMPLOYEE DASHBOARD
        # ----------------------------------------------------
        print("\n2. Logging in as Employee (AS-1019)...")
        page.fill("input[type='text']", "AS-1019")
        page.fill("input[type='password']", "password123")
        page.click("button[type='submit']")
        
        # Wait for dashboard to load
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=15000)
        time.sleep(2)
        emp_dash_shot = os.path.join(OUTPUT_DIR, "02_employee_dashboard.png")
        page.screenshot(path=emp_dash_shot, full_page=True)
        print(f"   [Screenshot saved]: {emp_dash_shot}")

        # ----------------------------------------------------
        # 3. LEAVES & OVERTIME (TASK 2 VERIFICATION)
        # ----------------------------------------------------
        print("\n3. Testing Leaves, WFH & Overtime (/leaves)...")
        page.goto(f"{BASE_URL}/leaves", wait_until="networkidle")
        time.sleep(1.5)
        
        # Click Overtime Log tab
        page.click("button:has-text('Overtime Log')")
        time.sleep(1)

        # Open Overtime Modal and submit request
        print("   Submitting new Overtime Request...")
        # Look for Log Overtime or Request Overtime button
        ot_btn = page.locator("button:has-text('Request Overtime'), button:has-text('Log Overtime')").first
        ot_btn.click()
        time.sleep(0.5)

        # Fill modal form
        page.fill("input[type='date']", "2026-11-26")
        page.fill("textarea", "Automated Task 3 Live Playwright OT Verification")
        page.click("button:has-text('Submit Overtime Request')")
        time.sleep(2)

        ot_shot = os.path.join(OUTPUT_DIR, "03_leaves_overtime_portal.png")
        page.screenshot(path=ot_shot, full_page=True)
        print(f"   [Screenshot saved]: {ot_shot}")

        # ----------------------------------------------------
        # 4. ENTERPRISE ASSETS (TASK 2 VERIFICATION)
        # ----------------------------------------------------
        print("\n4. Testing Enterprise Assets (/enterprise)...")
        page.goto(f"{BASE_URL}/enterprise", wait_until="networkidle")
        time.sleep(1.5)

        # Hardware Tab
        hw_shot = os.path.join(OUTPUT_DIR, "04_assets_hardware_inventory.png")
        page.screenshot(path=hw_shot, full_page=True)
        print(f"   [Screenshot saved]: {hw_shot}")

        # Software Tab
        print("   Switching to Software Licenses tab...")
        page.click("button:has-text('Software Licenses')")
        time.sleep(1)
        sw_shot = os.path.join(OUTPUT_DIR, "05_assets_software_licenses.png")
        page.screenshot(path=sw_shot, full_page=True)
        print(f"   [Screenshot saved]: {sw_shot}")

        # Seating & Lockers Tab
        print("   Switching to Desk & Locker Bay tab...")
        page.click("button:has-text('Desk & Locker Bay')")
        time.sleep(1)
        seat_shot = os.path.join(OUTPUT_DIR, "06_assets_seating_lockers.png")
        page.screenshot(path=seat_shot, full_page=True)
        print(f"   [Screenshot saved]: {seat_shot}")

        # ----------------------------------------------------
        # 5. CELEBRATIONS & KUDOS WALL (TASK 2 VERIFICATION)
        # ----------------------------------------------------
        print("\n5. Testing Celebrations & Kudos Wall (/celebrations)...")
        page.goto(f"{BASE_URL}/celebrations", wait_until="networkidle")
        time.sleep(1.5)

        # Give Kudos Modal
        print("   Giving Kudos to AS-1001...")
        page.click("button:has-text('Give Kudos Points')")
        time.sleep(0.5)
        page.fill("input[placeholder*='AS-1019']", "AS-1001")
        page.fill("textarea[placeholder*='contribution stand out']", "Live browser automated verification recognition for exemplary sprint teamwork!")
        page.click("button:has-text('Post Appreciation')")
        time.sleep(2)

        kudos_shot = os.path.join(OUTPUT_DIR, "07_celebrations_kudos_wall.png")
        page.screenshot(path=kudos_shot, full_page=True)
        print(f"   [Screenshot saved]: {kudos_shot}")

        # ----------------------------------------------------
        # 6. MANAGER DASHBOARD (MGR-1001)
        # ----------------------------------------------------
        print("\n6. Logging in as Manager (MGR-1001)...")
        # Clear cookies/session
        context.clear_cookies()
        page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        page.click("button:has-text('Leadership / HR')")
        time.sleep(0.5)
        page.fill("input[type='text']", "MGR-1001")
        page.fill("input[type='password']", "password123")
        page.click("button[type='submit']")
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=15000)
        time.sleep(2)
        mgr_shot = os.path.join(OUTPUT_DIR, "08_manager_dashboard.png")
        page.screenshot(path=mgr_shot, full_page=True)
        print(f"   [Screenshot saved]: {mgr_shot}")

        # ----------------------------------------------------
        # 7. HR DASHBOARD (HR-1001)
        # ----------------------------------------------------
        print("\n7. Logging in as HR (HR-1001)...")
        context.clear_cookies()
        page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        page.click("button:has-text('Leadership / HR')")
        time.sleep(0.5)
        page.fill("input[type='text']", "HR-1001")
        page.fill("input[type='password']", "password123")
        page.click("button[type='submit']")
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=15000)
        time.sleep(2)
        hr_shot = os.path.join(OUTPUT_DIR, "09_hr_dashboard.png")
        page.screenshot(path=hr_shot, full_page=True)
        print(f"   [Screenshot saved]: {hr_shot}")

        # ----------------------------------------------------
        # 8. ADMIN DASHBOARD & CONTROL CENTER (ADMIN-1001)
        # ----------------------------------------------------
        print("\n8. Logging in as Admin (ADMIN-1001)...")
        context.clear_cookies()
        page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        page.click("button:has-text('Leadership / HR')")
        time.sleep(0.5)
        page.fill("input[type='text']", "ADMIN-1001")
        page.fill("input[type='password']", "password123")
        page.click("button[type='submit']")
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=15000)
        time.sleep(2)
        admin_dash_shot = os.path.join(OUTPUT_DIR, "10_admin_dashboard.png")
        page.screenshot(path=admin_dash_shot, full_page=True)
        print(f"   [Screenshot saved]: {admin_dash_shot}")

        # Admin Control Center
        print("   Navigating to Admin Control Center (/admin)...")
        page.goto(f"{BASE_URL}/admin", wait_until="networkidle")
        time.sleep(1.5)
        admin_ctrl_shot = os.path.join(OUTPUT_DIR, "11_admin_control_center.png")
        page.screenshot(path=admin_ctrl_shot, full_page=True)
        print(f"   [Screenshot saved]: {admin_ctrl_shot}")

        # Workforce Directory
        print("   Navigating to Workforce Directory (/directory)...")
        page.goto(f"{BASE_URL}/directory", wait_until="networkidle")
        time.sleep(1.5)
        dir_shot = os.path.join(OUTPUT_DIR, "12_workforce_directory.png")
        page.screenshot(path=dir_shot, full_page=True)
        print(f"   [Screenshot saved]: {dir_shot}")

        # Payroll Center
        print("   Navigating to Payroll Center (/payroll)...")
        page.goto(f"{BASE_URL}/payroll", wait_until="networkidle")
        time.sleep(1.5)
        payroll_shot = os.path.join(OUTPUT_DIR, "13_payroll_center.png")
        page.screenshot(path=payroll_shot, full_page=True)
        print(f"   [Screenshot saved]: {payroll_shot}")

        browser.close()
        print("\n=== All Live Playwright Verifications & Screenshots Completed Successfully! ===")

if __name__ == "__main__":
    run_verification()

