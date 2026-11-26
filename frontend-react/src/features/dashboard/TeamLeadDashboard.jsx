import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Users, CalendarDays, CheckCircle2, AlertCircle, Award, Briefcase, ArrowRight } from 'lucide-react';
import StatCard from '../../components/common/StatCard';
import EmptyState from '../../components/common/EmptyState';
import Badge from '../../components/common/Badge';
import { attendanceApi } from '../../services/api/attendanceApi';
import { leavesApi } from '../../services/api/leavesApi';
import { projectsApi } from '../../services/api/projectsApi';
import { adminApi } from '../../services/api/adminApi';

export const TeamLeadDashboard = () => {
  const [teamMembers, setTeamMembers] = useState([]);
  const [pendingLeaves, setPendingLeaves] = useState([]);
  const [teamAttendance, setTeamAttendance] = useState(null);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchTLData = async () => {
      try {
        setLoading(true);
        const [usersRes, leavesRes, attRes, prjRes] = await Promise.allSettled([
          adminApi.getUsers({ team_id: 'TEAM-ENG-01' }),
          leavesApi.getAllPendingLeaves(),
          attendanceApi.getTeamOverview(),
          projectsApi.getProjects(),
        ]);

        if (usersRes.status === 'fulfilled') setTeamMembers(usersRes.value?.users || usersRes.value || []);
        if (leavesRes.status === 'fulfilled') setPendingLeaves(leavesRes.value?.requests || leavesRes.value || []);
        if (attRes.status === 'fulfilled') setTeamAttendance(attRes.value);
        if (prjRes.status === 'fulfilled') setProjects(prjRes.value?.projects || prjRes.value || []);
      } catch (err) {
        console.warn('TL dashboard fetch notice:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchTLData();
  }, []);

  const handleApproveLeave = async (requestId) => {
    try {
      await leavesApi.approveLeave(requestId, 'Approved by Team Lead');
      setPendingLeaves((prev) => prev.filter((l) => l.request_id !== requestId));
    } catch (e) {
      alert(e.response?.data?.message || 'Approval failed');
    }
  };

  const handleRejectLeave = async (requestId) => {
    try {
      await leavesApi.rejectLeave(requestId, 'Declined due to sprint deliverable');
      setPendingLeaves((prev) => prev.filter((l) => l.request_id !== requestId));
    } catch (e) {
      alert(e.response?.data?.message || 'Rejection failed');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="rounded-2xl bg-gradient-to-r from-amber-700 via-amber-800 to-slate-900 p-6 sm:p-8 text-white shadow-md">
        <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-white/10 text-amber-200 text-xs font-semibold uppercase tracking-wider mb-2">
          Engineering Squad Lead
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
          Squad Operations & Team Review
        </h1>
        <p className="text-sm text-amber-200 mt-1">
          Review daily attendance, assess intern skill matrices, and sign off on sprint work diaries.
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Squad Strength"
          value={teamMembers.length || 12}
          subtitle="Assigned interns & developers"
          icon={Users}
          color="blue"
        />
        <StatCard
          title="Pending Leave Reviews"
          value={pendingLeaves.length}
          subtitle="Leave & WFH approvals"
          icon={CalendarDays}
          color={pendingLeaves.length > 0 ? 'amber' : 'green'}
        />
        <StatCard
          title="Active Squad Projects"
          value={projects.length}
          subtitle="Under technical supervision"
          icon={Briefcase}
          color="purple"
        />
        <StatCard
          title="Squad Attendance"
          value="96%"
          subtitle="Present on shift today"
          icon={CheckCircle2}
          color="green"
        />
      </div>

      {/* Main Grid: Pending Leave Requests & Squad Members */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Leave Approval Queue */}
        <div className="lg:col-span-2 space-y-6">
          <div className="card">
            <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
              <CalendarDays className="w-4 h-4 text-amber-600" />
              Pending Team Leave & WFH Requests
            </h2>

            {pendingLeaves.length === 0 ? (
              <EmptyState
                icon={CalendarDays}
                title="All caught up!"
                description="There are currently zero pending leave requests requiring team lead review."
              />
            ) : (
              <div className="divide-y divide-slate-100">
                {pendingLeaves.map((l) => (
                  <div key={l.request_id || l._id} className="py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-slate-900">
                          {l.employee_name || l.employee_id}
                        </span>
                        <Badge status={l.status}>{l.status}</Badge>
                      </div>
                      <div className="text-xs text-slate-600 mt-0.5">
                        <span className="font-semibold">{l.leave_type}</span>: {l.start_date} to {l.end_date} ({l.days_count || l.total_days || 1} day)
                      </div>
                      {l.reason && (
                        <p className="text-xs text-slate-500 italic mt-1">
                          "{l.reason}"
                        </p>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => handleApproveLeave(l.request_id)}
                        className="px-3 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg shadow-xs transition"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => handleRejectLeave(l.request_id)}
                        className="px-3 py-1.5 text-xs font-semibold text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded-lg transition"
                      >
                        Decline
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right 1 Col: Squad Directory List */}
        <div className="space-y-6">
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <Users className="w-4 h-4 text-blue-600" />
                Squad Interns
              </h3>
              <Link to="/directory" className="text-xs text-blue-600 hover:underline">
                View All
              </Link>
            </div>

            <div className="divide-y divide-slate-100 max-h-96 overflow-y-auto">
              {teamMembers.slice(0, 6).map((m) => (
                <div key={m.employee_id || m.emp_id} className="py-2.5 flex items-center justify-between">
                  <div>
                    <div className="text-xs font-semibold text-slate-800">
                      {m.full_name || m.name}
                    </div>
                    <div className="text-[11px] text-slate-400 font-mono">
                      {m.employee_id || m.emp_id}
                    </div>
                  </div>
                  <Link
                    to={`/skills?employee_id=${m.employee_id || m.emp_id}`}
                    className="p-1.5 text-slate-400 hover:text-amber-600 hover:bg-amber-50 rounded-lg transition"
                    title="Assess Skills"
                  >
                    <Award className="w-4 h-4" />
                  </Link>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TeamLeadDashboard;

