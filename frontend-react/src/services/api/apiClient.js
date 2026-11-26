import axios from 'axios';

const apiClient = axios.create({
  baseURL: '', // Proxied via Vite to http://127.0.0.1:5000 in dev
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
  timeout: 30000,
});

// Response interceptor for handling unauthenticated sessions
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      // If unauthorized and not already on auth/login paths, redirect to login
      const currentPath = window.location.pathname;
      if (!currentPath.startsWith('/login') && !currentPath.startsWith('/activate')) {
        window.location.href = '/login?session_expired=1';
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;

