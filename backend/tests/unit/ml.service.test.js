import { afterEach, describe, it } from 'node:test';
import assert from 'node:assert/strict';
import proxyMlRequest from '../../src/services/ml.service.js';

const originalFetch = globalThis.fetch;
const originalUrl = process.env.ML_SERVICE_URL;
afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalUrl === undefined) delete process.env.ML_SERVICE_URL;
  else process.env.ML_SERVICE_URL = originalUrl;
});

describe('FastAPI proxy client', () => {
  it('forwards approved JSON routes to the configured ML service', async () => {
    process.env.ML_SERVICE_URL = 'http://127.0.0.1:8123/';
    let request;
    globalThis.fetch = async (url, init) => {
      request = { url, init };
      return new Response(JSON.stringify({ success: true, results: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    };
    const response = await proxyMlRequest('/indicators/analyze', { method: 'POST', body: { region: { bbox: [1, 2, 3, 4] } } });
    assert.equal(response.success, true);
    assert.equal(request.url, 'http://127.0.0.1:8123/indicators/analyze');
    assert.deepEqual(JSON.parse(request.init.body), { region: { bbox: [1, 2, 3, 4] } });
  });

  it('rejects paths outside the fixed proxy allowlist', async () => {
    await assert.rejects(proxyMlRequest('/health/../../admin'), { statusCode: 404 });
  });

  it('maps failed service requests to a bounded availability error', async () => {
    globalThis.fetch = async () => { throw new TypeError('internal address detail'); };
    await assert.rejects(proxyMlRequest('/indicators/catalog'), (error) => error.statusCode === 503 && !error.message.includes('internal address'));
  });
});
