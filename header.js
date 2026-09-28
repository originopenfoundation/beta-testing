let siteSearchIndex = null;
let siteSearchLoading = false;
const navigationStateKey = "oof-navigation-expanded";
const navigationScrollKey = "oof-navigation-scroll";

function loadCloudflareAnalytics() {
  if (location.protocol === "file:" || location.hostname === "localhost" || location.hostname === "127.0.0.1") return;
  if (document.querySelector('script[data-cf-beacon]')) return;

  const beacon = document.createElement("script");
  beacon.type = "module";
  beacon.src = "https://static.cloudflareinsights.com/beacon.min.js";
  beacon.dataset.cfBeacon = JSON.stringify({ token: "358af31e8be84a238826900e0aba2cc3" });
  document.body.appendChild(beacon);
}

function getNavigationState() {
  try {
    return JSON.parse(sessionStorage.getItem(navigationStateKey) || "{}");
  } catch (error) {
    return {};
  }
}

function getNavigationStateId(id) {
  return id.replace(/^mega-/, "");
}

function saveNavigationState(id, expanded) {
  try {
    const state = getNavigationState();
    const stateId = getNavigationStateId(id);
    if (expanded) state[stateId] = true;
    else delete state[stateId];
    sessionStorage.setItem(navigationStateKey, JSON.stringify(state));
  } catch (error) {
    return;
  }
}

function restoreNavigationState(menu) {
  const state = getNavigationState();

  menu.querySelectorAll("[aria-controls]").forEach(toggle => {
    const controlledId = toggle.getAttribute("aria-controls");
    if (!controlledId || !state[getNavigationStateId(controlledId)]) return;

    const controlled = getById(controlledId);
    if (!controlled) return;

    controlled.style.display = "block";
    toggle.setAttribute("aria-expanded", "true");
    toggle.classList.toggle("burger-main-active", toggle.classList.contains("burger-main-toggle"));
    toggle.classList.toggle("menu-toggle-open", toggle.classList.contains("burger-toggle"));
  });
}

function setupNavigationScrollPersistence(menu) {
  if (menu.dataset.scrollPersistenceReady === "true") return;
  menu.dataset.scrollPersistenceReady = "true";

  requestAnimationFrame(() => {
    const savedScroll = Number(sessionStorage.getItem(navigationScrollKey));
    if (Number.isFinite(savedScroll) && savedScroll > 0) menu.scrollTop = savedScroll;
  });

  menu.addEventListener("scroll", () => {
    try {
      sessionStorage.setItem(navigationScrollKey, String(menu.scrollTop));
    } catch (error) {
      return;
    }
  }, { passive: true });
}

function getById(id) {
  return document.getElementById(id);
}

function setDisplay(element, display) {
  if (element) element.style.display = display;
}

function isOpen(element) {
  return element && element.style.display === "block";
}

function toggleElement(id) {
  const element = getById(id);
  if (!element) return;
  element.style.display = isOpen(element) ? "none" : "block";
}


function getSiteRootPrefix() {
  const path = window.location.pathname.replace(/\\/g, "/");
  const parts = path.split("/").filter(Boolean);
  if (parts.length <= 1) return "";
  return "../".repeat(parts.length - 1);
}

function withSiteRoot(url) {
  if (!url || /^(?:[a-z]+:|#|\/)/i.test(url)) return url;
  return getSiteRootPrefix() + url.replace(/^\.\//, "");
}

function getSiteRootUrl() {
  const headerScripts = Array.from(document.scripts).filter(script =>
    /(?:^|\/)header\.js(?:[?#].*)?$/.test(script.src)
  );
  const headerScript = headerScripts[headerScripts.length - 1];
  return headerScript ? new URL(".", headerScript.src) : new URL("./", window.location.href);
}

function getCurrentPagePdfUrl() {
  const siteRoot = getSiteRootUrl();
  const pageUrl = new URL(window.location.href);
  const rootPath = decodeURIComponent(siteRoot.pathname);
  const pagePath = decodeURIComponent(pageUrl.pathname);
  let relativePath = pagePath.startsWith(rootPath)
    ? pagePath.slice(rootPath.length)
    : pagePath.replace(/^\/+/, "");

  if (!relativePath || relativePath.endsWith("/")) relativePath += "index.html";
  relativePath = relativePath.replace(/\.html?$/i, "") + ".pdf";
  return new URL("pdf/" + relativePath, siteRoot).href;
}

function setupPagePdfDownload() {
  const footer = document.querySelector("#footer .footer2, footer.footer2");
  if (!footer) return;

  let download = footer.querySelector(".page-pdf-download");
  if (!download) {
    download = document.createElement("div");
    download.className = "page-pdf-download";
    download.innerHTML = '<a download>Download this page as PDF</a>';
    footer.insertBefore(download, footer.firstChild);
  }

  const link = download.querySelector("a");
  if (link) link.href = getCurrentPagePdfUrl();
}

function normalizePageLinks(root = document) {
  root.querySelectorAll("a[href]").forEach(link => {
    const href = link.getAttribute("href");
    const sharedNavigationLink = Boolean(link.closest("#header, #footer"));
    const siteRootPath = href && href.includes("/");
    if (href && !/^(?:[a-z]+:|#|\/|\.\.\/)/i.test(href) && (sharedNavigationLink || siteRootPath)) {
      link.setAttribute("href", withSiteRoot(href));
    }
  });
  setupPagePdfDownload();
}

function toggleBurger() {
  ensureStructuredArchitectureLink();
  setupBurgerMainSections();
  toggleElement("burgerMenu");
}

function toggleBurgerSub(submenuId, toggle) {
  toggleSubmenu(submenuId, toggle);
}

function toggleSubmenu(submenuId, toggle) {
  const submenu = getById(submenuId);
  if (!submenu) return;

  const opening = !isOpen(submenu);
  submenu.style.display = opening ? "block" : "none";
  saveNavigationState(submenuId, opening);
  if (toggle) {
    toggle.classList.toggle("menu-toggle-open", opening);
    toggle.setAttribute("aria-expanded", String(opening));
  }
}

function configureMenuToggle(toggle, controlledId) {
  const controlled = getById(controlledId);
  if (!toggle || !controlled) return;

  toggle.setAttribute("role", "button");
  toggle.setAttribute("tabindex", "0");
  toggle.setAttribute("aria-controls", controlledId);
  toggle.setAttribute("aria-expanded", String(isOpen(controlled)));

  if (toggle.dataset.keyboardReady === "true") return;
  toggle.dataset.keyboardReady = "true";
  toggle.addEventListener("keydown", event => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    toggle.click();
  });
}

function initializeSubmenuControls(root) {
  root.querySelectorAll(".burger-toggle[onclick]").forEach(toggle => {
    const handler = toggle.getAttribute("onclick") || "";
    const match = handler.match(/toggle(?:Burger|Mega)Sub\('([^']+)'/);
    if (match) configureMenuToggle(toggle, match[1]);
  });
}

function buildMegaMenu() {
  ensureStructuredArchitectureLink();
  const source = getById("burgerMenu");
  const target = getById("megaMenuContent");
  if (!source || !target || target.dataset.ready === "true") return;

  const html = (source.dataset.originalHtml || source.innerHTML)
    .replace(/toggleBurgerSub\('([^']+)', this\)/g, "toggleMegaSub('mega-$1', this)")
    .replace(/id="([^"]+)"/g, 'id="mega-$1"');

  target.innerHTML = html;
  organizeMegaMenuContent(target);
  initializeSubmenuControls(target);
  target.dataset.ready = "true";
}

function ensureStructuredArchitectureLink() {
  const menu = getById("burgerMenu");
  if (!menu || menu.querySelector('a[href="oof-structured-architecture-index.html"]')) return;

  const standardsIndex = menu.querySelector('a[href="standardinde.html"]');
  if (!standardsIndex) return;

  const link = document.createElement("a");
  link.href = withSiteRoot("oof-structured-architecture-index.html");
  link.textContent = "OOF Structured Architecture Index";
  standardsIndex.insertAdjacentElement("afterend", link);
}

function organizeMegaMenuContent(target) {
  const nodes = Array.from(target.childNodes);
  target.textContent = "";

  const entries = [];
  const sections = [];
  let currentBody = null;

  nodes.forEach(node => {
    if (node.nodeType === Node.TEXT_NODE && node.textContent.trim() === "") return;
    if (node.nodeName === "BR") return;
    if (node.nodeType === Node.ELEMENT_NODE && node.classList.contains("burger-search")) return;

    if (node.nodeType === Node.ELEMENT_NODE && node.classList.contains("podstranka")) {
      Array.from(node.children).forEach(child => {
        if (child.nodeName === "A") entries.push({ type: "direct", link: child });
      });
      return;
    }

    if (node.nodeName === "HR") {
      currentBody = null;
      return;
    }

    if (node.nodeName === "H3") {
      currentBody = document.createElement("div");
      currentBody.className = "mega-section-body";
      sections.push({
        title: node.textContent.trim(),
        body: currentBody
      });
      entries.push({ type: "section", index: sections.length - 1 });
      return;
    }

    if (!currentBody) {
      currentBody = document.createElement("div");
      currentBody.className = "mega-section-body";
      sections.push({
        title: "Navigation",
        body: currentBody
      });
    }

    currentBody.appendChild(node);
  });

  const tabs = document.createElement("div");
  const detail = document.createElement("div");
  tabs.className = "mega-menu-tabs";
  detail.className = "mega-menu-detail";

  sections.forEach((section, index) => {
    section.body.dataset.sectionIndex = String(index);
    detail.appendChild(section.body);
  });

  entries.forEach(entry => {
    if (entry.type === "direct") {
      entry.link.className = "mega-section-tab mega-direct-link";
      tabs.appendChild(entry.link);
      return;
    }

    const section = sections[entry.index];
    const button = document.createElement("button");
    button.type = "button";
    button.className = "mega-section-tab";
    button.textContent = section.title;
    button.addEventListener("click", () => showMegaSection(entry.index));
    tabs.appendChild(button);
  });

  target.appendChild(tabs);
  target.appendChild(detail);
  showMegaSection(0);
}

function toggleMegaMenu() {
  buildMegaMenu();
  closeSiteSearch();
  toggleElement("megaMenu");
}

function closeMegaMenu() {
  setDisplay(getById("megaMenu"), "none");
}

function toggleMegaSub(submenuId, toggle) {
  toggleSubmenu(submenuId, toggle);
}

function showMegaSection(index) {
  const content = getById("megaMenuContent");
  if (!content) return;

  content.querySelectorAll("button.mega-section-tab").forEach((button, buttonIndex) => {
    button.classList.toggle("mega-section-active", buttonIndex === index);
  });

  content.querySelectorAll(".mega-section-body").forEach(body => {
    body.style.display = body.dataset.sectionIndex === String(index) ? "block" : "none";
  });
}

function setupBurgerMainSections() {
  const menu = getById("burgerMenu");
  if (!menu || menu.dataset.ready === "true") return;
  menu.dataset.originalHtml = menu.innerHTML;

  const nodes = Array.from(menu.childNodes);
  const fragment = document.createDocumentFragment();
  let currentBody = null;
  let sectionIndex = 0;

  nodes.forEach(node => {
    if (node.nodeType === Node.TEXT_NODE && node.textContent.trim() === "") return;
    if (node.nodeName === "BR" || node.nodeName === "HR") return;

    if (node.nodeType === Node.ELEMENT_NODE && node.classList.contains("podstranka")) {
      Array.from(node.children).forEach(child => {
        if (child.nodeName === "A") fragment.appendChild(child);
      });
      currentBody = null;
      return;
    }

    if (node.nodeName === "H3") {
      const toggle = document.createElement("h3");
      toggle.className = "nadp burger-main-toggle";
      toggle.textContent = node.textContent.trim();

      const sectionBody = document.createElement("div");
      sectionBody.className = "burger-main-section";
      sectionBody.id = `burger-main-section-${sectionIndex++}`;
      currentBody = sectionBody;

      toggle.addEventListener("click", () => {
        const opening = sectionBody.style.display !== "block";
        toggle.classList.toggle("burger-main-active", opening);
        toggle.setAttribute("aria-expanded", String(opening));
        sectionBody.style.display = opening ? "block" : "none";
        saveNavigationState(sectionBody.id, opening);
      });

      fragment.appendChild(toggle);
      fragment.appendChild(sectionBody);
      return;
    }

    if (currentBody) {
      currentBody.appendChild(node);
    } else {
      fragment.appendChild(node);
    }
  });

  menu.textContent = "";
  menu.appendChild(fragment);
  menu.querySelectorAll(".burger-main-toggle").forEach(toggle => {
    const sectionBody = toggle.nextElementSibling;
    if (sectionBody?.id) configureMenuToggle(toggle, sectionBody.id);
  });
  initializeSubmenuControls(menu);
  restoreNavigationState(menu);
  setupNavigationScrollPersistence(menu);
  menu.dataset.ready = "true";
}

function createPageAnchor(heading, index) {
  if (heading.id) return heading.id;

  const base = heading.textContent
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "") || `section-${index + 1}`;
  let id = base;
  let suffix = 2;

  while (document.getElementById(id)) {
    id = `${base}-${suffix}`;
    suffix += 1;
  }

  heading.id = id;
  return id;
}

function setupPageContentsNavigation() {
  if (getById("pageContents")) return;

  const headings = Array.from(document.querySelectorAll(
    "body .container .oof-warning3 > h1, body .container > h1"
  )).filter(heading => !heading.closest("#header, #footer"));

  if (headings.length < 2) return;

  const aside = document.createElement("aside");
  aside.id = "pageContents";
  aside.className = "page-contents";
  aside.setAttribute("aria-label", "On this page");

  const title = document.createElement("h2");
  title.textContent = "On this page";
  aside.appendChild(title);

  const navigation = document.createElement("nav");
  headings.forEach((heading, index) => {
    const link = document.createElement("a");
    link.href = `#${createPageAnchor(heading, index)}`;
    link.textContent = heading.textContent.trim();
    navigation.appendChild(link);
  });

  aside.appendChild(navigation);
  document.body.appendChild(aside);
}

function toggleSiteSearch() {
  const panel = getById("siteSearchPanel");
  const input = getById("siteSearchInput");
  if (!panel) return;

  const shouldOpen = !isOpen(panel);
  panel.style.display = shouldOpen ? "block" : "none";

  if (shouldOpen && input) {
    closeMegaMenu();
    loadSiteSearchIndex();
    setTimeout(() => input.focus(), 0);
  }
}

function closeSiteSearch() {
  setDisplay(getById("siteSearchPanel"), "none");
}

async function loadSiteSearchIndex(resultsId = "siteSearchResults") {
  if (siteSearchIndex || siteSearchLoading) return;

  siteSearchLoading = true;
  renderSearchStatus("Loading search...", resultsId);

  try {
    const response = await fetch(withSiteRoot("search-index.json"), { cache: "no-store" });
    if (!response.ok) throw new Error("Search index not found");
    siteSearchIndex = await response.json();
    renderSearchStatus("Type to search.", resultsId);
  } catch (error) {
    renderSearchStatus("Search index is not available.", resultsId);
  } finally {
    siteSearchLoading = false;
  }
}

function runSiteSearch(query, resultsId = "siteSearchResults") {
  const results = getById(resultsId);
  if (!results) return;

  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (words.join("").length < 2) {
    renderSearchStatus("Type at least 2 characters.", resultsId);
    return;
  }

  if (!siteSearchIndex) {
    loadSiteSearchIndex(resultsId).then(() => runSiteSearch(query, resultsId));
    return;
  }

  const matches = siteSearchIndex
    .map(page => ({ page, score: getSearchScore(page, words) }))
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score || a.page.title.localeCompare(b.page.title))
    .slice(0, 12);

  if (matches.length === 0) {
    renderSearchStatus("No results found.", resultsId);
    return;
  }

  results.innerHTML = matches.map(({ page }) => {
    const title = highlightSearchTerms(page.title || page.url, words);
    const excerpt = highlightSearchTerms(makeSearchExcerpt(page.text || "", words), words);
    return `<a class="site-search-result" href="${withSiteRoot(page.url)}"><b>${title}</b><span>${excerpt}</span></a>`;
  }).join("");
}

function getSearchScore(page, words) {
  const title = (page.title || "").toLowerCase();
  const text = (page.text || "").toLowerCase();

  return words.reduce((score, word) => {
    if (title.includes(word)) score += 10;
    if (text.includes(word)) score += 1;
    return score;
  }, 0);
}

function renderSearchStatus(message, resultsId = "siteSearchResults") {
  const results = getById(resultsId);
  if (results) results.innerHTML = `<p class="site-search-status">${escapeHtml(message)}</p>`;
}

function makeSearchExcerpt(text, words) {
  const normalized = text.replace(/\s+/g, " ").trim();
  const lower = normalized.toLowerCase();
  const foundAt = words
    .map(word => lower.indexOf(word))
    .filter(index => index >= 0)
    .sort((a, b) => a - b)[0];
  const start = Math.max(0, (foundAt || 0) - 55);
  const excerpt = normalized.slice(start, start + 150);
  return (start > 0 ? "..." : "") + excerpt + (start + 150 < normalized.length ? "..." : "");
}

function highlightSearchTerms(value, words) {
  let highlighted = escapeHtml(value);
  const uniqueWords = Array.from(new Set(words.filter(word => word.length > 1)))
    .sort((a, b) => b.length - a.length);

  uniqueWords.forEach(word => {
    const safeWord = word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    highlighted = highlighted.replace(new RegExp(`(${safeWord})`, "gi"), '<mark class="site-search-highlight">$1</mark>');
  });

  return highlighted;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

document.addEventListener("click", event => {
  const burger = document.querySelector(".burger");
  const burgerMenu = getById("burgerMenu");
  const megaNav = document.querySelector(".desktop-mega-nav");
  const megaMenu = getById("megaMenu");
  const searchPanel = getById("siteSearchPanel");

  if (burgerMenu && burger && !burgerMenu.contains(event.target) && !burger.contains(event.target)) {
    setDisplay(burgerMenu, "none");
  }

  if (megaMenu && megaNav && !megaNav.contains(event.target)) {
    setDisplay(megaMenu, "none");
  }

  if (searchPanel && megaNav && !searchPanel.contains(event.target) && !event.target.closest(".site-search-toggle")) {
    setDisplay(searchPanel, "none");
  }
});

function initializeHeaderNavigation() {
  normalizePageLinks();
  buildMegaMenu();
  setupBurgerMainSections();
  setupPageContentsNavigation();
  document.body.classList.add("oof-sidebar-layout");
}

function watchHeaderNavigation() {
  const headerRoot = getById("header");
  if (!headerRoot || headerRoot.dataset.navigationWatcher === "true") return;

  headerRoot.dataset.navigationWatcher = "true";

  if (headerRoot.querySelector("header")) {
    initializeHeaderNavigation();
    return;
  }

  const observer = new MutationObserver(() => {
    if (!headerRoot.querySelector("header")) return;
    initializeHeaderNavigation();
    observer.disconnect();
  });

  observer.observe(headerRoot, { childList: true });
}

watchHeaderNavigation();
document.addEventListener("DOMContentLoaded", watchHeaderNavigation);
loadCloudflareAnalytics();

// LaRA is an optional assistant layer. Canonical page content remains untouched.
function loadLaRA() {
  if (document.querySelector('script[data-lara-widget]')) return;
  const stylesheet = document.createElement("link");
  stylesheet.rel = "stylesheet";
  stylesheet.href = "/assets/lara/lara.css?v=20260928-4";
  document.head.appendChild(stylesheet);
  const widget = document.createElement("script");
  widget.src = "/assets/lara/lara.js?v=20260928-4";
  widget.defer = true;
  widget.dataset.laraWidget = "true";
  document.body.appendChild(widget);
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", loadLaRA, { once: true });
else loadLaRA();
