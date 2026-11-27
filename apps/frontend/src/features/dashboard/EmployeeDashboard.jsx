import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CalendarCheck,
  CalendarDays,
  Award,
  BookOpen,
  Briefcase,
  Gift,
  ArrowRight,
  Clock,
  CheckCircle,
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import StatCard from '../../components/common/StatCard';
import EmptyState from '../../components/common/EmptyState';
import Badge from '../../components/common/Badge';
import { attendanceApi } from '../../services/api/attendanceApi';
import { leavesApi } from '../../services/api/leavesApi';
import { projectsApi } from '../../services/api/projectsApi';
import { workDiaryApi } from '../../services/api/workDiaryApi';
import { enterpriseApi } from '../../services/api/enterpriseApi';

export const EmployeeDashboard = () => {
  const { user } = useAuth();

  const [attendance, setAttendance] = useState(null);
  const [leaveBalances, setLeaveBalances] = useState(null);
  const [myLeaves, setMyLeaves] = useState([]);
  const [projects, setProjects] = useState([]);
  const [dailyDiary, setDailyDiary] = useState([]);
  const [birthdays, setBirthdays] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setLoading(true);
        const [attRes, balRes, lvsRes, prjRes, dryRes, bdayRes] = await Promise.allSettled([
          attendanceApi.getTodayStatus(),
          leavesApi.getBalances(),
          leavesApi.getMyRequests(),
          projectsApi.getProjects(),
          workDiaryApi.getDailyEntries(),
          enterpriseApi.getMonthlyBirthdays(),
        ]);

        if (attRes.status === 'fulfilled') setAttendance(attRes.value);
        if (balRes.status === 'fulfilled') setLeaveBalances(balRes.value?.balances || balRes.value);
        if (lvsRes.status === 'fulfilled') setMyLeaves(lvsRes.value?.requests || lvsRes.value || []);
        if (prjRes.status === 'fulfilled') setProjects(prjRes.value?.projects || prjRes.value || []);
        if (dryRes.status === 'fulfilled') setDailyDiary(dryRes.value?.entries || dryRes.value || []);
        if (bdayRes.status === 'fulfilled') setBirthdays(bdayRes.value?.birthdays || bdayRes.value || []);
      } catch (err) {
        console.warn('Dashboard fetch notice:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

  const checkedIn = attendance?.checked_in || attendance?.is_checked_in;
  const punchInTime = attendance?.first_punch_in || attendance?.check_in_time || '--:--';

  return (
    <div className="space-y-6">
      {/* Welcome Banner */}
      <div className="rounded-2xl bg-gradient-to-r from-blue-900 via-indigo-900 to-slate-900 p-6 sm:p-8 text-white shadow-md relative overflow-hidden">
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-white/10 text-blue-200 text-xs font-semibold uppercase tracking-wider mb-2">
              Workforce Portal
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
              Welcome back, {user?.full_name || user?.name || 'Intern'}!
            </h1>
            <p className="text-sm text-blue-200 mt-1">
              {user?.designation || 'Software Engineering Intern'} • {user?.department || 'Engineering'} • {user?.employee_id || ''}
            </p>
          </div>

          <div className="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-white/10 flex items-center gap-4">
            <div className="p-3 rounded-lg bg-blue-600/30 text-blue-200">
              <Clock className="w-6 h-6" />
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wider text-blue-200 font-semibold">
                Today's Punch
              </div>
              <div className="text-lg font-bold">
                {checkedIn ? `Active since ${punchInTime}` : 'Not Checked In Yet'}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Attendance Status"
          value={checkedIn ? 'PRESENT' : 'AWAITING PUNCH'}
          subtitle={checkedIn ? 'Punched in on schedule' : 'Click punch clock to begin day'}
          icon={CalendarCheck}
          color={checkedIn ? 'green' : 'amber'}
        />
        <StatCard
          title="Casual Leave Balance"
          value={leaveBalances?.casual_leave?.remaining ?? 6}
          subtitle="Annual entitlement available"
          icon={CalendarDays}
          color="blue"
        />
        <StatCard
          title="Active Projects"
          value={projects.length}
          subtitle="Assigned engineering initiatives"
          icon={Briefcase}
          color="purple"
        />
        <StatCard
          title="Today's Work Diary"
          value={`${dailyDiary.length} entries`}
          subtitle="Daily progress log"
          icon={BookOpen}
          color="green"
        />
      </div>

      {/* Main Grid: Projects & Leave History */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Assigned Projects */}
        <div className="lg:col-span-2 space-y-6">
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <Briefcase className="w-4 h-4 text-blue-600" />
                Active Engineering Projects
              </h2>
              <Link
                to="/projects"
                className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
              >
                View All <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {projects.length === 0 ? (
              <EmptyState
                icon={Briefcase}
                title="No active projects"
                description="You are currently not assigned to any ongoing project sprint."
              />
            ) : (
              <div className="space-y-3">
                {projects.slice(0, 3).map((prj) => (
                  <div
                    key={prj.project_id || prj._id}
                    className="p-4 rounded-xl border border-slate-200/80 bg-slate-50/50 hover:bg-white hover:border-blue-200 transition"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <span className="text-xs font-mono text-blue-600 font-semibold">
                          {prj.project_id}
                        </span>
                        <h4 className="text-sm font-bold text-slate-900 mt-0.5">
                          {prj.title || prj.name}
                        </h4>
                        <p className="text-xs text-slate-500 mt-1 line-clamp-2">
                          {prj.description}
                        </p>
                      </div>
                      <Badge status={prj.status || 'Active'}>{prj.status || 'Active'}</Badge>
                    </div>

                    <div className="mt-3 flex items-center gap-3">
                      <div className="flex-1 bg-slate-200 rounded-full h-2 overflow-hidden">
                        <div
                          className="bg-blue-600 h-2 rounded-full"
                          style={{ width: `${prj.progress_percentage || 50}%` }}
                        />
                      </div>
                      <span className="text-xs font-semibold text-slate-700 font-mono">
                        {prj.progress_percentage || 50}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent Leave Requests with genuine empty state */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <CalendarDays className="w-4 h-4 text-blue-600" />
                Recent Leave & WFH Requests
              </h2>
              <Link
                to="/leaves"
                className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
              >
                Apply Leave <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {myLeaves.length === 0 ? (
              <EmptyState
                icon={CalendarDays}
                title="No leave requests"
                description="You haven't submitted any leave or work-from-home requests recently."
                actionText="Apply for Leave"
                onAction={() => (window.location.href = '/leaves')}
              />
            ) : (
              <div className="divide-y divide-slate-100">
                {myLeaves.slice(0, 4).map((l) => (
                  <div key={l.request_id || l._id} className="py-3 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-semibold text-slate-800">
                        {l.leave_type || 'Casual Leave'}
                      </div>
                      <div className="text-[11px] text-slate-500 mt-0.5 font-mono">
                        {l.start_date} to {l.end_date} ({l.days_count || l.total_days || 1} day)
                      </div>
                    </div>
                    <Badge status={l.status}>{l.status}</Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right 1 Col: Celebrations & Quick Actions */}
        <div className="space-y-6">
          {/* Quick Actions Card */}
          <div className="card">
            <h3 className="text-sm font-bold text-slate-900 mb-3">Quick Navigation</h3>
            <div className="grid grid-cols-2 gap-2">
              <Link
                to="/attendance"
                className="p-3 rounded-lg border border-slate-200 hover:border-blue-400 hover:bg-blue-50/50 flex flex-col items-center text-center transition"
              >
                <CalendarCheck className="w-5 h-5 text-blue-600 mb-1" />
                <span className="text-xs font-semibold text-slate-700">Attendance</span>
              </Link>

              <Link
                to="/work-diary"
                className="p-3 rounded-lg border border-slate-200 hover:border-blue-400 hover:bg-blue-50/50 flex flex-col items-center text-center transition"
              >
                <BookOpen className="w-5 h-5 text-indigo-600 mb-1" />
                <span className="text-xs font-semibold text-slate-700">Work Diary</span>
              </Link>

              <Link
                to="/skills"
                className="p-3 rounded-lg border border-slate-200 hover:border-blue-400 hover:bg-blue-50/50 flex flex-col items-center text-center transition"
              >
                <Award className="w-5 h-5 text-amber-600 mb-1" />
                <span className="text-xs font-semibold text-slate-700">Skill Matrix</span>
              </Link>

              <Link
                to="/payroll"
                className="p-3 rounded-lg border border-slate-200 hover:border-blue-400 hover:bg-blue-50/50 flex flex-col items-center text-center transition"
              >
                <CheckCircle className="w-5 h-5 text-emerald-600 mb-1" />
                <span className="text-xs font-semibold text-slate-700">Salary Slip</span>
              </Link>
            </div>
          </div>

          {/* Monthly Birthdays */}
          <div className="card">
            <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2">
              <Gift className="w-4 h-4 text-rose-500" />
              Monthly Birthdays & Wall
            </h3>
            {birthdays.length === 0 ? (
              <EmptyState
                icon={Gift}
                title="No birthdays this month"
                description="No upcoming employee birthdays scheduled for the current cycle."
              />
            ) : (
              <div className="divide-y divide-slate-100">
                {birthdays.slice(0, 4).map((b, i) => (
                  <div key={i} className="py-2.5 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-semibold text-slate-800">{b.name}</div>
                      <div className="text-[11px] text-slate-400">{b.department || 'Engineering'}</div>
                    </div>
                    <span className="text-xs font-medium text-rose-600 bg-rose-50 px-2 py-0.5 rounded-full">
                      {b.date || b.dob}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default EmployeeDashboard;

