import apiClient from './apiClient';

export const attendanceApi = {
  getTodayStatus: async () => {
    const res = await apiClient.get('/api/attendance/today');
    return res.data;
  },

  getCutoffStatus: async () => {
    const res = await apiClient.get('/api/attendance/cutoff-status');
    return res.data;
  },

  checkIn: async (data = {}) => {
    const res = await apiClient.post('/api/attendance/check-in', data);
    return res.data;
  },

  checkOut: async (data = {}) => {
    const res = await apiClient.post('/api/attendance/check-out', data);
    return res.data;
  },

  startBreak: async () => {
    const res = await apiClient.post('/api/attendance/break/start');
    return res.data;
  },

  endBreak: async () => {
    const res = await apiClient.post('/api/attendance/break/end');
    return res.data;
  },

  getMyHistory: async (limit = 30) => {
    const res = await apiClient.get(`/api/attendance/my-history?limit=${limit}`);
    return res.data;
  },

  getCalendarMonth: async (year, month) => {
    const res = await apiClient.get(`/api/attendance/calendar-month?year=${year}&month=${month}`);
    return res.data;
  },

  getTeamOverview: async () => {
    const res = await apiClient.get('/api/attendance/team-overview');
    return res.data;
  },

  getHrMonitor: async () => {
    const res = await apiClient.get('/api/attendance/hr-monitor');
    return res.data;
  },

  requestCorrection: async (data) => {
    const res = await apiClient.post('/api/attendance/corrections/request', data);
    return res.data;
  },

  getMyCorrections: async () => {
    const res = await apiClient.get('/api/attendance/corrections/my');
    return res.data;
  },

  getPendingCorrections: async () => {
    const res = await apiClient.get('/api/attendance/corrections/pending');
    return res.data;
  },

  reviewCorrection: async (requestId, payload) => {
    const res = await apiClient.post(`/api/attendance/corrections/${requestId}/review`, payload);
    return res.data;
  },
};

