import React, { useState, useEffect } from 'react';
import {
  CalendarCheck,
  Clock,
  Calendar,
  AlertCircle,
  PlusCircle,
  CheckCircle2,
  FileQuestion,
} from 'lucide-react';
import { attendanceApi } from '../../services/api/attendanceApi';
import StatCard from '../../components/common/StatCard';
import EmptyState from '../../components/common/EmptyState';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';
import PunchClockWidget from '../../components/layout/PunchClockWidget';

export const AttendancePortal = () => {
  const [history, setHistory] = useState([]);
  const [corrections, setCorrections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Correction form state
  const [corrDate, setCorrDate] = useState('');
  const [requestedCheckIn, setRequestedCheckIn] = useState('09:30');
  const [requestedCheckOut, setRequestedCheckOut] = useState('18:30');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState(null);

  const fetchAttendanceData = async () => {
    try {
      setLoading(true);
      const [histRes, corrRes] = await Promise.allSettled([
        attendanceApi.getMyHistory(30),
        attendanceApi.getMyCorrections(),
      ]);

      if (histRes.status === 'fulfilled') {
        setHistory(histRes.value?.attendance || histRes.value?.history || histRes.value || []);
      }
      if (corrRes.status === 'fulfilled') {
        setCorrections(corrRes.value?.requests || corrRes.value || []);
      }
    } catch (e) {
      console.warn('Attendance fetch error:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAttendanceData();
  }, []);

  const handleCorrectionSubmit = async (e) => {
    e.preventDefault();
    if (!corrDate || !reason) {
      alert('Please fill out date and reason.');
      return;
    }
    try {
      setSubmitting(true);
      await attendanceApi.requestCorrection({
        date: corrDate,
        requested_check_in: requestedCheckIn,
        requested_check_out: requestedCheckOut,
        reason: reason,
      });
      setMsg({ type: 'success', text: 'Attendance correction request submitted to Team Lead!' });
      setIsModalOpen(false);
      setReason('');
      fetchAttendanceData();
    } catch (err) {
      setMsg({
        type: 'error',
        text: err.response?.data?.message || err.response?.data?.error || 'Failed to submit request',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Attendance & Punch Center
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Real-time biometric attendance timeline, working hours calculator, and correction requests.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <PunchClockWidget />
          <button
            onClick={() => setIsModalOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-lg shadow-xs transition"
          >
            <FileQuestion className="w-4 h-4 text-blue-600" />
            Request Correction
          </button>
        </div>
      </div>

      {msg && (
        <div
          className={`p-3 rounded-lg flex items-center gap-2 text-xs ${
            msg.type === 'success'
              ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
              : 'bg-rose-50 text-rose-800 border border-rose-200'
          }`}
        >
          {msg.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
          ) : (
            <AlertCircle className="w-4 h-4 text-rose-600" />
          )}
          <span>{msg.text}</span>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Working Days This Month"
          value="22 Days"
          subtitle="Enterprise standard calendar"
          icon={Calendar}
          color="blue"
        />
        <StatCard
          title="On-Time Attendance"
          value="100%"
          subtitle="Punctual check-ins recorded"
          icon={CheckCircle2}
          color="green"
        />
        <StatCard
          title="Correction Intimations"
          value={corrections.length}
          subtitle="Pending supervisor review"
          icon={Clock}
          color={corrections.length > 0 ? 'amber' : 'purple'}
        />
      </div>

      {/* Attendance History Table */}
      <div className="card">
        <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
          <CalendarCheck className="w-4 h-4 text-blue-600" />
          Attendance Punch Log (Last 30 Days)
        </h2>

        {history.length === 0 ? (
          <EmptyState
            icon={CalendarCheck}
            title="No past attendance punches"
            description="Punch records will accumulate here once check-in/out cycles are completed."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                <tr>
                  <th className="p-3">Date</th>
                  <th className="p-3">First Punch In</th>
                  <th className="p-3">Last Punch Out</th>
                  <th className="p-3">Total Break</th>
                  <th className="p-3">Total Hours</th>
                  <th className="p-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {history.map((h, i) => (
                  <tr key={i} className="hover:bg-slate-50/60">
                    <td className="p-3 font-semibold text-slate-800 font-mono">{h.date}</td>
                    <td className="p-3 text-slate-600 font-mono">{h.first_punch_in || h.check_in || '--:--'}</td>
                    <td className="p-3 text-slate-600 font-mono">{h.last_punch_out || h.check_out || '--:--'}</td>
                    <td className="p-3 text-slate-500">{h.total_break_minutes || 0} min</td>
                    <td className="p-3 font-semibold text-slate-800">{h.total_working_hours || h.hours || '8.0'} hrs</td>
                    <td className="p-3">
                      <Badge status={h.status || 'Present'}>{h.status || 'Present'}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Corrections Queue */}
      <div className="card">
        <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
          <FileQuestion className="w-4 h-4 text-amber-600" />
          My Submitted Attendance Corrections
        </h2>

        {corrections.length === 0 ? (
          <EmptyState
            icon={FileQuestion}
            title="No correction requests"
            description="You have not submitted any attendance correction intimations."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                <tr>
                  <th className="p-3">Date</th>
                  <th className="p-3">Requested In</th>
                  <th className="p-3">Requested Out</th>
                  <th className="p-3">Reason</th>
                  <th className="p-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {corrections.map((c) => (
                  <tr key={c.request_id || c._id} className="hover:bg-slate-50/60">
                    <td className="p-3 font-mono font-semibold text-slate-800">{c.date}</td>
                    <td className="p-3 font-mono text-slate-600">{c.requested_check_in}</td>
                    <td className="p-3 font-mono text-slate-600">{c.requested_check_out}</td>
                    <td className="p-3 text-slate-600">{c.reason}</td>
                    <td className="p-3">
                      <Badge status={c.status}>{c.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal for Correction */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Request Attendance Correction"
      >
        <form onSubmit={handleCorrectionSubmit} className="space-y-4">
          <div>
            <label className="label-text">Select Date</label>
            <input
              type="date"
              required
              value={corrDate}
              onChange={(e) => setCorrDate(e.target.value)}
              className="input-field"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label-text">Corrected Punch In</label>
              <input
                type="time"
                required
                value={requestedCheckIn}
                onChange={(e) => setRequestedCheckIn(e.target.value)}
                className="input-field font-mono"
              />
            </div>
            <div>
              <label className="label-text">Corrected Punch Out</label>
              <input
                type="time"
                required
                value={requestedCheckOut}
                onChange={(e) => setRequestedCheckOut(e.target.value)}
                className="input-field font-mono"
              />
            </div>
          </div>

          <div>
            <label className="label-text">Explanation / Reason</label>
            <textarea
              required
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Card scanner network error during client sync"
              className="input-field"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setIsModalOpen(false)}
              className="btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="btn-primary"
            >
              {submitting ? 'Submitting...' : 'Send to Team Lead'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default AttendancePortal;

