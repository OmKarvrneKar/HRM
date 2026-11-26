import urllib.request
import urllib.parse
import json
import http.cookiejar

cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

# 1. Login as Rahul Sharma
login_payload = json.dumps({
    'email': 'emp.rahul@aisamrat.com',
    'password': 'Emp@Rahul2026!',
    'selected_role': 'employee'
}).encode('utf-8')

req = urllib.request.Request(
    'http://localhost:5000/api/auth/login',
    data=login_payload,
    headers={'Content-Type': 'application/json'},
    method='POST'
)
res = opener.open(req)
assert res.status == 200, f'Login failed: {res.status}'
print('[1] Employee Login Successful (HTTP 200)')

# 2. Check initial attendance status
req = urllib.request.Request('http://localhost:5000/api/attendance/today')
res = opener.open(req)
data = json.loads(res.read().decode())
print(f"[2] Current Attendance Status: has_open_session = {data.get('has_open_session')}")

# If already clocked in, clock out first to start clean
if data.get('has_open_session'):
    req = urllib.request.Request(
        'http://localhost:5000/api/attendance/check-out',
        data=b'{}',
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    opener.open(req)
    print('    (Reset active session to ensure clean test sequence)')

# 3. Perform Clock In
req = urllib.request.Request(
    'http://localhost:5000/api/attendance/check-in',
    data=b'{}',
    headers={'Content-Type': 'application/json'},
    method='POST'
)
res = opener.open(req)
in_data = json.loads(res.read().decode())
assert in_data.get('success') is True, f'Check-in failed: {in_data}'
print(f"[3] Clock In Succeeded (HTTP 200) Session ID: {in_data.get('session_id')}")

# 4. Verify Dashboard endpoint sees Clocked In
res = opener.open('http://localhost:5000/api/attendance/today')
dash_data = json.loads(res.read().decode())
assert dash_data.get('has_open_session') is True
assert dash_data.get('is_clocked_in') is True
first_in = dash_data.get('first_login_local')
print(f'[4] Dashboard verified: Clocked In = True, First Login Time = {first_in}')

# 5. Verify Attendance Calendar endpoint sees Clocked In with exact same time
today_y, today_m = dash_data['today_date'].split('-')[:2]
res = opener.open(f'http://localhost:5000/api/attendance/calendar?year={today_y}&month={int(today_m)}')
cal_data = json.loads(res.read().decode())
today_cell = next(d for d in cal_data['days'] if d['date'] == dash_data['today_date'])
assert today_cell.get('has_open_session') is True
assert today_cell.get('first_login_local') == first_in
print(f"[5] Attendance Calendar verified: Clocked In = True, Cell Time = {today_cell.get('first_login_local')}")

# 6. Verify duplicate Clock In rejection (Idempotency / State Transition guard)
try:
    req = urllib.request.Request(
        'http://localhost:5000/api/attendance/check-in',
        data=b'{}',
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    opener.open(req)
    raise AssertionError('Duplicate clock in should have raised HTTP 400')
except urllib.error.HTTPError as e:
    assert e.code == 400
    err_body = json.loads(e.read().decode())
    print(f"[6] Duplicate Clock In successfully rejected (HTTP 400): {err_body.get('error')}")

# 7. Perform Clock Out
req = urllib.request.Request(
    'http://localhost:5000/api/attendance/check-out',
    data=b'{}',
    headers={'Content-Type': 'application/json'},
    method='POST'
)
res = opener.open(req)
out_data = json.loads(res.read().decode())
assert out_data.get('success') is True
print('[7] Clock Out Succeeded (HTTP 200)')

# 8. Verify Dashboard endpoint sees Clocked Out
res = opener.open('http://localhost:5000/api/attendance/today')
dash_after = json.loads(res.read().decode())
assert dash_after.get('has_open_session') is False
assert dash_after.get('is_clocked_in') is False
print('[8] Dashboard verified: Clocked Out = True')

# 9. Verify Attendance Calendar sees Clocked Out
res = opener.open(f'http://localhost:5000/api/attendance/calendar?year={today_y}&month={int(today_m)}')
cal_after = json.loads(res.read().decode())
today_cell_after = next(d for d in cal_after['days'] if d['date'] == dash_data['today_date'])
assert today_cell_after.get('has_open_session') is False
print(f"[9] Attendance Calendar verified: Clocked Out = True, Duration = {today_cell_after.get('duration_display')}")

# 10. Verify duplicate Clock Out rejection
try:
    req = urllib.request.Request(
        'http://localhost:5000/api/attendance/check-out',
        data=b'{}',
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    opener.open(req)
    raise AssertionError('Duplicate clock out should have raised HTTP 400')
except urllib.error.HTTPError as e:
    assert e.code == 400
    err_body = json.loads(e.read().decode())
    print(f"[10] Duplicate Clock Out successfully rejected (HTTP 400): {err_body.get('error')}")

# 11. Verify Cross-Employee Tampering Protection
try:
    bad_payload = json.dumps({'employee_id': 'EMP-1005'}).encode('utf-8')
    req = urllib.request.Request(
        'http://localhost:5000/api/attendance/check-in',
        data=bad_payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    opener.open(req)
    raise AssertionError('Tampering should have raised HTTP 403')
except urllib.error.HTTPError as e:
    assert e.code == 403
    print('[11] Cross-Employee Clock In attempt rejected (HTTP 403 Forbidden)')

print('============================================================')
print('  ALL LIVE END-TO-END ATTENDANCE SYNCHRONIZATION TESTS PASSED')
print('============================================================')
