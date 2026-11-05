const OPEN_METEO_URL = 'https://api.open-meteo.com/v1/forecast';
const REQUEST_TIMEOUT_MS = 10000;

const createServiceError = (message, statusCode) => {
  const error = new Error(message);
  error.statusCode = statusCode;
  return error;
};

const toCoordinate = (value, name, minimum, maximum) => {
  if (
    value === null
    || value === undefined
    || (typeof value === 'string' && value.trim().length === 0)
    || (typeof value !== 'string' && typeof value !== 'number')
  ) {
    throw createServiceError(`${name} is required.`, 400);
  }

  const coordinate = typeof value === 'string' ? Number(value.trim()) : value;
  if (!Number.isFinite(coordinate) || coordinate < minimum || coordinate > maximum) {
    throw createServiceError(`${name} must be between ${minimum} and ${maximum}.`, 400);
  }

  return coordinate;
};

const requireNumber = (value, field) => {
  if (!Number.isFinite(value)) {
    throw createServiceError(`Open-Meteo returned an incomplete response: ${field}.`, 502);
  }

  return value;
};

const requireDailyValue = (daily, field) => {
  if (!Array.isArray(daily?.[field]) || daily[field].length === 0) {
    throw createServiceError(`Open-Meteo returned an incomplete response: daily.${field}.`, 502);
  }

  return requireNumber(daily[field][0], `daily.${field}`);
};

const getWeatherAnalysis = async ({ regionName, latitude, longitude } = {}) => {
  if (typeof regionName !== 'string' || regionName.trim().length === 0) {
    throw createServiceError('regionName is required.', 400);
  }

  const validLatitude = toCoordinate(latitude, 'latitude', -90, 90);
  const validLongitude = toCoordinate(longitude, 'longitude', -180, 180);

  const url = new URL(OPEN_METEO_URL);
  url.search = new URLSearchParams({
    latitude: String(validLatitude),
    longitude: String(validLongitude),
    current: 'temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m',
    daily: 'temperature_2m_max,temperature_2m_min,precipitation_sum',
    timezone: 'UTC',
    forecast_days: '1',
  });

  let response;
  try {
    response = await fetch(url, {
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    const message = error.name === 'TimeoutError'
      ? 'Weather data request timed out.'
      : 'Unable to connect to the weather data provider.';
    throw createServiceError(message, 503);
  }

  if (!response.ok) {
    throw createServiceError(
      `Weather data provider returned HTTP ${response.status}.`,
      502,
    );
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    throw createServiceError('Weather data provider returned invalid JSON.', 502);
  }

  const current = payload?.current;
  const daily = payload?.daily;
  const currentUnits = payload?.current_units || {};
  const dailyUnits = payload?.daily_units || {};
  if (!current || !daily) {
    throw createServiceError('Weather data provider returned an incomplete response.', 502);
  }

  const result = {
    region: {
      name: regionName.trim(),
      latitude: validLatitude,
      longitude: validLongitude,
    },
    analysis: {
      current: {
        temperature: requireNumber(current.temperature_2m, 'current.temperature_2m'),
        relativeHumidity: requireNumber(
          current.relative_humidity_2m,
          'current.relative_humidity_2m',
        ),
        precipitation: requireNumber(current.precipitation, 'current.precipitation'),
        windSpeed: requireNumber(current.wind_speed_10m, 'current.wind_speed_10m'),
      },
      daily: {
        maximumTemperature: requireDailyValue(daily, 'temperature_2m_max'),
        minimumTemperature: requireDailyValue(daily, 'temperature_2m_min'),
        precipitation: requireDailyValue(daily, 'precipitation_sum'),
      },
    },
    units: {
      temperature: currentUnits.temperature_2m || '°C',
      relativeHumidity: currentUnits.relative_humidity_2m || '%',
      precipitation: currentUnits.precipitation || 'mm',
      windSpeed: currentUnits.wind_speed_10m || 'km/h',
      dailyMaximumTemperature: dailyUnits.temperature_2m_max || '°C',
      dailyMinimumTemperature: dailyUnits.temperature_2m_min || '°C',
      dailyPrecipitation: dailyUnits.precipitation_sum || 'mm',
    },
    dataProvider: 'Open-Meteo',
    retrievedAt: new Date().toISOString(),
  };

  return result;
};

export { getWeatherAnalysis };
export default getWeatherAnalysis;