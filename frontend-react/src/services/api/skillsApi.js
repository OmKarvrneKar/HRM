import apiClient from './apiClient';

export const skillsApi = {
  getCategories: async () => {
    const res = await apiClient.get('/api/skills/categories');
    return res.data;
  },

  getUserSkills: async (employeeId) => {
    const res = await apiClient.get(`/api/skills/user/${employeeId}`);
    return res.data;
  },

  addSkill: async (payload) => {
    const res = await apiClient.post('/api/skills', payload);
    return res.data;
  },

  updateSkill: async (skillId, payload) => {
    const res = await apiClient.put(`/api/skills/${skillId}`, payload);
    return res.data;
  },

  deleteSkill: async (skillId) => {
    const res = await apiClient.delete(`/api/skills/${skillId}`);
    return res.data;
  },

  assessSkill: async (skillId, payload) => {
    const res = await apiClient.post(`/api/skills/${skillId}/assess`, payload);
    return res.data;
  },

  getTeamMatrix: async (teamId) => {
    const res = await apiClient.get(`/api/skills/team/${teamId}`);
    return res.data;
  },

  getCompanyMatrix: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    const res = await apiClient.get(`/api/skills/company?${query}`);
    return res.data;
  },

  addCategory: async (name) => {
    const res = await apiClient.post('/api/skills/categories', { name });
    return res.data;
  },

  deleteCategory: async (categoryName) => {
    const res = await apiClient.delete(`/api/skills/categories/${encodeURIComponent(categoryName)}`);
    return res.data;
  },
};

