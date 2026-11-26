import React, { useState, useEffect } from 'react';
import { Award, PlusCircle, Star, CheckCircle, Search, Layers } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { skillsApi } from '../../services/api/skillsApi';
import StatCard from '../../components/common/StatCard';
import EmptyState from '../../components/common/EmptyState';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';

export const SkillMatrixView = () => {
  const { user, role } = useAuth();
  const [categories, setCategories] = useState([]);
  const [userSkills, setUserSkills] = useState([]);
  const [activeCategory, setActiveCategory] = useState('ALL');
  const [loading, setLoading] = useState(true);

  // Add Skill Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [skillName, setSkillName] = useState('');
  const [category, setCategory] = useState('Frontend Web');
  const [proficiency, setProficiency] = useState(3);
  const [submitting, setSubmitting] = useState(false);

  const fetchSkills = async () => {
    try {
      setLoading(true);
      const [catRes, userRes] = await Promise.allSettled([
        skillsApi.getCategories(),
        skillsApi.getUserSkills(user?.employee_id || user?.emp_id || 'AS-1001'),
      ]);

      if (catRes.status === 'fulfilled') {
        const cats = catRes.value?.categories || [];
        setCategories(cats);
        if (cats.length > 0) {
          setCategory(cats[0]);
        }
      }
      if (userRes.status === 'fulfilled') {
        setUserSkills(userRes.value?.skills || userRes.value || []);
      }
    } catch (e) {
      console.warn('Skills fetch error:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user) {
      fetchSkills();
    }
  }, [user]);

  const avgProf = userSkills.length > 0
    ? `${(userSkills.reduce((acc, s) => acc + Number(s.proficiency_level || s.proficiency_score || 0), 0) / userSkills.length).toFixed(1)} / 5.0`
    : '—';

  const handleAddSkill = async (e) => {
    e.preventDefault();
    if (!skillName.trim()) return;
    if (categories.length === 0) {
      alert('No skill categories configured in the database. Please contact HR/Admin.');
      return;
    }

    try {
      setSubmitting(true);
      await skillsApi.addSkill({
        employee_id: user?.employee_id || user?.emp_id,
        skill_name: skillName.trim(),
        category: category,
        proficiency_level: Number(proficiency),
        self_rating: Number(proficiency),
      });
      setIsModalOpen(false);
      setSkillName('');
      fetchSkills();
    } catch (err) {
      alert(err.response?.data?.message || err.response?.data?.error || 'Failed to add skill');
    } finally {
      setSubmitting(false);
    }
  };

  const filteredSkills =
    activeCategory === 'ALL'
      ? userSkills
      : userSkills.filter((s) => s.category === activeCategory);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Enterprise Skill Matrix
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Map competencies across database-configured engineering categories, track trainer sign-offs and star ratings.
          </p>
        </div>

        <button
          onClick={() => setIsModalOpen(true)}
          className="btn-primary text-xs"
        >
          <PlusCircle className="w-3.5 h-3.5 mr-1" />
          Add Competency
        </button>
      </div>

      {categories.length === 0 && (
        <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs">
          <strong>Database Notice:</strong> No company skill categories are currently configured in the database. HR or Admin can configure official tracks in the Admin Control Center.
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Verified Competencies"
          value={userSkills.length}
          subtitle="Skills recorded in database"
          icon={Award}
          color="blue"
        />
        <StatCard
          title="Average Proficiency"
          value={avgProf}
          subtitle={userSkills.length > 0 ? "Calculated from technical assessments" : "No recorded assessments"}
          icon={Star}
          color="amber"
        />
        <StatCard
          title="Skill Domains"
          value={categories.length}
          subtitle="Database-managed tracks"
          icon={Layers}
          color="purple"
        />
      </div>

      {/* Category Filter Pills */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2 border-b border-slate-200">
        <button
          onClick={() => setActiveCategory('ALL')}
          className={`px-3 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition ${
            activeCategory === 'ALL'
              ? 'bg-blue-600 text-white shadow-xs'
              : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
          }`}
        >
          All Domains ({userSkills.length})
        </button>
        {categories.map((c) => (
          <button
            key={c}
            onClick={() => setActiveCategory(c)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition ${
              activeCategory === c
                ? 'bg-blue-600 text-white shadow-xs'
                : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
            }`}
          >
            {c}
          </button>
        ))}
      </div>

      {/* Skills Grid */}
      <div className="card">
        <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
          <Award className="w-4 h-4 text-blue-600" />
          Proficiency Matrix
        </h2>

        {filteredSkills.length === 0 ? (
          <EmptyState
            icon={Award}
            title="No skills recorded in this category"
            description="Add your validated technical skills and frameworks to build your competency profile."
            actionText="Add Skill"
            onAction={() => setIsModalOpen(true)}
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredSkills.map((s, idx) => (
              <div
                key={s.skill_id || s._id || idx}
                className="p-4 rounded-xl border border-slate-200/80 bg-slate-50/50 hover:bg-white hover:border-blue-300 transition"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-slate-900">{s.skill_name || s.name}</h3>
                    <span className="text-[11px] text-slate-500 font-medium">
                      {s.category || 'Engineering'}
                    </span>
                  </div>
                  <Badge status={s.is_verified ? 'approved' : 'pending'}>
                    {s.is_verified ? 'Verified' : 'Self-Rated'}
                  </Badge>
                </div>

                <div className="mt-4 flex items-center justify-between">
                  <div className="flex items-center gap-1">
                    {[1, 2, 3, 4, 5].map((star) => (
                      <Star
                        key={star}
                        className={`w-4 h-4 ${
                          star <= (s.proficiency_level || s.rating || 3)
                            ? 'text-amber-400 fill-amber-400'
                            : 'text-slate-200'
                        }`}
                      />
                    ))}
                  </div>
                  <span className="text-xs font-semibold text-slate-700">
                    Level {s.proficiency_level || s.rating || 3}/5
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add Skill Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Register Technical Competency"
      >
        <form onSubmit={handleAddSkill} className="space-y-4">
          <div>
            <label className="label-text">Skill / Technology Name</label>
            <input
              type="text"
              required
              placeholder="e.g. React.js, Python Flask, Docker, PyTorch"
              value={skillName}
              onChange={(e) => setSkillName(e.target.value)}
              className="input-field"
            />
          </div>

          <div>
            <label className="label-text">Category / Domain</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="input-field"
              disabled={categories.length === 0}
            >
              {categories.length === 0 ? (
                <option value="">No categories configured in database</option>
              ) : (
                categories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))
              )}
            </select>
            {categories.length === 0 && (
              <span className="text-[10px] text-amber-600 mt-1 block">
                Official skill categories must be configured in Admin Control Center first.
              </span>
            )}
          </div>

          <div>
            <label className="label-text">Self-Assessed Proficiency (1 to 5 Stars)</label>
            <select
              value={proficiency}
              onChange={(e) => setProficiency(e.target.value)}
              className="input-field"
            >
              <option value={1}>1 Star - Novice / Fundamental Concepts</option>
              <option value={2}>2 Stars - Beginner / Supervised Application</option>
              <option value={3}>3 Stars - Competent / Independent Production Code</option>
              <option value={4}>4 Stars - Advanced / Architectural Implementation</option>
              <option value={5}>5 Stars - Expert / Enterprise Lead / Authority</option>
            </select>
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
              {submitting ? 'Saving...' : 'Save Skill'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default SkillMatrixView;

