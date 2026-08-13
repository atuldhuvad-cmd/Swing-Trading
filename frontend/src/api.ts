import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const importsApi = {
  uploadFile: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/imports/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }).then(res => res.data);
  },
  applyMapping: (batchId: number, mapping: any) => 
    api.post(`/imports/${batchId}/mapping`, { mapping }).then(res => res.data),
  getPreview: (batchId: number) => 
    api.get(`/imports/${batchId}/preview`).then(res => res.data),
  confirmBatch: (batchId: number) => 
    api.post(`/imports/${batchId}/confirm`).then(res => res.data),
  rollbackBatch: (batchId: number) => 
    api.post(`/imports/${batchId}/rollback`).then(res => res.data),
  getBatches: () => 
    api.get('/imports').then(res => res.data)
};

export const reviewApi = {
  getItems: () => api.get('/review').then(res => res.data),
  resolveItem: (reviewId: number, req: any) => api.post(`/review/${reviewId}/resolve`, req).then(res => res.data),
};

export default api;
