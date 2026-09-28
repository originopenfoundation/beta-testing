(function () {
  "use strict";

  const layouts = {
    GOA: "GOA",
    INTEGROS: "INTEGROS",
    AIG: "AIG",
    ORA: "ORA",
    ASGA: "ASGA",
    CLIA: "CLIA",
    MGIA: "MGIA",
    TREGA: "TREGA",
    AGA: "AGA",
    OBIDENITY: "OBIDENITY",
    CLA: "CLA",
    SIMULOS: "SIMULOS",
    VFM: "VFM",
    VALIDOS: "VALIDOS"
  };

  const root = document.getElementById("oof-architecture-territories");
  const status = document.getElementById("oof-map-status");
  const panel = document.getElementById("oof-selected-architecture");
  const title = document.getElementById("oof-selected-title");
  const selectedStatus = document.getElementById("oof-selected-status");
  const links = document.getElementById("oof-selected-links");
  const note = document.getElementById("oof-selected-development-note");
  const frame = document.getElementById("oof-selected-page");

  function setLayout(button, item) {
    const area = layouts[item.acronym];
    if (area) button.style.gridArea = area;
  }

  function selectArchitecture(item, button) {
    root.querySelectorAll(".oof-map-territory").forEach((territory) => territory.setAttribute("aria-pressed", "false"));
    button.setAttribute("aria-pressed", "true");
    panel.hidden = false;
    title.textContent = item.displayName || `${item.acronym} — ${item.name}`;
    selectedStatus.textContent = item.status === "development" ? "Status: In Development" : "Status: Completed / Published Architecture";
    links.replaceChildren();

    if (item.status === "development") {
      note.hidden = false;
      frame.hidden = true;
      frame.removeAttribute("src");
    } else {
      note.hidden = true;
      const primary = item.primaryPage || item.pages[0];
      frame.src = primary.url;
      frame.hidden = false;
      item.pages.filter((page) => page.url !== primary.url).forEach((page) => {
        const anchor = document.createElement("a");
        anchor.href = page.url;
        anchor.textContent = `${page.label} →`;
        links.append(anchor);
      });
    }
    panel.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }

  function render(data) {
    const items = [...data.architectures, ...data.developmentArchitectures];
    items.forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "oof-map-territory";
      button.dataset.status = item.status;
      button.setAttribute("aria-pressed", "false");
      button.setAttribute("aria-label", `${item.displayName || `${item.acronym} — ${item.name}`}. Status: ${item.status === "development" ? "In Development" : "Completed / Published Architecture"}.`);
      setLayout(button, item);
      const acronym = document.createElement("span");
      acronym.className = "oof-map-acronym";
      acronym.textContent = item.acronymLabel || item.acronym;
      const name = document.createElement("span");
      name.className = "oof-map-name";
      name.textContent = item.name;
      const state = document.createElement("span");
      state.className = "oof-map-territory-status";
      state.textContent = item.status === "development" ? "In Development" : "Completed";
      button.append(acronym, name, state);
      button.addEventListener("click", () => selectArchitecture(item, button));
      root.append(button);
    });
    root.setAttribute("aria-busy", "false");
    status.textContent = `${data.architectures.length} completed architectures from the official Architecture Index${data.developmentArchitectures.length ? ` · ${data.developmentArchitectures.length} in development` : ""}.`;
  }

  fetch("data/oof-architecture-registry.json")
    .then((response) => {
      if (!response.ok) throw new Error(`Registry request failed (${response.status})`);
      return response.json();
    })
    .then(render)
    .catch(() => {
      root.setAttribute("aria-busy", "false");
      status.textContent = "The Architecture Map could not load the official Architecture Index data.";
    });
})();
