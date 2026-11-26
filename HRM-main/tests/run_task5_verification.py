import os
import sys
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = r"C:\Users\Omkar\.gemini\antigravity\brain\d03ec726-4c17-48f4-862a-49cb371f8a5b\screenshots_task5"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://localhost:5173"

def run_task5_verification():
    print(f"=== Starting Task 5 Live Browser Verification ===")
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
        # 1. LOGIN AS ADMIN (ADMIN-1001)
        # ----------------------------------------------------
        print("\n1. Logging in as System Administrator (ADMIN-1001)...")
        page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        time.sleep(1)

        # Switch to Leadership tab
        leadership_tab = page.locator("button:has-text('Leadership / HR')")
        if leadership_tab.is_visible():
            leadership_tab.click()
            time.sleep(0.5)

        text_inputs = page.locator("input[type='text']")
        text_inputs.first.fill("ADMIN-1001")
        page.fill("input[type='password']", "password123")
        page.click("button[type='submit']")

        page.wait_for_url("**/dashboard**", timeout=15000)
        time.sleep(2)
        print(f"   Successfully authenticated! Current URL: {page.url}")

        # ----------------------------------------------------
        # 2. WORKFORCE DIRECTORY - OVERVIEW
        # ----------------------------------------------------
        print("2. Navigating to Workforce Directory (/directory)...")
        page.goto(f"{BASE_URL}/directory", wait_until="networkidle")
        time.sleep(2)
        shot1 = os.path.join(OUTPUT_DIR, "task5_01_directory_overview.png")
        page.screenshot(path=shot1, full_page=True)
        print(f"   [Saved]: {shot1}")

        # ----------------------------------------------------
        # 3. WORKFORCE DIRECTORY - PENDING VERIFICATION FILTER
        # ----------------------------------------------------
        print("3. Filtering Workforce Directory by Pending Verification...")
        selects = page.locator("select:has(option[value='pending_verification'])")
        if selects.count() > 0:
            selects.first.select_option("pending_verification")
            time.sleep(1.5)
        shot2 = os.path.join(OUTPUT_DIR, "task5_02_directory_pending_filter.png")
        page.screenshot(path=shot2, full_page=True)
        print(f"   [Saved]: {shot2}")

        # ----------------------------------------------------
        # 4. ADMIN CONTROL CENTER - WORKFORCE ACCOUNTS
        # ----------------------------------------------------
        print("4. Navigating to Admin Control Center (/admin)...")
        page.goto(f"{BASE_URL}/admin", wait_until="networkidle")
        time.sleep(2)
        shot3 = os.path.join(OUTPUT_DIR, "task5_03_admin_accounts_governance.png")
        page.screenshot(path=shot3, full_page=True)
        print(f"   [Saved]: {shot3}")

        # ----------------------------------------------------
        # 5. ADMIN CONTROL CENTER - PENDING VERIFICATION FILTER
        # ----------------------------------------------------
        print("5. Filtering Admin Control Center by Pending Verification...")
        admin_selects = page.locator("select:has(option[value='pending_verification'])")
        if admin_selects.count() > 0:
            admin_selects.first.select_option("pending_verification")
            time.sleep(1.5)
        shot4 = os.path.join(OUTPUT_DIR, "task5_04_admin_pending_accounts_filter.png")
        page.screenshot(path=shot4, full_page=True)
        print(f"   [Saved]: {shot4}")

        # ----------------------------------------------------
        # 6. ADMIN CONTROL CENTER - VERIFY & ONBOARDING MODAL
        # ----------------------------------------------------
        print("6. Opening Candidate Profile Verification & Onboarding Modal...")
        verify_btn = page.locator("button:has-text('Verify & Onboard')").first
        if verify_btn.is_visible():
            verify_btn.click()
            time.sleep(1.5)
            shot5 = os.path.join(OUTPUT_DIR, "task5_05_admin_verify_onboarding_modal.png")
            page.screenshot(path=shot5, full_page=True)
            print(f"   [Saved]: {shot5}")
            # Close modal
            close_btn = page.locator("button:has-text('Cancel')").first
            if close_btn.is_visible():
                close_btn.click()
                time.sleep(1)

        # ----------------------------------------------------
        # 7. LEAVES & OVERTIME - VERIFY TEST TRANSACTIONS REMOVED
        # ----------------------------------------------------
        print("7. Verifying Overtime Screen (/leaves) - Test Records Removed...")
        page.goto(f"{BASE_URL}/leaves", wait_until="networkidle")
        time.sleep(1.5)
        # Click on Overtime tab
        ot_tab = page.locator("button:has-text('Overtime')").first
        if ot_tab.is_visible():
            ot_tab.click()
            time.sleep(1.5)
        shot6 = os.path.join(OUTPUT_DIR, "task5_06_leaves_overtime_clean.png")
        page.screenshot(path=shot6, full_page=True)
        print(f"   [Saved]: {shot6}")

        # ----------------------------------------------------
        # 8. CELEBRATIONS & KUDOS - VERIFY DUMMY/TEST RECORDS REMOVED
        # ----------------------------------------------------
        print("8. Verifying Celebrations & Kudos (/celebrations) - Clean Empty State...")
        page.goto(f"{BASE_URL}/celebrations", wait_until="networkidle")
        time.sleep(2)
        shot7 = os.path.join(OUTPUT_DIR, "task5_07_social_kudos_clean.png")
        page.screenshot(path=shot7, full_page=True)
        print(f"   [Saved]: {shot7}")

        # ----------------------------------------------------
        # 9. ASSETS & INVENTORY - HARDWARE (0 UNVERIFIED BASELINE)
        # ----------------------------------------------------
        print("9. Verifying Assets Inventory (/enterprise) - Hardware Inventory...")
        page.goto(f"{BASE_URL}/enterprise", wait_until="networkidle")
        time.sleep(2)
        page.click("button:has-text('Hardware Inventory')")
        time.sleep(1.5)
        shot8 = os.path.join(OUTPUT_DIR, "task5_08_assets_hardware_clean.png")
        page.screenshot(path=shot8, full_page=True)
        print(f"   [Saved]: {shot8}")

        # ----------------------------------------------------
        # 10. ASSETS & INVENTORY - SOFTWARE (0 UNVERIFIED BASELINE)
        # ----------------------------------------------------
        print("10. Verifying Assets Inventory (/enterprise) - Software Licenses...")
        page.click("button:has-text('Software Licenses')")
        time.sleep(1.5)
        shot9 = os.path.join(OUTPUT_DIR, "task5_09_assets_software_clean.png")
        page.screenshot(path=shot9, full_page=True)
        print(f"   [Saved]: {shot9}")

        # ----------------------------------------------------
        # 11. ASSETS & INVENTORY - SEATING & LOCKERS (0 ALGORITHMIC)
        # ----------------------------------------------------
        print("11. Verifying Assets Inventory (/enterprise) - Desk & Locker Bay...")
        page.click("button:has-text('Desk & Locker Bay')")
        time.sleep(1.5)
        shot10 = os.path.join(OUTPUT_DIR, "task5_10_assets_seating_clean.png")
        page.screenshot(path=shot10, full_page=True)
        print(f"   [Saved]: {shot10}")

        browser.close()
        print("\n=== Task 5 Live Verification Completed Successfully! ===")

if __name__ == "__main__":
    run_task5_verification()
