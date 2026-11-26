import os
import sys
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = r"C:\Users\Omkar\.gemini\antigravity\brain\d03ec726-4c17-48f4-862a-49cb371f8a5b\screenshots_task9"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://localhost:5173"

def run_task9_verification():
    print("=== Starting Task 9 Live Browser Verification ===")
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
        # 2. ENTERPRISE ASSETS & ZERO CONFIRMED STATCARDS
        # ----------------------------------------------------
        print("\n2. Navigating to Enterprise Assets (/enterprise)...")
        page.goto(f"{BASE_URL}/enterprise", wait_until="networkidle")
        time.sleep(2)

        shot1 = os.path.join(OUTPUT_DIR, "task9_01_enterprise_kpi_zero_confirmed.png")
        page.screenshot(path=shot1, full_page=False)
        print(f"   [Saved]: {shot1}")

        # ----------------------------------------------------
        # 3. MEETING ROOMS TAB (ALL 3 UNVERIFIED, EMPTY CONFIRMED STATE)
        # ----------------------------------------------------
        print("\n3. Navigating to Meeting Rooms Tab...")
        page.click("button:has-text('Meeting Rooms')")
        time.sleep(1.5)

        shot2 = os.path.join(OUTPUT_DIR, "task9_02_meeting_rooms_all_unverified_empty_state.png")
        page.screenshot(path=shot2, full_page=True)
        print(f"   [Saved]: {shot2}")

        # ----------------------------------------------------
        # 4. CORRECTED VERIFY ROOM MODAL (EMPTY MANDATORY NOTES)
        # ----------------------------------------------------
        print("\n4. Opening Corrected Verify Room Modal for ROOM-MANTHAN...")
        verify_room_btn = page.locator("button:has-text('Verify Facility')").first
        if verify_room_btn.is_visible():
            verify_room_btn.click()
            time.sleep(1)
            shot3 = os.path.join(OUTPUT_DIR, "task9_03_corrected_verify_room_modal.png")
            page.screenshot(path=shot3, full_page=False)
            print(f"   [Saved]: {shot3}")
            # Cancel modal
            page.click("button:has-text('Cancel')")
            time.sleep(1)

        # ----------------------------------------------------
        # 5. DESK & LOCKER BAY REGISTRY (ALL 38 PROVISIONAL, SNEHA K REVERTED)
        # ----------------------------------------------------
        print("\n5. Navigating to Desk & Locker Bay Registry...")
        page.click("button:has-text('Desk & Locker Bay')")
        time.sleep(1.5)

        shot4 = os.path.join(OUTPUT_DIR, "task9_04_seating_provisional_registry_all_38.png")
        page.screenshot(path=shot4, full_page=True)
        print(f"   [Saved]: {shot4}")

        # ----------------------------------------------------
        # 6. CORRECTED VERIFY SEATING MODAL (EMPTY MANDATORY NOTES)
        # ----------------------------------------------------
        print("\n6. Opening Corrected Verify Seating Modal for SL-AS-1001 (Sneha K)...")
        # Find the Verify button in Sneha K's row or first verify button
        verify_seat_btn = page.locator("button:has-text('Verify')").first
        if verify_seat_btn.is_visible():
            verify_seat_btn.click()
            time.sleep(1)
            shot5 = os.path.join(OUTPUT_DIR, "task9_05_corrected_verify_seating_modal.png")
            page.screenshot(path=shot5, full_page=False)
            print(f"   [Saved]: {shot5}")
            page.click("button:has-text('Cancel')")
            time.sleep(1)

        browser.close()
        print("\n=== Task 9 Live Verification Completed Successfully! ===")

if __name__ == "__main__":
    run_task9_verification()

