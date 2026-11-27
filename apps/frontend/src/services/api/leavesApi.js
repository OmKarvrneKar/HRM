import apiClient from './apiClient';

export const leavesApi = {
  getBalances: async () => {
    const res = await apiClient.get('/api/leaves/balances');
    return res.data;
  },

  getMyRequests: async () => {
    const res = await apiClient.get('/api/leaves/my-requests');
    return res.data;
  },

  applyLeave: async (payload) => {
    const res = await apiClient.post('/api/leaves/apply', payload);
    return res.data;
  },

  cancelLeave: async (requestId) => {
    const res = await apiClient.delete(`/api/leaves/my-requests/${requestId}`);
    return res.data;
  },

  getAllPendingLeaves: async () => {
    const res = await apiClient.get('/api/leaves/all');
    return res.data;
  },

  approveLeave: async (requestId, remarks = '') => {
    const res = await apiClient.post(`/api/leaves/${requestId}/approve`, { remarks });
    return res.data;
  },

  rejectLeave: async (requestId, remarks = '') => {
    const res = await apiClient.post(`/api/leaves/${requestId}/reject`, { remarks });
    return res.data;
  },

  applyWfh: async (payload) => {
    const res = await apiClient.post('/api/wfh/request', payload);
    return res.data;
  },

  getMyWfh: async () => {
    const res = await apiClient.get('/api/wfh/my');
    return res.data;
  },

  getPendingWfh: async () => {
    const res = await apiClient.get('/api/wfh/pending');
    return res.data;
  },

  reviewWfh: async (requestId, payload) => {
    const res = await apiClient.post(`/api/wfh/${requestId}/review`, payload);
    return res.data;
  },

  getOvertimeRequests: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    const res = await apiClient.get(`/api/overtime/list${query ? `?${query}` : ''}`);
    return res.data;
  },

  applyOvertime: async (payload) => {
    const res = await apiClient.post('/api/overtime/request', payload);
    return res.data;
  },
};

