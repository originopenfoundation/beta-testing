(function () {
  "use strict";

  const COLORS = {
    high: "#167a45",
    moderate: "#2468b4",
    emerging: "#d6a51f",
    insufficient: "#a3a3a3",
    hover: "#f2f2f2"
  };
  const STATUS_LABELS = {
    high: "High Interest",
    moderate: "Moderate Interest",
    emerging: "Emerging Interest",
    insufficient: "Insufficient Signal"
  };
  const MOMENTUM_LABELS = {
    "rapidly-rising": "↑ Rapidly Rising",
    rising: "↗ Rising",
    stable: "→ Stable",
    declining: "↘ Declining"
  };
  const WORLD_BOUNDS = [[-58, -180], [84, 180]];

  const container = document.getElementById("global-interest-globe");
  const fallback = document.getElementById("global-interest-fallback");
  const select = document.getElementById("global-interest-country-select");
  const card = document.getElementById("global-interest-country-card");
  const countryName = document.getElementById("global-interest-country-name");
  const countryStatus = document.getElementById("global-interest-country-status");
  const countryMomentum = document.getElementById("global-interest-country-momentum");
  const viewControls = document.querySelector(".oof-global-interest-view-controls");
  if (!container || !select || !card) return;

  let map;
  let selectedFeature = null;
  let hoveredFeature = null;
  let countryLayers = [];
  let labelLayers = [];
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const precisePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  function countryCode(feature) {
    const properties = feature && feature.properties ? feature.properties : {};
    const candidates = [properties.ISO_A2_EH, properties.ISO_A2];
    return String(candidates.find(code => code && code !== "-99") || "").toUpperCase();
  }

  function countryLabel(feature) {
    const properties = feature && feature.properties ? feature.properties : {};
    return properties.NAME_EN || properties.ADMIN || properties.NAME_LONG || properties.NAME || "Unknown country";
  }

  function featureCenter(feature) {
    const properties = feature && feature.properties ? feature.properties : {};
    const lat = Number(properties.LABEL_Y);
    const lng = Number(properties.LABEL_X);
    return Number.isFinite(lat) && Number.isFinite(lng) ? [lat, lng] : null;
  }

  function isTinyFeature(feature) {
    const properties = feature && feature.properties ? feature.properties : {};
    return Number(properties.TINY) > 0;
  }

  function flagFor(iso) {
    if (!/^[A-Z]{2}$/.test(iso)) return "";
    return String.fromCodePoint(...iso.split("").map(letter => 127397 + letter.charCodeAt(0)));
  }

  function publicState(feature) {
    return feature.__oofInterest || { status: "insufficient" };
  }

  function escapeHtml(value) {
    const span = document.createElement("span");
    span.textContent = value;
    return span.innerHTML;
  }

  function showCountry(feature) {
    if (!feature) {
      countryName.textContent = "Select a country";
      countryStatus.textContent = "Interest classification will appear here.";
      countryMomentum.hidden = true;
      return;
    }
    const iso = countryCode(feature);
    const state = publicState(feature);
    const flag = flagFor(iso);
    countryName.textContent = `${flag ? flag + " " : ""}${countryLabel(feature)}`;
    countryStatus.textContent = `Interest: ${STATUS_LABELS[state.status] || STATUS_LABELS.insufficient}`;
    if (state.momentum && MOMENTUM_LABELS[state.momentum]) {
      countryMomentum.textContent = `Momentum: ${MOMENTUM_LABELS[state.momentum]}`;
      countryMomentum.hidden = false;
    } else {
      countryMomentum.hidden = true;
    }
  }

  function countryStyle(feature) {
    const state = publicState(feature);
    const highlighted = feature === selectedFeature || feature === hoveredFeature;
    const activeTiny = isTinyFeature(feature) && state.status !== "insufficient";
    return {
      color: highlighted ? "#ffffff" : "rgba(255,255,255,0.68)",
      weight: feature === selectedFeature ? 3.4 : highlighted ? 2.4 : activeTiny ? 3 : 0.7,
      opacity: 1,
      fillColor: feature === hoveredFeature ? COLORS.hover : COLORS[state.status] || COLORS.insufficient,
      fillOpacity: state.status === "insufficient" ? 0.7 : 0.92
    };
  }

  function refreshHighlights() {
    countryLayers.forEach(({ feature, layer }) => layer.setStyle(countryStyle(feature)));
  }

  function selectFeature(feature, focus) {
    selectedFeature = feature;
    showCountry(feature);
    select.value = countryCode(feature);
    refreshHighlights();
    const center = featureCenter(feature);
    if (focus && center) {
      map.flyTo(center, Math.max(map.getZoom(), isTinyFeature(feature) ? 8 : 4), {
        animate: !reducedMotion,
        duration: reducedMotion ? 0 : 0.55
      });
    }
  }

  function minimumLabelZoom(feature) {
    if (isTinyFeature(feature) && publicState(feature).status !== "insufficient") return 1;
    const properties = feature.properties || {};
    const sourceZoom = Number(properties.MIN_LABEL);
    const rank = Number(properties.LABELRANK);
    const suggested = Number.isFinite(sourceZoom) && sourceZoom > 0 ? sourceZoom : rank;
    return Math.max(3, Math.min(6, Number.isFinite(suggested) ? suggested : 5));
  }

  function createLabel(feature, minimumZoom, maximumZoom, callout) {
    const center = featureCenter(feature);
    if (!center) return;
    const state = publicState(feature);
    const icon = L.divIcon({
      className: `oof-country-label-marker${callout ? ` is-tiny-callout is-${state.status}` : ""}`,
      html: `<span>${escapeHtml(countryLabel(feature))}</span>`,
      iconSize: callout ? [140, 32] : null,
      iconAnchor: callout ? [0, 16] : undefined
    });
    const marker = L.marker(center, {
      icon,
      interactive: Boolean(callout),
      keyboard: Boolean(callout),
      title: callout ? `Show ${countryLabel(feature)}` : undefined
    });
    if (callout) marker.on("click", () => selectFeature(feature, true));
    labelLayers.push({
      minimumZoom,
      maximumZoom,
      layer: marker
    });
  }

  function updateLabels() {
    const zoom = map.getZoom();
    labelLayers.forEach(item => {
      const shouldShow = zoom >= item.minimumZoom && (!item.maximumZoom || zoom < item.maximumZoom);
      if (shouldShow && !map.hasLayer(item.layer)) item.layer.addTo(map);
      if (!shouldShow && map.hasLayer(item.layer)) item.layer.removeFrom(map);
    });
  }

  function populateCountrySelector(features) {
    const unique = new Map();
    features.forEach(feature => {
      const iso = countryCode(feature);
      if (iso && !unique.has(iso)) unique.set(iso, feature);
    });
    const sorted = [...unique.values()].sort((a, b) => countryLabel(a).localeCompare(countryLabel(b), "en"));
    const fragment = document.createDocumentFragment();
    sorted.forEach(feature => {
      const option = document.createElement("option");
      option.value = countryCode(feature);
      option.textContent = countryLabel(feature);
      option.__feature = feature;
      fragment.appendChild(option);
    });
    select.appendChild(fragment);
    select.addEventListener("change", () => {
      const option = select.options[select.selectedIndex];
      if (option && option.__feature) selectFeature(option.__feature, true);
      else {
        selectedFeature = null;
        showCountry(null);
        refreshHighlights();
      }
    });
  }

  function showFallback(message) {
    container.classList.add("is-fallback");
    container.innerHTML = `<p>${message}</p>`;
    if (viewControls) viewControls.hidden = true;
    if (fallback) fallback.hidden = false;
  }

  Promise.all([
    fetch("assets/data/ne_50m_admin_0_countries.geojson", { cache: "force-cache" }).then(response => {
      if (!response.ok) throw new Error("Country geometry unavailable");
      return response.json();
    }),
    fetch("data/oof-global-interest-heat-map.json", { cache: "no-cache" }).then(response => {
      if (!response.ok) throw new Error("Public interest dataset unavailable");
      return response.json();
    })
  ]).then(([world, dataset]) => {
    if (typeof window.L !== "object") throw new Error("2D map library unavailable");

    const publicCountries = new Map((dataset.countries || []).map(item => [String(item.iso || "").toUpperCase(), item]));
    const features = (world.features || []).filter(feature => {
      const iso = countryCode(feature);
      return iso && iso !== "AQ";
    });
    features.forEach(feature => {
      const state = publicCountries.get(countryCode(feature));
      feature.__oofInterest = state && STATUS_LABELS[state.status] ? state : { status: "insufficient" };
    });
    container.innerHTML = "";
    map = L.map(container, {
      attributionControl: true,
      zoomControl: false,
      minZoom: 1,
      maxZoom: 9,
      zoomSnap: 0.25,
      zoomDelta: 0.5,
      wheelPxPerZoomLevel: 90,
      maxBounds: [[-85, -190], [85, 190]],
      maxBoundsViscosity: 1,
      worldCopyJump: false,
      preferCanvas: true
    });
    map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
    map.attributionControl.addAttribution('<a href="https://www.naturalearthdata.com" target="_blank" rel="noopener">Natural Earth</a>');
    map.fitBounds(WORLD_BOUNDS, { padding: [8, 8], animate: false });

    L.geoJSON(features, {
      style: countryStyle,
      onEachFeature(feature, layer) {
        countryLayers.push({ feature, layer });
        layer.on({
          click: () => selectFeature(feature, false),
          mouseover: () => {
            if (!precisePointer) return;
            hoveredFeature = feature;
            showCountry(feature);
            refreshHighlights();
            layer.bringToFront();
          },
          mouseout: () => {
            if (!precisePointer) return;
            hoveredFeature = null;
            showCountry(selectedFeature);
            refreshHighlights();
          }
        });
        if (isTinyFeature(feature) && publicState(feature).status !== "insufficient") {
          createLabel(feature, 1, 4, true);
          createLabel(feature, 4);
        } else {
          createLabel(feature, minimumLabelZoom(feature));
        }
      }
    }).addTo(map);

    populateCountrySelector(features);
    updateLabels();
    map.on("zoomend", () => {
      updateLabels();
      refreshHighlights();
    });

    if (viewControls) {
      viewControls.addEventListener("click", event => {
        const button = event.target.closest("button[data-map-action]");
        if (!button) return;
        if (button.dataset.mapAction === "zoom-in") map.zoomIn(0.5);
        if (button.dataset.mapAction === "zoom-out") map.zoomOut(0.5);
        if (button.dataset.mapAction === "reset") {
          selectedFeature = null;
          hoveredFeature = null;
          select.value = "";
          showCountry(null);
          refreshHighlights();
          map.fitBounds(WORLD_BOUNDS, { padding: [8, 8], animate: !reducedMotion });
        }
      });
    }

    if ("ResizeObserver" in window) {
      const observer = new ResizeObserver(() => map.invalidateSize({ pan: false }));
      observer.observe(container);
    } else {
      window.addEventListener("resize", () => map.invalidateSize({ pan: false }));
    }
  }).catch(error => {
    showFallback("The public map could not be loaded. The last valid dataset remains unavailable in this preview.");
    console.error("OOF Global Interest Heat Map:", error);
  });
})();
