"use strict";
(() => {
  const button = document.getElementById("load-map");
  const status = document.getElementById("map-status");
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "Loading map…";
    try {
      if (!window.L) {
        await Promise.all([
          new Promise((resolve, reject) => {
            const css = document.createElement("link");
            css.rel = "stylesheet";
            css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
            css.integrity = "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=";
            css.crossOrigin = "anonymous";
            css.onload = resolve; css.onerror = reject;
            document.head.appendChild(css);
          }),
          new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
            script.integrity = "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=";
            script.crossOrigin = "anonymous";
            script.onload = resolve; script.onerror = reject;
            document.head.appendChild(script);
          })
        ]);
      }
      document.getElementById("study-map").replaceChildren();
      const map = L.map("study-map", {scrollWheelZoom:false}).setView([35.23579, -80.84027], 16);
      const center = [35.23579, -80.84027];
      const boundary = L.circle(center, {radius:304.8, color:"#20695f", weight:2, fillOpacity:0.09}).addTo(map);
      L.circleMarker(center, {radius:5, color:"#fff", weight:2, fillColor:"#18343f", fillOpacity:1})
        .addTo(map).bindTooltip("Garrison · study center", {permanent:true, direction:"top"});
      const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom:19,
        attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      }).addTo(map);
      tiles.on("tileerror", () => {
        status.textContent = "Some street tiles could not load. The outlined radius is 1,000 feet; it is not a property boundary. Retry by reloading the page.";
      });
      map.fitBounds(boundary.getBounds(), {padding:[24,24]});
      L.control.scale({imperial:true,metric:false}).addTo(map);
    } catch (error) {
      console.error("Study map failed", error);
      button.disabled = false;
      button.textContent = "Retry map";
      status.textContent = "The map could not load. The study center is 35.23579, −80.84027, with a 1,000-foot radius. The report counts are still available above.";
    }
  });
})();
