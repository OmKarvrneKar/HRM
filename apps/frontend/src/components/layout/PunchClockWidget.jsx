import React, { useState, useEffect } from 'react';
import { Play, Square, Coffee, Clock } from 'lucide-react';
import { attendanceApi } from '../../services/api/attendanceApi';

export const PunchClockWidget = () => {
  const [time, setTime] = useState(new Date());
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState(null);

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const refreshStatus = async () => {
    try {
      const data = await attendanceApi.getTodayStatus();
      setStatus(data);
    } catch (e) {
      // Quiet fail if not authenticated
    }
  };

  useEffect(() => {
    refreshStatus();
  }, []);

  const handleAction = async (actionFn, successMsg) => {
    try {
      setLoading(true);
      setActionMsg(null);
      await actionFn();
      setActionMsg(successMsg);
      await refreshStatus();
      setTimeout(() => setActionMsg(null), 3000);
    } catch (err) {
      setActionMsg(err.response?.data?.message || err.response?.data?.error || 'Action failed');
      setTimeout(() => setActionMsg(null), 4000);
    } finally {
      setLoading(false);
    }
  };

  const isCheckedIn = status?.checked_in || status?.is_checked_in;
  const isCheckedOut = status?.checked_out || status?.is_checked_out;
  const isOnBreak = status?.on_break || status?.is_on_break;

  return (
    <div className="flex items-center gap-3 bg-slate-100/80 px-3 py-1.5 rounded-xl border border-slate-200">
      <div className="flex items-center gap-1.5 text-xs font-mono font-semibold text-slate-700">
        <Clock className="w-3.5 h-3.5 text-blue-600" />
        {time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </div>

      <div className="h-4 w-px bg-slate-300 mx-0.5" />

      {actionMsg && (
        <span className="text-xs text-blue-700 font-medium animate-pulse">{actionMsg}</span>
      )}

      <div className="flex items-center gap-1.5">
        {!isCheckedIn ? (
          <button
            onClick={() => handleAction(() => attendanceApi.checkIn(), 'Checked In successfully')}
            disabled={loading}
            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg shadow-xs transition"
          >
            <Play className="w-3 h-3 fill-current" />
            Check In
          </button>
        ) : !isCheckedOut ? (
          <>
            {isOnBreak ? (
              <button
                onClick={() => handleAction(() => attendanceApi.endBreak(), 'Break Ended')}
                disabled={loading}
                className="inline-flex items-center gap-1 px-2 py-1 text-xs font-semibold text-amber-700 bg-amber-100 hover:bg-amber-200 rounded-lg border border-amber-300 transition"
              >
                <Coffee className="w-3 h-3" />
                End Break
              </button>
            ) : (
              <button
                onClick={() => handleAction(() => attendanceApi.startBreak(), 'Break Started')}
                disabled={loading}
                className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300 shadow-xs transition"
              >
                <Coffee className="w-3 h-3 text-amber-600" />
                Break
              </button>
            )}

            <button
              onClick={() => handleAction(() => attendanceApi.checkOut(), 'Checked Out successfully')}
              disabled={loading}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-xs transition"
            >
              <Square className="w-3 h-3 fill-current" />
              Check Out
            </button>
          </>
        ) : (
          <span className="text-xs font-semibold text-slate-500 bg-slate-200 px-2 py-0.5 rounded">
            Completed Today
          </span>
        )}
      </div>
    </div>
  );
};

export default PunchClockWidget;

