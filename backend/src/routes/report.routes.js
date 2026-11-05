import { Router } from 'express';
import config from '../config/env.js';

const router = Router();

// Renders the PDF in the ML service (reportlab) from the analysis the UI already holds.
router.post('/pdf', async (req, res) => {
  if (!req.body || typeof req.body !== 'object' || Array.isArray(req.body)) {
    res.status(400).json({ success: false, message: 'A valid JSON request body is required.' });
    return;
  }
  try {
    const response = await fetch(`${config.ML_SERVICE_URL}/report/pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body),
      signal: AbortSignal.timeout(30000),
      redirect: 'error',
    });
    if (!response.ok) {
      res.status(502).json({ success: false, message: 'Report generation failed.' });
      return;
    }
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', 'attachment; filename="geointelligence-report.pdf"');
    res.status(200).send(Buffer.from(await response.arrayBuffer()));
  } catch {
    res.status(503).json({ success: false, message: 'ML service is unavailable.' });
  }
});

export default router;
