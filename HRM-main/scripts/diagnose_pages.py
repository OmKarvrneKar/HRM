import urllib.request
import urllib.parse
import json
import http.cookiejar

accounts = [
    ("emp.rahul@aisamrat.com", "Emp@Rahul2026!", "employee"),
    ("hr.priya@aisamrat.com", "Hr@Priya2026!", "hr"),
    ("lead.kavita@aisamrat.com", "Lead@Kavita2026!", "employee"),
    ("trainer.rajesh@aisamrat.com", "Trainer@Rajesh2026!", "employee"),
    ("org@aisamrat.com", "Org@Samrat2026!", "hr"),
    ("admin@aisamrat.com", "Admin@Samrat2026!", "hr"),
    ("mgr@aisamrat.com", "Admin@Nexus2026!", "hr")
]

pages = [
    "/dashboard/employee",
    "/dashboard/hr",
    "/dashboard/hr-manager",
    "/dashboard/organization",
    "/dashboard/admin",
    "/dashboard/team-lead",
    "/dashboard/trainer",
    "/work-diary",
    "/attendance",
    "/leaves",
    "/profiles",
    "/projects",
    "/salary",
    "/holidays",
    "/inbox",
    "/notifications",
    "/settings",
    "/audit-logs",
    "/complaints"
]

for email, pwd, role in accounts:
    print(f"\n==================== Testing: {email} ({role}) ====================")
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    login_req = urllib.request.Request(
        "http://localhost:5000/api/auth/login",
        data=json.dumps({"email": email, "password": pwd, "role": role}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        resp = opener.open(login_req)
        data = json.loads(resp.read().decode("utf-8"))
        print(f"LOGIN OK -> role: {data.get('user', {}).get('role')}, redirect: {data.get('redirect_url')}")
    except urllib.error.HTTPError as e:
        print(f"LOGIN FAILED ({e.code}) -> {e.read().decode('utf-8')}")
        continue

    for page in pages:
        page_req = urllib.request.Request(f"http://localhost:5000{page}")
        try:
            p_resp = opener.open(page_req)
            content = p_resp.read().decode("utf-8", errors="ignore")
            # Check if redirected to login
            final_url = p_resp.geturl()
            status = p_resp.getcode()
            if "/login" in final_url and page != "/login":
                print(f"  [REDIRECT TO LOGIN] {page} -> {final_url}")
            else:
                print(f"  [200 OK] {page} (length {len(content)})")
        except urllib.error.HTTPError as pe:
            print(f"  [ERROR {pe.code}] {page}")
        except Exception as ex:
            print(f"  [EXCEPTION] {page}: {ex}")
