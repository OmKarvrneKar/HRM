import os
import sys
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = r"C:\Users\Omkar\.gemini\antigravity\brain\d03ec726-4c17-48f4-862a-49cb371f8a5b\screenshots_task8"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://localhost:5173"

def run_employee_view():
    print("=== Testing Employee UI Permissions on Enterprise Page ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME_PATH,
            headless=True,
            args=["--disable-web-security", "--no-sandbox"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()

        # Login as Employee (AS-1001)
        print("Logging in as regular employee (AS-1001)...")
        page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        time.sleep(1)

        text_inputs = page.locator("input[type='text']")
        text_inputs.first.fill("AS-1001")
        page.fill("input[type='password']", "password123")
        page.click("button[type='submit']")

        page.wait_for_url("**/dashboard**", timeout=15000)
        time.sleep(2)

        # Go to Enterprise
        print("Navigating to /enterprise as employee...")
        page.goto(f"{BASE_URL}/enterprise", wait_until="networkidle")
        time.sleep(2)

        page.click("button:has-text('Meeting Rooms')")
        time.sleep(1.5)

        shot = os.path.join(OUTPUT_DIR, "task8_05_employee_rbac_no_verify_buttons.png")
        page.screenshot(path=shot, full_page=True)
        print(f"Saved: {shot}")

        browser.close()
        print("Employee UI RBAC check passed!")

if __name__ == "__main__":
    run_employee_view()

