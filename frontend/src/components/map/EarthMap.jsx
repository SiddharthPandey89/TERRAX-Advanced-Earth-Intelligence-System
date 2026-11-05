import React, { useEffect, useRef, useState } from 'react';
import {
  CircleMarker,
  GeoJSON,
  ImageOverlay,
  Rectangle,
  LayerGroup,
  LayersControl,
  MapContainer,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from 'react-leaflet';

const SATELLITE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const PLACE_LABELS_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}';
const TRANSPORT_LABELS_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}';
const ESRI_ATTRIBUTION = 'Tiles &copy; Esri, HERE, Garmin, (c) OpenStreetMap contributors, and the GIS user community';

function MapSelection({ onSelect, drawMode }) {
  useMapEvents({
    click: ({ latlng }) => !drawMode && onSelect({ latitude: latlng.lat, longitude: latlng.lng, zoom: 12 }),
  });
  return null;
}

function BoxDrawer({ active, onBox }) {
  const map = useMap();
  const [box, setBox] = useState(null);
  const start = useRef(null);
  useEffect(() => {
    if (!active) { map.dragging.enable(); return undefined; }
    map.dragging.disable();
    map.getContainer().style.cursor = 'crosshair';
    return () => { map.dragging.enable(); map.getContainer().style.cursor = ''; setBox(null); };
  }, [active, map]);
  useMapEvents({
    mousedown: (e) => { if (active) { start.current = e.latlng; setBox([[e.latlng.lat, e.latlng.lng], [e.latlng.lat, e.latlng.lng]]); } },
    mousemove: (e) => { if (active && start.current) setBox([[start.current.lat, start.current.lng], [e.latlng.lat, e.latlng.lng]]); },
    mouseup: (e) => {
      if (!active || !start.current) return;
      const a = start.current; start.current = null; setBox(null);
      const west = Math.min(a.lng, e.latlng.lng); const east = Math.max(a.lng, e.latlng.lng);
      const south = Math.min(a.lat, e.latlng.lat); const north = Math.max(a.lat, e.latlng.lat);
      if (east - west > 0.005 && north - south > 0.005) onBox([west, south, east, north]);
    },
  });
  return box ? <Rectangle bounds={box} pathOptions={{ color: '#ffc857', weight: 2, dashArray: '4' }} /> : null;
}

function FitRegion({ region }) {
  const map = useMap();
  useEffect(() => {
    if (!region?.bbox || region.tooLarge) return;
    map.flyToBounds([[region.bbox[1], region.bbox[0]], [region.bbox[3], region.bbox[2]]], { duration: 0.8, padding: [30, 30], maxZoom: 13 });
  }, [region, map]);
  return null;
}

function FlyToSelection({ location }) {
  const map = useMap();
  useEffect(() => {
    if (!location) return;
    if (location.bbox) {
      map.flyToBounds([[location.bbox[1], location.bbox[0]], [location.bbox[3], location.bbox[2]]], { duration: 0.8, padding: [20, 20] });
      return;
    }
    map.flyTo(
      [location.latitude, location.longitude],
      Math.min(Math.max(location.zoom || 12, 2), 23),
      { duration: 0.8, easeLinearity: 0.25 },
    );
  }, [location, map]);
  return null;
}

function MapViewportSync() {
  const map = useMap();

  useEffect(() => {
    const invalidate = () => map.invalidateSize({ pan: false, animate: false });
    const frame = window.requestAnimationFrame(invalidate);
    window.addEventListener('resize', invalidate);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', invalidate);
    };
  }, [map]);

  return null;
}

export default function EarthMap({ selectedLocation, onSelect, language = 'en', region = null, drawMode = false, overlay = null, onBox = () => {} }) {
  const normalLabel = language === 'hi' ? 'सामान्य मानचित्र' : 'Normal Map';
  const satelliteLabel = language === 'hi' ? 'उपग्रह मानचित्र' : 'Satellite Map';

  return (
    <MapContainer
      className="earth-map"
      center={[20, 0]}
      zoom={2}
      minZoom={1}
      maxZoom={23}
      scrollWheelZoom
      wheelDebounceTime={40}
      wheelPxPerZoomLevel={60}
      doubleClickZoom
      touchZoom
      zoomControl
      zoomSnap={0.25}
      zoomDelta={1}
      zoomAnimation
      fadeAnimation
      markerZoomAnimation
      bounceAtZoomLimits={false}
      worldCopyJump
      preferCanvas
      style={{ width: '100%', height: '100%' }}
    >
      <LayersControl key={language} position="topright">
        <LayersControl.BaseLayer checked name={normalLabel}>
          <TileLayer
            attribution="&copy; OpenStreetMap contributors"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            maxNativeZoom={19}
            maxZoom={23}
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name={satelliteLabel}>
          <LayerGroup>
            <TileLayer
              className="satellite-imagery-tile"
              attribution={ESRI_ATTRIBUTION}
              url={SATELLITE_URL}
              maxNativeZoom={23}
              maxZoom={23}
            />
            <TileLayer
              className="satellite-label-tile"
              attribution={ESRI_ATTRIBUTION}
              url={PLACE_LABELS_URL}
              maxNativeZoom={23}
              maxZoom={23}
              opacity={1}
            />
            <TileLayer
              className="satellite-label-tile"
              attribution={ESRI_ATTRIBUTION}
              url={TRANSPORT_LABELS_URL}
              maxNativeZoom={23}
              maxZoom={23}
              opacity={0.9}
            />
          </LayerGroup>
        </LayersControl.BaseLayer>
      </LayersControl>
      <MapViewportSync />
      <MapSelection onSelect={onSelect} drawMode={drawMode} />
      {overlay && <ImageOverlay key={overlay.id} url={overlay.image} bounds={overlay.bounds} opacity={0.85} zIndex={400} />}
      <FitRegion region={region} />
      <BoxDrawer active={drawMode} onBox={onBox} />
      {region && (region.geometry
        ? <GeoJSON key={JSON.stringify(region.bbox)} data={{ type: 'Feature', geometry: region.geometry }} style={{ color: '#ffc857', weight: 2, fillOpacity: 0.08 }} />
        : <Rectangle bounds={[[region.bbox[1], region.bbox[0]], [region.bbox[3], region.bbox[2]]]} pathOptions={{ color: '#ffc857', weight: 2, fillOpacity: 0.08 }} />)}
      <FlyToSelection location={selectedLocation} />
      {selectedLocation && (
        <CircleMarker
          center={[selectedLocation.latitude, selectedLocation.longitude]}
          radius={9}
          pathOptions={{ color: '#7de3ff', fillColor: '#7de3ff', fillOpacity: 0.85, weight: 3 }}
        >
          <Tooltip permanent direction="top" offset={[0, -8]}>
            {selectedLocation.name || `${selectedLocation.latitude.toFixed(4)}, ${selectedLocation.longitude.toFixed(4)}`}
          </Tooltip>
        </CircleMarker>
      )}
    </MapContainer>
  );
}
