import os
import sys
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = r"C:\Users\Omkar\.gemini\antigravity\brain\d03ec726-4c17-48f4-862a-49cb371f8a5b\screenshots_task7"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://localhost:5173"

def run_task7_verification():
    print("=== Starting Task 7 Live Browser Verification ===")
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
        # 2. MEETING ROOMS DYNAMIC VERIFICATION (/enterprise)
        # ----------------------------------------------------
        print("\n2. Navigating to Enterprise Facilities - Meeting Rooms Tab...")
        page.goto(f"{BASE_URL}/enterprise", wait_until="networkidle")
        time.sleep(2)

        page.click("button:has-text('Meeting Rooms')")
        time.sleep(1.5)
        shot1 = os.path.join(OUTPUT_DIR, "task7_01_meeting_rooms_unverified_actual.png")
        page.screenshot(path=shot1, full_page=True)
        print(f"   [Saved]: {shot1}")

        # ----------------------------------------------------
        # 3. SEATING ALLOCATIONS REGISTRY (/enterprise)
        # ----------------------------------------------------
        print("\n3. Checking Desk & Locker Bay Registry...")
        page.click("button:has-text('Desk & Locker Bay')")
        time.sleep(1.5)
        shot2 = os.path.join(OUTPUT_DIR, "task7_02_seating_allocations_unverified_registry.png")
        page.screenshot(path=shot2, full_page=True)
        print(f"   [Saved]: {shot2}")

        # ----------------------------------------------------
        # 4. ADMIN CONTROL CENTER - ONBOARDING CONTROLS
        # ----------------------------------------------------
        print("\n4. Checking Admin Control Center Safety Controls (/admin)...")
        page.goto(f"{BASE_URL}/admin", wait_until="networkidle")
        time.sleep(2)

        admin_selects = page.locator("select:has(option[value='pending_verification'])")
        if admin_selects.count() > 0:
            admin_selects.first.select_option("pending_verification")
            time.sleep(1.5)

        shot3 = os.path.join(OUTPUT_DIR, "task7_03_admin_onboarding_safety_controls.png")
        page.screenshot(path=shot3, full_page=True)
        print(f"   [Saved]: {shot3}")

        browser.close()
        print("\n=== Task 7 Live Verification Completed Successfully! ===")

if __name__ == "__main__":
    run_task7_verification()

