import apiClient from './apiClient';

export const payrollApi = {
  getUserSalary: async (employeeId) => {
    const res = await apiClient.get(`/api/users/${employeeId}/salary`);
    return res.data;
  },

  generateSalarySlip: async (employeeId, payload) => {
    const res = await apiClient.post(`/api/users/${employeeId}/salary/generate-slip`, payload);
    return res.data;
  },

  getSalarySlip: async (employeeId, yearMonth) => {
    const res = await apiClient.get(`/api/users/${employeeId}/salary-slip/${yearMonth}`);
    return res.data;
  },

  updateSalaryStructure: async (employeeId, structure) => {
    const res = await apiClient.put(`/api/users/${employeeId}/salary`, structure);
    return res.data;
  },
};

