import { Router } from 'express';
import { getHabitabilityAnalysis } from '../services/habitability.service.js';
import { sendError, sendSuccess } from '../utils/response.js';

const router = Router();

router.post('/', async (req, res) => {
  const body = req.body;

  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    sendError(res, 'A valid JSON request body is required.', 400);
    return;
  }

  try {
    const result = await getHabitabilityAnalysis({
      regionName: body.regionName,
      latitude: body.latitude,
      longitude: body.longitude,
    });

    sendSuccess(res, result);
  } catch (error) {
    const statusCode = Number.isInteger(error?.statusCode)
      && error.statusCode >= 400
      && error.statusCode <= 599
      ? error.statusCode
      : 500;
    const message = statusCode >= 500
      ? 'Unable to complete habitability analysis request.'
      : error.message || 'Habitability analysis request failed.';

    console.error('Habitability analysis request failed:', error.message);
    sendError(res, message, statusCode);
  }
});

export default router;
