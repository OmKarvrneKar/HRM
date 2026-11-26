document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    setupClock();
    initSmoothPageTransitions();
    initGlobalNotificationDropdown();
    initRealtimeDashboardSearch();
    initShortcutTooltips();
    initShortcutFlyouts();
    initSidebarScrollRestoration();

    // Guard: Only poll and initialize authenticated services when an active session exists
    const isAuthUser = document.body.dataset.authenticated === 'true' || (
        document.body.dataset.authenticated !== 'false' && Boolean(
            document.getElementById('userHeaderWidget') ||
            document.getElementById('topNavLogoutBtn') ||
            document.querySelector('.user-header-widget') ||
            document.querySelector('.topnav-logout-btn')
        )
    );

    if (isAuthUser) {
        loadUnreadNotifications();
        checkGlobalCutoffIntimation();
        AttendanceSync.init();
        checkUserBirthdayCelebration();
        checkFestiveGreetings();
        setupBirthdayConfettiTrigger();
        // Auto-refresh notifications and cutoff intimation in background
        setInterval(loadUnreadNotifications, 20000);
        setInterval(checkGlobalCutoffIntimation, 15000);
    }
});

// Clean Progress Bar & Smooth Tab Transition Controller
function initSmoothPageTransitions() {
    let bar = document.getElementById('topLoadingBar');
    if (!bar) {
        bar = document.createElement('div');
        bar.id = 'topLoadingBar';
        document.body.prepend(bar);
    }

    // Dismiss loading bar on page load
    bar.style.width = '100%';
    setTimeout(() => {
        bar.style.opacity = '0';
        setTimeout(() => { bar.style.width = '0%'; }, 200);
    }, 80);

    // Show instant visual progress on link navigation
    document.addEventListener('click', (e) => {
        const link = e.target.closest('a[href]');
        if (!link) return;

        const href = link.getAttribute('href');
        if (!href) return;

        // Skip non-page links, anchors, JS protocols, modals, external, and file downloads
        if (href.startsWith('#') || 
            href.startsWith('javascript:') || 
            link.target === '_blank' || 
            href.startsWith('/api/export') ||
            link.hasAttribute('data-bs-toggle') ||
            link.hasAttribute('download')) {
            return;
        }

        if (bar) {
            bar.style.opacity = '1';
            bar.style.width = '60%';
        }
    });

    // Reset progress when returning via back/forward cache
    window.addEventListener('pageshow', () => {
        if (bar) {
            bar.style.width = '100%';
            setTimeout(() => {
                bar.style.opacity = '0';
                setTimeout(() => { bar.style.width = '0%'; }, 200);
            }, 80);
        }
    });

}

// Preserve and restore sidebar navigation scroll position & auto-center active tab
function initSidebarScrollRestoration() {
    if (typeof window.restoreSidebarActiveTab === 'function') {
        window.restoreSidebarActiveTab(false);
    }

    const nav = document.getElementById('sidebarNav') || document.querySelector('.sidebar nav');
    if (!nav) return;

    // Guard against layout-thrashing initial 0-scroll events
    let isStabilizing = true;
    setTimeout(() => { isStabilizing = false; }, 350);

    // Debounced listener to persist scroll on genuine user scrolling
    let scrollTimeout;
    nav.addEventListener('scroll', () => {
        if (isStabilizing) return;
        clearTimeout(scrollTimeout);
        scrollTimeout = setTimeout(() => {
            try { sessionStorage.setItem('aisamrat_sidebar_scroll', String(nav.scrollTop)); } catch(e) {}
        }, 100);
    }, { passive: true });

    // Persist position with capture phase whenever a sidebar link is clicked
    nav.addEventListener('click', (e) => {
        const link = e.target.closest('a');
        if (link) {
            try {
                sessionStorage.setItem('aisamrat_sidebar_scroll', String(nav.scrollTop));
                sessionStorage.setItem('aisamrat_clicked_href', link.getAttribute('href') || '');
            } catch(e) {}
        }
    }, true);
}

// Toast Notification Helper
function showToast(message, type = 'info') {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        document.body.appendChild(container);
    }

    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center text-white bg-${type === 'error' ? 'danger' : type} border-0 show mb-2 shadow-lg`;
    toastEl.setAttribute('role', 'alert');
    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body fw-medium">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    container.appendChild(toastEl);
    setTimeout(() => {
        toastEl.classList.remove('show');
        setTimeout(() => toastEl.remove(), 300);
    }, 4500);
}

// Global Shared Chart Theme & Color Token Palette (Unified Design System)
function getChartThemeColors() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    return {
        isDark: isDark,
        textColor: isDark ? '#cbd5e1' : '#475569',
        headingColor: isDark ? '#f8fafc' : '#0f172a',
        gridColor: isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 43, 128, 0.06)',
        borderColor: isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(226, 232, 240, 0.9)',
        primary: '#0056d6',
        cyan: '#00c2ff',
        success: '#10b981',
        warning: '#f59e0b',
        danger: '#ef4444',
        purple: '#8b5cf6',
        palette: ['#0056d6', '#00c2ff', '#10b981', '#f59e0b', '#8b5cf6', '#64748b']
    };
}

// Live Clock for Asia/Kolkata
function setupClock() {
    const clockEl = document.getElementById('liveClock');
    const dateEl = document.getElementById('liveDate');
    const fullClockEls = document.querySelectorAll('.live-time-ticker');

    const updateTime = () => {
        const now = new Date();
        const timeStr = now.toLocaleTimeString('en-IN', {
            timeZone: 'Asia/Kolkata',
            hour12: true,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });

        if (clockEl) {
            clockEl.textContent = timeStr;
        }

        if (dateEl) {
            dateEl.textContent = now.toLocaleDateString('en-IN', {
                timeZone: 'Asia/Kolkata',
                weekday: 'short',
                day: 'numeric',
                month: 'short',
                year: 'numeric'
            });
        }

        if (fullClockEls.length > 0) {
            fullClockEls.forEach(el => el.textContent = `${timeStr} IST`);
        }
    };

    updateTime();
    setInterval(updateTime, 1000);
}

// Live timer formatting utility: converts seconds to 00h 00m 00s
function formatLiveTimer(totalSeconds) {
    if (!totalSeconds || totalSeconds < 0) totalSeconds = 0;
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = Math.floor(totalSeconds % 60);
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(h)}h ${pad(m)}m ${pad(s)}s`;
}

// Formats seconds into clean concise format like "2h 45m"
function formatDurationDisplay(totalSeconds) {
    if (!totalSeconds || totalSeconds <= 0) return '0h 0m';
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    return `${h}h ${m}m`;
}

// ============================================================================
// SHARED REAL-TIME ATTENDANCE SYNCHRONIZATION SERVICE
// ============================================================================
const AttendanceSync = (function() {
    const CHANNEL_NAME = 'aisamrat_attendance_sync';
    let _channel = null;
    let _inFlight = false;
    let _currentRecord = null;
    let _hasOpenSession = false;

    try {
        if (typeof window.BroadcastChannel !== 'undefined') {
            _channel = new BroadcastChannel(CHANNEL_NAME);
            _channel.onmessage = (event) => {
                if (event.data && event.data.type === 'ATTENDANCE_STATE_CHANGE') {
                    // Sync from another tab immediately
                    AttendanceSync.syncFromServer(true);
                    if (event.data.action === 'CLOCK_OUT') {
                        const banner = document.getElementById('globalCutoffIntimationBar');
                        if (banner) banner.style.display = 'none';
                    }
                } else if (event.data && event.data.type === 'CUTOFF_BANNER_DISMISSED') {
                    const banner = document.getElementById('globalCutoffIntimationBar');
                    if (banner) banner.style.display = 'none';
                }
            };
        }
    } catch (e) {
        // Fallback to storage event
    }

    // Storage event fallback for cross-tab synchronization
    window.addEventListener('storage', (e) => {
        if (e.key === 'aisamrat_attendance_last_event') {
            AttendanceSync.syncFromServer(true);
        }
    });

    // Re-validate state when user returns to window/tab
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            AttendanceSync.syncFromServer(true);
        }
    });
    window.addEventListener('focus', () => {
        AttendanceSync.syncFromServer(true);
    });

    function _broadcastChange(action, data) {
        const payload = { type: 'ATTENDANCE_STATE_CHANGE', action: action, timestamp: Date.now() };
        if (_channel) {
            try { _channel.postMessage(payload); } catch (e) {}
        }
        try {
            localStorage.setItem('aisamrat_attendance_last_event', Date.now().toString());
        } catch (e) {}
    }

    function _setSwitchLoading(loading) {
        const switches = document.querySelectorAll('.punch-power-switch, #punchPowerSwitch');
        switches.forEach(sw => {
            if (loading) {
                sw.disabled = true;
                sw.classList.add('is-loading');
                sw.setAttribute('aria-busy', 'true');
            } else {
                sw.disabled = false;
                sw.classList.remove('is-loading');
                sw.removeAttribute('aria-busy');
            }
        });
    }

    function updateUI(hasOpenSession, attRecord) {
        _hasOpenSession = Boolean(hasOpenSession);
        if (attRecord !== undefined) {
            _currentRecord = attRecord;
        }

        // Hide cutoff banner immediately if no open session
        if (!_hasOpenSession) {
            const banner = document.getElementById('globalCutoffIntimationBar');
            if (banner) banner.style.display = 'none';
        }

        // 1. Update all switch buttons across the active page
        const switches = document.querySelectorAll('.punch-power-switch, #punchPowerSwitch');
        const statusLabels = document.querySelectorAll('.punch-switch-meta .meta-status, #punchSwitchStatusText');

        switches.forEach(sw => {
            if (_hasOpenSession) {
                sw.className = 'punch-power-switch state-on';
                sw.setAttribute('aria-checked', 'true');
                sw.title = 'Active Session: Click to switch off and clock out';
            } else {
                sw.className = 'punch-power-switch state-off';
                sw.setAttribute('aria-checked', 'false');
                sw.title = 'Standby: Click to switch on and clock in';
            }
        });

        const breakBtns = document.querySelectorAll('.break-control-btn, #btnBreakControl, #shiftCardBreakBtn');
        const isOnBreak = Boolean(attRecord && attRecord.is_on_break);

        statusLabels.forEach(label => {
            if (_hasOpenSession) {
                if (isOnBreak) {
                    label.innerHTML = '<span class="text-warning fw-bold"><span class="pulse-dot-inline me-1" style="background:#f59e0b;"></span>ON BREAK</span>';
                } else {
                    label.innerHTML = '<span class="text-primary fw-bold"><span class="pulse-dot-inline me-1"></span>ON DUTY</span>';
                }
            } else {
                label.innerHTML = '<span class="text-muted">STANDBY (OFF)</span>';
            }
        });

        breakBtns.forEach(btn => {
            if (!_hasOpenSession) {
                btn.style.display = 'none';
                btn.disabled = true;
            } else {
                btn.style.display = 'inline-flex';
                btn.disabled = false;
                if (isOnBreak) {
                    btn.className = 'btn btn-sm btn-warning d-inline-flex align-items-center gap-1 shadow-sm break-control-btn';
                    btn.innerHTML = '<i class="bi bi-play-circle-fill"></i> Resume Work';
                    btn.title = 'You are currently on break. Click to resume active work.';
                } else {
                    btn.className = 'btn btn-sm btn-outline-warning d-inline-flex align-items-center gap-1 break-control-btn';
                    btn.innerHTML = '<i class="bi bi-cup-hot"></i> Take Break';
                    btn.title = 'Click to record work break and pause active work duration.';
                }
            }
        });

        // 1b. Update top navbar duty status pill & shift card punch buttons
        const dutyText = document.getElementById('dutyStatusText');
        const dutyDot = document.getElementById('dutyPulseDot') || document.getElementById('dutyIndicatorDot');
        const dutyPill = document.getElementById('dutyStatusPill');
        const topNavBreak = document.getElementById('topNavBreakBtn');
        const topNavBreakText = document.getElementById('topNavBreakBtnText');

        if (dutyText) {
            if (_hasOpenSession) {
                if (isOnBreak) {
                    dutyText.textContent = 'On Break';
                    if (dutyDot) {
                        dutyDot.style.display = 'inline-block';
                        dutyDot.className = 'pulse-dot pulse-break';
                        dutyDot.style.background = '#f59e0b';
                    }
                    if (dutyPill) dutyPill.className = 'duty-status-pill on-break';
                } else {
                    dutyText.innerHTML = '<span class="pulse-dot-inline me-1"></span>Active Session (Live)';
                    if (dutyDot) {
                        dutyDot.style.display = 'inline-block';
                        dutyDot.className = 'pulse-dot pulse-active';
                        dutyDot.style.background = '#00c2ff';
                    }
                    if (dutyPill) dutyPill.className = 'duty-status-pill active';
                }
            } else {
                dutyText.textContent = 'Clocked Out';
                if (dutyDot) dutyDot.style.display = 'none';
                if (dutyPill) dutyPill.className = 'duty-status-pill inactive';
            }
        }

        // 1c. Synchronize In-Card Shift Attendance Punch Buttons across pages
        const cardPunchBtns = document.querySelectorAll('.card-punch-btn, #shiftCardPunchBtn');
        cardPunchBtns.forEach(btn => {
            if (_hasOpenSession) {
                btn.className = 'btn btn-sm btn-outline-danger rounded-pill px-3 shadow-sm card-punch-btn d-inline-flex align-items-center gap-1';
                btn.innerHTML = '<i class="bi bi-power"></i> <span id="shiftCardPunchText">Clock Out</span>';
                btn.title = 'Active Session: Click to clock out';
            } else {
                btn.className = 'btn btn-sm btn-primary rounded-pill px-3 shadow-sm card-punch-btn d-inline-flex align-items-center gap-1';
                btn.innerHTML = '<i class="bi bi-power"></i> <span id="shiftCardPunchText">Clock In</span>';
                btn.title = 'Offline: Click to clock in';
            }
        });

        if (topNavBreak) {
            if (_hasOpenSession) {
                topNavBreak.classList.remove('d-none');
                topNavBreak.classList.add('d-inline-flex');
                if (isOnBreak) {
                    topNavBreak.className = 'btn btn-sm btn-warning rounded-pill px-3 shadow-sm d-inline-flex align-items-center gap-1 text-dark';
                    if (topNavBreakText) topNavBreakText.textContent = 'Resume Work';
                } else {
                    topNavBreak.className = 'btn btn-sm btn-outline-warning rounded-pill px-3 shadow-sm d-inline-flex align-items-center gap-1';
                    if (topNavBreakText) topNavBreakText.textContent = 'Take Break';
                }
            } else {
                topNavBreak.classList.add('d-none');
                topNavBreak.classList.remove('d-inline-flex');
            }
        }

        // 2. Refresh Dashboard attendance state if on Dashboard
        if (typeof window.loadTodayAttendance === 'function') {
            try { window.loadTodayAttendance(true); } catch (e) {}
        }

        // 3. Refresh Attendance Calendar and History if on Attendance Page
        if (typeof window.loadCalendar === 'function') {
            try { window.loadCalendar(); } catch (e) {}
        }
        if (typeof window.loadMyHistory === 'function') {
            try { window.loadMyHistory(); } catch (e) {}
        }
    }

    async function syncFromServer(isSilent = false) {
        // Only query attendance if attendance UI controls exist on the active page
        if (!document.querySelector('.punch-power-switch, #punchPowerSwitch, .duty-status-pill, #cardShiftHoursText')) {
            return null;
        }
        try {
            const res = await fetch('/api/attendance/today');
            if (!res.ok) return null;
            const data = await res.json();
            
            const hasOpen = Boolean(data.has_open_session);

            updateUI(hasOpen, data.attendance);
            return data;
        } catch (e) {
            if (!isSilent) console.error('Failed to sync attendance state:', e);
            return null;
        }
    }

    async function _captureLocationSnapshot() {
        if (!navigator.geolocation) {
            return { status: "UNAVAILABLE", reason: "Geolocation not supported" };
        }
        return new Promise((resolve) => {
            const timeoutId = setTimeout(() => {
                resolve({ status: "TIMEOUT", reason: "Location acquisition timed out" });
            }, 3500);

            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    clearTimeout(timeoutId);
                    resolve({
                        status: "CAPTURED",
                        latitude: pos.coords.latitude,
                        longitude: pos.coords.longitude,
                        accuracy_meters: pos.coords.accuracy,
                        captured_at: new Date().toISOString()
                    });
                },
                (err) => {
                    clearTimeout(timeoutId);
                    const status = err.code === 1 ? "DENIED" : "UNAVAILABLE";
                    const reason = err.code === 1 ? "Permission denied by user" :
                                   err.code === 2 ? "Position unavailable" : "Timeout";
                    resolve({ status: status, reason: reason });
                },
                { enableHighAccuracy: true, timeout: 3000, maximumAge: 0 }
            );
        });
    }

    async function clockIn() {
        if (_inFlight) return;
        _inFlight = true;
        _setSwitchLoading(true);

        try {
            const todayStr = getIstDateString();
            const istDate = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
            const isOvertime = istDate.getHours() >= 18;
            if (isOvertime) {
                localStorage.setItem(`aisamrat_manual_overtime_${todayStr}`, 'true');
            }

            const location = await _captureLocationSnapshot();
            const res = await fetch('/api/attendance/check-in', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    location: location,
                    notes: isOvertime ? 'Overtime / Extra Shift Duty' : 'Standard Shift Punch'
                })
            });
            const data = await res.json();

            if (res.ok && data.success) {
                const locMsg = location.status === 'CAPTURED' ? ' (Location Verified)' : '';
                const msg = isOvertime
                    ? 'Overtime Shift started! Active extra duty session is live.'
                    : 'Checked in successfully!' + locMsg + ' Attendance session is active.';
                showToast(msg, 'success');
                updateUI(true, data.attendance);
                _broadcastChange('CLOCK_IN', data);
            } else {
                showToast(data.error || 'Failed to check in.', 'error');
                await syncFromServer(true);
            }
        } catch (e) {
            showToast('Network error while checking in. Please try again.', 'error');
            await syncFromServer(true);
        } finally {
            _inFlight = false;
            _setSwitchLoading(false);
        }
    }

    async function clockOut(sessionId = null, skipConfirm = false) {
        if (_inFlight) return;

        if (!skipConfirm && !confirm('Confirm session checkout? Your active shift hours will be calculated and logged.')) {
            return;
        }

        _inFlight = true;
        _setSwitchLoading(true);

        try {
            const todayStr = getIstDateString();
            localStorage.removeItem(`aisamrat_manual_overtime_${todayStr}`);
            const location = await _captureLocationSnapshot();
            const res = await fetch('/api/attendance/check-out', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, location: location })
            });
            const data = await res.json();

            if (res.ok && data.success) {
                if (!skipConfirm) {
                    showToast('Clocked out successfully! Daily summary updated.', 'success');
                }
                updateUI(false, data.attendance);
                const banner = document.getElementById('globalCutoffIntimationBar');
                if (banner) banner.style.display = 'none';
                _broadcastChange('CLOCK_OUT', data);
            } else {
                if (!skipConfirm) showToast(data.error || 'Failed to clock out.', 'error');
                await syncFromServer(true);
            }
        } catch (e) {
            if (!skipConfirm) showToast('Network error while checking out. Please try again.', 'error');
            await syncFromServer(true);
        } finally {
            _inFlight = false;
            _setSwitchLoading(false);
        }
    }

    async function startBreak(notes = 'Work Break') {
        if (_inFlight) return;
        _inFlight = true;
        try {
            const res = await fetch('/api/attendance/break/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ notes: notes })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                showToast('Break started. Active work duration paused.', 'info');
                updateUI(true, data.attendance);
                _broadcastChange('BREAK_START', data);
            } else {
                showToast(data.error || 'Failed to start break.', 'error');
                await syncFromServer(true);
            }
        } catch (e) {
            showToast('Network error while starting break.', 'error');
            await syncFromServer(true);
        } finally {
            _inFlight = false;
        }
    }

    async function endBreak() {
        if (_inFlight) return;
        _inFlight = true;
        try {
            const res = await fetch('/api/attendance/break/end', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await res.json();
            if (res.ok && data.success) {
                showToast('Welcome back! Active working time resumed.', 'success');
                updateUI(true, data.attendance);
                _broadcastChange('BREAK_END', data);
            } else {
                showToast(data.error || 'Failed to end break.', 'error');
                await syncFromServer(true);
            }
        } catch (e) {
            showToast('Network error while ending break.', 'error');
            await syncFromServer(true);
        } finally {
            _inFlight = false;
        }
    }

    async function toggleBreak() {
        if (_currentRecord && _currentRecord.is_on_break) {
            await endBreak();
        } else {
            await startBreak();
        }
    }

    async function toggle() {
        if (_inFlight) return;
        const sw = document.getElementById('punchPowerSwitch');
        const isCurrentlyOn = sw ? sw.classList.contains('state-on') : _hasOpenSession;
        if (isCurrentlyOn) {
            await clockOut();
        } else {
            await clockIn();
        }
    }

    function init() {
        syncFromServer(true);
        // Periodic background poll every 25s
        setInterval(() => {
            syncFromServer(true);
        }, 25000);
    }

    return {
        init,
        toggle,
        clockIn,
        clockOut,
        startBreak,
        endBreak,
        toggleBreak,
        syncFromServer,
        updateUI,
        getState: () => ({ hasOpenSession: _hasOpenSession, record: _currentRecord })
    };
})();

// Legacy wrapper functions for complete backward compatibility
async function toggleDutyPunchSwitch() {
    await AttendanceSync.toggle();
}

async function toggleWorkBreak() {
    await AttendanceSync.toggleBreak();
}

function updatePunchSwitchUI(hasOpenSession) {
    AttendanceSync.updateUI(hasOpenSession);
}

async function performCheckIn() {
    await AttendanceSync.clockIn();
}

async function performCheckOut(sessionId = null) {
    await AttendanceSync.clockOut(sessionId);
}

// Logout
async function performAppLogout() {
    try {
        await fetch('/api/auth/logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
    } catch (e) {}
    try {
        sessionStorage.clear();
        localStorage.removeItem('hrm_access_token');
        const paths = ['/', '/api', '/api/auth'];
        paths.forEach(p => {
            document.cookie = `hrm_access_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=${p};`;
            document.cookie = `session=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=${p};`;
        });
    } catch (e) {}
    window.location.replace('/login?logged_out=1');
}

// Notifications Dropdown Manager (Hover-Triggered & Unread vs Read separation)
function initGlobalNotificationDropdown() {
    const dropdownEl = document.getElementById('globalNotifDropdown');
    const bellBtn = document.getElementById('notifBellBtn');
    if (!dropdownEl || !bellBtn) return;

    let hoverTimer = null;

    // Hover trigger: entering bell or dropdown opens and refreshes immediately
    dropdownEl.addEventListener('mouseenter', () => {
        clearTimeout(hoverTimer);
        loadUnreadNotifications(true);
    });

    // Clicking bell navigates to notification center or acts as fallback
    bellBtn.addEventListener('click', (e) => {
        e.preventDefault();
        loadUnreadNotifications(true);
    });

    // Clean Escape key handler to close notification dropdown cleanly
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const menu = dropdownEl.querySelector('.notifications-dropdown-menu');
            if (menu) menu.style.display = 'none';
            setTimeout(() => { if (menu) menu.style.display = ''; }, 300);
        }
    });
}

async function markAllNotificationsAsRead(event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    const btn = document.getElementById('btnMarkAllNotifsRead');
    if (btn) btn.disabled = true;

    try {
        const res = await fetch('/api/notifications/read-all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        if (res.ok) {
            const badge = document.getElementById('notifCountBadge');
            if (badge) badge.style.display = 'none';
            await loadUnreadNotifications(true);
            showToast('All notifications marked as read', 'success');
        }
    } catch (e) {
        showToast('Failed to mark all as read', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function markNotificationReadAndNavigate(notifId, link) {
    try {
        const res = await fetch(`/api/notifications/${notifId}/read`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        if (!res.ok) {
            showToast('Could not mark notification as read. Please try again.', 'error');
            return;
        }
    } catch (e) {
        showToast('Could not mark notification as read. Please try again.', 'error');
        return;
    }
    if (link && link !== '#') {
        window.location.href = link;
    } else {
        loadUnreadNotifications(true);
    }
}

function renderNotifRowHtml(n, isUnread) {
    const timeStr = n.created_at ? new Date(n.created_at).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: true }) : '';
    let iconClass = 'bi-bell-fill text-primary';
    if (n.category === 'LEAVE') iconClass = 'bi-calendar-check text-warning';
    else if (n.category === 'ATTENDANCE') iconClass = 'bi-clock-history text-info';
    else if (n.category === 'ANNOUNCEMENT') iconClass = 'bi-megaphone text-danger';

    const safeTitle = (typeof escapeHtml === 'function' ? escapeHtml(n.title) : n.title) || 'Notification';
    const safeMsg = (typeof escapeHtml === 'function' ? escapeHtml(n.message) : n.message) || '';
    const safeId = n.notification_id || n._id || n.id;
    const safeLink = n.link || '/notifications';

    return `
        <div class="notification-item-compact cursor-pointer ${isUnread ? 'is-unread' : 'is-read'}" style="cursor: pointer;" onclick="markNotificationReadAndNavigate('${safeId}', '${safeLink}')">
            <div class="d-flex align-items-start gap-2">
                <i class="bi ${iconClass} mt-1 flex-shrink-0"></i>
                <div class="overflow-hidden flex-grow-1">
                    <div class="d-flex justify-content-between align-items-baseline gap-1">
                        <span class="fw-semibold text-headline small text-truncate ${isUnread ? 'text-primary' : ''}" style="font-size: 0.8rem;">${safeTitle}</span>
                        <span class="text-muted font-mono flex-shrink-0" style="font-size: 0.65rem;">${timeStr}</span>
                    </div>
                    <div class="text-muted text-truncate" style="font-size: 0.72rem; max-width: 280px;">${safeMsg}</div>
                </div>
            </div>
        </div>
    `;
}

// Notifications badge loader & Quick Dropdown list renderer (Active vs Read separation)
async function loadUnreadNotifications(renderList = false) {
    try {
        const res = await fetch('/api/notifications?unread_only=false');
        if (!res.ok) return;
        const data = await res.json();
        const badge = document.getElementById('notifCountBadge');
        const notifs = data.notifications || [];
        const unreadList = notifs.filter(n => !n.is_read);
        const readList = notifs.filter(n => n.is_read);
        const count = unreadList.length;

        if (badge) {
            if (count > 0) {
                badge.textContent = count > 99 ? '99+' : count;
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        }

        const list = document.getElementById('quickNotifList');
        if (list && (renderList || list.dataset.initialized !== 'true')) {
            list.dataset.initialized = 'true';
            if (notifs.length === 0) {
                list.innerHTML = `
                    <div class="text-muted small text-center py-4 px-3">
                        <i class="bi bi-check2-circle text-success fs-4 d-block mb-1"></i>
                        <span class="fw-medium text-dark">All caught up!</span>
                        <div class="text-muted" style="font-size: 0.72rem;">No notifications found.</div>
                    </div>
                `;
            } else {
                let html = '';
                
                // 1. Unread / Active Section
                if (unreadList.length > 0) {
                    html += `
                        <div class="notif-section-header">
                            <span class="d-flex align-items-center gap-1">
                                <span class="notif-status-dot bg-primary"></span> UNREAD (ACTIVE)
                            </span>
                            <span class="badge bg-primary-subtle text-primary font-mono" style="font-size: 0.62rem;">${unreadList.length}</span>
                        </div>
                    `;
                    html += unreadList.slice(0, 6).map(n => renderNotifRowHtml(n, true)).join('');
                } else {
                    html += `
                        <div class="notif-section-header">
                            <span class="d-flex align-items-center gap-1 text-muted">
                                <i class="bi bi-check2-all text-success"></i> UNREAD (ACTIVE)
                            </span>
                            <span class="text-muted font-mono" style="font-size: 0.62rem;">0</span>
                        </div>
                        <div class="px-3 py-2 text-muted small text-center" style="font-size: 0.72rem;">
                            No unread notifications
                        </div>
                    `;
                }

                // 2. Earlier / Read Section
                if (readList.length > 0) {
                    html += `
                        <div class="notif-section-header border-top">
                            <span class="d-flex align-items-center gap-1 text-muted">
                                <i class="bi bi-clock-history"></i> EARLIER (READ)
                            </span>
                            <span class="text-muted font-mono" style="font-size: 0.62rem;">${readList.length}</span>
                        </div>
                    `;
                    html += readList.slice(0, 6).map(n => renderNotifRowHtml(n, false)).join('');
                }

                list.innerHTML = html;
            }
        }
    } catch (e) {
        // Silent fail for polling
    }
}

// Live Real-Time Search Filter for Dashboard (Tasks, Logs, Records)
function initRealtimeDashboardSearch() {
    const searchInputs = document.querySelectorAll('#dashSearchInput, .search-capsule-input');
    searchInputs.forEach(input => {
        // Prevent form submit on Enter in search capsule
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
            } else if (e.key === 'Escape') {
                input.value = '';
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.blur();
            }
        });
    });

    const searchInput = document.getElementById('dashSearchInput');
    const clearBtn = document.getElementById('dashSearchClearBtn');
    if (!searchInput) return;

    const performFilter = () => {
        const q = searchInput.value.trim().toLowerCase();
        if (clearBtn) {
            clearBtn.style.display = q.length > 0 ? 'inline-block' : 'none';
        }

        // 1. Filter Tasks & Projects in #employeeTasksList
        const taskCards = document.querySelectorAll('#employeeTasksList > div');
        taskCards.forEach(card => {
            const text = card.textContent.toLowerCase();
            const match = !q || text.includes(q);
            card.style.display = match ? '' : 'none';
        });

        // 2. Filter Daily Punch Logs in #sessionsTimeline
        const sessionItems = document.querySelectorAll('#sessionsTimeline .timeline-item');
        sessionItems.forEach(item => {
            const text = item.textContent.toLowerCase();
            const match = !q || text.includes(q);
            item.style.display = match ? '' : 'none';
        });

        // 3. Filter Upcoming Holidays and general searchable items
        const extraItems = document.querySelectorAll('#dashUpcomingHolidaysList .holiday-item, .employee-searchable-row, .searchable-dashboard-item');
        extraItems.forEach(item => {
            const text = item.textContent.toLowerCase();
            const match = !q || text.includes(q);
            item.style.display = match ? '' : 'none';
        });
    };

    searchInput.addEventListener('input', performFilter);

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            searchInput.value = '';
            performFilter();
            searchInput.focus();
        });
    }
}

// Instant Shortcut Popover / Hover Tooltip Initializer
function initShortcutTooltips() {
    document.querySelectorAll('#shortcutTilesContainer .capsule-tile-btn[title]').forEach(el => {
        const label = el.getAttribute('title');
        if (!label) return;

        el.dataset.shortcutLabel = label;
        if (!el.hasAttribute('aria-label')) el.setAttribute('aria-label', label);
        el.removeAttribute('title');
        el.removeAttribute('data-bs-toggle');
    });

    if (typeof bootstrap === 'undefined' || !bootstrap.Tooltip) return;
    const elements = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    elements.forEach(el => {
        const text = el.getAttribute('data-bs-title') || el.getAttribute('title');
        if (text) {
            el.setAttribute('data-bs-title', text);
            el.setAttribute('data-bs-toggle', 'tooltip');
            el.setAttribute('data-bs-placement', el.getAttribute('data-bs-placement') || 'bottom');
            try {
                const existing = bootstrap.Tooltip.getInstance(el);
                if (existing) existing.dispose();
                new bootstrap.Tooltip(el, {
                    delay: { show: 60, hide: 80 },
                    customClass: 'capsule-rich-tooltip',
                    fallbackPlacements: ['top', 'bottom']
                });
            } catch (e) {}
        }
    });
}

// Shortcut flyout card deactivated in favor of native tooltips & direct navigation
function initShortcutFlyouts() {
    // Intentionally clean no-op
}

// Theme Switcher (Light / Dark) & Chart.js Integration
function initTheme() {
    const saved = localStorage.getItem('ai_samrat_theme') || 'light';
    applyTheme(saved);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    applyTheme(next);
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.setAttribute('data-bs-theme', theme);
    if (document.body) {
        document.body.classList.remove('dark-mode', 'light-mode');
        document.body.classList.add(theme === 'dark' ? 'dark-mode' : 'light-mode');
        if (theme === 'dark') {
            document.body.style.backgroundColor = '#070f1e';
            document.body.style.backgroundImage = 'none';
        } else {
            document.body.style.backgroundColor = '';
            document.body.style.backgroundImage = '';
        }
    }
    if (theme === 'dark') {
        document.documentElement.style.backgroundColor = '#070f1e';
        document.documentElement.style.colorScheme = 'dark';
    } else {
        document.documentElement.style.backgroundColor = '#dbeafe';
        document.documentElement.style.colorScheme = 'light';
    }
    localStorage.setItem('ai_samrat_theme', theme);
    updateThemeIcon(theme);

    // Set default Chart.js colors for any charts instantiated later
    if (window.Chart) {
        const colors = getChartThemeColors();
        Chart.defaults.color = colors.textColor;
        Chart.defaults.borderColor = colors.gridColor;
    }

    // Notify all active Chart.js instances and dynamic widgets across the application
    window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme } }));
}

function updateThemeIcon(theme) {
    const btns = document.querySelectorAll('#themeToggleBtn, .theme-toggle-btn, [data-action="toggle-theme"], .topnav-theme-btn');
    btns.forEach(btn => {
        const icon = btn.querySelector('i');
        if (!icon) return;
        if (theme === 'dark') {
            icon.className = 'bi bi-sun';
            btn.setAttribute('title', 'Switch to Light Mode');
        } else {
            icon.className = 'bi bi-moon-stars';
            btn.setAttribute('title', 'Switch to Dark Mode');
        }
    });
}

// Chart.js Theme Token Helper for all HRMS Analytics
function getChartThemeColors() {
    const isDark = (document.documentElement.getAttribute('data-theme') || 'light') === 'dark';
    return {
        isDark: isDark,
        textColor: isDark ? '#cbd5e1' : '#475569',
        headingColor: isDark ? '#f8fafc' : '#0f172a',
        gridColor: isDark ? 'rgba(0, 229, 255, 0.08)' : 'rgba(0, 102, 255, 0.06)',
        tooltipBg: isDark ? '#0d1728' : '#0f172a',
        tooltipText: isDark ? '#f8fafc' : '#ffffff',
        borderColor: isDark ? 'rgba(0, 229, 255, 0.2)' : '#e2e8f0',
        palette: [
            '#00e5ff', '#0066ff', '#10b981', '#f59e0b',
            '#8b5cf6', '#ec4899', '#06b6d4', '#6366f1'
        ]
    };
}

// Auto-update any running Chart.js instances when theme is toggled
window.addEventListener('themeChanged', () => {
    try {
        if (window.Chart && Chart.instances) {
            const colors = getChartThemeColors();
            Object.values(Chart.instances).forEach(chart => {
                if (chart && chart.options) {
                    if (chart.options.scales) {
                        Object.values(chart.options.scales).forEach(scale => {
                            if (scale.ticks) scale.ticks.color = colors.textColor;
                            if (scale.grid) scale.grid.color = colors.gridColor;
                        });
                    }
                    if (chart.options.plugins && chart.options.plugins.legend && chart.options.plugins.legend.labels) {
                        chart.options.plugins.legend.labels.color = colors.textColor;
                    }
                    chart.update();
                }
            });
        }
    } catch (e) {
        // Safe fallback
    }
});

// ==========================================================================
// AI SAMRAT Cutoff Intimation Monitor & Notification System
// Shift: 10:00 AM - 6:00 PM | System Cutoff: 7:00 PM
// Intimation Notice: 45 Minutes Prior (Starting 6:15 PM)
// ==========================================================================

function getIstDateString() {
    const now = new Date();
    const istString = now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' });
    const ist = new Date(istString);
    const y = ist.getFullYear();
    const m = String(ist.getMonth() + 1).padStart(2, '0');
    const d = String(ist.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function checkGlobalCutoffIntimation() {
    const banner = document.getElementById('globalCutoffIntimationBar');
    if (!banner) return;

    // 1. If user is offline / no active session: NEVER show any reminder or cutoff banner
    if (typeof AttendanceSync !== 'undefined') {
        const state = AttendanceSync.getState();
        if (!state || !state.hasOpenSession) {
            banner.style.display = 'none';
            return;
        }
    }

    // 2. If user has dismissed the notice for today: persist dismissal across tabs, reloads & routes
    const todayStr = getIstDateString();
    const dismissalKey = `aisamrat_cutoff_dismissed_${todayStr}`;
    if (localStorage.getItem(dismissalKey) === 'true') {
        banner.style.display = 'none';
        return;
    }

    const now = new Date();
    const istString = now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' });
    const istDate = new Date(istString);
    const y = istDate.getFullYear(), m = istDate.getMonth(), d = istDate.getDate();

    const targetShiftEnd = new Date(y, m, d, 18, 0, 0);     // 6:00 PM (Shift End)
    const targetIntimation = new Date(y, m, d, 18, 15, 0);   // 6:15 PM (Cutoff Warning)
    const targetCutoff = new Date(y, m, d, 19, 0, 0);         // 7:00 PM (Hard Cutoff)

    // Check if user manually opted in to overtime after 6:00 PM
    const isManualOvertime = localStorage.getItem(`aisamrat_manual_overtime_${todayStr}`) === 'true';

    // 3. Shift Completion Auto Clock-Out (at 6:00 PM IST)
    if (istDate >= targetShiftEnd && !isManualOvertime) {
        const shiftAutoLoggedKey = `aisamrat_shift_auto_executed_${todayStr}`;
        if (!sessionStorage.getItem(shiftAutoLoggedKey)) {
            sessionStorage.setItem(shiftAutoLoggedKey, 'true');
            localStorage.setItem(dismissalKey, 'true');
            sessionStorage.setItem(dismissalKey, 'true');
            if (typeof AttendanceSync !== 'undefined' && AttendanceSync.clockOut) {
                AttendanceSync.clockOut(null, true); // true = skip confirmation dialog
            }
            showToast('Shift Completed (6:00 PM): You have been automatically clocked out. You may manually click Clock In if working extra / overtime.', 'info');
        }
        banner.style.display = 'none';
        return;
    }

    // 4. Overtime Warning & 7:00 PM Hard Cutoff (for employees working overtime)
    if (istDate >= targetIntimation && istDate < targetCutoff) {
        const secLeft = Math.floor((targetCutoff - istDate) / 1000);
        const minsLeft = Math.max(1, Math.floor(secLeft / 60));

        banner.style.display = 'block';
        const badge = document.getElementById('cutoffCountdownBadge');
        if (badge) badge.textContent = `${minsLeft}m remaining`;

        const sub = document.getElementById('cutoffBannerSubtitle');
        if (sub) {
            sub.textContent = `Shift completed at 6:00 PM. Hard system cutoff is strictly at 7:00 PM (${minsLeft} minutes remaining). Please submit your work diary and clock out.`;
        }

        const alertKey = `aisamrat_cutoff_alert_toast_fired_${todayStr}`;
        if (!localStorage.getItem(alertKey)) {
            localStorage.setItem(alertKey, 'true');
            sessionStorage.setItem(alertKey, 'true');
            showToast(`⚠️ Mandatory Notice: ${minsLeft} minutes until 7:00 PM cutoff! Please submit work diary and clock out.`, 'warning');
        }
    } else if (istDate >= targetCutoff) {
        // Active session remains past 7:00 PM hard cutoff: execute clean auto clock-out
        banner.style.display = 'none';
        const cutoffAutoLoggedKey = `aisamrat_cutoff_auto_executed_${todayStr}`;
        if (!sessionStorage.getItem(cutoffAutoLoggedKey)) {
            sessionStorage.setItem(cutoffAutoLoggedKey, 'true');
            localStorage.setItem(dismissalKey, 'true');
            if (typeof AttendanceSync !== 'undefined' && AttendanceSync.clockOut) {
                AttendanceSync.clockOut(null, true);
            }
            showToast('7:00 PM Cutoff Passed: Session automatically checked out.', 'warning');
        }
    } else {
        banner.style.display = 'none';
    }
}

function dismissCutoffNoticeToday() {
    const banner = document.getElementById('globalCutoffIntimationBar');
    if (banner) banner.style.display = 'none';
    // Persist dismissal for today across tabs, navigation, and reloads without changing attendance
    const todayStr = getIstDateString();
    const dismissalKey = `aisamrat_cutoff_dismissed_${todayStr}`;
    try {
        localStorage.setItem(dismissalKey, 'true');
        sessionStorage.setItem(dismissalKey, 'true');
    } catch (e) {}

    // Broadcast dismissal to all other tabs immediately
    try {
        if (typeof window.BroadcastChannel !== 'undefined') {
            const ch = new BroadcastChannel('aisamrat_attendance_sync');
            ch.postMessage({ type: 'CUTOFF_BANNER_DISMISSED', date: todayStr });
        }
    } catch (e) {}
}

async function performCutoffDirectClockOut() {
    await performCheckOut();
    const banner = document.getElementById('globalCutoffIntimationBar');
    if (banner) banner.style.display = 'none';
}

// Global Shortcut Megamenu Flyout Window Toggling & Dismissal
function toggleShortcutFlyout(event, btn) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    const wrapper = btn.closest('.shortcut-hover-wrapper');
    if (!wrapper) return;
    const isCurrentlyActive = wrapper.classList.contains('active-flyout');

    // Close all other open flyouts
    document.querySelectorAll('.shortcut-hover-wrapper.active-flyout').forEach(el => {
        if (el !== wrapper) el.classList.remove('active-flyout');
    });

    if (isCurrentlyActive) {
        wrapper.classList.remove('active-flyout');
    } else {
        wrapper.classList.add('active-flyout');
    }
}

document.addEventListener('click', (e) => {
    if (!e.target.closest('.shortcut-hover-wrapper')) {
        document.querySelectorAll('.shortcut-hover-wrapper.active-flyout').forEach(el => {
            el.classList.remove('active-flyout');
        });
    }
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.shortcut-hover-wrapper.active-flyout').forEach(el => {
            el.classList.remove('active-flyout');
        });
    }
});

// ==========================================================================
// Multi-Pad Sticky Notepad Client Controller (Neural-Tech Glassmorphism)
// ==========================================================================
let globalUserNotepads = [];
let activeNotepadId = null;
let notepadDebounceTimer = null;
let isNotepadDirty = false;

async function toggleGlobalNotepadDrawer() {
    const drawer = document.getElementById('globalNotepadDrawer');
    const backdrop = document.getElementById('globalNotepadBackdrop');
    if (!drawer) return;

    if (drawer.classList.contains('show')) {
        closeGlobalNotepadDrawer();
    } else {
        drawer.classList.add('show');
        if (backdrop) backdrop.classList.add('show');
        await loadUserNotepads();
    }
}

function closeGlobalNotepadDrawer() {
    const drawer = document.getElementById('globalNotepadDrawer');
    const backdrop = document.getElementById('globalNotepadBackdrop');
    if (drawer) drawer.classList.remove('show');
    if (backdrop) backdrop.classList.remove('show');
    if (isNotepadDirty) {
        saveCurrentNotepadImmediately();
    }
}

async function loadUserNotepads() {
    try {
        const res = await fetch('/api/notepads');
        if (!res.ok) return;
        const data = await res.json();
        globalUserNotepads = data.notes || [];
        if (globalUserNotepads.length > 0) {
            if (!activeNotepadId || !globalUserNotepads.some(n => n.note_id === activeNotepadId)) {
                activeNotepadId = globalUserNotepads[0].note_id;
            }
        } else {
            activeNotepadId = null;
        }
        renderNotepadTabs();
        populateActiveNotepad();
    } catch (e) {
        console.error('Failed to load notepads:', e);
    }
}

function renderNotepadTabs() {
    const container = document.getElementById('notepadTabsContainer');
    if (!container) return;

    if (globalUserNotepads.length === 0) {
        container.innerHTML = '<span class="text-muted small py-1">No pads open</span>';
        return;
    }

    container.innerHTML = globalUserNotepads.map((note, idx) => {
        const isActive = note.note_id === activeNotepadId;
        const pinIcon = note.is_pinned ? '<i class="bi bi-pin-fill text-warning" style="font-size:0.65rem;"></i>' : '';
        const titleText = (note.title || `Pad #${idx + 1}`).slice(0, 15);
        return `
            <button type="button" class="notepad-tab-btn ${isActive ? 'active' : ''}" onclick="switchNotepadTab('${note.note_id}')">
                ${pinIcon}
                <span style="color:${note.color || '#00e5ff'}; font-size: 0.65rem;">●</span>
                <span>${typeof escapeHtml === 'function' ? escapeHtml(titleText) : titleText}</span>
            </button>
        `;
    }).join('');
}

function switchNotepadTab(noteId) {
    if (activeNotepadId === noteId) return;
    if (isNotepadDirty) {
        saveCurrentNotepadImmediately();
    }
    activeNotepadId = noteId;
    renderNotepadTabs();
    populateActiveNotepad();
}

function populateActiveNotepad() {
    const current = globalUserNotepads.find(n => n.note_id === activeNotepadId);
    const titleInput = document.getElementById('notepadTitleInput');
    const contentInput = document.getElementById('notepadContentInput');
    const pinIcon = document.getElementById('btnPinNotepadIcon');
    const saveIndicator = document.getElementById('notepadSaveIndicator');

    if (!current) {
        if (titleInput) titleInput.value = '';
        if (contentInput) contentInput.value = '';
        return;
    }

    if (titleInput) titleInput.value = current.title || '';
    if (contentInput) contentInput.value = current.content || '';
    if (pinIcon) {
        pinIcon.className = current.is_pinned ? 'bi bi-pin-fill text-warning' : 'bi bi-pin-angle';
    }
    if (saveIndicator) {
        saveIndicator.innerHTML = '<i class="bi bi-check2 text-success me-1"></i>Saved to Cloud';
    }
    isNotepadDirty = false;
}

async function createNewNotepadTab() {
    if (isNotepadDirty) {
        await saveCurrentNotepadImmediately();
    }
    const padCount = globalUserNotepads.length + 1;
    const colors = ['#0066ff', '#00e5ff', '#10b981', '#f59e0b', '#8b5cf6'];
    const chosenColor = colors[padCount % colors.length];

    try {
        const res = await fetch('/api/notepads', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: `Pad ${padCount}`,
                content: '',
                color: chosenColor,
                is_pinned: false
            })
        });
        if (!res.ok) throw new Error('Could not create new pad');
        const data = await res.json();
        const newNote = data.note;
        globalUserNotepads.unshift(newNote);
        activeNotepadId = newNote.note_id;
        renderNotepadTabs();
        populateActiveNotepad();
        const titleInput = document.getElementById('notepadTitleInput');
        if (titleInput) titleInput.focus();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

function onNotepadContentChanged() {
    isNotepadDirty = true;
    const saveIndicator = document.getElementById('notepadSaveIndicator');
    if (saveIndicator) {
        saveIndicator.innerHTML = '<span class="spinner-border spinner-border-sm me-1" style="width:0.65rem;height:0.65rem;"></span>Saving...';
    }
    clearTimeout(notepadDebounceTimer);
    notepadDebounceTimer = setTimeout(saveCurrentNotepadImmediately, 1200);
}

async function saveCurrentNotepadImmediately() {
    if (!activeNotepadId) return;
    clearTimeout(notepadDebounceTimer);
    const titleInput = document.getElementById('notepadTitleInput');
    const contentInput = document.getElementById('notepadContentInput');
    const saveIndicator = document.getElementById('notepadSaveIndicator');

    const title = titleInput ? titleInput.value.trim() : 'Untitled Pad';
    const content = contentInput ? contentInput.value : '';

    const current = globalUserNotepads.find(n => n.note_id === activeNotepadId);
    if (current) {
        current.title = title || 'Untitled Pad';
        current.content = content;
    }

    try {
        const res = await fetch(`/api/notepads/${activeNotepadId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, content })
        });
        if (res.ok) {
            isNotepadDirty = false;
            renderNotepadTabs();
            if (saveIndicator) {
                saveIndicator.innerHTML = '<i class="bi bi-check2 text-success me-1"></i>Saved to Cloud';
            }
        }
    } catch (e) {
        if (saveIndicator) {
            saveIndicator.innerHTML = '<i class="bi bi-cloud-slash text-danger me-1"></i>Sync Offline';
        }
    }
}

async function togglePinCurrentNotepad() {
    if (!activeNotepadId) return;
    const current = globalUserNotepads.find(n => n.note_id === activeNotepadId);
    if (!current) return;

    const nextPinState = !current.is_pinned;
    current.is_pinned = nextPinState;

    try {
        await fetch(`/api/notepads/${activeNotepadId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_pinned: nextPinState })
        });
        const pinIcon = document.getElementById('btnPinNotepadIcon');
        if (pinIcon) {
            pinIcon.className = nextPinState ? 'bi bi-pin-fill text-warning' : 'bi bi-pin-angle';
        }
        await loadUserNotepads();
    } catch (e) {}
}

async function setNotepadColor(colorHex) {
    if (!activeNotepadId) return;
    const current = globalUserNotepads.find(n => n.note_id === activeNotepadId);
    if (!current) return;

    current.color = colorHex;
    renderNotepadTabs();

    try {
        await fetch(`/api/notepads/${activeNotepadId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ color: colorHex })
        });
    } catch (e) {}
}

async function deleteCurrentNotepad() {
    if (!activeNotepadId) return;
    if (!confirm('Are you sure you want to delete this notepad?')) return;

    try {
        const res = await fetch(`/api/notepads/${activeNotepadId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            showToast('Notepad deleted', 'info');
            globalUserNotepads = globalUserNotepads.filter(n => n.note_id !== activeNotepadId);
            activeNotepadId = globalUserNotepads.length > 0 ? globalUserNotepads[0].note_id : null;
            renderNotepadTabs();
            populateActiveNotepad();
        }
    } catch (e) {
        showToast('Failed to delete notepad', 'error');
    }
}

// ==========================================================================
// Smart Feedback & Bug Reporting Modal Controller (Admin Triage Routing)
// ==========================================================================
let globalFeedbackModalInstance = null;

function openFeedbackModal() {
    const el = document.getElementById('reportIssueFeedbackModal');
    if (!el) return;
    if (!globalFeedbackModalInstance) {
        globalFeedbackModalInstance = new bootstrap.Modal(el);
    }
    const form = document.getElementById('systemFeedbackForm');
    if (form) form.reset();
    globalFeedbackModalInstance.show();
}

async function submitSystemFeedback(event) {
    event.preventDefault();
    const btn = document.getElementById('btnSubmitFeedback');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Submitting...';
    }

    const payload = {
        category: document.getElementById('feedbackCategory')?.value || 'Bug',
        severity: document.getElementById('feedbackSeverity')?.value || 'Medium',
        summary: document.getElementById('feedbackSummary')?.value.trim() || '',
        details: document.getElementById('feedbackDetails')?.value.trim() || '',
        dashboard_source: window.location.pathname
    };

    try {
        const res = await fetch('/api/feedback/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to submit feedback');

        showToast('Feedback submitted to Administrator triage!', 'success');
        if (globalFeedbackModalInstance) globalFeedbackModalInstance.hide();
        const form = document.getElementById('systemFeedbackForm');
        if (form) form.reset();
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-send me-1"></i> Submit Report';
        }
    }
}

// ==========================================================================
// Birthday-only confetti and click-triggered festival animations.
// ==========================================================================
let confettiAnimationId = null;
let activeFestivalCelebration = null;

function triggerCelebrationConfetti() {
    const canvas = document.getElementById('globalCelebrationCanvas');
    if (!canvas) return;

    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    canvas.style.display = 'block';

    const ctx = canvas.getContext('2d');
    const particles = [];
    const colors = ['#00e5ff', '#0066ff', '#f59e0b', '#ec4899', '#10b981', '#ffffff', '#8b5cf6'];

    // Generate 140 celebratory confetti particles originating from bottom-middle and sides
    for (let i = 0; i < 140; i++) {
        particles.push({
            x: canvas.width * 0.5 + (Math.random() - 0.5) * 200,
            y: canvas.height * 0.7,
            vx: (Math.random() - 0.5) * 18,
            vy: -Math.random() * 20 - 8,
            size: Math.random() * 8 + 4,
            color: colors[Math.floor(Math.random() * colors.length)],
            rotation: Math.random() * 360,
            rotationSpeed: (Math.random() - 0.5) * 12,
            gravity: 0.42,
            opacity: 1,
            decay: Math.random() * 0.012 + 0.008
        });
    }

    if (confettiAnimationId) cancelAnimationFrame(confettiAnimationId);

    function renderConfetti() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        let activeCount = 0;

        for (let p of particles) {
            if (p.opacity > 0) {
                activeCount++;
                p.x += p.vx;
                p.y += p.vy;
                p.vy += p.gravity;
                p.vx *= 0.99;
                p.rotation += p.rotationSpeed;
                p.opacity -= p.decay;

                ctx.save();
                ctx.translate(p.x, p.y);
                ctx.rotate((p.rotation * Math.PI) / 180);
                ctx.globalAlpha = Math.max(0, p.opacity);
                ctx.fillStyle = p.color;
                ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 1.5);
                ctx.restore();
            }
        }

        if (activeCount > 0) {
            confettiAnimationId = requestAnimationFrame(renderConfetti);
        } else {
            canvas.style.display = 'none';
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
    }

    renderConfetti();
}

function setupBirthdayConfettiTrigger() {
    const banners = [
        document.getElementById('userPersonalBirthdayBanner'),
        document.getElementById('userBirthdayBanner')
    ];
    banners.forEach(b => {
        if (b) {
            b.style.cursor = 'pointer';
            b.addEventListener('click', (e) => {
                if (e.target.closest('a') || e.target.closest('button.btn-close')) return;
                triggerCelebrationConfetti();
            });
        }
    });
}

async function checkUserBirthdayCelebration() {
    const banner = document.getElementById('userPersonalBirthdayBanner');
    if (!banner) return;

    const todayStr = getIstDateString();
    const dismissKey = `aisamrat_bday_dismissed_${todayStr}`;
    if (localStorage.getItem(dismissKey) === 'true') {
        banner.style.display = 'none';
        return;
    }

    try {
        const res = await fetch('/api/birthdays/user-status');
        if (!res.ok) return;
        const data = await res.json();

        if (data.is_birthday_today) {
            banner.style.display = 'block';
            const nameEl = document.getElementById('bdayCelebrantName');
            const msgEl = document.getElementById('bdayCelebrantMsg');
            if (nameEl && data.full_name) nameEl.textContent = data.full_name;
            if (msgEl && data.message) msgEl.textContent = data.message;

            // Celebrate the user's birthday once per session.
            const confettiShownKey = `aisamrat_bday_confetti_${todayStr}`;
            if (sessionStorage.getItem(confettiShownKey) !== 'true') {
                sessionStorage.setItem(confettiShownKey, 'true');
                setTimeout(() => {
                    triggerCelebrationConfetti();
                }, 800);
            }
        } else {
            banner.style.display = 'none';
        }
    } catch (e) {
        console.debug('Birthday celebration check error:', e);
    }
}

function dismissUserBirthdayBannerToday() {
    const banner = document.getElementById('userPersonalBirthdayBanner');
    if (banner) banner.style.display = 'none';
    const todayStr = getIstDateString();
    localStorage.setItem(`aisamrat_bday_dismissed_${todayStr}`, 'true');
}

async function checkFestiveGreetings() {
    const button = document.getElementById('festivalCelebrationButton');
    const icon = document.getElementById('festivalCelebrationIcon');
    if (!button || !icon) return;

    try {
        const res = await fetch('/api/festivals/current');
        if (!res.ok) throw new Error(`Festival lookup failed (${res.status})`);
        const data = await res.json();

        if (data.active && data.festival) {
            activeFestivalCelebration = data.festival;
            icon.textContent = activeFestivalCelebration.emoji || '🎉';
            button.title = `Celebrate ${activeFestivalCelebration.name}`;
            button.setAttribute('aria-label', `Celebrate ${activeFestivalCelebration.name}`);
            button.hidden = false;
        } else {
            activeFestivalCelebration = null;
            button.hidden = true;
        }
    } catch (e) {
        console.error('Festival greeting lookup failed:', e);
    }
}

function triggerFestivalAnimation() {
    if (!activeFestivalCelebration) return;
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const canvas = document.getElementById('globalCelebrationCanvas');
    if (!canvas) return;

    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    canvas.style.display = 'block';
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    if (confettiAnimationId) cancelAnimationFrame(confettiAnimationId);

    const festival = activeFestivalCelebration;
    const animationType = festival.animation_type || 'celebration';
    const isSnow = animationType === 'christmas_snow';
    const isKite = animationType === 'sankranti_kites';
    const isStars = animationType === 'crescent_stars';
    const isLeaf = animationType === 'ugadi_foliage';
    const isStreamer = ['karnataka_ribbon', 'confetti_streamers', 'tricolor_accents'].includes(animationType);
    const button = document.getElementById('festivalCelebrationButton');
    const bounds = button ? button.getBoundingClientRect() : { left: canvas.width / 2, top: 0, width: 0, height: 0 };
    const palette = festival.id === 'diwali'
        ? ['#f59e0b', '#ef4444', '#22c55e', '#38bdf8', '#f8fafc']
        : festival.id === 'karnataka_rajyotsava'
            ? ['#facc15', '#dc2626', '#f8fafc']
            : festival.id === 'independence_day' || festival.id === 'republic_day'
                ? ['#f97316', '#ffffff', '#16a34a']
                : festival.id === 'christmas'
                    ? ['#e0f2fe', '#ffffff', '#38bdf8']
                    : festival.id === 'eid'
                        ? ['#10b981', '#f59e0b', '#fef3c7']
                        : ['#f59e0b', '#10b981', '#38bdf8', '#ec4899', '#ffffff'];
    const originX = bounds.left + bounds.width / 2;
    const originY = Math.max(90, bounds.top + bounds.height + 35);
    const particles = [];

    for (let i = 0; i < 96; i++) {
        const angle = Math.random() * Math.PI * 2;
        const speed = isSnow ? Math.random() * 1.2 + 0.4 : Math.random() * 4 + 1.5;
        particles.push({
            x: isSnow ? Math.random() * canvas.width : originX,
            y: isSnow ? -Math.random() * canvas.height : originY,
            vx: isSnow ? (Math.random() - 0.5) * 0.8 : Math.cos(angle) * speed,
            vy: isSnow ? Math.random() * 1.5 + 0.5 : Math.sin(angle) * speed - 1.2,
            size: Math.random() * 3 + 2,
            color: palette[Math.floor(Math.random() * palette.length)],
            rotation: Math.random() * Math.PI,
            rotationSpeed: (Math.random() - 0.5) * 0.08
        });
    }

    let frames = 0;
    function renderFestivalAnimation() {
        frames++;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (const particle of particles) {
            particle.x += particle.vx;
            particle.y += particle.vy;
            particle.vy += isSnow ? 0 : 0.045;
            particle.rotation += particle.rotationSpeed;
            ctx.save();
            ctx.translate(particle.x, particle.y);
            ctx.rotate(particle.rotation);
            ctx.globalAlpha = Math.max(0, 1 - frames / 180);
            ctx.fillStyle = particle.color;
            ctx.beginPath();
            if (isSnow) {
                ctx.arc(0, 0, particle.size, 0, Math.PI * 2);
            } else if (isKite) {
                ctx.moveTo(0, -particle.size * 2);
                ctx.lineTo(particle.size, 0);
                ctx.lineTo(0, particle.size * 2);
                ctx.lineTo(-particle.size, 0);
                ctx.closePath();
            } else if (isStars) {
                for (let point = 0; point < 10; point++) {
                    const radius = point % 2 === 0 ? particle.size * 2 : particle.size;
                    const angle = -Math.PI / 2 + point * Math.PI / 5;
                    const x = Math.cos(angle) * radius;
                    const y = Math.sin(angle) * radius;
                    if (point === 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                }
                ctx.closePath();
            } else if (isLeaf) {
                ctx.ellipse(0, 0, particle.size * 1.8, particle.size, 0, 0, Math.PI * 2);
            } else if (isStreamer) {
                ctx.fillRect(-particle.size / 2, -particle.size * 2, particle.size, particle.size * 4);
            } else {
                ctx.arc(0, 0, particle.size, 0, Math.PI * 2);
            }
            ctx.fill();
            ctx.restore();
        }

        if (frames < 180) {
            confettiAnimationId = requestAnimationFrame(renderFestivalAnimation);
        } else {
            canvas.style.display = 'none';
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
    }

    renderFestivalAnimation();
    showToast(festival.greeting || `Happy ${festival.name}!`, 'success');
}
