import React, { useEffect, useRef, useState } from 'react';
import EarthMap from './components/map/EarthMap.jsx';
import AutoAnalysisPanel from './components/analysis/AutoAnalysisPanel.jsx';
import {
  requestWeatherAnalysis,
  resolveRegion,
  searchPlaces,
} from './services/analysisService.js';

const formatValue = (value) => (
  typeof value === 'number'
    ? value.toLocaleString(undefined, { maximumFractionDigits: 1 })
    : '—'
);

const formatTimestamp = (value) => {
  if (!value) return '—';
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
};

const formatStatus = (value, language = 'en') => {
  if (!value) return '—';
  const labels = language === 'hi'
    ? { available: 'उपलब्ध', unavailable: 'अनुपलब्ध', 'insufficient-data': 'अपर्याप्त डेटा' }
    : {};
  return labels[value] || value.replace(/-/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase());
};

const formatLabel = (value) => (
  value.replace(/([A-Z])/g, ' $1').replace(/^./, (character) => character.toUpperCase())
);

const formatMatchType = (value) => (
  value === 'broader-prefix' ? 'broader spelling' : value ? `${value} match` : ''
);

const translations = {
  en: {
    language: 'Language', status: 'Live analysis workspace', eyebrow: 'GEOSPATIAL OBSERVATORY / 01',
    title: 'Read the atmosphere', titleSuffix: 'at any point on Earth.', intro: 'Select a location to retrieve a focused weather analysis from the Open-Meteo forecast service.',
    dataLayer: 'DATA LAYER', weatherLive: 'WEATHER / LIVE', noKey: 'Open-Meteo · no API key required', searchLabel: 'Search a place', placeholder: 'City, state, country, or village', find: 'Find place', searching: 'Searching…',
    mapView: 'PRIMARY VIEW', earthSurface: 'Earth surface', interactive: 'Interactive', selectedPoint: 'Selected point', layers: 'Layers: Normal Map · Satellite Map', clickMap: 'CLICK TO SELECT COORDINATES',
    context: 'LOCATION CONTEXT', noLocation: 'No location selected', readyWeather: 'Ready for a weather analysis request.', chooseLocation: 'Choose a location to begin exploring the weather layer.', analysisLabel: 'Analysis label', runWeather: 'Run weather analysis', retrievingWeather: 'Retrieving weather…', habitability: 'Habitability Analysis', assessing: 'Assessing environment…', privacy: 'Only the selected coordinates and label are sent to the configured backend.',
    analysisUnavailable: 'Analysis unavailable', weatherConditions: 'Weather conditions', awaiting: 'Awaiting a location', searchOrMap: 'Search for a place or click the map, then run an analysis to populate this layer.', retrieved: 'Retrieved', environmental: 'ENVIRONMENTAL SCREENING', habitabilityAnalysis: 'Habitability analysis', habitabilityUnavailable: 'Habitability unavailable', retrievingEnvironmental: 'Retrieving environmental data', checkingEnvironmental: 'Checking the configured environmental assessment service for this location.', readyHabitability: 'Habitability analysis is ready', useHabitability: 'Select a location, then use the Habitability Analysis button to review available evidence and data limitations.', availableEvidence: 'AVAILABLE EVIDENCE', weatherIndicators: 'Weather indicators', dataGaps: 'DATA GAPS', unavailableIndicators: 'Unavailable indicators', provenance: 'PROVENANCE', sourcesLimitations: 'Sources and limitations', scoreUnavailable: 'Score unavailable', footer: 'Results come from public datasets (Open-Meteo, Sentinel-2, ESA WorldCover, SoilGrids, USGS, OpenStreetMap, Macrostrat) and are screening information, not a survey, reserve or resource estimate.', noMatches: 'No matching places found.', searchUnavailable: 'Place suggestions are unavailable right now.', exactFound: 'Exact place found. Run an analysis when ready.', chooseMatch: 'Select the intended place from the verified matches below.', noResults: 'No matching places were found. Try a nearby city, state, or country.', enterPlace: 'Enter a place name to search.', selected: 'Location selected. Run weather analysis when ready.', selectFirst: 'Select a point on the map or search for a place first.',
  },
  hi: {
    language: 'भाषा', status: 'लाइव विश्लेषण कार्यक्षेत्र', eyebrow: 'भू-स्थानिक वेधशाला / 01',
    title: 'वायुमंडल को पढ़ें', titleSuffix: 'पृथ्वी के किसी भी स्थान पर।', intro: 'Open-Meteo पूर्वानुमान सेवा से मौसम विश्लेषण प्राप्त करने के लिए स्थान चुनें।',
    dataLayer: 'डेटा लेयर', weatherLive: 'मौसम / लाइव', noKey: 'Open-Meteo · API कुंजी आवश्यक नहीं', searchLabel: 'स्थान खोजें', placeholder: 'शहर, राज्य, देश या गांव', find: 'स्थान खोजें', searching: 'खोज जारी…',
    mapView: 'मुख्य दृश्य', earthSurface: 'पृथ्वी की सतह', interactive: 'इंटरैक्टिव', selectedPoint: 'चयनित बिंदु', layers: 'लेयर: सामान्य मानचित्र · उपग्रह मानचित्र', clickMap: 'निर्देशांक चुनने के लिए क्लिक करें',
    context: 'स्थान संदर्भ', noLocation: 'कोई स्थान चयनित नहीं', readyWeather: 'मौसम विश्लेषण अनुरोध के लिए तैयार।', chooseLocation: 'मौसम लेयर देखने के लिए स्थान चुनें।', analysisLabel: 'विश्लेषण नाम', runWeather: 'मौसम विश्लेषण चलाएं', retrievingWeather: 'मौसम प्राप्त हो रहा है…', habitability: 'रहने योग्य विश्लेषण', assessing: 'पर्यावरण का आकलन हो रहा है…', privacy: 'केवल चयनित निर्देशांक और नाम कॉन्फ़िगर किए गए बैकएंड को भेजे जाते हैं।',
    analysisUnavailable: 'विश्लेषण उपलब्ध नहीं', weatherConditions: 'मौसम की स्थिति', awaiting: 'स्थान की प्रतीक्षा', searchOrMap: 'स्थान खोजें या मानचित्र पर क्लिक करें, फिर इस लेयर को भरने के लिए विश्लेषण चलाएं।', retrieved: 'प्राप्त', environmental: 'पर्यावरणीय स्क्रीनिंग', habitabilityAnalysis: 'रहने योग्य विश्लेषण', habitabilityUnavailable: 'रहने योग्य विश्लेषण उपलब्ध नहीं', retrievingEnvironmental: 'पर्यावरणीय डेटा प्राप्त हो रहा है', checkingEnvironmental: 'इस स्थान के लिए कॉन्फ़िगर की गई पर्यावरणीय सेवा की जांच हो रही है।', readyHabitability: 'रहने योग्य विश्लेषण तैयार है', useHabitability: 'स्थान चुनें और उपलब्ध प्रमाण व डेटा सीमाओं को देखने के लिए बटन दबाएं।', availableEvidence: 'उपलब्ध प्रमाण', weatherIndicators: 'मौसम संकेतक', dataGaps: 'डेटा अंतराल', unavailableIndicators: 'अनुपलब्ध संकेतक', provenance: 'स्रोत', sourcesLimitations: 'स्रोत और सीमाएं', scoreUnavailable: 'स्कोर उपलब्ध नहीं', footer: 'परिणाम सार्वजनिक डेटासेट (Open-Meteo, Sentinel-2, ESA WorldCover, SoilGrids, USGS, OpenStreetMap, Macrostrat) से आते हैं और केवल प्रारंभिक जानकारी हैं; ये सर्वेक्षण, भंडार या संसाधन अनुमान नहीं हैं।', noMatches: 'कोई मिलान स्थान नहीं मिला।', searchUnavailable: 'स्थान सुझाव अभी उपलब्ध नहीं हैं।', exactFound: 'सटीक स्थान मिला। तैयार होने पर विश्लेषण चलाएं।', chooseMatch: 'नीचे दिए गए सत्यापित परिणामों में सही स्थान चुनें।', noResults: 'कोई मिलान स्थान नहीं मिला। पास का शहर, राज्य या देश आज़माएं।', enterPlace: 'खोजने के लिए स्थान का नाम दर्ज करें।', selected: 'स्थान चयनित। मौसम विश्लेषण चलाएं।', selectFirst: 'पहले मानचित्र पर बिंदु चुनें या स्थान खोजें।',
  },
};

const metricLabels = {
  en: {
    temperature: 'Current temperature', humidity: 'Relative humidity', precipitation: 'Precipitation', wind: 'Wind speed',
    maximum: 'Daily maximum', minimum: 'Daily minimum', dailyPrecipitation: 'Daily precipitation',
  },
  hi: {
    temperature: 'वर्तमान तापमान', humidity: 'सापेक्ष आर्द्रता', precipitation: 'वर्षण', wind: 'हवा की गति',
    maximum: 'दैनिक अधिकतम', minimum: 'दैनिक न्यूनतम', dailyPrecipitation: 'दैनिक वर्षण',
  },
};

function MetricCard({ label, value, unit, tone = 'cyan' }) {
  return (
    <article className={`metric-card metric-card--${tone}`}>
      <span className="metric-card__label">{label}</span>
      <strong className="metric-card__value">
        {value}
        <small>{unit}</small>
      </strong>
    </article>
  );
}

function App() {
  const [language, setLanguage] = useState('en');
  const [searchQuery, setSearchQuery] = useState('');
  const [regionName, setRegionName] = useState('');
  const [selectedLocation, setSelectedLocation] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');
  const [searchMessage, setSearchMessage] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [suggestionError, setSuggestionError] = useState('');
  const [activeSuggestion, setActiveSuggestion] = useState(-1);
  const [region, setRegion] = useState(null);
  const [regionError, setRegionError] = useState('');
  const [drawMode, setDrawMode] = useState(false);
  const [analyzeSignal, setAnalyzeSignal] = useState(0);
  const [overlays, setOverlays] = useState([]);
  const [shownOverlay, setShownOverlay] = useState(null);
  const regionRequestRef = useRef(0);
  const suggestionRequestRef = useRef(0);
  const suppressSuggestionRef = useRef(false);
  const text = translations[language];
  const metrics = metricLabels[language];

  useEffect(() => {
    if (suppressSuggestionRef.current) {
      suppressSuggestionRef.current = false;
      setSuggestions([]);
      return undefined;
    }

    const query = searchQuery.trim();
    if (query.length < 2) {
      setSuggestions([]);
      setSuggestionsLoading(false);
      setSuggestionError('');
      return undefined;
    }

    const controller = new AbortController();
    const requestId = ++suggestionRequestRef.current;
    const timer = setTimeout(async () => {
      setSuggestionsLoading(true);
      setSuggestionError('');

      try {
        const results = await searchPlaces(query, { signal: controller.signal });
        if (requestId !== suggestionRequestRef.current) return;
        setSuggestions(results);
        setActiveSuggestion(-1);
      } catch (suggestionRequestError) {
        if (suggestionRequestError.name === 'AbortError') return;
        if (requestId !== suggestionRequestRef.current) return;
        setSuggestions([]);
        setSuggestionError(text.searchUnavailable);
      } finally {
        if (requestId === suggestionRequestRef.current) setSuggestionsLoading(false);
      }
    }, 300);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [searchQuery, text.searchUnavailable]);

  const selectLocation = (location) => {
    const requestId = ++regionRequestRef.current;
    setRegion(null);
    setOverlays([]);
    setShownOverlay(null);
    setRegionError('');
    resolveRegion(location).then((resolved) => {
      if (requestId !== regionRequestRef.current) return;
      setRegion(resolved);
      if (resolved.tooLarge) setRegionError('This place is larger than 10°. Use “Draw area” to select a smaller part of it.');
    }).catch(() => {});
    setSelectedLocation(location);
    setAnalysis(null);
    setError('');
    setSuggestions([]);
    setSearchMessage(text.selected);
  };

  const selectSuggestion = (result) => {
    const displayName = result.displayName || [result.name, result.admin1, result.country].filter(Boolean).join(', ');
    suppressSuggestionRef.current = true;
    setSearchQuery(displayName);
    setRegionName(displayName);
    setActiveSuggestion(-1);
    selectLocation({
      id: result.id,
      latitude: result.latitude,
      longitude: result.longitude,
      name: displayName,
      context: result.context,
      placeType: result.placeType,
      zoom: result.zoom,
    });
  };

  const handleSearchKeyDown = (event) => {
    if (event.key === 'Escape') {
      setSuggestions([]);
      setActiveSuggestion(-1);
      return;
    }

    if (event.key === 'ArrowDown' && suggestions.length > 0) {
      event.preventDefault();
      setActiveSuggestion((current) => (current + 1) % suggestions.length);
    }

    if (event.key === 'ArrowUp' && suggestions.length > 0) {
      event.preventDefault();
      setActiveSuggestion((current) => (current - 1 + suggestions.length) % suggestions.length);
    }

    if (event.key === 'Enter' && activeSuggestion >= 0 && suggestions[activeSuggestion]) {
      event.preventDefault();
      selectSuggestion(suggestions[activeSuggestion]);
    }
  };

  const handleSearch = async (event) => {
    event.preventDefault();
    if (!searchQuery.trim()) {
      setSearchMessage(text.enterPlace);
      return;
    }

    setSearching(true);
    setSearchMessage(text.searching);
    setError('');

    try {
      const results = await searchPlaces(searchQuery.trim());
      setSuggestions(results);
      setActiveSuggestion(-1);

      const exactResults = results.filter((result) => result.matchType === 'exact');
      if (results.length === 1 && exactResults.length === 1) {
        selectSuggestion(results[0]);
        setSearchMessage(text.exactFound);
      } else if (results.length > 0) {
        setSearchMessage(text.chooseMatch);
      } else {
        setSearchMessage(text.noResults);
      }
    } catch (searchError) {
      setSearchMessage(searchError.message || text.noResults);
    } finally {
      setSearching(false);
    }
  };

  const handleAnalyze = async () => {
    if (!selectedLocation) {
      setError(text.selectFirst);
      return;
    }

    const name = regionName.trim() || selectedLocation.name || 'Selected map location';
    setLoading(true);
    setError('');

    try {
      const result = await requestWeatherAnalysis({
        regionName: name,
        latitude: selectedLocation.latitude,
        longitude: selectedLocation.longitude,
      });
      setAnalysis(result.data);
    } catch (requestError) {
      setError(requestError.message || text.analysisUnavailable);
    } finally {
      setLoading(false);
    }
  };


  const current = analysis?.analysis?.current;
  const daily = analysis?.analysis?.daily;
  const units = analysis?.units || {};

  return (
    <div className="app-shell" lang={language}>
      <header className="topbar">
        <a className="brand" href="/" aria-label="Earth GeoIntelligence home">
          <span className="brand__mark"><span /></span>
          <span>
            <strong>EARTH</strong>
            <em>GEOINTELLIGENCE</em>
          </span>
        </a>
        <div className="topbar__actions">
          <label className="language-picker" htmlFor="language-select">{text.language}
            <select id="language-select" value={language} onChange={(event) => setLanguage(event.target.value)}>
              <option value="en">English</option>
              <option value="hi">हिन्दी</option>
            </select>
          </label>
          <div className="topbar__status"><span className="status-dot" /> {text.status}</div>
        </div>
      </header>

      <main className="dashboard">
        <section className="intro-row">
          <div>
            <p className="eyebrow">{text.eyebrow}</p>
            <h1>{text.title}<br /><span>{text.titleSuffix}</span></h1>
            <p className="intro-copy">{text.intro}</p>
          </div>
          <div className="intro-meta">
            <span>{text.dataLayer}</span>
            <strong>{text.weatherLive}</strong>
            <small>{text.noKey}</small>
          </div>
        </section>

        <section className="control-bar panel">
          <form className="search-form" onSubmit={handleSearch}>
            <label htmlFor="place-search">{text.searchLabel}</label>
            <div className="search-form__input">
              <span className="search-icon">⌕</span>
              <input
                id="place-search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                onKeyDown={handleSearchKeyDown}
                placeholder={text.placeholder}
                autoComplete="off"
                role="combobox"
                aria-autocomplete="list"
                aria-expanded={searchQuery.trim().length >= 2 && suggestions.length > 0}
              />
              <button type="submit" disabled={searching}>{searching ? text.searching : text.find}</button>
            </div>
            {searchQuery.trim().length >= 2 && (suggestionsLoading || suggestionError || suggestions.length > 0) && (
              <div className="suggestions" role="listbox">
                {suggestionsLoading && <div className="suggestion-status">{text.searching}</div>}
                {!suggestionsLoading && suggestionError && <div className="suggestion-status suggestion-status--error">{suggestionError}</div>}
                {!suggestionsLoading && !suggestionError && suggestions.length === 0 && <div className="suggestion-status">{text.noMatches}</div>}
                {!suggestionsLoading && !suggestionError && suggestions.map((suggestion, index) => (
                  <button
                    className={`suggestion-item${index === activeSuggestion ? ' is-active' : ''}`}
                    key={`${suggestion.id || suggestion.name}-${suggestion.latitude}-${suggestion.longitude}`}
                    type="button"
                    role="option"
                    aria-selected={index === activeSuggestion}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => selectSuggestion(suggestion)}
                  >
                    <strong>{suggestion.displayName || suggestion.name}</strong>
                    <span>{suggestion.placeType}{suggestion.matchType ? ` · ${formatMatchType(suggestion.matchType)}` : ''}</span>
                    <small>{suggestion.latitude.toFixed(4)}, {suggestion.longitude.toFixed(4)}</small>
                  </button>
                ))}
              </div>
            )}
          </form>
          <div className="control-hint" aria-live="polite">{searchMessage || text.clickMap}</div>
        </section>

        <section className="workspace-grid">
          <div className="map-panel panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">{text.mapView}</p>
                <h2>{text.earthSurface}</h2>
              </div>
              <span className="map-badge"><span className="status-dot" /> {text.interactive}</span>
            </div>
            <div className="map-wrap">
              <EarthMap
                selectedLocation={selectedLocation}
                onSelect={selectLocation}
                language={language}
                region={region}
                drawMode={drawMode}
                overlay={overlays.find((o) => o.id === shownOverlay) || null}
                onBox={(bbox) => {
                  setDrawMode(false);
                  selectLocation({ latitude: (bbox[1] + bbox[3]) / 2, longitude: (bbox[0] + bbox[2]) / 2, bbox, name: 'Drawn area' });
                }}
              />
              {overlays.length > 0 && (
                <div className="gi-layers" role="group" aria-label="Map layers">
                  <strong>Layers</strong>
                  <button type="button" className={shownOverlay === null ? 'is-on' : ''} onClick={() => setShownOverlay(null)}>Base map</button>
                  {overlays.map((o) => <button type="button" key={o.id} className={shownOverlay === o.id ? 'is-on' : ''} onClick={() => setShownOverlay(shownOverlay === o.id ? null : o.id)}>{o.label}</button>)}
                  {overlays.find((o) => o.id === shownOverlay) && (
                    <div className="gi-legend">{overlays.find((o) => o.id === shownOverlay).legend.map((l) => <span key={l.label}><i style={{ background: l.color }} />{l.label}</span>)}</div>
                  )}
                </div>
              )}
              <div className="map-overlay">{text.clickMap}</div>
            </div>
            <div className="map-caption">
              <span><i className="legend-dot" /> {text.selectedPoint}</span>
              <span>{text.layers}</span>
            </div>
          </div>

          <aside className="selection-panel panel">
            <p className="eyebrow">{text.context}</p>
            <h2>{selectedLocation?.name || text.noLocation}</h2>
            <p className="selection-copy">
              {selectedLocation ? text.readyWeather : text.chooseLocation}
            </p>
            <div className="coordinate-box">
              <div><span>LATITUDE</span><strong>{selectedLocation ? selectedLocation.latitude.toFixed(4) : '—'}</strong></div>
              <div><span>LONGITUDE</span><strong>{selectedLocation ? selectedLocation.longitude.toFixed(4) : '—'}</strong></div>
            </div>
            <label className="field-label" htmlFor="region-name">{text.analysisLabel}</label>
            <input
              id="region-name"
              className="text-input"
              value={regionName}
              onChange={(event) => setRegionName(event.target.value)}
              placeholder="e.g. Bhopal"
            />
            <button
              className="analyze-button gi-primary"
              type="button"
              disabled={!region || region.tooLarge}
              onClick={() => { setAnalyzeSignal((v) => v + 1); document.getElementById('region-analysis')?.scrollIntoView({ behavior: 'smooth' }); }}
            >
              <span>Analyze region</span>
              <span>↗</span>
            </button>
            <button className="secondary-action" type="button" onClick={handleAnalyze} disabled={!selectedLocation || loading}>
              <span>{loading ? text.retrievingWeather : text.runWeather}</span>
              <span>↗</span>
            </button>
            <button className="secondary-action" type="button" onClick={() => setDrawMode((v) => !v)}>
              {drawMode ? 'Drag on the map… (click to cancel)' : 'Draw area on map'}
            </button>
            <p className="privacy-note">{text.privacy}</p>
          </aside>
        </section>

        {error && <div className="alert alert--error" role="alert"><strong>{text.analysisUnavailable}</strong><span>{error}</span></div>}

        <section className="results-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">{language === 'hi' ? 'विश्लेषण परिणाम' : 'ANALYSIS OUTPUT'}</p>
              <h2>{text.weatherConditions}</h2>
            </div>
            {analysis && <span className="result-state"><span className="status-dot" /> {text.retrieved}</span>}
          </div>
          {!analysis ? (
            <div className="empty-results panel"><span className="empty-results__icon">◌</span><h3>{text.awaiting}</h3><p>{text.searchOrMap}</p></div>
          ) : (
            <>
              <div className="metric-grid">
                <MetricCard label={metrics.temperature} value={formatValue(current?.temperature)} unit={units.temperature} />
                <MetricCard label={metrics.humidity} value={formatValue(current?.relativeHumidity)} unit={units.relativeHumidity} tone="purple" />
                <MetricCard label={metrics.precipitation} value={formatValue(current?.precipitation)} unit={units.precipitation} />
                <MetricCard label={metrics.wind} value={formatValue(current?.windSpeed)} unit={units.windSpeed} tone="purple" />
                <MetricCard label={metrics.maximum} value={formatValue(daily?.maximumTemperature)} unit={units.dailyMaximumTemperature} />
                <MetricCard label={metrics.minimum} value={formatValue(daily?.minimumTemperature)} unit={units.dailyMinimumTemperature} tone="purple" />
                <MetricCard label={metrics.dailyPrecipitation} value={formatValue(daily?.precipitation)} unit={units.dailyPrecipitation} />
              </div>
              <div className="provenance panel">
                <div><span className="provenance__label">{language === 'hi' ? 'मौसम विश्लेषण' : 'WEATHER ANALYSIS'}</span><strong>{analysis.region?.name}</strong></div>
                <div><span className="provenance__label">{language === 'hi' ? 'डेटा प्रदाता' : 'DATA PROVIDER'}</span><strong>{analysis.dataProvider}</strong></div>
                <div><span className="provenance__label">{language === 'hi' ? 'प्राप्त समय' : 'RETRIEVED'}</span><strong>{formatTimestamp(analysis.retrievedAt)}</strong></div>
              </div>
            </>
          )}
        </section>

        <AutoAnalysisPanel region={region} regionError={regionError} analyzeSignal={analyzeSignal} onOverlays={setOverlays} />



        <footer className="footer-note">{text.footer}</footer>
      </main>
    </div>
  );
}

export default App;
