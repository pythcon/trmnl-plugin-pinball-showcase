/* Header type-ahead: live results from /api/v1/search with art previews.
   Without JavaScript the form still submits to /search. Follows the WAI-ARIA combobox
   pattern: arrows move, Enter opens, Escape closes (twice clears), "/" focuses. */
(function () {
  "use strict";

  var form = document.querySelector("[data-search]");
  if (!form) return;
  var input = form.querySelector("input[name=q]");
  var panel = form.querySelector(".search-panel");
  var status = form.querySelector("[data-search-status]");

  var DEBOUNCE_MS = 120;
  var LIMIT = 8;
  var cache = new Map();
  var timer = null;
  var inflight = null;
  var options = [];
  var active = -1;
  var lastQuery = "";
  var shownQuery = null; // the query the visible options belong to

  // Options on screen only count if they match what's in the box right now; otherwise
  // a quick Enter after typing could open a result for the previous text.
  function fresh() {
    return shownQuery !== null && shownQuery === input.value.trim();
  }

  function normalize(text) {
    return text
      .normalize("NFKD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/&/g, " and ")
      .replace(/[^0-9a-z]+/g, " ")
      .trim();
  }

  // Name with the parts that matched the query in <mark>, built as DOM nodes.
  function highlighted(name, query) {
    var tokens = normalize(query).split(" ").filter(Boolean);
    var fragment = document.createDocumentFragment();
    name.split(/(\s+)/).forEach(function (part) {
      var plain = normalize(part);
      var hit = tokens.find(function (t) { return plain && plain.indexOf(t) === 0; });
      if (!hit) {
        fragment.appendChild(document.createTextNode(part));
        return;
      }
      // Map the matched length back onto the original characters (accents, punctuation).
      var end = 0;
      var seen = 0;
      while (end < part.length && seen < hit.length) {
        if (normalize(part[end])) seen += normalize(part[end]).length;
        end++;
      }
      var mark = document.createElement("mark");
      mark.textContent = part.slice(0, end);
      fragment.appendChild(mark);
      fragment.appendChild(document.createTextNode(part.slice(end)));
    });
    return fragment;
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function open() {
    panel.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function close() {
    panel.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    setActive(-1);
  }

  function setActive(index) {
    options.forEach(function (option, i) {
      option.setAttribute("aria-selected", i === index ? "true" : "false");
    });
    active = index;
    if (index >= 0 && options[index]) {
      input.setAttribute("aria-activedescendant", options[index].id);
      options[index].scrollIntoView({ block: "nearest" });
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function render(query, results) {
    panel.replaceChildren();
    options = [];
    active = -1;
    shownQuery = query;

    if (!results.length) {
      var empty = el("div", "search-empty");
      empty.appendChild(el("strong", null, "No machines match “" + query + "”"));
      empty.appendChild(el("span", null, "Try fewer words, or the start of a name."));
      panel.appendChild(empty);
      status.textContent = "No results";
      open();
      return;
    }

    results.forEach(function (r, i) {
      var option = el("a", "search-option");
      option.id = "search-option-" + i;
      option.href = r.url;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", "false");
      option.tabIndex = -1;

      var art = el("span", "search-art");
      if (r.image) {
        var img = el("img");
        img.src = r.image;
        img.alt = "";
        img.loading = "lazy";
        img.decoding = "async";
        art.appendChild(img);
      }
      option.appendChild(art);

      var text = el("span", "search-text");
      var name = el("span", "search-name");
      var title = el("span", "search-title-text");
      title.appendChild(highlighted(r.name, query));
      name.appendChild(title);
      if (r.edition_label) name.appendChild(el("span", "search-badge", r.edition_label));
      text.appendChild(name);
      var meta = [r.manufacturer || "Unknown maker"];
      if (r.year) meta.push(String(r.year));
      if (r.edition_count > 1) meta.push(r.edition_count + " editions");
      text.appendChild(el("span", "search-meta", meta.join(" · ")));
      if (r.image_borrowed) text.appendChild(el("span", "search-note", "Photo of another edition"));
      option.appendChild(text);

      option.addEventListener("mousemove", function () { if (active !== i) setActive(i); });
      panel.appendChild(option);
      options.push(option);
    });

    var all = el("a", "search-all", "See all results for “" + query + "”");
    all.href = "/search?q=" + encodeURIComponent(query);
    panel.appendChild(all);

    status.textContent = results.length + (results.length === 1 ? " result" : " results");
    open();
  }

  function fetchResults(query) {
    if (cache.has(query)) {
      render(query, cache.get(query));
      return;
    }
    if (inflight) inflight.abort();
    inflight = new AbortController();
    form.setAttribute("aria-busy", "true");
    fetch("/api/v1/search?limit=" + LIMIT + "&q=" + encodeURIComponent(query), {
      signal: inflight.signal,
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (!response.ok) throw new Error("search failed: " + response.status);
        return response.json();
      })
      .then(function (body) {
        cache.set(query, body.results);
        if (cache.size > 100) cache.delete(cache.keys().next().value);
        // Only draw if this is still what the box says.
        if (input.value.trim() === query) render(query, body.results);
      })
      .catch(function (error) {
        if (error.name === "AbortError") return;
        panel.replaceChildren(el("div", "search-empty", "Search is unavailable right now."));
        open();
      })
      .finally(function () { form.removeAttribute("aria-busy"); });
  }

  function onInput() {
    var query = input.value.trim();
    clearTimeout(timer);
    if (!fresh()) setActive(-1);
    if (query === lastQuery && !panel.hidden) return;
    lastQuery = query;
    if (!query) {
      if (inflight) inflight.abort();
      close();
      shownQuery = null;
      panel.replaceChildren();
      return;
    }
    timer = setTimeout(function () { fetchResults(query); }, DEBOUNCE_MS);
  }

  input.addEventListener("input", onInput);

  input.addEventListener("focus", function () {
    if (input.value.trim() && panel.childElementCount) open();
  });

  input.addEventListener("keydown", function (event) {
    var count = fresh() ? options.length : 0;
    switch (event.key) {
      case "ArrowDown":
        if (panel.hidden && input.value.trim()) { onInput(); open(); }
        if (count) { setActive((active + 1) % count); event.preventDefault(); }
        break;
      case "ArrowUp":
        if (count) { setActive(active <= 0 ? count - 1 : active - 1); event.preventDefault(); }
        break;
      case "Enter":
        if (fresh() && active >= 0 && options[active]) {
          event.preventDefault();
          window.location.href = options[active].href;
        }
        // Otherwise the form submits to the full /search page.
        break;
      case "Escape":
        if (!panel.hidden) close();
        else { input.value = ""; lastQuery = ""; shownQuery = null; panel.replaceChildren(); }
        event.preventDefault();
        break;
      case "Tab":
        close();
        break;
    }
  });

  // "/" anywhere focuses the search, unless you're already typing somewhere.
  document.addEventListener("keydown", function (event) {
    if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
    var target = event.target;
    var typing = target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
    if (typing) return;
    event.preventDefault();
    input.focus();
    input.select();
  });

  document.addEventListener("pointerdown", function (event) {
    if (!form.contains(event.target)) close();
  });

  // Coming back via the browser's back button: don't leave a stale panel open.
  window.addEventListener("pageshow", function () { close(); });
})();
