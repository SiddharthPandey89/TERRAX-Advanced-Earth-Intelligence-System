import { Pool } from 'pg';
import config from './env.js';

export const pool = config.DATABASE_URL
  ? new Pool({ connectionString: config.DATABASE_URL })
  : null;

export async function checkDatabaseConnection() {
  if (!pool) {
    return {
      success: false,
      message: 'DATABASE_URL is not configured.',
    };
  }

  try {
    await pool.query('SELECT 1');
    return {
      success: true,
      message: 'Database connection successful.',
    };
  } catch (error) {
    console.error('Database connection failed:', error.message);
    return {
      success: false,
      message: 'Database connection failed.',
    };
  }
}

