import os
import sys
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = r"C:\Users\Omkar\.gemini\antigravity\brain\d03ec726-4c17-48f4-862a-49cb371f8a5b\screenshots_task8"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://localhost:5173"

def run_task8_verification():
    print("=== Starting Task 8 Live Browser Verification ===")
    print(f"Screenshots directory: {OUTPUT_DIR}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME_PATH,
            headless=True,
            args=["--disable-web-security", "--no-sandbox"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 950})
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
        # 2. ENTERPRISE ASSETS & KPI STATCARDS (/enterprise)
        # ----------------------------------------------------
        print("\n2. Navigating to Enterprise Assets (/enterprise)...")
        page.goto(f"{BASE_URL}/enterprise", wait_until="networkidle")
        time.sleep(2)

        shot1 = os.path.join(OUTPUT_DIR, "task8_01_kpi_statcards_distinguished.png")
        page.screenshot(path=shot1, full_page=False)
        print(f"   [Saved]: {shot1}")

        # ----------------------------------------------------
        # 3. MEETING ROOMS TAB - VERIFIED VS UNVERIFIED
        # ----------------------------------------------------
        print("\n3. Navigating to Meeting Rooms Tab...")
        page.click("button:has-text('Meeting Rooms')")
        time.sleep(1.5)

        shot2 = os.path.join(OUTPUT_DIR, "task8_02_meeting_rooms_distinguished.png")
        page.screenshot(path=shot2, full_page=True)
        print(f"   [Saved]: {shot2}")

        # ----------------------------------------------------
        # 4. VERIFY FACILITY MODAL INTERACTION
        # ----------------------------------------------------
        print("\n4. Opening Verify Facility Modal for an unverified room...")
        verify_room_btn = page.locator("button:has-text('Verify Facility')").first
        if verify_room_btn.is_visible():
            verify_room_btn.click()
            time.sleep(1)
            shot4 = os.path.join(OUTPUT_DIR, "task8_04_verify_facility_modal.png")
            page.screenshot(path=shot4, full_page=False)
            print(f"   [Saved]: {shot4}")
            # Close the modal using Cancel button
            page.click("button:has-text('Cancel')")
            time.sleep(1)

        # ----------------------------------------------------
        # 5. DESK & LOCKER BAY REGISTRY
        # ----------------------------------------------------
        print("\n5. Navigating to Desk & Locker Bay Registry...")
        page.click("button:has-text('Desk & Locker Bay')")
        time.sleep(1.5)

        shot3 = os.path.join(OUTPUT_DIR, "task8_03_seating_provisional_registry.png")
        page.screenshot(path=shot3, full_page=True)
        print(f"   [Saved]: {shot3}")

        browser.close()
        print("\n=== Task 8 Live Verification Completed Successfully! ===")

if __name__ == "__main__":
    run_task8_verification()

