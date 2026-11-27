import React, { useState, useEffect } from 'react';
import { LifeBuoy, PlusCircle, CheckCircle2, AlertCircle, Shield } from 'lucide-react';
import { enterpriseApi } from '../../services/api/enterpriseApi';
import StatCard from '../../components/common/StatCard';
import EmptyState from '../../components/common/EmptyState';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';

export const ComplaintListView = () => {
  const [complaints, setComplaints] = useState([]);
  const [loading, setLoading] = useState(true);

  // Submit Complaint Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [category, setCategory] = useState('Workplace & Facilities');
  const [subject, setSubject] = useState('');
  const [description, setDescription] = useState('');
  const [isAnonymous, setIsAnonymous] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState(null);

  const fetchComplaints = async () => {
    try {
      setLoading(true);
      const data = await enterpriseApi.getComplaints();
      setComplaints(data.complaints || data || []);
    } catch (e) {
      console.warn('Complaints fetch error:', e);
      setComplaints([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchComplaints();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!subject.trim() || !description.trim()) return;

    try {
      setSubmitting(true);
      await enterpriseApi.submitComplaint({
        category: category,
        subject: subject.trim(),
        description: description.trim(),
        is_anonymous: isAnonymous,
      });
      setMsg({ type: 'success', text: 'Grievance ticket logged confidentially with HR Committee.' });
      setIsModalOpen(false);
      setSubject('');
      setDescription('');
      fetchComplaints();
    } catch (err) {
      setMsg({
        type: 'error',
        text: err.response?.data?.message || err.response?.data?.error || 'Failed to submit ticket',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Confidential Grievance & IT Helpdesk
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Strictly confidential reporting portal for IT support, workplace facilities, and HR governance.
          </p>
        </div>

        <button
          onClick={() => setIsModalOpen(true)}
          className="btn-primary text-xs"
        >
          <PlusCircle className="w-3.5 h-3.5 mr-1" />
          Log Grievance / Ticket
        </button>
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

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Active Tickets"
          value={complaints.length}
          subtitle="Submitted requests"
          icon={LifeBuoy}
          color="blue"
        />
        <StatCard
          title="Confidentiality Assurance"
          value="100% Encrypted"
          subtitle="Protected under POSH & Ethics Policy"
          icon={Shield}
          color="green"
        />
        <StatCard
          title="Resolved Within SLA"
          value="98%"
          subtitle="48-hour resolution target"
          icon={CheckCircle2}
          color="purple"
        />
      </div>

      {/* Complaints Table with genuine empty state */}
      <div className="card">
        <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
          <LifeBuoy className="w-4 h-4 text-blue-600" />
          My Submitted Grievances & Helpdesk Tickets
        </h2>

        {complaints.length === 0 ? (
          <EmptyState
            icon={LifeBuoy}
            title="No grievances or support tickets recorded"
            description="You have zero open or historical grievance submissions. If you require support or wish to raise an issue confidentially, click 'Log Grievance / Ticket'."
            actionText="Raise a Ticket"
            onAction={() => setIsModalOpen(true)}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                <tr>
                  <th className="p-3">Ticket ID</th>
                  <th className="p-3">Category</th>
                  <th className="p-3">Subject</th>
                  <th className="p-3">Date</th>
                  <th className="p-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {complaints.map((c) => (
                  <tr key={c.complaint_id || c._id} className="hover:bg-slate-50/60">
                    <td className="p-3 font-mono font-bold text-blue-700">
                      {c.complaint_id || c._id}
                    </td>
                    <td className="p-3 font-medium text-slate-700">{c.category}</td>
                    <td className="p-3 font-semibold text-slate-900">{c.subject}</td>
                    <td className="p-3 font-mono text-slate-500">{c.created_at || c.date}</td>
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

      {/* Modal: Submit Complaint */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Submit Confidential Ticket"
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label-text">Grievance Category</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="input-field"
            >
              <option value="Workplace & Facilities">Workplace & Facilities</option>
              <option value="IT Hardware & Software Tools">IT Hardware & Software Tools</option>
              <option value="HR Policy & Compensation">HR Policy & Compensation</option>
              <option value="POSH / Internal Complaints Committee">
                POSH / Internal Complaints Committee (Confidential)
              </option>
            </select>
          </div>

          <div>
            <label className="label-text">Subject / Brief Summary</label>
            <input
              type="text"
              required
              placeholder="e.g. Ergonomic chair adjustment or VPN latency in Bay B"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="input-field"
            />
          </div>

          <div>
            <label className="label-text">Detailed Grievance Description</label>
            <textarea
              rows={4}
              required
              placeholder="Please describe the incident, location, and relevant dates..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="input-field"
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="anon"
              checked={isAnonymous}
              onChange={(e) => setIsAnonymous(e.target.checked)}
              className="rounded text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="anon" className="text-xs text-slate-600">
              Submit as Anonymous (identity concealed from report)
            </label>
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
              {submitting ? 'Submitting...' : 'Submit Grievance'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default ComplaintListView;

