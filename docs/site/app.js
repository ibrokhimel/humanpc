/* humanpc docs app: builds pages from embedded Markdown, wires nav/search/
 * theme/scroll-spy/copy, and highlights code. No external dependencies. */
(function () {
  "use strict";

  var content = document.getElementById("content");
  var nav = document.getElementById("nav");
  var pages = [];        // { id, title, file, headings, el, navPage, navSections }
  var fileToId = {};     // "PYTHON_API.md" -> "python-api"

  // ---- 1. Parse embedded markdown + render pages ----
  var blocks = document.querySelectorAll('script[type="text/markdown"]');
  blocks.forEach(function (b) { fileToId[b.dataset.file] = b.dataset.id; });

  blocks.forEach(function (b) {
    var pid = b.dataset.id;
    var out = window.renderMarkdown(b.textContent.replace(/^\n/, ""));
    var section = document.createElement("section");
    section.className = "page";
    section.id = "page-" + pid;
    section.innerHTML = out.html;
    // Scope heading ids per page (headings repeat across pages) and point the
    // in-content anchor pilcrows at the router's "#page@slug" form.
    section.querySelectorAll("[id]").forEach(function (el) { el.id = pid + "--" + el.id; });
    section.querySelectorAll("a.anchor").forEach(function (a) {
      a.setAttribute("href", "#" + pid + "@" + a.getAttribute("href").slice(1));
    });
    content.appendChild(section);
    pages.push({
      id: pid, title: b.dataset.title, file: b.dataset.file,
      headings: out.headings, el: section,
    });
  });

  // ---- 2. Rewrite cross-doc links (foo.md -> #page) & scope heading ids ----
  content.querySelectorAll("a[href]").forEach(function (a) {
    var href = a.getAttribute("href");
    if (/^(https?:|mailto:|#)/.test(href)) return;      // external / in-page anchor
    var base = href.split("#")[0];
    if (fileToId[base]) {                                // another site page
      a.setAttribute("href", "#" + fileToId[base]);
      return;
    }
    // A repo file not bundled in the site (e.g. the design docs). The site
    // lives at docs/site/, so resolve such links against the repo root.
    a.setAttribute("href", "../../" + href);
    a.setAttribute("target", "_blank");
    a.setAttribute("rel", "noopener");
  });

  // ---- 3. Build sidebar ----
  pages.forEach(function (p) {
    var group = document.createElement("div");
    group.className = "nav-group";

    var pageLink = document.createElement("a");
    pageLink.className = "nav-page";
    pageLink.href = "#" + p.id;
    pageLink.textContent = p.title;
    group.appendChild(pageLink);

    var secWrap = document.createElement("div");
    secWrap.className = "nav-sections hidden";
    p.headings.filter(function (h) { return h.level >= 2; }).forEach(function (h) {
      var s = document.createElement("a");
      s.className = "nav-sec lvl" + h.level;
      s.href = "#" + p.id + "@" + h.slug;
      s.textContent = h.text;
      s.dataset.target = p.id + "--" + h.slug;
      secWrap.appendChild(s);
    });
    group.appendChild(secWrap);
    nav.appendChild(group);

    p.navPage = pageLink;
    p.navSections = secWrap;
  });

  // ---- 4. Syntax highlighting ----
  var KEYWORDS = {
    python: /\b(import|from|as|def|class|return|if|elif|else|for|while|in|with|try|except|finally|raise|lambda|and|or|not|is|None|True|False|pass|break|continue|yield|global|await|async)\b/,
    bash: /\b(cd|pip|python|humanpc|git|npx|npm|echo|export|sudo|install)\b/,
    yaml: null, json: null, text: null,
  };
  function highlight(code, lang) {
    var kw = KEYWORDS[lang];
    var re = /(#[^\n]*)|('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][\w]*)|(\s+)|([^\sA-Za-z0-9_])/g;
    var out = "", m;
    function e(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
    while ((m = re.exec(code))) {
      if (m[1]) out += '<span class="tok-c">' + e(m[1]) + "</span>";
      else if (m[2]) out += '<span class="tok-s">' + e(m[2]) + "</span>";
      else if (m[3]) out += '<span class="tok-n">' + e(m[3]) + "</span>";
      else if (m[4]) {
        var next = code[re.lastIndex];
        if (kw && kw.test(m[4])) out += '<span class="tok-k">' + m[4] + "</span>";
        else if (next === "(") out += '<span class="tok-f">' + m[4] + "</span>";
        else if (lang === "yaml" && next === ":") out += '<span class="tok-key">' + m[4] + "</span>";
        else out += e(m[4]);
      }
      else if (m[5]) out += m[5];
      else out += e(m[6]);
    }
    return out;
  }
  content.querySelectorAll("pre code").forEach(function (el) {
    var cls = (el.className.match(/language-(\w+)/) || [])[1] || "text";
    el.innerHTML = highlight(el.textContent, cls);
  });

  // ---- 5. Copy buttons ----
  content.addEventListener("click", function (e) {
    var btn = e.target.closest(".copy");
    if (!btn) return;
    var code = btn.closest(".code").querySelector("code");
    navigator.clipboard.writeText(code.textContent).then(function () {
      btn.textContent = "Copied!"; btn.classList.add("done");
      setTimeout(function () { btn.textContent = "Copy"; btn.classList.remove("done"); }, 1400);
    });
  });

  // ---- 6. Routing (hash: #page  or  #page@section) ----
  function parseHash() {
    var raw = decodeURIComponent(location.hash.replace(/^#/, ""));
    var at = raw.indexOf("@");
    if (at !== -1) return { page: raw.slice(0, at), slug: raw.slice(at + 1) };
    return { page: raw, slug: "" };
  }
  function pageById(id) {
    for (var i = 0; i < pages.length; i++) if (pages[i].id === id) return pages[i];
    return null;
  }
  function showPage(id, slug) {
    var target = pageById(id) || pages[0];
    if (!target) return;
    pages.forEach(function (p) {
      var on = p === target;
      p.el.classList.toggle("active", on);
      p.navPage.classList.toggle("active", on);
      p.navSections.classList.toggle("hidden", !on);
    });
    document.body.classList.remove("nav-open");
    if (slug) {
      var h = document.getElementById(target.id + "--" + slug);
      if (h) { h.scrollIntoView(); updateSpy(); return; }
    }
    content.scrollTop = 0;
    window.scrollTo(0, 0);
    content.focus({ preventScroll: true });
    updateSpy();
  }
  function route() {
    var h = parseHash();
    showPage(h.page || (pages[0] && pages[0].id), h.slug);
  }
  window.addEventListener("hashchange", route);

  // ---- 7. Scroll-spy (highlight the active section in the sidebar) ----
  var spyTimer = null;
  function updateSpy() {
    var active = pages.filter(function (p) { return p.el.classList.contains("active"); })[0];
    if (!active) return;
    var heads = active.el.querySelectorAll("h2, h3");
    var top = 90, current = null;
    heads.forEach(function (hd) { if (hd.getBoundingClientRect().top <= top) current = hd.id; });
    active.navSections.querySelectorAll(".nav-sec").forEach(function (s) {
      s.classList.toggle("active", s.dataset.target === current);
    });
  }
  window.addEventListener("scroll", function () {
    if (spyTimer) return;
    spyTimer = setTimeout(function () { spyTimer = null; updateSpy(); }, 80);
  }, { passive: true });

  // ---- 8. Search (filters sidebar entries) ----
  var search = document.getElementById("search");
  search.addEventListener("input", function () {
    var q = search.value.trim().toLowerCase();
    pages.forEach(function (p) {
      var pageHit = p.title.toLowerCase().indexOf(q) !== -1;
      var anySec = false;
      p.navSections.querySelectorAll(".nav-sec").forEach(function (s) {
        var hit = !q || s.textContent.toLowerCase().indexOf(q) !== -1;
        s.style.display = hit ? "" : "none";
        if (hit) anySec = true;
      });
      if (q) p.navSections.classList.remove("hidden");
      else p.navSections.classList.toggle("hidden", !p.navPage.classList.contains("active"));
      p.navPage.parentElement.style.display = (!q || pageHit || anySec) ? "" : "none";
    });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement !== search) { e.preventDefault(); search.focus(); }
    if (e.key === "Escape" && document.activeElement === search) { search.value = ""; search.dispatchEvent(new Event("input")); search.blur(); }
  });

  // ---- 9. Theme toggle ----
  var themeBtn = document.getElementById("theme");
  var KEY = "humanpc-docs-theme";
  var saved = localStorage.getItem(KEY);
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  else if (window.matchMedia && !window.matchMedia("(prefers-color-scheme: dark)").matches)
    document.documentElement.setAttribute("data-theme", "light");
  function syncThemeIcon() { themeBtn.textContent = document.documentElement.getAttribute("data-theme") === "dark" ? "☼" : "☽"; }
  syncThemeIcon();
  themeBtn.addEventListener("click", function () {
    var now = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", now);
    localStorage.setItem(KEY, now); syncThemeIcon();
  });

  // ---- 10. Mobile menu ----
  document.getElementById("menu").addEventListener("click", function () { document.body.classList.toggle("nav-open"); });
  document.getElementById("overlay").addEventListener("click", function () { document.body.classList.remove("nav-open"); });

  // ---- Go ----
  route();
})();
