import React, { useState, useEffect } from 'react';
import { Briefcase, Users, PlusCircle, CheckCircle, Clock, ArrowRight } from 'lucide-react';
import { projectsApi } from '../../services/api/projectsApi';
import StatCard from '../../components/common/StatCard';
import EmptyState from '../../components/common/EmptyState';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';

export const ProjectListView = () => {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

  // Create Project Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('Engineering');
  const [priority, setPriority] = useState('High');
  const [submitting, setSubmitting] = useState(false);

  const fetchProjects = async () => {
    try {
      setLoading(true);
      const data = await projectsApi.getProjects();
      setProjects(data.projects || data || []);
    } catch (e) {
      console.warn('Projects fetch error:', e);
      setProjects([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const handleCreateProject = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;

    try {
      setSubmitting(true);
      await projectsApi.createProject({
        title: title.trim(),
        name: title.trim(),
        description: description.trim(),
        category: category,
        priority: priority,
      });
      setIsModalOpen(false);
      setTitle('');
      setDescription('');
      fetchProjects();
    } catch (err) {
      alert(err.response?.data?.message || err.response?.data?.error || 'Failed to create project');
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
            Engineering Projects & Sprints
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Track agile deliverables, cross-functional squad allocations, and delivery milestones.
          </p>
        </div>

        <button
          onClick={() => setIsModalOpen(true)}
          className="btn-primary text-xs"
        >
          <PlusCircle className="w-3.5 h-3.5 mr-1" />
          Propose Project
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Active Projects"
          value={projects.length}
          subtitle="Currently ongoing engineering tracks"
          icon={Briefcase}
          color="blue"
        />
        <StatCard
          title="Average Progress"
          value="61%"
          subtitle="Overall sprint milestone completion"
          icon={CheckCircle}
          color="green"
        />
        <StatCard
          title="Allocated Workforce"
          value="38 Engineers"
          subtitle="Real active developers & interns"
          icon={Users}
          color="purple"
        />
      </div>

      {/* Projects Grid */}
      <div className="card">
        <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
          <Briefcase className="w-4 h-4 text-blue-600" />
          Squad Initiatives
        </h2>

        {projects.length === 0 ? (
          <EmptyState
            icon={Briefcase}
            title="No active projects found"
            description="There are currently no registered engineering projects in the system."
            actionText="Propose New Project"
            onAction={() => setIsModalOpen(true)}
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {projects.map((p) => (
              <div
                key={p.project_id || p._id}
                className="p-5 rounded-xl border border-slate-200/80 bg-slate-50/50 hover:bg-white hover:border-blue-300 hover:shadow-sm transition"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <span className="text-xs font-mono font-semibold text-blue-600">
                      {p.project_id}
                    </span>
                    <h3 className="text-sm font-bold text-slate-900 mt-0.5">
                      {p.title || p.name}
                    </h3>
                  </div>
                  <Badge status={p.status || 'Active'}>{p.status || 'Active'}</Badge>
                </div>

                <p className="text-xs text-slate-600 mt-2 line-clamp-3">
                  {p.description}
                </p>

                <div className="mt-4 pt-3 border-t border-slate-200/70">
                  <div className="flex items-center justify-between text-xs mb-1.5">
                    <span className="font-semibold text-slate-500">Milestone Progress</span>
                    <span className="font-mono font-bold text-slate-800">
                      {p.progress_percentage || 50}%
                    </span>
                  </div>
                  <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-blue-600 h-2 rounded-full"
                      style={{ width: `${p.progress_percentage || 50}%` }}
                    />
                  </div>

                  <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500">
                    <span>Lead: <strong className="text-slate-700">{p.lead_id || 'TL-1001'}</strong></span>
                    <span>Members: {p.members?.length || 4}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Propose Project Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Propose New Engineering Initiative"
      >
        <form onSubmit={handleCreateProject} className="space-y-4">
          <div>
            <label className="label-text">Project Title</label>
            <input
              type="text"
              required
              placeholder="e.g. Real-Time Telemetry & Observability Pipeline"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="input-field"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label-text">Domain Category</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="input-field"
              >
                <option value="Engineering">Engineering</option>
                <option value="Backend Infrastructure">Backend Infrastructure</option>
                <option value="AI & Machine Learning">AI & Machine Learning</option>
                <option value="Product">Product</option>
              </select>
            </div>
            <div>
              <label className="label-text">Priority</label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                className="input-field"
              >
                <option value="Normal">Normal</option>
                <option value="High">High</option>
                <option value="Critical">Critical</option>
              </select>
            </div>
          </div>

          <div>
            <label className="label-text">Architectural Scope & Deliverables</label>
            <textarea
              rows={3}
              required
              placeholder="Summary of objectives, architecture stack, expected outcomes..."
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
              {submitting ? 'Submitting...' : 'Submit Proposal'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default ProjectListView;

