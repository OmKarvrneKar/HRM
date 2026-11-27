import urllib.request
import json
import http.cookiejar
from bs4 import BeautifulSoup

def main():
    print("=" * 60)
    print("AISamrat HRMS — Live Server E2E Verification")
    print("=" * 60)

    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    # 1. Login as Employee
    login_payload = json.dumps({
        "email": "snehak2003k@gmail.com",
        "password": "Sneha@Samrat2026!"
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:5000/api/auth/login",
        data=login_payload,
        headers={"Content-Type": "application/json"}
    )
    res = opener.open(req)
    print(f"[1] Employee Login Status: {res.getcode()} (OK)")

    # 2. Check Employee Dashboard & Sidebar
    res = opener.open("http://localhost:5000/dashboard/employee")
    html = res.read().decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")
    sidebar = soup.find("aside", class_="sidebar")
    nav_links = [a.get("href") for a in sidebar.find_all("a", class_="nav-link")]
    print(f"[2] Employee Sidebar Links: {nav_links}")

    # Expected WORKSPACE links
    assert "/dashboard/employee" in nav_links, "Overview missing"
    assert "/work-diary" in nav_links, "Work Diary missing"
    assert "/attendance" in nav_links, "My Attendance missing"
    assert "/leaves" in nav_links, "Leave & Permissions missing"
    assert "/projects" in nav_links, "Projects & Tasks missing"

    # Expected COMMUNICATION links
    assert "/inbox" in nav_links, "Team & Project Chat missing"
    assert "/complaints" in nav_links, "Workplace Concerns missing"
    assert "/notifications" in nav_links, "Notifications missing"
    assert "/profile/EMP-1005" in nav_links, "My Profile missing"

    # Must NOT contain standalone items
    assert "/holidays" not in nav_links, "Holiday Calendar should NOT be in Employee sidebar"
    assert "/salary" not in nav_links, "Salary Slips should NOT be in Employee sidebar"
    assert "/analytics" not in nav_links, "Analytics should NOT be in Employee sidebar"
    print(" -> Sidebar structure verified strictly as specified!")

    # 3. Check /attendance internal tabs
    res = opener.open("http://localhost:5000/attendance")
    html = res.read().decode("utf-8")
    assert 'id="viewAttendanceOverview"' in html, "viewAttendanceOverview tab missing"
    assert 'id="viewAttendanceCalendar"' in html, "viewAttendanceCalendar tab missing"
    assert 'id="viewHolidayCalendar"' in html, "viewHolidayCalendar tab missing"
    assert 'id="viewPunchHistory"' in html, "viewPunchHistory tab missing"
    print("[3] My Attendance internal tabs (Overview, Calendar, Holidays, Punch History) verified!")

    # 4. Check /projects internal tabs
    res = opener.open("http://localhost:5000/projects")
    html = res.read().decode("utf-8")
    assert 'id="viewMyProjects"' in html, "viewMyProjects tab missing"
    assert 'id="viewMyTasks"' in html, "viewMyTasks tab missing"
    assert 'id="viewProjectProgress"' in html, "viewProjectProgress tab missing"
    assert 'id="viewMyAnalytics"' in html, "viewMyAnalytics tab missing"
    print("[4] Projects & Tasks internal tabs (My Projects, My Tasks, Progress, Analytics) verified!")

    # 5. Check /salary direct accessibility
    res = opener.open("http://localhost:5000/salary")
    assert res.getcode() == 200, "Direct /salary route inaccessible"
    print("[5] Salary slips module accessible via route (/salary)!")

    # 6. Check /profile includes salary slips
    res = opener.open("http://localhost:5000/profile/EMP-1005")
    html = res.read().decode("utf-8")
    assert "Monthly Salary Slips" in html or "Salary Statements" in html, "Salary slips section missing in Profile"
    print("[6] Salary slips accessible via Employee Profile (/profile/EMP-1005)!")

    # 7. Check /holidays redirect for Employee
    class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    no_redir_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar), NoRedirectHandler)
    try:
        no_redir_opener.open("http://localhost:5000/holidays")
    except urllib.error.HTTPError as e:
        print(f"[7] /holidays redirect: HTTP {e.code} -> {e.headers.get('Location')}")
        assert "/attendance?tab=holidays" in e.headers.get("Location")

    try:
        no_redir_opener.open("http://localhost:5000/analytics")
    except urllib.error.HTTPError as e:
        print(f"[8] /analytics redirect: HTTP {e.code} -> {e.headers.get('Location')}")
        assert "/projects?tab=analytics" in e.headers.get("Location")

    # 9. Verify Dark Mode CSS Tokens and Login Page
    res = urllib.request.urlopen("http://localhost:5000/static/css/style.css")
    css_content = res.read().decode("utf-8")
    assert '--bg-app: #0b0f19;' in css_content, "Dark mode --bg-app token missing"
    assert '--sidebar-bg: #070a12;' in css_content, "Dark mode --sidebar-bg token missing"
    assert '--surface-card: #121c2d;' in css_content, "Dark mode --surface-card token missing"
    assert '--text-headline: #f8fafc;' in css_content, "Dark mode --text-headline token missing"
    print("[9] Centralized semantic dark theme tokens in style.css verified!")

    res = urllib.request.urlopen("http://localhost:5000/login")
    login_html = res.read().decode("utf-8")
    assert 'id="themeToggleBtn"' in login_html, "Theme toggle button missing on login page"
    assert "localStorage.getItem('ai_samrat_theme')" in login_html, "Anti-flash script missing on login page"
    print("[10] Login page dark mode toggle and anti-flash script verified!")

    print("=" * 60)
    print("ALL 10 VERIFICATION CHECKS PASSED ON LIVE RUNNING APPLICATION!")
    print("=" * 60)

if __name__ == "__main__":
    main()
