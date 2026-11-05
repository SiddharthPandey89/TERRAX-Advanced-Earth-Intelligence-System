import { Router } from 'express';
import proxyMlRequest from '../services/ml.service.js';

const router = Router();
const validBody = (req, res, next) => {
  if (!req.body || typeof req.body !== 'object' || Array.isArray(req.body)) {
    res.status(400).json({ success: false, message: 'A valid JSON request body is required.' });
    return;
  }
  next();
};
const run = (path, method = 'POST') => async (req, res) => {
  try {
    const data = await proxyMlRequest(path, { method, ...(method === 'POST' ? { body: req.body } : {}) });
    res.status(200).json(data);
  } catch (error) {
    const status = Number.isInteger(error.statusCode) ? error.statusCode : 502;
    res.status(status).json({ success: false, message: error.message || 'ML service request failed.' });
  }
};

router.get('/indicators/catalog', run('/indicators/catalog', 'GET'));
router.post('/indicators/analyze', validBody, run('/indicators/analyze'));
router.post('/habitability/analyze', validBody, run('/habitability/analyze'));
router.post('/patterns/analyze', validBody, run('/patterns/analyze'));
router.post('/prospectivity/analyze', validBody, run('/prospectivity/analyze'));
router.post('/prospectivity/auto', validBody, run('/prospectivity/auto'));
router.post('/environment/module', validBody, run('/environment/module'));
router.get('/ingestion/providers', run('/ingestion/providers', 'GET'));
router.post('/ingestion/:provider/search', validBody, (req, res, next) => {
  const allowed = new Set(['nasa-modis', 'copernicus-sentinel', 'usgs-elevation', 'usgs-geology', 'openstreetmap']);
  if (!allowed.has(req.params.provider)) { res.status(404).json({ success: false, message: 'Unknown provider.' }); return; }
  return run(`/ingestion/${req.params.provider}/search`)(req, res, next);
});

export default router;
