import apiClient from './apiClient';

export const projectsApi = {
  getProjects: async () => {
    const res = await apiClient.get('/api/projects');
    return res.data;
  },

  getProjectDetail: async (projectId) => {
    const res = await apiClient.get(`/api/projects/${projectId}`);
    return res.data;
  },

  createProject: async (payload) => {
    const res = await apiClient.post('/api/projects', payload);
    return res.data;
  },

  updateProject: async (projectId, payload) => {
    const res = await apiClient.put(`/api/projects/${projectId}`, payload);
    return res.data;
  },

  getEligibleMembers: async () => {
    const res = await apiClient.get('/api/projects/eligible-members');
    return res.data;
  },

  getPendingApprovals: async () => {
    const res = await apiClient.get('/api/projects/pending-approvals');
    return res.data;
  },

  approveProject: async (projectId, remarks = '') => {
    const res = await apiClient.post(`/api/projects/${projectId}/approve`, { remarks });
    return res.data;
  },

  rejectProject: async (projectId, reason = '') => {
    const res = await apiClient.post(`/api/projects/${projectId}/reject`, { reason });
    return res.data;
  },

  getTasks: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    const res = await apiClient.get(`/api/tasks?${query}`);
    return res.data;
  },

  createTask: async (payload) => {
    const res = await apiClient.post('/api/tasks', payload);
    return res.data;
  },

  updateTaskProgress: async (taskId, progress, status) => {
    const res = await apiClient.put(`/api/tasks/${taskId}/progress`, {
      progress_percentage: progress,
      status: status,
    });
    return res.data;
  },
};

