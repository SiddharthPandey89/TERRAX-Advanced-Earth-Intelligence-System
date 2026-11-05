import { Router } from 'express';
import { getWeatherAnalysis } from '../services/analysis.service.js';

const router = Router();

router.post('/', async (req, res) => {
  const body = req.body;

  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    res.status(400).json({
      success: false,
      message: 'A valid JSON request body is required.',
    });
    return;
  }

  try {
    const result = await getWeatherAnalysis({
      regionName: body.regionName,
      latitude: body.latitude,
      longitude: body.longitude,
    });

    res.status(200).json({
      success: true,
      data: result,
    });
  } catch (error) {
    const statusCode = Number.isInteger(error?.statusCode)
      && error.statusCode >= 400
      && error.statusCode <= 599
      ? error.statusCode
      : 500;

    const message = statusCode === 500
      ? 'Unable to complete analysis request.'
      : error.message || 'Analysis request failed.';

    console.error('Analysis request failed:', error.message);

    res.status(statusCode).json({
      success: false,
      message,
    });
  }
});

export default router;

