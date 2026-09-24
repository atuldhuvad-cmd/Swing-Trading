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

export const consensusApi = {
  getCandidates: (params?: Record<string, any>) => 
    api.get('/consensus/candidates', { params }).then(res => res.data),
  getStockConsensus: (stockId: number, params?: Record<string, any>) => 
    api.get(`/consensus/stocks/${stockId}`, { params }).then(res => res.data),
  getSourceReadiness: () =>
    api.get('/consensus/source-readiness').then(res => res.data),
};

export const stocksApi = {
  getStocks: (params?: Record<string, any>) => api.get('/stocks', { params }).then(res => res.data),
  getStock: (id: number) => api.get(`/stocks/${id}`).then(res => res.data),
};

export const brokersApi = {
  getBrokers: () => api.get('/brokers').then(res => res.data),
};

export const recommendationsApi = {
  getRecommendations: (params?: Record<string, any>) => api.get('/recommendations', { params }).then(res => res.data),
  getRecommendation: (id: number) => api.get(`/recommendations/${id}`).then(res => res.data),
};

export const settingsApi = {
  getSettings: () => api.get('/reference/settings').then(res => res.data),
  updateSettings: (payload: any) => api.put('/reference/settings', payload).then(res => res.data),
};

export const evidenceApi = {
  getCandidates: () => api.get('/evidence/candidates').then(res => res.data),
  getStockEvidence: (stockId: number) => api.get(`/evidence/stocks/${stockId}`).then(res => res.data),
  getMarketData: () => api.get('/evidence/market-data').then(res => res.data),
};

export const fundamentalsApi = {
  getCatalog: () => api.get('/fundamentals/catalog').then(res => res.data),
  preview: (payload: any) => api.post('/fundamentals/preview', payload).then(res => res.data),
  confirm: (payload: any) => api.post('/fundamentals/confirm', payload).then(res => res.data),
};

export const dataSyncApi = {
  getJobs: () => api.get('/data-sync/jobs').then(res => res.data),
  runJob: (jobId: string, confirmProduction = false) => api.post(`/data-sync/jobs/${jobId}/run`, { confirm_production: confirmProduction }).then(res => res.data),
};

export const brokerUploadsApi = {
  list: () => api.get('/broker-uploads').then(res => res.data),
  upload: (file: File, brokerName: string, stockSymbol?: string, note?: string, discoverySource?: string, discoveryUrl?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('broker_name', brokerName);
    if (stockSymbol) formData.append('stock_symbol', stockSymbol);
    if (note) formData.append('note', note);
    if (discoverySource) formData.append('discovery_source', discoverySource);
    if (discoveryUrl) formData.append('discovery_url', discoveryUrl);
    return api.post('/broker-uploads', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }).then(res => res.data);
  },
  // Read-only: nothing is stored or imported.
  preview: (file: File, stockSymbol?: string, discoverySource?: string, discoveryUrl?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    if (stockSymbol) formData.append('stock_symbol', stockSymbol);
    if (discoverySource) formData.append('discovery_source', discoverySource);
    if (discoveryUrl) formData.append('discovery_url', discoveryUrl);
    return api.post('/broker-uploads/preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }).then(res => res.data);
  },
  fileUrl: (uploadId: string) => `/api/broker-uploads/${uploadId}/file`,
};

export default api;

export const tradesApi = {
  calculatePositionSize: (req: { entry_price: number, stop_price: number, max_risk_amount: number, max_capital_allocation?: number }) =>
    api.post('/trades/position-size', req).then(res => res.data),
  createTrade: (req: any) => api.post('/trades/', req).then(res => res.data),
  updateTrade: (tradeId: number, req: any) => api.patch('/trades/' + tradeId, req).then(res => res.data),
  getTrades: () => api.get('/trades/').then(res => res.data),
  getTrade: (tradeId: number) => api.get('/trades/' + tradeId).then(res => res.data),
};
