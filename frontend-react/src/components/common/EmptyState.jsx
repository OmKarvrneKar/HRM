import React from 'react';
import { Inbox, PlusCircle } from 'lucide-react';

export const EmptyState = ({
  icon: Icon = Inbox,
  title = 'No records found',
  description = 'There are no active records in this section at the moment.',
  actionText,
  onAction,
  className = '',
}) => {
  return (
    <div
      className={`flex flex-col items-center justify-center p-8 text-center bg-slate-50/50 border border-dashed border-slate-200 rounded-xl my-4 ${className}`}
    >
      <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mb-3">
        <Icon className="w-6 h-6 stroke-[1.5]" />
      </div>
      <h3 className="text-base font-semibold text-slate-800 mb-1">{title}</h3>
      <p className="text-xs text-slate-500 max-w-sm mb-4 leading-relaxed">{description}</p>
      {actionText && onAction && (
        <button
          onClick={onAction}
          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-lg shadow-sm transition"
        >
          <PlusCircle className="w-3.5 h-3.5" />
          {actionText}
        </button>
      )}
    </div>
  );
};

export default EmptyState;

