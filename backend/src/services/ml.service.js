const DEFAULT_TIMEOUT_MS = 30000;
const ALLOWED_PATH = /^\/(?:indicators\/(?:catalog|analyze)|habitability\/analyze|patterns\/analyze|prospectivity\/(?:analyze|auto)|environment\/module|ingestion\/providers|ingestion\/(?:nasa-modis|copernicus-sentinel|usgs-elevation|usgs-geology|openstreetmap)\/search)$/;
const serviceError = (message, statusCode) => Object.assign(new Error(message), { statusCode });

export async function proxyMlRequest(path, { method = 'GET', body } = {}) {
  if (!ALLOWED_PATH.test(path)) throw serviceError('Unsupported ML API route.', 404);
  const base = (process.env.ML_SERVICE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
  let response;
  try {
    response = await fetch(`${base}${path}`, {
      method,
      headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: AbortSignal.timeout(path.startsWith('/ingestion/') || path.startsWith('/environment/') || path === '/prospectivity/auto' ? 100000 : DEFAULT_TIMEOUT_MS),
      redirect: 'error',
    });
  } catch (error) {
    if (error?.name === 'TimeoutError' || error?.name === 'AbortError') throw serviceError('ML service request timed out.', 504);
    throw serviceError('ML service is unavailable.', 503);
  }
  let payload;
  try { payload = await response.json(); }
  catch { throw serviceError('ML service returned an invalid response.', 502); }
  if (!response.ok) {
    const message = typeof payload?.detail === 'string' ? payload.detail : 'ML service rejected the request.';
    throw serviceError(message.slice(0, 500), response.status >= 400 && response.status < 600 ? response.status : 502);
  }
  return payload;
}
export default proxyMlRequest;
