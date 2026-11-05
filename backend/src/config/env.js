import 'dotenv/config';

const config = {
  PORT: Number(process.env.PORT || process.env.BACKEND_PORT) || 5000,
  NODE_ENV: process.env.NODE_ENV || 'development',
  ML_SERVICE_URL: (process.env.ML_SERVICE_URL || 'http://127.0.0.1:8000').replace(/\/$/, ''),
  DATABASE_URL: process.env.DATABASE_URL || '',
};

export default config;
