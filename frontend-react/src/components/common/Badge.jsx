import React from 'react';

const statusStyles = {
  // Common states
  active: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  approved: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  present: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  completed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  
  pending: 'bg-amber-50 text-amber-700 border-amber-200',
  pending_tl: 'bg-amber-50 text-amber-700 border-amber-200',
  pending_manager: 'bg-amber-50 text-amber-700 border-amber-200',
  in_progress: 'bg-sky-50 text-sky-700 border-sky-200',
  
  rejected: 'bg-rose-50 text-rose-700 border-rose-200',
  absent: 'bg-rose-50 text-rose-700 border-rose-200',
  inactive: 'bg-slate-100 text-slate-600 border-slate-200',
  draft: 'bg-slate-100 text-slate-600 border-slate-200',
};

export const Badge = ({ status = 'default', children, className = '' }) => {
  const normalized = (status || '').toLowerCase().replace(/[\s-]/g, '_');
  const style = statusStyles[normalized] || 'bg-slate-100 text-slate-700 border-slate-200';

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${style} ${className}`}
    >
      {children || status}
    </span>
  );
};

export default Badge;

