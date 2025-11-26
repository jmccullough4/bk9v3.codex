mapboxgl.accessToken = 'pk.eyJ1Ijoiam1jY3VsbG91Z2g0IiwiYSI6ImNtMGJvOXh3cDBjNncya3B4cDg0MXFuYnUifQ.uDJKnqE9WgkvGXYGLge-NQ';

const tableBody = document.getElementById('table-body');
const logDiv = document.getElementById('log');
const stylePicker = document.getElementById('style-picker');
const alertSound = document.getElementById('alert-sound');
const toggleFollowBtn = document.getElementById('toggle-follow');
const clearBtn = document.getElementById('clear');
const logoutBtn = document.getElementById('logout');
const targetsList = document.getElementById('targets');
const targetForm = document.getElementById('target-form');
const toggleCep = document.getElementById('toggle-cep');

let map;
let markers = {};
let targetMarkers = {};
let followGps = false;
let lastUserPosition = null;
let cepLayerId = 'cep-area';

function initMap() {
  map = new mapboxgl.Map({
    container: 'map',
    style: stylePicker.value,
    center: [-122.4194, 37.7749],
    zoom: 13,
  });

  map.addControl(new mapboxgl.NavigationControl());

  map.on('load', () => {
    map.addSource('system', { type: 'geojson', data: geojsonPoint([-122.4194, 37.7749]) });
    map.addLayer({
      id: 'system',
      type: 'circle',
      source: 'system',
      paint: { 'circle-radius': 8, 'circle-color': '#2ed1ff' },
    });
  });
}

function geojsonPoint([lng, lat], accuracy = 50) {
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [lng, lat] },
        properties: { accuracy },
      },
    ],
  };
}

async function loadDevices() {
  const res = await fetch('/api/devices');
  const data = await res.json();
  renderDevices(data.devices || []);
}

async function loadLogs() {
  const res = await fetch('/api/logs');
  const data = await res.json();
  renderLogs(data.logs || []);
}

async function loadTargets() {
  const res = await fetch('/api/targets');
  const data = await res.json();
  targetsList.innerHTML = '';
  (data.targets || []).forEach((t) => {
    const li = document.createElement('li');
    li.innerHTML = `<strong>${t.bd_address}</strong> - ${t.name || 'Unknown'} <span class="muted">${t.manufacturer || ''}</span>`;
    targetsList.appendChild(li);
  });
}

function renderDevices(devices) {
  tableBody.innerHTML = '';
  devices.forEach((device) => {
    const tr = document.createElement('tr');
    if (device.is_target) tr.classList.add('row-target');
    tr.innerHTML = `
      <td>${device.bd_address}</td>
      <td>${device.name}</td>
      <td>${device.manufacturer}</td>
      <td>${device.device_type}</td>
      <td>${device.rssi}</td>
      <td>${formatLocation(device.emitter_location)}</td>
      <td>${formatLocation(device.system_location)}</td>
      <td>${device.first_seen}</td>
      <td>${device.last_seen}</td>
    `;
    tableBody.appendChild(tr);
    renderMarker(device);
    if (device.is_target) {
      highlightTarget(device);
    }
  });
}

function renderMarker(device) {
  const { emitter_location: loc, bd_address } = device;
  if (!loc) return;
  const lngLat = [loc.lng, loc.lat];
  if (markers[bd_address]) {
    markers[bd_address].setLngLat(lngLat);
  } else {
    const el = document.createElement('div');
    el.className = device.is_target ? 'marker marker-target' : 'marker';
    markers[bd_address] = new mapboxgl.Marker(el).setLngLat(lngLat).addTo(map);
  }
  if (toggleCep.checked) {
    drawCep(loc);
  } else if (map.getLayer(cepLayerId)) {
    map.removeLayer(cepLayerId);
    map.removeSource(cepLayerId);
  }
}

function highlightTarget(device) {
  if (!device.emitter_location) return;
  if (!targetMarkers[device.bd_address]) {
    const popup = new mapboxgl.Popup({ offset: 12 }).setHTML(
      `<strong>Target Found</strong><br>${device.bd_address}<br>RSSI ${device.rssi}`
    );
    targetMarkers[device.bd_address] = new mapboxgl.Marker({ color: '#ff5f6d' })
      .setLngLat([device.emitter_location.lng, device.emitter_location.lat])
      .setPopup(popup)
      .addTo(map);
    alertSound.play();
  }
}

function drawCep(loc) {
  const radius = Math.max(20, loc.accuracy || 80);
  const center = [loc.lng, loc.lat];
  const circle = turf.circle(center, radius / 1000, { steps: 60, units: 'kilometers' });
  if (map.getSource(cepLayerId)) {
    map.getSource(cepLayerId).setData(circle);
  } else {
    map.addSource(cepLayerId, { type: 'geojson', data: circle });
    map.addLayer({
      id: cepLayerId,
      type: 'fill',
      source: cepLayerId,
      paint: { 'fill-color': '#2ed1ff', 'fill-opacity': 0.2 },
    });
  }
}

function renderLogs(logs) {
  logDiv.innerHTML = logs.map((l) => `<div>${l}</div>`).join('');
  logDiv.scrollTop = logDiv.scrollHeight;
}

function formatLocation(loc) {
  if (!loc) return '—';
  return `${loc.lat.toFixed(5)}, ${loc.lng.toFixed(5)} (${loc.accuracy || 50}m)`;
}

function setupEvents() {
  stylePicker.addEventListener('change', () => {
    map.setStyle(stylePicker.value);
    map.on('styledata', () => {
      if (!map.getSource('system')) {
        map.addSource('system', { type: 'geojson', data: geojsonPoint([-122.4194, 37.7749]) });
        map.addLayer({ id: 'system', type: 'circle', source: 'system', paint: { 'circle-radius': 8, 'circle-color': '#2ed1ff' } });
      }
    });
  });

  toggleFollowBtn.addEventListener('click', () => {
    followGps = !followGps;
    toggleFollowBtn.textContent = followGps ? 'Following GPS' : 'Toggle Follow GPS';
  });

  clearBtn.addEventListener('click', async () => {
    await fetch('/api/clear', { method: 'POST' });
    loadDevices();
  });

  logoutBtn.addEventListener('click', () => {
    fetch('/logout', { method: 'POST' }).then(() => (window.location = '/login'));
  });

  targetForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = new FormData(targetForm);
    const payload = Object.fromEntries(form.entries());
    await fetch('/api/targets', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    targetForm.reset();
    loadTargets();
  });
}

function trackGps() {
  if (!navigator.geolocation) return;
  navigator.geolocation.watchPosition(
    (pos) => {
      const coords = [pos.coords.longitude, pos.coords.latitude];
      lastUserPosition = coords;
      if (followGps && map) {
        map.flyTo({ center: coords, essential: false });
      }
      if (map.getSource('system')) {
        map.getSource('system').setData(geojsonPoint(coords, pos.coords.accuracy));
      }
    },
    (err) => console.warn(err),
    { enableHighAccuracy: true }
  );
}

async function poll() {
  await Promise.all([loadDevices(), loadLogs(), loadTargets()]);
  setTimeout(poll, 5000);
}

(async function start() {
  initMap();
  setupEvents();
  trackGps();
  poll();
})();
