import getWeatherAnalysis from './analysis.service.js';
import { BadRequestError } from '../utils/errors.js';

const OPEN_METEO_FORECAST_URL = 'https://api.open-meteo.com/v1/forecast';

const toCoordinate = (value, name, minimum, maximum) => {
  if (
    value === null
    || value === undefined
    || (typeof value === 'string' && value.trim().length === 0)
    || (typeof value !== 'string' && typeof value !== 'number')
  ) {
    throw new BadRequestError(`${name} is required.`);
  }

  const coordinate = typeof value === 'string' ? Number(value.trim()) : value;
  if (!Number.isFinite(coordinate) || coordinate < minimum || coordinate > maximum) {
    throw new BadRequestError(`${name} must be between ${minimum} and ${maximum}.`);
  }

  return coordinate;
};

const unavailableIndicator = (reason) => ({
  status: 'unavailable',
  value: null,
  unit: null,
  reason,
});

const getHabitabilityAnalysis = async ({ regionName, latitude, longitude } = {}) => {
  if (typeof regionName !== 'string' || regionName.trim().length === 0) {
    throw new BadRequestError('regionName is required.');
  }

  const validLatitude = toCoordinate(latitude, 'latitude', -90, 90);
  const validLongitude = toCoordinate(longitude, 'longitude', -180, 180);
  const weather = await getWeatherAnalysis({
    regionName: regionName.trim(),
    latitude: validLatitude,
    longitude: validLongitude,
  });

  return {
    region: weather.region,
    assessment: {
      status: 'insufficient-data',
      score: null,
      conclusion: null,
      explanation: 'Habitability is not determined because the verified inputs are limited to weather observations and forecasts.',
    },
    availableIndicators: {
      weather: {
        status: 'available',
        data: weather.analysis,
        units: weather.units,
        method: 'Current and one-day forecast values retrieved from the existing weather analysis service.',
      },
    },
    unavailableIndicators: {
      vegetation: unavailableIndicator('No verified vegetation dataset is configured for this service.'),
      waterAvailability: unavailableIndicator('No verified surface-water or hydrology dataset is configured for this service.'),
      soilQuality: unavailableIndicator('No verified soil dataset is configured for this service.'),
      airQuality: unavailableIndicator('No verified air-quality dataset is configured for this service.'),
      elevation: unavailableIndicator('No verified elevation dataset is configured for this service.'),
      landCover: unavailableIndicator('No verified land-cover dataset is configured for this service.'),
    },
    sources: [
      {
        provider: weather.dataProvider,
        endpoint: OPEN_METEO_FORECAST_URL,
        retrievedAt: weather.retrievedAt,
        coverage: 'Point weather data for the requested coordinates; this does not provide complete environmental coverage.',
      },
    ],
    limitations: [
      'Weather measurements alone cannot scientifically establish habitability.',
      'No numerical habitability score is produced from the currently available data.',
      'Unavailable indicators are not estimated, imputed, or replaced with sample values.',
      'A future assessment requires additional verified datasets, documented methods, and uncertainty analysis.',
    ],
    retrievedAt: weather.retrievedAt,
  };
};

export { getHabitabilityAnalysis };
export default getHabitabilityAnalysis;

