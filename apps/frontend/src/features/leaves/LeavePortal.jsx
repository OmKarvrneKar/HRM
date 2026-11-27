import React, { useState, useEffect } from 'react';
import {
  CalendarDays,
  Home,
  Clock,
  PlusCircle,
  CheckCircle2,
  AlertCircle,
  FileText,
} from 'lucide-react';
import { leavesApi } from '../../services/api/leavesApi';
import StatCard from '../../components/common/StatCard';
import EmptyState from '../../components/common/EmptyState';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';

export const LeavePortal = () => {
  const [activeTab, setActiveTab] = useState('leaves'); // 'leaves', 'wfh', 'overtime'
  const [balances, setBalances] = useState(null);
  const [requests, setRequests] = useState([]);
  const [wfhRequests, setWfhRequests] = useState([]);
  const [overtimeRequests, setOvertimeRequests] = useState([]);
  const [loading, setLoading] = useState(true);

  // Leave Modal
  const [isLeaveModalOpen, setIsLeaveModalOpen] = useState(false);
  const [leaveType, setLeaveType] = useState('Casual Leave');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [reason, setReason] = useState('');

  // WFH Modal
  const [isWfhModalOpen, setIsWfhModalOpen] = useState(false);
  const [wfhDate, setWfhDate] = useState('');
  const [wfhReason, setWfhReason] = useState('');

  // Overtime Modal
  const [isOtModalOpen, setIsOtModalOpen] = useState(false);
  const [otDate, setOtDate] = useState('');
  const [otStartTime, setOtStartTime] = useState('07:00 PM');
  const [otEndTime, setOtEndTime] = useState('09:00 PM');
  const [otType, setOtType] = useState('After shift');
  const [otReason, setOtReason] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState(null);

  const fetchLeaveData = async () => {
    try {
      setLoading(true);
      const [balRes, reqRes, wfhRes, otRes] = await Promise.allSettled([
        leavesApi.getBalances(),
        leavesApi.getMyRequests(),
        leavesApi.getMyWfh(),
        leavesApi.getOvertimeRequests(),
      ]);

      if (balRes.status === 'fulfilled') setBalances(balRes.value?.balances || balRes.value);
      if (reqRes.status === 'fulfilled') setRequests(reqRes.value?.requests || reqRes.value || []);
      if (wfhRes.status === 'fulfilled') setWfhRequests(wfhRes.value?.requests || wfhRes.value || []);
      if (otRes.status === 'fulfilled') setOvertimeRequests(otRes.value?.overtime_requests || otRes.value?.requests || otRes.value || []);
    } catch (e) {
      console.warn('Leaves fetch error:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLeaveData();
  }, []);

  const handleApplyLeave = async (e) => {
    e.preventDefault();
    if (!startDate || !endDate || !reason) {
      alert('Please fill out all required fields.');
      return;
    }
    try {
      setSubmitting(true);
      await leavesApi.applyLeave({
        leave_type: leaveType,
        start_date: startDate,
        end_date: endDate,
        reason: reason,
      });
      setMsg({ type: 'success', text: 'Leave application submitted successfully!' });
      setIsLeaveModalOpen(false);
      setReason('');
      fetchLeaveData();
    } catch (err) {
      setMsg({
        type: 'error',
        text: err.response?.data?.message || err.response?.data?.error || 'Failed to submit leave',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleApplyWfh = async (e) => {
    e.preventDefault();
    if (!wfhDate || !wfhReason) {
      alert('Please fill out WFH date and justification.');
      return;
    }
    try {
      setSubmitting(true);
      await leavesApi.applyWfh({
        date: wfhDate,
        reason: wfhReason,
      });
      setMsg({ type: 'success', text: 'Work-from-home application submitted!' });
      setIsWfhModalOpen(false);
      setWfhReason('');
      fetchLeaveData();
    } catch (err) {
      setMsg({
        type: 'error',
        text: err.response?.data?.message || err.response?.data?.error || 'Failed to submit WFH',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleApplyOvertime = async (e) => {
    e.preventDefault();
    if (!otDate || !otReason) {
      alert('Please fill out overtime date and reason.');
      return;
    }
    try {
      setSubmitting(true);
      await leavesApi.applyOvertime({
        overtime_date: otDate,
        start_time: otStartTime || '07:00 PM',
        end_time: otEndTime || '09:00 PM',
        reason: otReason,
        overtime_type: otType,
      });
      setMsg({ type: 'success', text: 'Overtime request submitted successfully!' });
      setIsOtModalOpen(false);
      setOtReason('');
      fetchLeaveData();
    } catch (err) {
      setMsg({
        type: 'error',
        text: err.response?.data?.message || err.response?.data?.error || 'Failed to submit overtime request',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Leaves, WFH & Overtime
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Apply for statutory leaves, request work-from-home days, and track supervisor sign-offs.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsOtModalOpen(true)}
            className="btn-secondary text-xs"
          >
            <Clock className="w-3.5 h-3.5 mr-1 text-slate-600" />
            Log Overtime
          </button>
          <button
            onClick={() => setIsWfhModalOpen(true)}
            className="btn-secondary text-xs"
          >
            <Home className="w-3.5 h-3.5 mr-1 text-slate-600" />
            Apply WFH
          </button>
          <button
            onClick={() => setIsLeaveModalOpen(true)}
            className="btn-primary text-xs"
          >
            <PlusCircle className="w-3.5 h-3.5 mr-1" />
            Apply Leave
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
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
          )}
          <span>{msg.text}</span>
        </div>
      )}

      {/* Balance Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Casual Leave (CL)"
          value={`${balances?.casual_leave?.remaining ?? 6} Days`}
          subtitle="Remaining of 12 annual days"
          icon={CalendarDays}
          color="blue"
        />
        <StatCard
          title="Sick Leave (SL)"
          value={`${balances?.sick_leave?.remaining ?? 8} Days`}
          subtitle="Remaining of 10 annual days"
          icon={CalendarDays}
          color="green"
        />
        <StatCard
          title="Earned Leave (EL)"
          value={`${balances?.earned_leave?.remaining ?? 15} Days`}
          subtitle="Accrued statutory leave balance"
          icon={CalendarDays}
          color="purple"
        />
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-200">
        <button
          onClick={() => setActiveTab('leaves')}
          className={`py-3 px-4 text-xs font-semibold uppercase tracking-wider transition ${
            activeTab === 'leaves'
              ? 'border-b-2 border-blue-600 text-blue-700 bg-blue-50/40'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          Leave Applications ({requests.length})
        </button>
        <button
          onClick={() => setActiveTab('wfh')}
          className={`py-3 px-4 text-xs font-semibold uppercase tracking-wider transition ${
            activeTab === 'wfh'
              ? 'border-b-2 border-blue-600 text-blue-700 bg-blue-50/40'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          Work From Home ({wfhRequests.length})
        </button>
        <button
          onClick={() => setActiveTab('overtime')}
          className={`py-3 px-4 text-xs font-semibold uppercase tracking-wider transition ${
            activeTab === 'overtime'
              ? 'border-b-2 border-blue-600 text-blue-700 bg-blue-50/40'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          Overtime Log ({overtimeRequests.length})
        </button>
      </div>

      {/* Tab Content: Leaves */}
      {activeTab === 'leaves' && (
        <div className="card">
          <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
            <CalendarDays className="w-4 h-4 text-blue-600" />
            My Leave Request History
          </h2>

          {requests.length === 0 ? (
            <EmptyState
              icon={CalendarDays}
              title="No leave applications found"
              description="You have not submitted any leave requests yet. Click 'Apply Leave' above to submit a new application."
              actionText="Apply for Leave"
              onAction={() => setIsLeaveModalOpen(true)}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                  <tr>
                    <th className="p-3">Leave Type</th>
                    <th className="p-3">From</th>
                    <th className="p-3">To</th>
                    <th className="p-3">Duration</th>
                    <th className="p-3">Reason</th>
                    <th className="p-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {requests.map((r) => (
                    <tr key={r.request_id || r._id} className="hover:bg-slate-50/60">
                      <td className="p-3 font-semibold text-slate-800">{r.leave_type}</td>
                      <td className="p-3 font-mono text-slate-600">{r.start_date}</td>
                      <td className="p-3 font-mono text-slate-600">{r.end_date}</td>
                      <td className="p-3 font-semibold text-slate-700">
                        {r.days_count || r.total_days || 1} day(s)
                      </td>
                      <td className="p-3 text-slate-600 max-w-xs truncate">{r.reason}</td>
                      <td className="p-3">
                        <Badge status={r.status}>{r.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab Content: WFH */}
      {activeTab === 'wfh' && (
        <div className="card">
          <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
            <Home className="w-4 h-4 text-blue-600" />
            Work From Home Logs
          </h2>

          {wfhRequests.length === 0 ? (
            <EmptyState
              icon={Home}
              title="No WFH applications found"
              description="You have no past or upcoming work-from-home records."
              actionText="Request WFH"
              onAction={() => setIsWfhModalOpen(true)}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                  <tr>
                    <th className="p-3">Date</th>
                    <th className="p-3">Justification</th>
                    <th className="p-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {wfhRequests.map((w) => (
                    <tr key={w.request_id || w._id} className="hover:bg-slate-50/60">
                      <td className="p-3 font-mono font-semibold text-slate-800">{w.date}</td>
                      <td className="p-3 text-slate-600">{w.reason}</td>
                      <td className="p-3">
                        <Badge status={w.status}>{w.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab Content: Overtime */}
      {activeTab === 'overtime' && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Clock className="w-4 h-4 text-blue-600" />
              Overtime Logs
            </h2>
            <button
              onClick={() => setIsOtModalOpen(true)}
              className="btn-primary text-xs"
            >
              <PlusCircle className="w-3.5 h-3.5 mr-1" />
              Request Overtime
            </button>
          </div>

          {overtimeRequests.length === 0 ? (
            <EmptyState
              icon={Clock}
              title="No overtime records found"
              description="No authorized overtime entries are recorded for this account."
              actionText="Request Overtime"
              onAction={() => setIsOtModalOpen(true)}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                  <tr>
                    <th className="p-3">Date</th>
                    <th className="p-3">Type</th>
                    <th className="p-3">Duration / Time</th>
                    <th className="p-3">Deliverable / Reason</th>
                    <th className="p-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {overtimeRequests.map((o) => (
                    <tr key={o.request_id || o._id} className="hover:bg-slate-50/60">
                      <td className="p-3 font-mono font-semibold text-slate-800">
                        {o.overtime_date || o.date}
                      </td>
                      <td className="p-3 text-slate-600">
                        {o.overtime_type || 'After shift'}
                      </td>
                      <td className="p-3 font-semibold text-slate-700">
                        {o.duration_display || (o.duration_hours ? `${o.duration_hours} hrs` : (o.hours ? `${o.hours} hrs` : `${o.start_time || '07:00 PM'} - ${o.end_time || '09:00 PM'}`))}
                      </td>
                      <td className="p-3 text-slate-600 max-w-xs truncate">{o.reason || o.task_details}</td>
                      <td className="p-3">
                        <Badge status={o.status}>{o.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Modal: Apply Leave */}
      <Modal
        isOpen={isLeaveModalOpen}
        onClose={() => setIsLeaveModalOpen(false)}
        title="Apply for Official Leave"
      >
        <form onSubmit={handleApplyLeave} className="space-y-4">
          <div>
            <label className="label-text">Leave Category</label>
            <select
              value={leaveType}
              onChange={(e) => setLeaveType(e.target.value)}
              className="input-field"
            >
              <option value="Casual Leave">Casual Leave (CL)</option>
              <option value="Sick Leave">Sick Leave (SL)</option>
              <option value="Earned Leave">Earned Leave (EL)</option>
              <option value="Maternity / Paternity Leave">Maternity / Paternity Leave</option>
              <option value="Bereavement Leave">Bereavement Leave</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label-text">From Date</label>
              <input
                type="date"
                required
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="input-field"
              />
            </div>
            <div>
              <label className="label-text">To Date</label>
              <input
                type="date"
                required
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="input-field"
              />
            </div>
          </div>

          <div>
            <label className="label-text">Reason for Application</label>
            <textarea
              required
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="State clear purpose of leave..."
              className="input-field"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setIsLeaveModalOpen(false)}
              className="btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="btn-primary"
            >
              {submitting ? 'Submitting...' : 'Submit Application'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Modal: Apply WFH */}
      <Modal
        isOpen={isWfhModalOpen}
        onClose={() => setIsWfhModalOpen(false)}
        title="Request Work-From-Home (WFH)"
      >
        <form onSubmit={handleApplyWfh} className="space-y-4">
          <div>
            <label className="label-text">WFH Date</label>
            <input
              type="date"
              required
              value={wfhDate}
              onChange={(e) => setWfhDate(e.target.value)}
              className="input-field"
            />
          </div>

          <div>
            <label className="label-text">Justification & Connectivity Commitment</label>
            <textarea
              required
              rows={3}
              value={wfhReason}
              onChange={(e) => setWfhReason(e.target.value)}
              placeholder="e.g. Fiber broadband available, remote sprint deliverable execution..."
              className="input-field"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setIsWfhModalOpen(false)}
              className="btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="btn-primary"
            >
              {submitting ? 'Submitting...' : 'Submit WFH Request'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Modal: Apply Overtime */}
      <Modal
        isOpen={isOtModalOpen}
        onClose={() => setIsOtModalOpen(false)}
        title="Submit Overtime (OT) Request"
      >
        <form onSubmit={handleApplyOvertime} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label-text">Overtime Date</label>
              <input
                type="date"
                required
                value={otDate}
                onChange={(e) => setOtDate(e.target.value)}
                className="input-field"
              />
            </div>
            <div>
              <label className="label-text">Overtime Shift Type</label>
              <select
                value={otType}
                onChange={(e) => setOtType(e.target.value)}
                className="input-field"
              >
                <option value="After shift">After shift</option>
                <option value="Weekend shift">Weekend shift</option>
                <option value="Holiday support">Holiday support</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label-text">Start Time</label>
              <input
                type="text"
                value={otStartTime}
                onChange={(e) => setOtStartTime(e.target.value)}
                placeholder="07:00 PM"
                className="input-field font-mono"
              />
            </div>
            <div>
              <label className="label-text">End Time</label>
              <input
                type="text"
                value={otEndTime}
                onChange={(e) => setOtEndTime(e.target.value)}
                placeholder="09:00 PM"
                className="input-field font-mono"
              />
            </div>
          </div>

          <div>
            <label className="label-text">Reason / Deliverable Description</label>
            <textarea
              required
              rows={3}
              value={otReason}
              onChange={(e) => setOtReason(e.target.value)}
              placeholder="e.g. Critical release testing, production bug remediation, emergency server deployment..."
              className="input-field"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setIsOtModalOpen(false)}
              className="btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="btn-primary"
            >
              {submitting ? 'Submitting...' : 'Submit Overtime Request'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default LeavePortal;

