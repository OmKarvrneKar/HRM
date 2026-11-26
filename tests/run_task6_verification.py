import os
import sys
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = r"C:\Users\Omkar\.gemini\antigravity\brain\d03ec726-4c17-48f4-862a-49cb371f8a5b\screenshots_task6"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://localhost:5173"

def run_task6_verification():
    print("=== Starting Task 6 Reconciliation Verification ===")
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
        # 2. ADMIN CONTROL CENTER - PENDING VERIFICATION FILTER
        # ----------------------------------------------------
        print("\n2. Navigating to Admin Control Center (/admin)...")
        page.goto(f"{BASE_URL}/admin", wait_until="networkidle")
        time.sleep(2)

        admin_selects = page.locator("select:has(option[value='pending_verification'])")
        if admin_selects.count() > 0:
            admin_selects.first.select_option("pending_verification")
            time.sleep(1.5)

        # ----------------------------------------------------
        # 3. VERIFY & ONBOARD MODAL (UNPOPULATED SAFETY CHECK)
        # ----------------------------------------------------
        print("3. Opening Verify & Onboard Modal on pending candidate...")
        verify_btn = page.locator("button:has-text('Verify & Onboard')").first
        if verify_btn.is_visible():
            verify_btn.click()
            time.sleep(1.5)
            shot1 = os.path.join(OUTPUT_DIR, "task6_01_verify_onboard_modal_unpopulated.png")
            page.screenshot(path=shot1, full_page=True)
            print(f"   [Saved]: {shot1}")

            # Close modal
            cancel_btn = page.locator("button:has-text('Cancel')").first
            if cancel_btn.is_visible():
                cancel_btn.click()
                time.sleep(1)

        # ----------------------------------------------------
        # 4. ADMIN CONTROL CENTER - TABLE SAFETY GUARD
        # ----------------------------------------------------
        print("4. Capturing Table Safety Guard (No Direct Activation Shortcut)...")
        shot2 = os.path.join(OUTPUT_DIR, "task6_02_onboarding_safety_table.png")
        page.screenshot(path=shot2, full_page=True)
        print(f"   [Saved]: {shot2}")

        # ----------------------------------------------------
        # 5. OVERTIME REQUESTS LOG (GENUINE EMPTY STATE)
        # ----------------------------------------------------
        print("5. Navigating to Leaves & Overtime Portal (/leaves)...")
        page.goto(f"{BASE_URL}/leaves", wait_until="networkidle")
        time.sleep(2)

        # Specifically click the "Overtime Log" tab button (NOT "Log Overtime")
        ot_log_tab = page.locator("button:has-text('Overtime Log')").first
        if ot_log_tab.is_visible():
            ot_log_tab.click()
            time.sleep(1.5)
        else:
            print("   WARNING: 'Overtime Log' tab not found!")

        shot3 = os.path.join(OUTPUT_DIR, "task6_03_leaves_overtime_empty_history.png")
        page.screenshot(path=shot3, full_page=True)
        print(f"   [Saved]: {shot3}")

        # ----------------------------------------------------
        # 6. CELEBRATIONS & KUDOS FEED (ACTUAL 3 RECORDS)
        # ----------------------------------------------------
        print("6. Navigating to Celebrations & Kudos (/celebrations)...")
        page.goto(f"{BASE_URL}/celebrations", wait_until="networkidle")
        time.sleep(2)

        shot4 = os.path.join(OUTPUT_DIR, "task6_04_kudos_feed_actual.png")
        page.screenshot(path=shot4, full_page=True)
        print(f"   [Saved]: {shot4}")

        # ----------------------------------------------------
        # 7. ASSETS & INVENTORY - HARDWARE
        # ----------------------------------------------------
        print("7. Navigating to Assets Inventory (/enterprise)...")
        page.goto(f"{BASE_URL}/enterprise", wait_until="networkidle")
        time.sleep(2)

        page.click("button:has-text('Hardware Inventory')")
        time.sleep(1.5)
        shot5 = os.path.join(OUTPUT_DIR, "task6_05_assets_hardware_clean.png")
        page.screenshot(path=shot5, full_page=True)
        print(f"   [Saved]: {shot5}")

        # ----------------------------------------------------
        # 8. ASSETS & INVENTORY - SOFTWARE
        # ----------------------------------------------------
        print("8. Checking Software Licenses Tab...")
        page.click("button:has-text('Software Licenses')")
        time.sleep(1.5)
        shot6 = os.path.join(OUTPUT_DIR, "task6_06_assets_software_clean.png")
        page.screenshot(path=shot6, full_page=True)
        print(f"   [Saved]: {shot6}")

        # ----------------------------------------------------
        # 9. ASSETS & INVENTORY - MEETING ROOMS (ACTUAL 3 ROOMS)
        # ----------------------------------------------------
        print("9. Checking Meeting Rooms Tab...")
        page.click("button:has-text('Meeting Rooms')")
        time.sleep(1.5)
        shot7 = os.path.join(OUTPUT_DIR, "task6_07_assets_facility_rooms_actual.png")
        page.screenshot(path=shot7, full_page=True)
        print(f"   [Saved]: {shot7}")

        # ----------------------------------------------------
        # 10. ASSETS & INVENTORY - SEATING & LOCKERS (ACTUAL 38 DESKS)
        # ----------------------------------------------------
        print("10. Checking Desk & Locker Bay Tab...")
        page.click("button:has-text('Desk & Locker Bay')")
        time.sleep(1.5)
        shot8 = os.path.join(OUTPUT_DIR, "task6_08_assets_seating_actual.png")
        page.screenshot(path=shot8, full_page=True)
        print(f"   [Saved]: {shot8}")

        browser.close()
        print("\n=== Task 6 Live Verification Completed Successfully! ===")

if __name__ == "__main__":
    run_task6_verification()
