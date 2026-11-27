import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  CalendarCheck,
  CalendarDays,
  Award,
  BookOpen,
  Briefcase,
  DollarSign,
  Building2,
  LifeBuoy,
  Gift,
  ShieldCheck,
  Users,
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';

export const Sidebar = ({ isOpen, onClose }) => {
  const { role } = useAuth();

  const navItems = [
    { label: 'Dashboard', path: '/dashboard', icon: LayoutDashboard, roles: ['employee', 'tl', 'manager', 'hr', 'admin'] },
    { label: 'Attendance', path: '/attendance', icon: CalendarCheck, roles: ['employee', 'tl', 'manager', 'hr', 'admin'] },
    { label: 'Leaves & WFH', path: '/leaves', icon: CalendarDays, roles: ['employee', 'tl', 'manager', 'hr', 'admin'] },
    { label: 'Skill Matrix', path: '/skills', icon: Award, roles: ['employee', 'tl', 'manager', 'hr', 'admin'] },
    { label: 'Work Diary', path: '/work-diary', icon: BookOpen, roles: ['employee', 'tl', 'manager', 'hr', 'admin'] },
    { label: 'Projects & Tasks', path: '/projects', icon: Briefcase, roles: ['employee', 'tl', 'manager', 'hr', 'admin'] },
    { label: 'Payroll & Slips', path: '/payroll', icon: DollarSign, roles: ['employee', 'tl', 'manager', 'hr', 'admin'] },
    { label: 'Enterprise Assets', path: '/enterprise', icon: Building2, roles: ['employee', 'tl', 'manager', 'hr', 'admin'] },
    { label: 'Helpdesk & Grievance', path: '/helpdesk', icon: LifeBuoy, roles: ['employee', 'tl', 'manager', 'hr', 'admin'] },
    { label: 'Celebrations & Wall', path: '/celebrations', icon: Gift, roles: ['employee', 'tl', 'manager', 'hr', 'admin'] },
    { label: 'Team Directory', path: '/directory', icon: Users, roles: ['tl', 'manager', 'hr', 'admin'] },
    { label: 'Admin Control Center', path: '/admin', icon: ShieldCheck, roles: ['admin', 'hr'] },
  ];

  const visibleItems = navItems.filter((item) =>
    !item.roles || item.roles.includes(role || 'employee')
  );

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/40 backdrop-blur-xs lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`fixed top-16 bottom-0 left-0 z-30 w-64 border-r border-slate-200 bg-white transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex h-full flex-col justify-between p-4 overflow-y-auto">
          <nav className="space-y-1">
            <div className="px-3 py-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Workforce Navigation
            </div>
            {visibleItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  onClick={onClose}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-semibold transition-all duration-150 ${
                      isActive
                        ? 'bg-blue-600 text-white shadow-xs'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }`
                  }
                >
                  <Icon className="w-4 h-4 stroke-[1.8]" />
                  <span>{item.label}</span>
                </NavLink>
              );
            })}
          </nav>

          <div className="border-t border-slate-100 pt-4 mt-6">
            <div className="rounded-xl bg-slate-50 p-3 border border-slate-200 text-center">
              <span className="text-[11px] font-semibold text-slate-700 block">
                Production Release v2.0
              </span>
              <span className="text-[10px] text-slate-400">
                Zero Mock Data • Real Workforce
              </span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
};

export default Sidebar;

