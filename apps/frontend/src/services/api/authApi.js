import apiClient from './apiClient';

export const authApi = {
  getCaptcha: async () => {
    const res = await apiClient.get('/api/auth/captcha');
    return res.data;
  },

  getDevCaptchaSolution: async () => {
    const res = await apiClient.get('/api/auth/dev-captcha-solution');
    return res.data;
  },

  login: async (credentials) => {
    const res = await apiClient.post('/api/auth/login', credentials);
    return res.data;
  },

  logout: async () => {
    const res = await apiClient.post('/api/auth/logout');
    return res.data;
  },

  getCurrentUser: async () => {
    const res = await apiClient.get('/api/auth/me');
    return res.data;
  },

  requestActivationOtp: async (employeeId, email) => {
    const res = await apiClient.post('/api/auth/activate/request-otp', {
      employee_id: employeeId,
      email: email,
    });
    return res.data;
  },

  completeActivation: async (payload) => {
    const res = await apiClient.post('/api/auth/activate/complete', payload);
    return res.data;
  },

  forgotPassword: async (email) => {
    const res = await apiClient.post('/api/auth/forgot-password', { email });
    return res.data;
  },

  resetPassword: async (payload) => {
    const res = await apiClient.post('/api/auth/reset-password', payload);
    return res.data;
  },
};

