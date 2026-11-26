import React from 'react';
import { Bell, LogOut, Shield, User } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import PunchClockWidget from './PunchClockWidget';

export const Navbar = ({ onToggleSidebar }) => {
  const { user, role, logout } = useAuth();

  const roleColors = {
    admin: 'bg-purple-100 text-purple-800 border-purple-200',
    hr: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    manager: 'bg-blue-100 text-blue-800 border-blue-200',
    tl: 'bg-amber-100 text-amber-800 border-amber-200',
    employee: 'bg-slate-100 text-slate-800 border-slate-200',
  };

  const currentRoleStyle = roleColors[role] || roleColors.employee;

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-200 bg-white/95 px-6 backdrop-blur-md transition-all">
      {/* Brand logo & mobile toggle */}
      <div className="flex items-center gap-4">
        <button
          onClick={onToggleSidebar}
          className="lg:hidden p-1.5 text-slate-600 hover:bg-slate-100 rounded-lg"
          aria-label="Toggle Navigation"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-blue-700 to-indigo-600 flex items-center justify-center text-white font-bold text-lg shadow-sm">
            AS
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-slate-900 leading-none">
              AI SAMRAT HRMS
            </h1>
            <p className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 mt-0.5">
              Enterprise Workforce
            </p>
          </div>
        </div>
      </div>

      {/* Center punch clock */}
      <div className="hidden md:flex items-center">
        <PunchClockWidget />
      </div>

      {/* Right controls: role pill, profile, notifications, logout */}
      <div className="flex items-center gap-3">
        {role && (
          <span
            className={`hidden sm:inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wider border ${currentRoleStyle}`}
          >
            <Shield className="w-3 h-3" />
            {role}
          </span>
        )}

        <div className="flex items-center gap-2 border-l border-slate-200 pl-3">
          <div className="flex flex-col text-right">
            <span className="text-xs font-semibold text-slate-900 leading-tight">
              {user?.full_name || user?.name || user?.employee_id || 'User'}
            </span>
            <span className="text-[11px] text-slate-500 font-mono">
              {user?.employee_id || user?.emp_id || ''}
            </span>
          </div>

          <button
            onClick={logout}
            title="Sign Out"
            className="p-2 text-slate-500 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
};

export default Navbar;

