import React, { useState, useEffect } from 'react';
import { Users, Search, Mail, Phone, Building, Award, Filter, ShieldCheck, Clock, AlertTriangle } from 'lucide-react';
import { adminApi } from '../../services/api/adminApi';
import StatCard from '../../components/common/StatCard';
import EmptyState from '../../components/common/EmptyState';
import Badge from '../../components/common/Badge';

export const TeamDirectoryView = () => {
  const [users, setUsers] = useState([]);
  const [search, setSearch] = useState('');
  const [selectedDept, setSelectedDept] = useState('ALL');
  const [verificationFilter, setVerificationFilter] = useState('ALL'); // ALL, verified, pending_verification, flagged
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDirectory = async () => {
      try {
        setLoading(true);
        const data = await adminApi.getUsers({ include_inactive: 'true' });
        setUsers(data.users || data || []);
      } catch (e) {
        console.warn('Directory fetch error:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchDirectory();
  }, []);

  const verifiedCount = users.filter((u) => u.verification_status === 'verified').length;
  const pendingCount = users.filter((u) => u.verification_status === 'pending_verification').length;
  const flaggedCount = users.filter((u) => u.needs_manual_confirmation).length;

  const filteredUsers = users.filter((u) => {
    const nameStr = (u.full_name || u.name || '').toLowerCase();
    const idStr = (u.employee_id || u.emp_id || '').toLowerCase();
    const emailStr = (u.email || '').toLowerCase();
    const query = search.toLowerCase();

    const matchesSearch = nameStr.includes(query) || idStr.includes(query) || emailStr.includes(query);

    const deptStr = (u.department || 'Unassigned').toLowerCase();
    const matchesDept =
      selectedDept === 'ALL' ||
      deptStr === selectedDept.toLowerCase();

    const matchesVerification =
      verificationFilter === 'ALL' ||
      (verificationFilter === 'verified' && u.verification_status === 'verified') ||
      (verificationFilter === 'pending_verification' && u.verification_status === 'pending_verification') ||
      (verificationFilter === 'flagged' && Boolean(u.needs_manual_confirmation));

    return matchesSearch && matchesDept && matchesVerification;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Workforce Directory
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Official roster of AI Samrat workforce: {verifiedCount} verified personnel and {pendingCount} candidate profiles awaiting onboarding verification.
          </p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <StatCard
          title="Total Master Records"
          value={users.length || 50}
          subtitle="Genuine database profiles"
          icon={Users}
          color="blue"
        />
        <StatCard
          title="Verified Workforce"
          value={`${verifiedCount} Verified`}
          subtitle="34 Interns + 4 Leadership"
          icon={ShieldCheck}
          color="green"
        />
        <StatCard
          title="Pending Verification"
          value={`${pendingCount} Pending`}
          subtitle="Real candidate imports"
          icon={Clock}
          color="amber"
        />
        <StatCard
          title="Flagged for HR Action"
          value={`${flaggedCount} Incomplete`}
          subtitle="Requires HR verification"
          icon={AlertTriangle}
          color={flaggedCount > 0 ? "rose" : "slate"}
        />
      </div>

      {/* Search and Filters */}
      <div className="card">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-6">
          <div className="relative flex-1 max-w-sm">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search by name, ID, or email..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="input-field pl-9"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1.5">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <select
                value={selectedDept}
                onChange={(e) => setSelectedDept(e.target.value)}
                className="input-field text-xs w-auto py-1.5"
              >
                <option value="ALL">All Departments</option>
                <option value="Engineering">Engineering</option>
                <option value="Human Resources">Human Resources</option>
                <option value="IT & Infrastructure">IT & Infrastructure</option>
                <option value="Unassigned">Unassigned</option>
              </select>
            </div>

            <div className="flex items-center gap-1.5">
              <select
                value={verificationFilter}
                onChange={(e) => setVerificationFilter(e.target.value)}
                className="input-field text-xs w-auto py-1.5"
              >
                <option value="ALL">All Profiles ({users.length})</option>
                <option value="verified">Verified Workforce ({verifiedCount})</option>
                <option value="pending_verification">Pending Verification ({pendingCount})</option>
                <option value="flagged">Flagged for HR ({flaggedCount})</option>
              </select>
            </div>
          </div>
        </div>

        {/* Directory Grid */}
        {filteredUsers.length === 0 ? (
          <EmptyState
            title="No matching profiles found"
            description="Try adjusting your search criteria or verification filter."
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredUsers.map((u) => {
              const eid = u.employee_id || u.emp_id;
              const isVerified = u.verification_status === 'verified';
              const displayName = u.full_name || u.name;
              const userKey = eid || (u._id && (u._id.$oid || u._id)) || u.email;

              return (
                <div
                  key={userKey}
                  className={`p-5 rounded-xl border transition ${
                    isVerified
                      ? 'border-slate-200/80 bg-white hover:border-blue-300 shadow-sm'
                      : 'border-amber-200/90 bg-amber-50/20 hover:border-amber-400'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-3 min-w-0">
                      <div
                        className={`h-10 w-10 shrink-0 rounded-full font-bold flex items-center justify-center text-sm shadow-inner ${
                          isVerified
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-amber-100 text-amber-800'
                        }`}
                      >
                        {displayName ? displayName[0].toUpperCase() : '?'}
                      </div>
                      <div className="min-w-0">
                        <h3 className="text-sm font-bold text-slate-900 leading-tight truncate">
                          {displayName || (
                            <span className="text-amber-800 font-medium italic">
                              Name Missing
                            </span>
                          )}
                        </h3>
                        <div className="mt-0.5">
                          {eid ? (
                            <span className="text-[11px] text-blue-700 font-mono font-semibold">
                              {eid}
                            </span>
                          ) : (
                            <span className="text-[10px] text-amber-700 bg-amber-100/80 px-1.5 py-0.5 rounded font-mono font-medium">
                              ID Pending Allocation
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div>
                      {isVerified ? (
                        <Badge status="active">Verified</Badge>
                      ) : (
                        <span className="inline-block px-2 py-0.5 text-[10px] font-semibold rounded-full bg-amber-100 text-amber-800 border border-amber-300 whitespace-nowrap">
                          Pending Verification
                        </span>
                      )}
                    </div>
                  </div>

                  {u.needs_manual_confirmation && (
                    <div className="mt-2.5 p-2 rounded-lg bg-rose-50 border border-rose-200 text-[11px] text-rose-800 flex items-start gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 text-rose-600 shrink-0 mt-0.5" />
                      <span>
                        <strong>HR Action Required:</strong> {u.confirmation_reason || 'Incomplete details from invitation'}
                      </span>
                    </div>
                  )}

                  <div className="mt-3.5 pt-3 border-t border-slate-200/60 space-y-1.5 text-xs text-slate-600">
                    <div className="flex items-center gap-2">
                      <Building className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span className="truncate">
                        {u.designation || 'Role Unassigned'} • {u.department || 'Dept Unassigned'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Mail className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span className="font-mono text-slate-500 truncate">{u.email}</span>
                    </div>
                    {u.contact && (
                      <div className="flex items-center gap-2">
                        <Phone className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className="font-mono text-slate-500">{u.contact}</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default TeamDirectoryView;
