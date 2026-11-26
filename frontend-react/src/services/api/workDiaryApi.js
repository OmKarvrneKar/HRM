import apiClient from './apiClient';

export const workDiaryApi = {
  getDailyEntries: async (date) => {
    const url = date ? `/api/work-diary/daily?date=${date}` : '/api/work-diary/daily';
    const res = await apiClient.get(url);
    return res.data;
  },

  createEntry: async (payload) => {
    const res = await apiClient.post('/api/work-diary/entries', payload);
    return res.data;
  },

  updateEntry: async (diaryId, payload) => {
    const res = await apiClient.put(`/api/work-diary/entries/${diaryId}`, payload);
    return res.data;
  },

  deleteEntry: async (diaryId) => {
    const res = await apiClient.delete(`/api/work-diary/entries/${diaryId}`);
    return res.data;
  },

  getMonthlyReport: async (year, month) => {
    const res = await apiClient.get(`/api/work-diary/monthly?year=${year}&month=${month}`);
    return res.data;
  },

  getTeamDiary: async (teamId, date) => {
    const params = new URLSearchParams();
    if (teamId) params.append('team_id', teamId);
    if (date) params.append('date', date);
    const res = await apiClient.get(`/api/work-diary/team?${params.toString()}`);
    return res.data;
  },

  submitSupervisorFeedback: async (diaryId, feedback) => {
    const res = await apiClient.post(`/api/work-diary/${diaryId}/feedback`, { feedback });
    return res.data;
  },
};

