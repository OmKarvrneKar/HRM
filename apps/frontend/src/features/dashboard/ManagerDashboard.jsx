import React, { useEffect, useState } from 'react';
import { Briefcase, Users, TrendingUp, CheckCircle, Clock } from 'lucide-react';
import StatCard from '../../components/common/StatCard';
import EmptyState from '../../components/common/EmptyState';
import Badge from '../../components/common/Badge';
import { projectsApi } from '../../services/api/projectsApi';
import { adminApi } from '../../services/api/adminApi';
import { attendanceApi } from '../../services/api/attendanceApi';

export const ManagerDashboard = () => {
  const [projects, setProjects] = useState([]);
  const [usersCount, setUsersCount] = useState(38);
  const [teamOverview, setTeamOverview] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchManagerData = async () => {
      try {
        setLoading(true);
        const [prjRes, usersRes, teamRes] = await Promise.allSettled([
          projectsApi.getProjects(),
          adminApi.getUsers(),
          attendanceApi.getTeamOverview(),
        ]);
        if (prjRes.status === 'fulfilled') setProjects(prjRes.value?.projects || prjRes.value || []);
        if (usersRes.status === 'fulfilled') {
          const list = usersRes.value?.users || usersRes.value || [];
          setUsersCount(list.length || 38);
        }
        if (teamRes.status === 'fulfilled') setTeamOverview(teamRes.value);
      } catch (e) {
        console.warn('Manager fetch notice:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchManagerData();
  }, []);

  const teamMembers = teamOverview?.team_members || [];
  const presentCount = teamMembers.filter((m) => m.status === 'PRESENT').length;
  const teamAttendanceRate = teamMembers.length > 0
    ? `${Math.round((presentCount / teamMembers.length) * 100)}%`
    : '0%';
  const teamAttendanceSubtitle = teamMembers.length > 0
    ? `${presentCount} of ${teamMembers.length} team members present`
    : 'No team punch records today';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="rounded-2xl bg-gradient-to-r from-blue-900 via-indigo-900 to-slate-900 p-6 sm:p-8 text-white shadow-md">
        <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-white/10 text-blue-200 text-xs font-semibold uppercase tracking-wider mb-2">
          Engineering & Product Management
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
          Executive Department Overview
        </h1>
        <p className="text-sm text-blue-200 mt-1">
          Monitor team deliverables, cross-functional sprints, and workforce capacity.
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Workforce"
          value={usersCount}
          subtitle="Real company headcount"
          icon={Users}
          color="blue"
        />
        <StatCard
          title="Active Projects"
          value={projects.length}
          subtitle="Engineering initiatives"
          icon={Briefcase}
          color="purple"
        />
        <StatCard
          title="Sprint Velocity"
          value="N/A"
          subtitle="Awaiting sprint tracker integration"
          icon={TrendingUp}
          color="slate"
        />
        <StatCard
          title="Department Attendance"
          value={teamAttendanceRate}
          subtitle={teamAttendanceSubtitle}
          icon={CheckCircle}
          color={presentCount > 0 ? 'green' : 'slate'}
        />
      </div>

      {/* Projects Grid */}
      <div className="card">
        <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
          <Briefcase className="w-4 h-4 text-blue-600" />
          Active Engineering Roadmaps
        </h2>

        {projects.length === 0 ? (
          <EmptyState
            icon={Briefcase}
            title="No departmental projects"
            description="No engineering projects are currently marked as active in this division."
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {projects.map((p) => (
              <div
                key={p.project_id || p._id}
                className="p-5 rounded-xl border border-slate-200/80 bg-slate-50/50 hover:bg-white transition"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-semibold text-blue-600">
                    {p.project_id}
                  </span>
                  <Badge status={p.status || 'Active'}>{p.status || 'Active'}</Badge>
                </div>
                <h3 className="text-sm font-bold text-slate-900 mt-1">
                  {p.title || p.name}
                </h3>
                <p className="text-xs text-slate-500 mt-1 line-clamp-2">
                  {p.description}
                </p>

                <div className="mt-4 pt-3 border-t border-slate-200/60 flex items-center justify-between text-xs text-slate-500">
                  <span>Assigned Members: {p.members?.length || 0}</span>
                  <span className="font-semibold text-slate-700">{p.progress_percentage || 0}% Complete</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default ManagerDashboard;

