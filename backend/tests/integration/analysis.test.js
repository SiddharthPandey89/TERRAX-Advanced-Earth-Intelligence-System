import { after, afterEach, describe, it } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';

import app from '../../src/app.js';
import getWeatherAnalysis from '../../src/services/analysis.service.js';

const originalFetch = globalThis.fetch;
const validPayload = {
  current: {
    temperature_2m: 25.4,
    relative_humidity_2m: 61,
    precipitation: 0.2,
    wind_speed_10m: 12.1,
  },
  current_units: {
    temperature_2m: '°C',
    relative_humidity_2m: '%',
    precipitation: 'mm',
    wind_speed_10m: 'km/h',
  },
  daily: {
    temperature_2m_max: [31.2],
    temperature_2m_min: [19.8],
    precipitation_sum: [2.6],
  },
  daily_units: {
    temperature_2m_max: '°C',
    temperature_2m_min: '°C',
    precipitation_sum: 'mm',
  },
};

const responseWithJson = (payload, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => payload,
});

const startServer = () => new Promise((resolve, reject) => {
  const server = app.listen(0, '127.0.0.1', () => resolve(server));
  server.once('error', reject);
});

const closeServer = (server) => new Promise((resolve, reject) => {
  if (!server.listening) {
    resolve();
    return;
  }

  server.close((error) => (error ? reject(error) : resolve()));
});

const request = (server, body) => new Promise((resolve, reject) => {
  const address = server.address();
  const requestBody = JSON.stringify(body);
  const requestOptions = {
    hostname: address.address,
    port: address.port,
    path: '/api/analysis',
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'content-length': Buffer.byteLength(requestBody),
    },
  };

  const clientRequest = http.request(requestOptions, (response) => {
    let responseBody = '';
    response.setEncoding('utf8');
    response.on('data', (chunk) => {
      responseBody += chunk;
    });
    response.on('end', () => {
      resolve({
        statusCode: response.statusCode,
        body: JSON.parse(responseBody),
      });
    });
  });

  clientRequest.on('error', reject);
  clientRequest.end(requestBody);
});

after(() => {
  globalThis.fetch = originalFetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe('getWeatherAnalysis', () => {
  it('returns structured weather data for valid region coordinates', async () => {
    let requestedUrl;
    globalThis.fetch = async (url) => {
      requestedUrl = new URL(url);
      return responseWithJson(validPayload);
    };

    const result = await getWeatherAnalysis({
      regionName: 'Bhopal',
      latitude: '23.2599',
      longitude: 77.4126,
    });

    assert.equal(result.region.name, 'Bhopal');
    assert.equal(result.region.latitude, 23.2599);
    assert.equal(result.analysis.current.temperature, 25.4);
    assert.equal(result.analysis.daily.maximumTemperature, 31.2);
    assert.equal(result.units.temperature, '°C');
    assert.equal(result.dataProvider, 'Open-Meteo');
    assert.ok(result.retrievedAt);
    assert.equal(requestedUrl.searchParams.get('forecast_days'), '1');
    assert.equal(
      requestedUrl.searchParams.get('current'),
      'temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m',
    );
  });

  it('rejects missing, empty, or non-string region names', async () => {
    for (const regionName of [undefined, '', '   ', 42]) {
      await assert.rejects(
        () => getWeatherAnalysis({ regionName, latitude: 23, longitude: 77 }),
        (error) => error.statusCode === 400 && error.message === 'regionName is required.',
      );
    }
  });

  it('rejects missing, non-numeric, and out-of-range coordinates', async () => {
    const invalidInputs = [
      { latitude: undefined, longitude: 77 },
      { latitude: 'not-a-number', longitude: 77 },
      { latitude: 91, longitude: 77 },
      { latitude: 23, longitude: undefined },
      { latitude: 23, longitude: 'not-a-number' },
      { latitude: 23, longitude: 181 },
    ];

    for (const coordinates of invalidInputs) {
      await assert.rejects(
        () => getWeatherAnalysis({ regionName: 'Bhopal', ...coordinates }),
        (error) => error.statusCode === 400,
      );
    }
  });

  it('maps provider HTTP failures to a 502 error', async () => {
    globalThis.fetch = async () => responseWithJson({ error: true }, 503);

    await assert.rejects(
      () => getWeatherAnalysis({ regionName: 'Bhopal', latitude: 23, longitude: 77 }),
      (error) => error.statusCode === 502
        && error.message === 'Weather data provider returned HTTP 503.',
    );
  });

  it('maps network failures and timeouts to 503 errors', async () => {
    globalThis.fetch = async () => {
      throw new TypeError('network unavailable');
    };

    await assert.rejects(
      () => getWeatherAnalysis({ regionName: 'Bhopal', latitude: 23, longitude: 77 }),
      (error) => error.statusCode === 503
        && error.message === 'Unable to connect to the weather data provider.',
    );

    globalThis.fetch = async () => {
      const error = new Error('request timed out');
      error.name = 'TimeoutError';
      throw error;
    };

    await assert.rejects(
      () => getWeatherAnalysis({ regionName: 'Bhopal', latitude: 23, longitude: 77 }),
      (error) => error.statusCode === 503
        && error.message === 'Weather data request timed out.',
    );
  });

  it('rejects invalid JSON and incomplete provider responses', async () => {
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      json: async () => {
        throw new SyntaxError('invalid JSON');
      },
    });

    await assert.rejects(
      () => getWeatherAnalysis({ regionName: 'Bhopal', latitude: 23, longitude: 77 }),
      (error) => error.statusCode === 502
        && error.message === 'Weather data provider returned invalid JSON.',
    );

    globalThis.fetch = async () => responseWithJson({
      current: validPayload.current,
      daily: {
        temperature_2m_max: [],
        temperature_2m_min: [19.8],
        precipitation_sum: [2.6],
      },
    });

    await assert.rejects(
      () => getWeatherAnalysis({ regionName: 'Bhopal', latitude: 23, longitude: 77 }),
      (error) => error.statusCode === 502
        && error.message.includes('daily.temperature_2m_max'),
    );
  });
});

describe('POST /api/analysis', () => {
  it('returns a successful API response using the analysis service', async () => {
    globalThis.fetch = async () => responseWithJson(validPayload);
    const server = await startServer();

    try {
      const result = await request(server, {
        regionName: 'Bhopal',
        latitude: 23.2599,
        longitude: 77.4126,
      });

      assert.equal(result.statusCode, 200);
      assert.equal(result.body.success, true);
      assert.equal(result.body.data.region.name, 'Bhopal');
      assert.equal(result.body.data.dataProvider, 'Open-Meteo');
    } finally {
      await closeServer(server);
    }
  });

  it('returns a validation error for an absent request body', async () => {
    const server = await startServer();

    try {
      const address = server.address();
      const result = await new Promise((resolve, reject) => {
        const clientRequest = http.request({
          hostname: address.address,
          port: address.port,
          path: '/api/analysis',
          method: 'POST',
          headers: { 'content-type': 'application/json' },
        }, (response) => {
          let body = '';
          response.on('data', (chunk) => { body += chunk; });
          response.on('end', () => resolve({
            statusCode: response.statusCode,
            body: JSON.parse(body),
          }));
        });
        clientRequest.on('error', reject);
        clientRequest.end();
      });

      assert.equal(result.statusCode, 400);
      assert.equal(result.body.success, false);
      assert.equal(result.body.message, 'regionName is required.');
    } finally {
      await closeServer(server);
    }
  });
});
