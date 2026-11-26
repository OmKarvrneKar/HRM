import apiClient from './apiClient';

export const adminApi = {
  getUsers: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    const res = await apiClient.get(`/api/users?${query}`);
    return res.data;
  },

  createUser: async (payload) => {
    const res = await apiClient.post('/api/users', payload);
    return res.data;
  },

  getUserDetail: async (employeeId) => {
    const res = await apiClient.get(`/api/users/${employeeId}`);
    return res.data;
  },

  updateUser: async (employeeId, payload) => {
    const res = await apiClient.put(`/api/users/${employeeId}`, payload);
    return res.data;
  },

  toggleUserStatus: async (employeeId) => {
    const res = await apiClient.post(`/api/users/${employeeId}/toggle-status`);
    return res.data;
  },

  getAuditLogs: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    const res = await apiClient.get(`/api/audit/logs?${query}`);
    return res.data;
  },

  getSettings: async () => {
    const res = await apiClient.get('/api/settings');
    return res.data;
  },

  updateSettings: async (payload) => {
    const res = await apiClient.put('/api/settings', payload);
    return res.data;
  },
};

