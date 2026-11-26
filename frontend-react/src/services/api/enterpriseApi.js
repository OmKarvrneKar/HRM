import apiClient from './apiClient';

export const enterpriseApi = {
  getAssetsInventory: async () => {
    const res = await apiClient.get('/api/assets/inventory');
    return res.data;
  },

  getHardwareAssets: async () => {
    const res = await apiClient.get('/api/assets/inventory');
    return res.data;
  },

  getSoftwareLicenses: async () => {
    const res = await apiClient.get('/api/assets/inventory');
    return res.data;
  },

  getSeatingAllocations: async () => {
    const res = await apiClient.get('/api/assets/seating-lockers');
    return res.data;
  },

  allocateSeating: async (payload = {}) => {
    const res = await apiClient.post('/api/assets/seating-lockers/allocate', payload);
    return res.data;
  },

  verifySeatingAllocation: async (allocationId, payload = {}) => {
    const res = await apiClient.post(`/api/assets/seating-lockers/${allocationId}/verify`, payload);
    return res.data;
  },

  getMeetingRooms: async () => {
    const res = await apiClient.get('/api/facilities/rooms');
    return res.data;
  },

  createMeetingRoom: async (payload = {}) => {
    const res = await apiClient.post('/api/facilities/rooms', payload);
    return res.data;
  },

  deleteMeetingRoom: async (roomId) => {
    const res = await apiClient.delete(`/api/facilities/rooms/${roomId}`);
    return res.data;
  },

  verifyMeetingRoom: async (roomId, payload = {}) => {
    const res = await apiClient.post(`/api/facilities/rooms/${roomId}/verify`, payload);
    return res.data;
  },

  getKudosFeed: async () => {
    const res = await apiClient.get('/api/engagement/kudos');
    return res.data;
  },

  sendKudos: async (payload) => {
    const res = await apiClient.post('/api/engagement/kudos/send', payload);
    return res.data;
  },

  getComplaints: async () => {
    const res = await apiClient.get('/api/complaints');
    return res.data;
  },

  submitComplaint: async (payload) => {
    const res = await apiClient.post('/api/complaints', payload);
    return res.data;
  },

  getMonthlyBirthdays: async () => {
    const res = await apiClient.get('/api/birthdays/monthly');
    return res.data;
  },

  getNotifications: async () => {
    const res = await apiClient.get('/api/notifications');
    return res.data;
  },

  markNotificationRead: async (notifId) => {
    const res = await apiClient.post(`/api/notifications/${notifId}/read`);
    return res.data;
  },

  markAllNotificationsRead: async () => {
    const res = await apiClient.post('/api/notifications/read-all');
    return res.data;
  },

  getHolidays: async (year) => {
    const url = year ? `/api/holidays?year=${year}` : '/api/holidays';
    const res = await apiClient.get(url);
    return res.data;
  },

  addHoliday: async (payload) => {
    const res = await apiClient.post('/api/holidays', payload);
    return res.data;
  },

  deleteHoliday: async (holidayId) => {
    const res = await apiClient.delete(`/api/holidays/${holidayId}`);
    return res.data;
  },
};

