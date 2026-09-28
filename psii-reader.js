(() => {
  const storageKey = "oof-psii-reader-mode";
  const questionPages = [
    "psii-governance-architecture-questions.html",
    "psii-problem-space-questions.html",
    "psii-operational-reality-questions.html",
    "psii-autonomous-systems-questions.html",
    "psii-intelligence-questions.html",
    "psii-evidence-questions.html",
    "psii-audit-questions.html",
    "psii-methodology-architecture-questions.html",
    "psii-methodology-evaluation-questions.html",
    "psii-methodology-modernization-questions.html",
    "psii-methodology-protection-questions.html",
    "psii-methodology-licensing-questions.html",
    "psii-methodology-lifecycle-questions.html",
    "psii-methodology-modularity-questions.html",
    "psii-methodology-governance-questions.html",
    "psii-methodology-asset-questions.html",
    "psii-methodology-quality-questions.html",
    "psii-methodology-engineering-questions.html",
    "psii-methodology-questions.html",
    "psii-compliance-questions.html",
    "psii-validation-questions.html",
    "psii-transparency-questions.html",
    "psii-trust-questions.html",
    "psii-risk-questions.html",
    "psii-decision-making-questions.html",
    "psii-authority-questions.html",
    "psii-accountability-questions.html",
    "psii-governance-questions.html"
  ];
  const body = document.body;
  const currentPage = window.location.pathname.split("/").pop();
  const currentIndex = questionPages.indexOf(currentPage);
  const toggle = document.createElement("button");
  const previous = document.createElement("a");
  const next = document.createElement("a");

  toggle.type = "button";
  toggle.className = "psii-reader-toggle";

  previous.className = "psii-reader-page psii-reader-previous";
  previous.innerHTML = '<span aria-hidden="true">&larr;</span>';
  previous.setAttribute("aria-label", "Previous question page");
  previous.title = "Previous question page";

  next.className = "psii-reader-page psii-reader-next";
  next.innerHTML = '<span aria-hidden="true">&rarr;</span>';
  next.setAttribute("aria-label", "Next question page");
  next.title = "Next question page";

  if (currentIndex > 0) {
    previous.href = `../p/${questionPages[currentIndex - 1]}`;
  } else {
    previous.hidden = true;
  }

  if (currentIndex >= 0 && currentIndex < questionPages.length - 1) {
    next.href = `../p/${questionPages[currentIndex + 1]}`;
  } else {
    next.hidden = true;
  }

  body.append(toggle, previous, next);

  function isActive() {
    return body.classList.contains("psii-reader-active");
  }

  function renderToggle() {
    const active = isActive();
    toggle.setAttribute("aria-pressed", String(active));
    toggle.setAttribute(
      "aria-label",
      active ? "Exit reader mode" : "Enable reader mode"
    );
    toggle.innerHTML = active
      ? '<span aria-hidden="true">&times;</span><span>Exit reader mode</span>'
      : '<span aria-hidden="true">&#9636;</span><span>Reader mode</span>';
  }

  function setReaderMode(active) {
    body.classList.toggle("psii-reader-active", active);
    localStorage.setItem(storageKey, active ? "on" : "off");
    renderToggle();
  }

  toggle.addEventListener("click", () => setReaderMode(!isActive()));
  document.addEventListener("keydown", event => {
    if (!isActive()) return;
    if (event.key === "Escape") setReaderMode(false);
    if (event.key === "ArrowLeft" && previous.href) previous.click();
    if (event.key === "ArrowRight" && next.href) next.click();
  });

  setReaderMode(localStorage.getItem(storageKey) === "on");
})();
