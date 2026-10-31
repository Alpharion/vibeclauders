/* Operational map. Layer toggles stay in the browser; airport and horizon go to Python. */
const LOWER_48 = [[48.4,-124.7],[49,-123],[49,-95.2],[48.7,-94.6],[48.3,-92],[48,-89.6],[46.5,-84.5],[45.3,-82.5],[43,-82.4],[42,-83],[42.8,-79],[43.3,-79],[43.6,-76.5],[45,-75],[45,-71.5],[46.7,-70],[47.4,-69],[47,-67.8],[44.8,-67],[43.6,-70],[42.2,-70.7],[41.7,-70],[40.7,-74],[38.5,-75.5],[37,-76],[35.3,-75.5],[33.9,-77.9],[32,-81],[30.5,-81.4],[26.9,-80],[25.2,-80.4],[26,-81.8],[28,-82.8],[30,-84],[29.7,-85.5],[30.3,-89],[29.2,-89.5],[29.5,-91.5],[29.6,-94],[27.8,-97],[26,-97.3],[26.5,-99.2],[29.8,-101.4],[29,-103],[30.6,-104.9],[31.8,-106.5],[31.3,-108.2],[31.3,-111],[32.5,-114.8],[32.5,-117.1],[34,-118.5],[34.6,-120.6],[37.2,-122.4],[40.3,-124.2],[43,-124.5],[46.2,-124]];

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function build(root) {
  const ops = element('div', 'ops');
  const head = element('div', 'head');
  const title = element('h3');
  const controls = element('span');
  controls.style.display = 'contents';
  head.append(title, controls);
  const banner = element('div', 'banner');
  const frame = element('div', 'frame');
  const mapNode = element('div', 'map');
  const flag = element('div', 'flag');
  frame.append(mapNode, flag);
  const legend = element('div', 'legend');
  const timeline = element('div', 'timeline');
  ops.append(head, banner, frame, legend, timeline);
  root.append(ops);
  return {ops, title, controls, banner, mapNode, flag, legend, timeline, map: null, base: null, layers: {}, enabled: {}, viewKey: null};
}

function ensureMap(state, data) {
  state.mapNode.style.height = `${data.height}px`;
  if (state.map) { state.map.invalidateSize(); return; }
  const map = L.map(state.mapNode, {zoomSnap: 0.25, minZoom: 3, maxZoom: 10, attributionControl: true});
  // The outline sits below the tile pane, so it only shows when basemap tiles fail to load.
  map.createPane('fallback').style.zIndex = 150;
  const labelPane = map.createPane('labels');
  labelPane.style.zIndex = 350;
  labelPane.style.pointerEvents = 'none';
  L.polygon(LOWER_48, {pane: 'fallback', color: '#3A4C5E', weight: 1, fillColor: '#2E4A5F', fillOpacity: 1, interactive: false}).addTo(map);
  state.base = L.tileLayer(data.basemap, {maxZoom: 12, zIndex: 1, className: 'basemap', attribution: 'Tiles © Esri'}).addTo(map);
  L.tileLayer(data.labels, {maxZoom: 12, pane: 'labels', className: 'map-labels'}).addTo(map);
  state.layers.weather = L.layerGroup().addTo(map);
  state.layers.connections = L.layerGroup().addTo(map);
  state.layers.flagged = L.layerGroup().addTo(map);
  state.layers.hubs = L.layerGroup().addTo(map);
  state.map = map;
  new ResizeObserver(() => map.invalidateSize()).observe(state.mapNode);
}

function radarLayer(state, data) {
  const group = state.layers.weather;
  group.clearLayers();
  state.radarFailed = false;
  if (!data.radar) return;
  const layer = L.tileLayer.wms(data.radar.url, {
    layers: 'nexrad-n0q-wmst', format: 'image/png', transparent: true, opacity: 0.75, zIndex: 2,
    time: data.radar.time, attribution: 'NEXRAD via Iowa Environmental Mesonet',
  });
  layer.on('tileerror', () => {
    if (state.radarFailed) return;
    state.radarFailed = true;
    state.flag.textContent = 'Radar tiles failed to load';
    state.flag.style.display = 'block';
  });
  group.addLayer(layer);
}

function drawNetwork(state, data, setTriggerValue) {
  const {connections, flagged, hubs} = state.layers;
  connections.clearLayers(); flagged.clearLayers(); hubs.clearLayers();
  data.lines.forEach(line => {
    const path = L.polyline(line.path, {color: line.color, weight: line.weight, dashArray: line.dash, opacity: 0.9});
    path.bindTooltip(line.label, {sticky: true});
    (line.flagged ? flagged : connections).addLayer(path);
  });
  data.markers.forEach(marker => {
    const group = marker.hub ? hubs : connections;
    if (marker.hub) group.addLayer(L.circleMarker([marker.lat, marker.lon], {radius: marker.radius + 6, stroke: false, fillColor: marker.color, fillOpacity: 0.25, interactive: false}));
    const dot = L.circleMarker([marker.lat, marker.lon], {radius: marker.radius, color: marker.hub ? '#0C1117' : '#F1F5F9', weight: marker.hub ? 3 : 1, fillColor: marker.color, fillOpacity: 1});
    dot.bindTooltip(marker.code, {permanent: true, direction: 'right', offset: [marker.radius, 0], className: 'code'});
    dot.bindPopup(() => { const p = document.createElement('div'); p.textContent = marker.label; return p; });
    if (marker.hub && marker.icao) dot.on('click', () => setTriggerValue('airport', marker.icao));
    group.addLayer(dot);
  });
}

function applyLayers(state) {
  Object.entries(state.enabled).forEach(([name, on]) => {
    const group = state.layers[name];
    if (group) (on ? state.map.addLayer(group) : state.map.removeLayer(group));
  });
}

function drawControls(state, data) {
  state.controls.replaceChildren();
  if (data.tag) state.controls.append(element('span', 'tag', data.tag));
  if (data.age) state.controls.append(element('span', 'age', data.age));
  data.layerButtons.forEach(button => {
    const node = element('button', 'layer', button.label);
    node.type = 'button';
    node.disabled = button.disabled;
    if (button.disabled) node.title = button.reason;
    state.enabled[button.key] ??= !button.disabled;
    if (button.disabled) state.enabled[button.key] = false;
    node.setAttribute('aria-pressed', String(state.enabled[button.key]));
    node.onclick = () => {
      state.enabled[button.key] = !state.enabled[button.key];
      node.setAttribute('aria-pressed', String(state.enabled[button.key]));
      applyLayers(state);
    };
    state.controls.append(node);
  });
}

function drawLegend(state, data) {
  state.legend.replaceChildren();
  data.legend.forEach(entry => {
    const item = element('span');
    const swatch = element('i', entry.kind === 'line' ? 'line' : '');
    swatch.style.background = entry.color;
    item.append(swatch, entry.label);
    state.legend.append(item);
  });
  state.legend.append(element('span', 'note', data.note));
}

function drawTimeline(state, data, setTriggerValue) {
  state.timeline.replaceChildren();
  state.timeline.style.display = data.stops.length ? 'block' : 'none';
  if (!data.stops.length) return;
  const last = data.stops[data.stops.length - 1].lead;
  const position = lead => `${(lead / last) * 100}%`;
  const selected = data.stops.find(stop => stop.selected);
  const elapsed = element('div', 'elapsed');
  elapsed.style.width = position(selected ? selected.lead : 0);
  state.timeline.append(element('div', 'track'), elapsed);
  data.stops.forEach(stop => {
    const node = element('button', 'stop');
    node.type = 'button';
    node.style.left = position(stop.lead);
    node.setAttribute('aria-pressed', String(stop.selected));
    node.disabled = stop.lead === 0;
    node.setAttribute('aria-label', stop.lead === 0 ? `Cutoff ${stop.label}` : `Horizon +${stop.lead} hours, valid ${stop.label}`);
    node.append(element('i'), stop.label);
    if (stop.lead) node.onclick = () => setTriggerValue('horizon', stop.lead);
    state.timeline.append(node);
  });
  state.timeline.append(element('div', 'valid', data.validLabel));
}

export default function ({data, parentElement, setTriggerValue}) {
  parentElement.__opsMap ??= build(parentElement.querySelector('.ops-root'));
  const state = parentElement.__opsMap;
  state.title.textContent = data.title;
  state.banner.textContent = data.banner.text;
  state.banner.className = `banner ${data.banner.alert ? 'alert' : ''}`;
  state.banner.style.display = data.banner.text ? 'flex' : 'none';
  state.flag.textContent = data.flag;
  state.flag.style.display = data.flag ? 'block' : 'none';
  ensureMap(state, data);
  drawControls(state, data);
  radarLayer(state, data);
  drawNetwork(state, data, setTriggerValue);
  applyLayers(state);
  drawLegend(state, data);
  drawTimeline(state, data, setTriggerValue);
  if (state.viewKey !== data.viewKey) {
    state.viewKey = data.viewKey;
    state.map.fitBounds(data.bounds, {padding: [36, 36], maxZoom: 6});
  }
}
