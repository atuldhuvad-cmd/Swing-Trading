import axios from 'axios';

const api = axios.create({
  baseURL: '/api', // Proxy is setup in vite.config.ts?
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;
