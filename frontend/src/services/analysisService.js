const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000').replace(/\/$/, '');
const GEOCODING_URL = 'https://geocoding-api.open-meteo.com/v1/search';
const SEARCH_RESULT_LIMIT = 100;

const readJson = async (response, fallbackMessage = 'The weather analysis request failed.') => {
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error('The service returned an invalid response.');
  }

  if (!response.ok) {
    throw new Error(payload?.message || fallbackMessage);
  }

  return payload;
};

const normalizeSearchText = (value = '') => value
  .normalize('NFKD')
  .replace(/[\u0300-\u036f]/g, '')
  .toLowerCase()
  .replace(/[^\p{Letter}\p{Number}]+/gu, ' ')
  .trim();

const uniqueParts = (parts) => [...new Set(parts.filter(Boolean).map((part) => part.trim()))];

const editDistance = (left, right) => {
  const previous = Array.from({ length: right.length + 1 }, (_, index) => index);
  for (let leftIndex = 1; leftIndex <= left.length; leftIndex += 1) {
    const current = [leftIndex];
    for (let rightIndex = 1; rightIndex <= right.length; rightIndex += 1) {
      current[rightIndex] = Math.min(
        current[rightIndex - 1] + 1,
        previous[rightIndex] + 1,
        previous[rightIndex - 1] + (left[leftIndex - 1] === right[rightIndex - 1] ? 0 : 1),
      );
    }
    for (let index = 0; index < current.length; index += 1) previous[index] = current[index];
  }
  return previous[right.length];
};

const getPlaceType = (featureCode = '') => {
  if (featureCode === 'PPLA' || featureCode === 'PPLA2' || featureCode === 'PPLA3' || featureCode === 'PPLA4') {
    return 'Administrative center';
  }
  if (featureCode === 'PPLC') return 'Capital city';
  if (featureCode === 'PPL') return 'Populated place';
  if (featureCode.startsWith('PPL')) return 'Populated place';
  return featureCode || 'Place';
};

const getSuggestedZoom = (featureCode = '') => {
  if (featureCode === 'PPLC') return 5;
  if (featureCode === 'PPLA' || featureCode === 'PPLA2') return 8;
  if (featureCode.startsWith('PPL')) return 12;
  return 10;
};

const toPlaceResult = (result, query, index, fallbackUsed = false) => {
  const name = result.name || result.toponymName || 'Unnamed place';
  const context = uniqueParts([
    result.admin4,
    result.admin3,
    result.admin2,
    result.admin1,
    result.country,
  ]).join(' · ');
  const normalizedQuery = normalizeSearchText(query.split(',')[0]);
  const normalizedName = normalizeSearchText(name);
  const matchType = normalizedName === normalizedQuery
    ? 'exact'
    : normalizedName.startsWith(normalizedQuery)
      ? 'prefix'
      : fallbackUsed
        ? 'broader-prefix'
        : 'provider-match';

  return {
    ...result,
    name,
    displayName: context ? `${name} — ${context}` : name,
    context,
    placeType: getPlaceType(result.feature_code),
    zoom: getSuggestedZoom(result.feature_code),
    matchType,
    _searchRank: matchType === 'exact' ? 0 : matchType === 'prefix' ? 1 : 2,
    _nameDistance: fallbackUsed ? editDistance(normalizedName, normalizedQuery) : 0,
    _providerIndex: index,
  };
};

const rankPlaces = (results, query, fallbackUsed = false) => results
  .map((result, index) => toPlaceResult(result, query, index, fallbackUsed))
  .sort((left, right) => (
    left._searchRank - right._searchRank
    || (fallbackUsed && left._nameDistance - right._nameDistance)
    || (Number(right.population) || 0) - (Number(left.population) || 0)
    || left._providerIndex - right._providerIndex
  ))
  .map(({ _searchRank, _nameDistance, _providerIndex, ...result }) => result);

export async function requestWeatherAnalysis({ regionName, latitude, longitude }) {
  const response = await fetch(`${API_BASE_URL}/api/analysis`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ regionName, latitude, longitude }),
  });
  return readJson(response);
}

export async function searchPlaces(name, { signal, countryCode } = {}) {
  const query = typeof name === 'string' ? name.trim() : '';
  if (query.length < 2) return [];

  const requestProvider = async (providerQuery) => {
    const url = new URL(GEOCODING_URL);
    url.search = new URLSearchParams({
      name: providerQuery,
      count: String(SEARCH_RESULT_LIMIT),
      language: 'en',
      format: 'json',
      ...(countryCode ? { countryCode } : {}),
    });

    const response = await fetch(url, { signal });
    return readJson(response, 'The place search service failed.');
  };

  const payload = await requestProvider(query);
  const directResults = Array.isArray(payload?.results) ? payload.results : [];
  if (directResults.length > 0 || query.length < 6) {
    return rankPlaces(directResults, query);
  }

  // Open-Meteo uses prefix matching. A single shorter retry can surface a
  // likely alternate spelling, but the user must still choose the result.
  const broaderQuery = query.slice(0, 5);
  const broaderPayload = await requestProvider(broaderQuery);
  const broaderResults = Array.isArray(broaderPayload?.results) ? broaderPayload.results : [];
  return rankPlaces(broaderResults, query, broaderResults.length > 0);
}

export async function geocodePlace(name, options) {
  const results = await searchPlaces(name, options);
  const result = results[0];

  if (!result) {
    throw new Error('No matching place was found.');
  }

  return result;
}

const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search';
const MAX_BOUNDARY_VERTICES = 3000;
const countVertices = (g) => JSON.stringify(g.coordinates).split('],[').length;
const pointBox = (latitude, longitude, half = 0.1) => [
  Math.max(-180, longitude - half), Math.max(-90, latitude - half),
  Math.min(180, longitude + half), Math.min(90, latitude + half),
];

// Resolve a selected place/point into a bounding box and (when available) boundary polygon.
export async function resolveRegion(location, { signal } = {}) {
  const fallback = {
    name: location.name || 'Selected map area',
    bbox: location.bbox || pointBox(location.latitude, location.longitude),
    geometry: null,
    boundarySource: location.bbox ? 'Area drawn on map' : '0.2° box around the selected point',
  };
  if (location.bbox || !location.name) return fallback;
  try {
    const query = location.name.split('—')[0].trim();
    const url = new URL(NOMINATIM_URL);
    url.search = new URLSearchParams({ q: query, format: 'jsonv2', polygon_geojson: '1', limit: '5' });
    const response = await fetch(url, { signal, headers: { Accept: 'application/json' } });
    if (!response.ok) return fallback;
    const results = await response.json();
    const dist = (r) => Math.hypot(Number(r.lat) - location.latitude, Number(r.lon) - location.longitude);
    const best = results.filter((r) => Array.isArray(r.boundingbox)).sort((a, b) => dist(a) - dist(b))[0];
    if (!best || dist(best) > 1) return fallback;
    const [south, north, west, east] = best.boundingbox.map(Number);
    if (![south, north, west, east].every(Number.isFinite)) return fallback;
    if (east - west > 10 || north - south > 10) {
      return { ...fallback, tooLarge: true, bbox: [west, south, east, north] };
    }
    if (east - west < 0.02 || north - south < 0.02) return fallback;
    const g = best.geojson;
    const polygon = g && (g.type === 'Polygon' || g.type === 'MultiPolygon') && countVertices(g) <= MAX_BOUNDARY_VERTICES ? g : null;
    return {
      name: location.name, bbox: [west, south, east, north], geometry: polygon,
      boundarySource: polygon ? 'OpenStreetMap administrative boundary' : 'OpenStreetMap bounding box',
    };
  } catch (error) {
    if (error?.name === 'AbortError') throw error;
    return fallback;
  }
}

const postJson = async (path, body) => {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  return readJson(response, 'The analysis request failed.');
};

// One independent request per intelligence module so a slow provider never blocks the rest.
export async function requestModule(bbox, module, geometry = null) {
  const result = await postJson('/api/ml/environment/module', geometry ? { bbox, module, geometry } : { bbox, module });
  return result.available
    ? { status: 'ok', data: result.data, overlays: result.overlays || [] }
    : { status: 'na', reason: result.reason || 'Data provider did not return data.' };
}

export async function requestProspectivity(region) {
  const mlRegion = region.geometry
    ? { name: region.name.slice(0, 256), geometry: region.geometry }
    : { name: region.name.slice(0, 256), bbox: { min_longitude: region.bbox[0], min_latitude: region.bbox[1], max_longitude: region.bbox[2], max_latitude: region.bbox[3] } };
  return postJson('/api/ml/prospectivity/auto', { region: mlRegion });
}

export async function downloadReportPdf(payload) {
  const response = await fetch(`${API_BASE_URL}/api/report/pdf`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error('The PDF report could not be generated.');
  const url = URL.createObjectURL(await response.blob());
  const link = Object.assign(document.createElement('a'), { href: url, download: 'geointelligence-report.pdf' });
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
