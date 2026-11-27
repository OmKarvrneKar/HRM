import React, { useState, useEffect } from 'react';
import { Gift, Calendar, Heart, Send, Sparkles, PlusCircle } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { enterpriseApi } from '../../services/api/enterpriseApi';
import StatCard from '../../components/common/StatCard';
import EmptyState from '../../components/common/EmptyState';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';

export const CelebrationsView = () => {
  const { user } = useAuth();
  const [birthdays, setBirthdays] = useState([]);
  const [kudos, setKudos] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [holidays, setHolidays] = useState([]);
  const [loading, setLoading] = useState(true);

  // Give Kudos Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [recipientName, setRecipientName] = useState('');
  const [category, setCategory] = useState('Teamwork');
  const [points, setPoints] = useState(50);
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Add Corporate Holiday Modal (HR/Admin)
  const [isHolidayModalOpen, setIsHolidayModalOpen] = useState(false);
  const [newHolidayName, setNewHolidayName] = useState('');
  const [newHolidayDate, setNewHolidayDate] = useState('');
  const [newHolidayType, setNewHolidayType] = useState('National');
  const [holidaySubmitting, setHolidaySubmitting] = useState(false);

  const canManageHolidays = user?.role === 'admin' || user?.role === 'hr' || user?.role === 'hr_manager';

  const fetchCelebrations = async () => {
    try {
      setLoading(true);
      const [bdayRes, kudosRes, holRes] = await Promise.allSettled([
        enterpriseApi.getMonthlyBirthdays(),
        enterpriseApi.getKudosFeed(),
        enterpriseApi.getHolidays(),
      ]);

      if (bdayRes.status === 'fulfilled') setBirthdays(bdayRes.value?.birthdays || bdayRes.value || []);
      if (kudosRes.status === 'fulfilled') {
        const kVal = kudosRes.value || {};
        setKudos(kVal.recent_kudos || kVal.kudos || []);
        setLeaderboard(kVal.leaderboard || []);
      }
      if (holRes.status === 'fulfilled') {
        setHolidays(holRes.value?.holidays || []);
      }
    } catch (e) {
      console.warn('Celebrations fetch error:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCelebrations();
  }, []);

  const handleSendKudos = async (e) => {
    e.preventDefault();
    const target = recipientName.trim();
    if (!target || !message.trim()) return;

    try {
      setSubmitting(true);
      await enterpriseApi.sendKudos({
        recipient_id: target,
        recipient_name: target,
        category: category,
        points: parseInt(points, 10),
        message: message.trim(),
      });
      setIsModalOpen(false);
      setRecipientName('');
      setMessage('');
      fetchCelebrations();
    } catch (err) {
      alert(err.response?.data?.message || err.response?.data?.error || 'Failed to send kudos');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCreateHoliday = async (e) => {
    e.preventDefault();
    if (!newHolidayName.trim() || !newHolidayDate) {
      alert('Please enter both holiday name and date.');
      return;
    }

    try {
      setHolidaySubmitting(true);
      await enterpriseApi.addHoliday({
        name: newHolidayName.trim(),
        date: newHolidayDate,
        type: newHolidayType,
      });
      setIsHolidayModalOpen(false);
      setNewHolidayName('');
      setNewHolidayDate('');
      fetchCelebrations();
    } catch (err) {
      alert(err.response?.data?.message || err.response?.data?.error || 'Failed to declare holiday');
    } finally {
      setHolidaySubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Celebrations, Festivals & Kudos Wall
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Recognize peer excellence with Kudos points, celebrate birthdays, and view company holidays.
          </p>
        </div>

        <button
          onClick={() => setIsModalOpen(true)}
          className="btn-primary text-xs"
        >
          <Sparkles className="w-3.5 h-3.5 mr-1" />
          Give Kudos Points
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Monthly Birthdays"
          value={birthdays.length}
          subtitle="Celebrations scheduled for this month"
          icon={Gift}
          color="rose"
        />
        <StatCard
          title="Peer Appreciations"
          value={kudos.length}
          subtitle="Kudos recognition messages sent"
          icon={Heart}
          color="purple"
        />
        <StatCard
          title="Upcoming Public Holidays"
          value={holidays.length}
          subtitle="Enterprise approved calendar"
          icon={Calendar}
          color="blue"
        />
      </div>

      {/* Grid: Birthdays & Holiday Calendar */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Monthly Birthdays */}
        <div className="card">
          <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
            <Gift className="w-4 h-4 text-rose-500" />
            Monthly Birthday Wall
          </h2>

          {birthdays.length === 0 ? (
            <EmptyState
              icon={Gift}
              title="No birthdays this month"
              description="No employee birthdays fall in the current calendar cycle."
            />
          ) : (
            <div className="divide-y divide-slate-100">
              {birthdays.map((b, idx) => (
                <div key={idx} className="py-3 flex items-center justify-between">
                  <div>
                    <h4 className="text-xs font-bold text-slate-800">{b.name}</h4>
                    <span className="text-[11px] text-slate-400">
                      {b.department || 'Engineering'} • {b.designation || 'Intern'}
                    </span>
                  </div>
                  <span className="text-xs font-semibold text-rose-600 bg-rose-50 px-2.5 py-1 rounded-full border border-rose-200">
                    {b.date || b.dob}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Public Holidays */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Calendar className="w-4 h-4 text-blue-600" />
              Official Holiday Calendar
            </h2>
            {canManageHolidays && (
              <button
                onClick={() => setIsHolidayModalOpen(true)}
                className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
              >
                <PlusCircle className="w-3.5 h-3.5" />
                Declare Holiday
              </button>
            )}
          </div>

          {holidays.length === 0 ? (
            <EmptyState
              icon={Calendar}
              title="No corporate holidays declared"
              description="No official holidays are currently configured in the database for this year. Official holidays will appear once declared by HR."
              actionText={canManageHolidays ? "Declare Corporate Holiday" : undefined}
              onAction={canManageHolidays ? () => setIsHolidayModalOpen(true) : undefined}
            />
          ) : (
            <div className="divide-y divide-slate-100">
              {holidays.map((h, idx) => (
                <div key={h.holiday_id || idx} className="py-3 flex items-center justify-between">
                  <div>
                    <h4 className="text-xs font-bold text-slate-800">{h.name}</h4>
                    <span className="text-[11px] text-slate-500">{h.type}</span>
                  </div>
                  <span className="text-xs font-mono font-semibold text-blue-700 bg-blue-50 px-2.5 py-1 rounded-full border border-blue-200">
                    {h.date}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Kudos Leaderboard & Feed Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Leaderboard Column */}
        <div className="card">
          <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-amber-500" />
            Kudos Leaderboard
          </h2>
          {leaderboard.length === 0 ? (
            <p className="text-xs text-slate-400">No leaderboard entries yet.</p>
          ) : (
            <div className="divide-y divide-slate-100">
              {leaderboard.map((item, idx) => (
                <div key={item.employee_id || idx} className="py-2.5 flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <span className="w-5 h-5 rounded-full bg-slate-100 text-slate-700 font-bold text-[10px] flex items-center justify-center font-mono">
                      {idx + 1}
                    </span>
                    <div>
                      <h4 className="text-xs font-bold text-slate-800">{item.name}</h4>
                      <span className="text-[10px] text-slate-400 font-mono">{item.employee_id}</span>
                    </div>
                  </div>
                  <span className="text-xs font-mono font-bold text-purple-700 bg-purple-50 px-2 py-0.5 rounded-full">
                    {item.total_points} pts
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Kudos Feed Column */}
        <div className="card lg:col-span-2">
          <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
            <Heart className="w-4 h-4 text-purple-600" />
            Peer Recognition Wall
          </h2>

          {kudos.length === 0 ? (
            <EmptyState
              icon={Heart}
              title="No kudos sent yet"
              description="Be the first to appreciate a peer for exceptional teamwork or innovation!"
              actionText="Send First Kudos"
              onAction={() => setIsModalOpen(true)}
            />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {kudos.map((k, idx) => (
                <div
                  key={k.kudos_id || idx}
                  className="p-4 rounded-xl border border-slate-200 bg-gradient-to-br from-purple-50/50 to-white"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-purple-700">
                      {k.sender_name} → <strong className="text-slate-900">{k.recipient_name}</strong>
                    </span>
                    <Badge status="active">+{k.points || 50} pts</Badge>
                  </div>
                  <p className="text-xs text-slate-700 mt-2 italic">
                    "{k.message}"
                  </p>
                  <div className="mt-3 text-[11px] text-slate-400">
                    Category: <span className="font-semibold text-slate-600">{k.category}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Give Kudos Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Appreciate a Colleague (Give Kudos)"
      >
        <form onSubmit={handleSendKudos} className="space-y-4">
          <div>
            <label className="label-text">Colleague Employee ID or Name</label>
            <input
              type="text"
              required
              placeholder="e.g. AS-1019, AS-1001, Deepak S J, Sneha K"
              value={recipientName}
              onChange={(e) => setRecipientName(e.target.value)}
              className="input-field"
            />
            <span className="text-[10px] text-slate-400 mt-1 block">
              Enter any employee ID (AS-1001 to AS-1034) or colleague's full name.
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label-text">Recognition Category</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="input-field"
              >
                <option value="Teamwork">Teamwork & Collaboration</option>
                <option value="Innovation">Technical Innovation</option>
                <option value="Excellence">Operational Excellence</option>
                <option value="Customer Focus">Customer & Product Focus</option>
              </select>
            </div>
            <div>
              <label className="label-text">Points Awarded</label>
              <select
                value={points}
                onChange={(e) => setPoints(e.target.value)}
                className="input-field font-mono"
              >
                <option value={25}>25 Points</option>
                <option value={50}>50 Points</option>
                <option value={100}>100 Points</option>
              </select>
            </div>
          </div>

          <div>
            <label className="label-text">Appreciation Message</label>
            <textarea
              rows={3}
              required
              placeholder="What makes their contribution stand out?"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
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
              {submitting ? 'Sending...' : 'Post Appreciation'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Declare Holiday Modal (HR/Admin) */}
      <Modal
        isOpen={isHolidayModalOpen}
        onClose={() => setIsHolidayModalOpen(false)}
        title="Declare Corporate Holiday"
      >
        <form onSubmit={handleCreateHoliday} className="space-y-4">
          <div>
            <label className="label-text">Holiday Name</label>
            <input
              type="text"
              required
              placeholder="e.g. Ugadi, Diwali, Independence Day"
              value={newHolidayName}
              onChange={(e) => setNewHolidayName(e.target.value)}
              className="input-field"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label-text">Date (YYYY-MM-DD)</label>
              <input
                type="date"
                required
                value={newHolidayDate}
                onChange={(e) => setNewHolidayDate(e.target.value)}
                className="input-field font-mono"
              />
            </div>
            <div>
              <label className="label-text">Holiday Type</label>
              <select
                value={newHolidayType}
                onChange={(e) => setNewHolidayType(e.target.value)}
                className="input-field"
              >
                <option value="National">National Holiday</option>
                <option value="Regional">Regional / State</option>
                <option value="Festival">Festival Holiday</option>
                <option value="Public">Public Holiday</option>
              </select>
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setIsHolidayModalOpen(false)}
              className="btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={holidaySubmitting}
              className="btn-primary"
            >
              {holidaySubmitting ? 'Saving...' : 'Declare Holiday'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default CelebrationsView;

