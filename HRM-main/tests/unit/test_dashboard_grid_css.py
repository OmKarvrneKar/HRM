import re
from pathlib import Path


def test_dashboard_grid_css_spec():
    """Verify that style.css contains the exact clean dashboard grid layout and standardized card styling."""
    css_path = Path("frontend/static/css/style.css")
    assert css_path.exists(), "style.css must exist"

    content = css_path.read_text(encoding="utf-8")

    # 1. Clean Dashboard Grid Layout
    assert ".dashboard-grid" in content
    assert "grid-template-columns: repeat(12, 1fr)" in content
    assert "gap: 20px" in content
    assert "padding: 24px" in content
    assert "align-items: start" in content

    # 2. Standardized Card Styling to Prevent Mismatched Sizes
    assert ".dashboard-card" in content
    assert "background: var(--card-bg, #ffffff)" in content
    assert "border-radius: 12px" in content
    assert "padding: 20px" in content
    assert "border: 1px solid var(--border-color, #e2e8f0)" in content
    assert "justify-content: space-between" in content
    assert "height: 100%" in content

    # 3. Span classes
    assert ".col-span-4 { grid-column: span 4; }" in content
    assert ".col-span-6 { grid-column: span 6; }" in content
    assert ".col-span-8 { grid-column: span 8; }" in content
    assert ".col-span-12 { grid-column: span 12; }" in content

    # 4. Media query for responsive sizing
    assert "@media (max-width: 1024px)" in content
    assert "grid-column: span 12;" in content

    # 5. CSS variables defined for light and dark modes
    assert "--card-bg: #ffffff" in content
    assert "--border-color: #e2e8f0" in content
    assert "--card-bg: var(--surface-card" in content
    assert "--border-color: var(--border-card" in content

    # 6. Floating & Shift Attendance Widgets
    assert ".floating-attendance-sidebar" in content
    assert "position: sticky" in content
    assert "border-radius: 16px" in content
    assert ".attendance-vertical-stack" in content
    assert ".shift-attendance-card" in content
    assert "border-radius: 14px" in content
    assert "padding: 20px 24px" in content

    # 7. Smooth Theme Transitions & Horizontal Shift Attendance Banner
    assert "body, .shift-attendance-card, .dashboard-card, .sidebar, .top-nav, input, button, select" in content
    assert "transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;" in content
    assert ".shift-attendance-horizontal" in content
    assert "grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));" in content
    assert "body.dark-mode" in content
    assert "body.light-mode" in content
    assert "--card-bg: #1e293b;" in content
    assert "--border-color: #334155;" in content
    assert "--text-primary: #f8fafc;" in content


