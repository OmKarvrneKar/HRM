import sys
import os

print("--- AI Samrat HRMS Diagnostic Check ---")

# 1. Check if core files exist
core_files = [
    'app.py',
    'config.py',
    'requirements.txt',
    'dist/index.html',
    'assets/img/ai_samrat_logo.jpeg',
]
for f in core_files:
    exists = os.path.exists(f)
    print(f"[{'PASS' if exists else 'FAIL'}] Core file '{f}' present: {exists}")

# 2. Test Flask App Initialization and Routes
try:
    from app import app
    print("[PASS] Flask app imported successfully.")

    with app.test_client() as client:
        health = client.get('/api/health')
        print(f"[{'PASS' if health.status_code == 200 else 'FAIL'}] /api/health status: {health.status_code}")

        response = client.get('/login')
        print(f"[{'PASS' if response.status_code == 200 else 'FAIL'}] /login SPA route status: {response.status_code}")

except Exception as e:
    print(f"[FAIL] Error loading Flask app or testing routes: {e}")

print("---------------------------------------")