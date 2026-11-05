import { Router } from 'express';
import { pool } from '../config/database.js';

const router = Router();
const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 100;

const regionFields = `
  id,
  name,
  description,
  region_type,
  ST_AsGeoJSON(boundary)::json AS boundary,
  created_at
`;

const parsePagination = (query) => {
  const limit = query.limit === undefined ? DEFAULT_LIMIT : Number(query.limit);
  const offset = query.offset === undefined ? 0 : Number(query.offset);

  if (
    !Number.isInteger(limit)
    || limit < 1
    || limit > MAX_LIMIT
    || !Number.isInteger(offset)
    || offset < 0
  ) {
    return null;
  }

  return { limit, offset };
};

const parseRegionId = (value) => {
  if (!/^\d+$/.test(value)) return null;

  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
};

router.get('/', async (req, res) => {
  const pagination = parsePagination(req.query);

  if (!pagination) {
    res.status(400).json({
      success: false,
      message: 'Invalid limit or offset. Limit must be 1-100 and offset must be a non-negative integer.',
    });
    return;
  }

  if (!pool) {
    res.status(503).json({
      success: false,
      message: 'Database service is unavailable.',
    });
    return;
  }

  try {
    const result = await pool.query(
      `SELECT ${regionFields}
       FROM regions
       ORDER BY id
       LIMIT $1 OFFSET $2`,
      [pagination.limit, pagination.offset],
    );

    res.status(200).json({
      success: true,
      data: result.rows,
      pagination,
    });
  } catch (error) {
    console.error('Failed to retrieve regions:', error.message);
    res.status(500).json({
      success: false,
      message: 'Unable to retrieve regions.',
    });
  }
});

router.get('/:id', async (req, res) => {
  const id = parseRegionId(req.params.id);

  if (!id) {
    res.status(400).json({
      success: false,
      message: 'Invalid region ID.',
    });
    return;
  }

  if (!pool) {
    res.status(503).json({
      success: false,
      message: 'Database service is unavailable.',
    });
    return;
  }

  try {
    const result = await pool.query(
      `SELECT ${regionFields}
       FROM regions
       WHERE id = $1`,
      [id],
    );

    if (result.rows.length === 0) {
      res.status(404).json({
        success: false,
        message: 'Region not found.',
      });
      return;
    }

    res.status(200).json({
      success: true,
      data: result.rows[0],
    });
  } catch (error) {
    console.error('Failed to retrieve region:', error.message);
    res.status(500).json({
      success: false,
      message: 'Unable to retrieve region.',
    });
  }
});

export default router;


