import React, { useState, useEffect } from 'react';
import { BookOpen, PlusCircle, Clock, Calendar, CheckCircle, FileText } from 'lucide-react';
import { workDiaryApi } from '../../services/api/workDiaryApi';
import StatCard from '../../components/common/StatCard';
import EmptyState from '../../components/common/EmptyState';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';

export const WorkDiaryView = () => {
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);

  // Entry Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [taskName, setTaskName] = useState('');
  const [description, setDescription] = useState('');
  const [hoursSpent, setHoursSpent] = useState('2.0');
  const [status, setStatus] = useState('Completed');
  const [submitting, setSubmitting] = useState(false);

  const fetchEntries = async (date) => {
    try {
      setLoading(true);
      const data = await workDiaryApi.getDailyEntries(date);
      setEntries(data.entries || data || []);
    } catch (e) {
      console.warn('Diary fetch error:', e);
      setEntries([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEntries(selectedDate);
  }, [selectedDate]);

  const handleCreateEntry = async (e) => {
    e.preventDefault();
    if (!taskName.trim() || !hoursSpent) return;

    try {
      setSubmitting(true);
      await workDiaryApi.createEntry({
        date: selectedDate,
        task_name: taskName.trim(),
        description: description.trim(),
        hours_spent: parseFloat(hoursSpent),
        status: status,
      });
      setIsModalOpen(false);
      setTaskName('');
      setDescription('');
      fetchEntries(selectedDate);
    } catch (err) {
      alert(err.response?.data?.message || err.response?.data?.error || 'Failed to log diary task');
    } finally {
      setSubmitting(false);
    }
  };

  const totalHours = entries.reduce(
    (sum, cur) => sum + (parseFloat(cur.hours_spent || cur.hours) || 0),
    0
  );

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Daily Work Diary & Timesheet
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Log daily engineering deliverables, track sprint hours, and receive supervisor sign-offs.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="input-field py-1.5 text-xs w-auto font-mono"
          />
          <button
            onClick={() => setIsModalOpen(true)}
            className="btn-primary text-xs shrink-0"
          >
            <PlusCircle className="w-3.5 h-3.5 mr-1" />
            Log Work
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Hours Logged Today"
          value={`${totalHours.toFixed(1)} hrs`}
          subtitle="Target: 8.0 daily work hours"
          icon={Clock}
          color={totalHours >= 8 ? 'green' : 'blue'}
        />
        <StatCard
          title="Tasks Completed"
          value={entries.length}
          subtitle="Logged deliverables for selected date"
          icon={CheckCircle}
          color="purple"
        />
        <StatCard
          title="Supervisor Sign-Off"
          value={entries.some((e) => e.supervisor_feedback) ? 'Reviewed' : 'Pending'}
          subtitle="Team lead sprint verification"
          icon={BookOpen}
          color="amber"
        />
      </div>

      {/* Entries List */}
      <div className="card">
        <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-blue-600" />
          Work Diary Logs for <span className="font-mono text-blue-700">{selectedDate}</span>
        </h2>

        {entries.length === 0 ? (
          <EmptyState
            icon={BookOpen}
            title="No work logged for this date"
            description="You have not recorded any daily work diary entries for the selected date."
            actionText="Log Work Now"
            onAction={() => setIsModalOpen(true)}
          />
        ) : (
          <div className="space-y-3">
            {entries.map((entry, idx) => (
              <div
                key={entry.diary_id || entry._id || idx}
                className="p-4 rounded-xl border border-slate-200/80 bg-slate-50/50 hover:bg-white transition"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-slate-900">
                      {entry.task_name || entry.title}
                    </h3>
                    <p className="text-xs text-slate-600 mt-1 whitespace-pre-line">
                      {entry.description || 'Deliverable executed as per sprint requirement.'}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-slate-800 bg-slate-200/80 px-2 py-0.5 rounded font-mono">
                      {entry.hours_spent || entry.hours} hrs
                    </span>
                    <Badge status={entry.status || 'Completed'}>
                      {entry.status || 'Completed'}
                    </Badge>
                  </div>
                </div>

                {entry.supervisor_feedback && (
                  <div className="mt-3 pt-2 border-t border-slate-200/60 text-xs text-blue-800 bg-blue-50/80 p-2 rounded-lg">
                    <span className="font-semibold">Supervisor Feedback: </span>
                    {entry.supervisor_feedback}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Modal: Log Work */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Log Work Diary Deliverable"
      >
        <form onSubmit={handleCreateEntry} className="space-y-4">
          <div>
            <label className="label-text">Task / Feature Title</label>
            <input
              type="text"
              required
              placeholder="e.g. Refactored React navigation and clean empty states"
              value={taskName}
              onChange={(e) => setTaskName(e.target.value)}
              className="input-field"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label-text">Hours Invested</label>
              <input
                type="number"
                step="0.5"
                min="0.5"
                max="12"
                required
                value={hoursSpent}
                onChange={(e) => setHoursSpent(e.target.value)}
                className="input-field font-mono"
              />
            </div>
            <div>
              <label className="label-text">Task Status</label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="input-field"
              >
                <option value="Completed">Completed</option>
                <option value="In Progress">In Progress</option>
                <option value="Blocked / Awaiting Review">Blocked / Awaiting Review</option>
              </select>
            </div>
          </div>

          <div>
            <label className="label-text">Detailed Description & PR / Ticket Links</label>
            <textarea
              rows={3}
              placeholder="Summary of engineering work performed, commits pushed, or milestones achieved..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
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
              {submitting ? 'Saving...' : 'Record Entry'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default WorkDiaryView;

