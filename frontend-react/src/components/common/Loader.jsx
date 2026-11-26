import React from 'react';
import { Loader2 } from 'lucide-react';

export const Loader = ({ message = 'Loading...', fullScreen = false }) => {
  if (fullScreen) {
    return (
      <div className="fixed inset-0 bg-slate-900/20 backdrop-blur-sm z-50 flex flex-col items-center justify-center">
        <div className="bg-white p-6 rounded-2xl shadow-xl flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
          <p className="text-sm font-medium text-slate-700">{message}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center p-8 gap-3">
      <Loader2 className="w-6 h-6 text-blue-600 animate-spin" />
      <p className="text-xs font-medium text-slate-500">{message}</p>
    </div>
  );
};

export default Loader;

