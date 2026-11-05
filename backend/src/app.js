import express from 'express';
import config from './config/env.js';
import regionsRouter from './routes/region.routes.js';
import analysisRouter from './routes/analysis.routes.js';
import habitabilityRouter from './routes/habitability.routes.js';
import reportRouter from './routes/report.routes.js';
import mlRouter from './routes/ml.routes.js';
import { checkDatabaseConnection, pool } from './config/database.js';

const app = express();

// ==========================================
// CORS CONFIGURATION
// ==========================================

const configuredOrigins = (
  process.env.CORS_ORIGIN ||
  process.env.FRONTEND_URL ||
  ''
)
  .split(',')
  .map((origin) => origin.trim().replace(/\/$/, ''))
  .filter(Boolean);

// Allowed frontend origins
const allowedOrigins = new Set([
  'https://terraxx.netlify.app',
  'http://localhost:5173',
  'http://localhost:3000',
  'http://127.0.0.1:5173',
  ...configuredOrigins
]);

// CORS Middleware
app.use((req, res, next) => {
  const origin = req.get('Origin');

  res.setHeader('Vary', 'Origin');

  if (!origin) {
    return next();
  }

  if (!allowedOrigins.has(origin.replace(/\/$/, ''))) {
    console.warn(`CORS blocked origin: ${origin}`);

    if (req.method === 'OPTIONS') {
      return res.status(403).json({
        success: false,
        message: 'CORS origin not allowed.'
      });
    }

    return res.status(403).json({
      success: false,
      message: 'Origin not allowed.'
    });
  }

  res.setHeader('Access-Control-Allow-Origin', origin);

  res.setHeader(
    'Access-Control-Allow-Methods',
    'GET, POST, PUT, PATCH, DELETE, OPTIONS'
  );

  res.setHeader(
    'Access-Control-Allow-Headers',
    'Content-Type, Authorization, Accept, X-Requested-With'
  );

  res.setHeader('Access-Control-Max-Age', '86400');

  // Handle preflight requests
  if (req.method === 'OPTIONS') {
    return res.status(204).end();
  }

  return next();
});

// ==========================================
// BODY PARSER
// ==========================================

app.use(express.json({
  limit: '4mb',
  strict: true
}));

// ==========================================
// HEALTH CHECK
// ==========================================

app.get('/api/health', async (_req, res) => {

  let ml = 'unavailable';

  try {
    const response = await fetch(
      `${config.ML_SERVICE_URL}/health`,
      {
        signal: AbortSignal.timeout(2000),
        redirect: 'error'
      }
    );

    ml = response.ok ? 'available' : 'unavailable';

  } catch (error) {
    console.error('ML service health check failed:', error.message);
  }

  let database = 'not_configured';

  if (pool) {
    try {
      const result = await checkDatabaseConnection();

      database = result.success ? 'available' : 'unavailable';

    } catch {
      database = 'unavailable';
    }
  }

  return res.json({
    status: 'ok',
    service: 'earth-geointelligence-backend',
    environment: config.NODE_ENV,
    dependencies: {
      ml_service: ml,
      database
    }
  });
});

// ==========================================
// API ROUTES
// ==========================================

app.use('/api/regions', regionsRouter);

app.use('/api/analysis', analysisRouter);

app.use('/api/habitability', habitabilityRouter);

app.use('/api/ml', mlRouter);

app.use('/api/report', reportRouter);

// ==========================================
// 404 HANDLER
// ==========================================

app.use((req, res) => {
  return res.status(404).json({
    success: false,
    message: 'API endpoint not found.'
  });
});

// ==========================================
// GLOBAL ERROR HANDLER
// ==========================================

app.use((error, _req, res, _next) => {

  if (error?.type === 'entity.too.large') {
    return res.status(413).json({
      success: false,
      message: 'Request body exceeds the 4 MiB limit.'
    });
  }

  if (
    error instanceof SyntaxError &&
    error.status === 400 &&
    'body' in error
  ) {
    return res.status(400).json({
      success: false,
      message: 'Request body must contain valid JSON.'
    });
  }

  console.error(
    'Unhandled request error:',
    error?.message || 'unknown error'
  );

  return res.status(500).json({
    success: false,
    message: 'Internal server error.'
  });

});

export default app;