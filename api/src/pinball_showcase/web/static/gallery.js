/* Machine photo gallery.

   On the page: a scroll-snap carousel (swipe on touch, arrows and ←/→ on desktop) with a
   counter, a live caption and a thumbnail rail that follows along.
   Full screen: a <dialog> viewer with swipe, keyboard, tap or double-click to zoom,
   neighbour preloading and a thumbnail rail; the browser's Back button closes it.
   Without JavaScript the carousel still scrolls and photos link to their full files. */
(function () {
  "use strict";

  var root = document.querySelector("[data-gallery]");
  if (!root) return;

  var track = root.querySelector(".gallery-track");
  var slides = Array.prototype.slice.call(root.querySelectorAll(".gallery-slide"));
  var thumbs = Array.prototype.slice.call(root.querySelectorAll(".gallery-thumb"));
  var thumbRail = root.querySelector(".gallery-thumbs");
  var prevButton = root.querySelector(".gallery-prev");
  var nextButton = root.querySelector(".gallery-next");
  var expandButton = root.querySelector(".gallery-expand");
  var indexOut = root.querySelector("[data-gallery-index]");
  var labelOut = root.querySelector("[data-gallery-label]");
  var editionOut = root.querySelector("[data-gallery-edition]");
  var noteOut = root.querySelector("[data-gallery-note]");
  var title = root.getAttribute("data-title") || "";
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var photos = slides.map(function (slide, i) {
    var thumbImg = thumbs[i] ? thumbs[i].querySelector("img") : slide.querySelector("img");
    return {
      full: slide.getAttribute("data-full"),
      label: slide.getAttribute("data-label") || "Photo",
      edition: slide.getAttribute("data-edition"),
      other: slide.hasAttribute("data-other"),
      thumb: thumbImg.getAttribute("src"),
    };
  });
  var count = photos.length;
  var current = 0;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function icon(path) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    var p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", path);
    svg.appendChild(p);
    return svg;
  }

  function clamp(i) {
    return Math.max(0, Math.min(count - 1, i));
  }

  function captionText(photo) {
    return photo.label + (photo.edition ? " · " + photo.edition : "");
  }

  /* ---- Carousel on the page --------------------------------------------------------- */

  function updateCarousel(index) {
    current = index;
    var photo = photos[index];
    if (indexOut) indexOut.textContent = String(index + 1);
    if (labelOut) labelOut.textContent = photo.label;
    if (editionOut) {
      editionOut.textContent = photo.edition || "";
      editionOut.hidden = !photo.edition;
    }
    if (noteOut) {
      var shownEdition = root.getAttribute("data-edition");
      var borrowed = photo.other && shownEdition;
      noteOut.hidden = !borrowed;
      noteOut.textContent = borrowed
        ? "Photo of the " + (photo.edition || "another") + " edition. OPDB has no photos of the " + shownEdition + " yet."
        : "";
    }
    if (prevButton) prevButton.disabled = index === 0;
    if (nextButton) nextButton.disabled = index === count - 1;
    thumbs.forEach(function (thumb, i) {
      if (i === index) thumb.setAttribute("aria-current", "true");
      else thumb.removeAttribute("aria-current");
    });
    // Keep the active thumbnail in view by scrolling the rail only, never the page.
    var active = thumbs[index];
    if (active && thumbRail) {
      var left = active.offsetLeft - (thumbRail.clientWidth - active.offsetWidth) / 2;
      thumbRail.scrollTo({ left: Math.max(0, left), behavior: reducedMotion ? "auto" : "smooth" });
    }
  }

  function goTo(index, smooth) {
    index = clamp(index);
    track.scrollTo({
      left: slides[index].offsetLeft - track.offsetLeft,
      behavior: smooth === false || reducedMotion ? "auto" : "smooth",
    });
    updateCarousel(index);
  }

  // Which slide is showing, from the scroll position (works for swipes, wheels, keys).
  var scrollTimer = null;
  track.addEventListener("scroll", function () {
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(function () {
      var index = clamp(Math.round(track.scrollLeft / Math.max(1, track.clientWidth)));
      if (index !== current) updateCarousel(index);
    }, 60);
  }, { passive: true });

  if (count > 1) {
    prevButton.hidden = false;
    nextButton.hidden = false;
    prevButton.addEventListener("click", function () { goTo(current - 1); });
    nextButton.addEventListener("click", function () { goTo(current + 1); });
  }

  track.addEventListener("keydown", function (event) {
    if (event.key === "ArrowLeft") { goTo(current - 1); event.preventDefault(); }
    else if (event.key === "ArrowRight") { goTo(current + 1); event.preventDefault(); }
    else if (event.key === "Enter") { openViewer(current); event.preventDefault(); }
  });

  thumbs.forEach(function (thumb, i) {
    thumb.addEventListener("click", function (event) {
      event.preventDefault();
      goTo(i);
    });
  });

  slides.forEach(function (slide, i) {
    slide.querySelector(".gallery-open").addEventListener("click", function (event) {
      event.preventDefault();
      openViewer(i);
    });
  });

  expandButton.hidden = false;
  expandButton.addEventListener("click", function () { openViewer(current); });

  document.querySelectorAll("[data-gallery-open]").forEach(function (link) {
    link.addEventListener("click", function (event) {
      event.preventDefault();
      openViewer(current);
    });
  });

  // Re-align after a resize or rotation so a half-scrolled slide doesn't stick.
  var resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { goTo(current, false); }, 120);
  });

  /* ---- Full-screen viewer ------------------------------------------------------------ */

  var viewer = null;
  var viewerIndex = 0;
  var opener = null;
  var pushedState = false;
  var parts = {};

  function buildViewer() {
    viewer = el("dialog", "viewer");
    viewer.setAttribute("aria-label", title + " photos");

    var bar = el("div", "viewer-bar");
    parts.count = el("span", "viewer-count");
    parts.caption = el("span", "viewer-caption");
    parts.original = el("a", "viewer-action", "Original");
    parts.original.target = "_blank";
    parts.original.rel = "noopener";
    parts.close = el("button", "viewer-action viewer-close");
    parts.close.type = "button";
    parts.close.setAttribute("aria-label", "Close");
    parts.close.appendChild(icon("M6 6l12 12M18 6L6 18"));
    var text = el("div", "viewer-text");
    text.appendChild(parts.count);
    text.appendChild(parts.caption);
    bar.appendChild(text);
    bar.appendChild(parts.original);
    bar.appendChild(parts.close);

    parts.stage = el("div", "viewer-stage");
    parts.image = el("img", "viewer-image");
    parts.image.alt = "";
    parts.image.draggable = false;
    parts.spinner = el("span", "viewer-spinner");
    parts.spinner.setAttribute("aria-hidden", "true");
    parts.stage.appendChild(parts.spinner);
    parts.stage.appendChild(parts.image);

    parts.prev = el("button", "viewer-nav viewer-prev");
    parts.prev.type = "button";
    parts.prev.setAttribute("aria-label", "Previous photo");
    parts.prev.appendChild(icon("M15 5l-7 7 7 7"));
    parts.next = el("button", "viewer-nav viewer-next");
    parts.next.type = "button";
    parts.next.setAttribute("aria-label", "Next photo");
    parts.next.appendChild(icon("M9 5l7 7-7 7"));

    parts.rail = el("div", "viewer-rail");
    parts.railItems = photos.map(function (photo, i) {
      var b = el("button", "viewer-thumb");
      b.type = "button";
      b.setAttribute("aria-label", "Photo " + (i + 1) + ": " + captionText(photo));
      var img = el("img");
      img.src = photo.thumb;
      img.alt = "";
      img.loading = "lazy";
      b.appendChild(img);
      b.addEventListener("click", function () { show(i); });
      parts.rail.appendChild(b);
      return b;
    });

    viewer.appendChild(bar);
    viewer.appendChild(parts.stage);
    if (count > 1) {
      viewer.appendChild(parts.prev);
      viewer.appendChild(parts.next);
      viewer.appendChild(parts.rail);
    }
    document.body.appendChild(viewer);

    parts.close.addEventListener("click", closeViewer);
    parts.prev.addEventListener("click", function () { show(viewerIndex - 1); });
    parts.next.addEventListener("click", function () { show(viewerIndex + 1); });
    parts.image.addEventListener("load", function () { parts.stage.classList.remove("is-loading"); });
    parts.image.addEventListener("error", function () { parts.stage.classList.remove("is-loading"); });

    // Esc (the dialog's own cancel) goes through closeViewer so history stays tidy.
    viewer.addEventListener("cancel", function (event) {
      event.preventDefault();
      closeViewer();
    });
    viewer.addEventListener("keydown", function (event) {
      if (event.key === "ArrowLeft") { show(viewerIndex - 1); event.preventDefault(); }
      else if (event.key === "ArrowRight") { show(viewerIndex + 1); event.preventDefault(); }
    });
    // Click on the dark backdrop around the photo closes; clicks on the photo zoom.
    parts.stage.addEventListener("click", function (event) {
      if (event.target === parts.stage && !parts.stage.classList.contains("is-zoomed")) closeViewer();
    });
    parts.image.addEventListener("click", toggleZoom);
    attachSwipe(parts.stage);
  }

  function toggleZoom(event) {
    var stage = parts.stage;
    var zooming = !stage.classList.contains("is-zoomed");
    if (zooming && parts.image.naturalWidth <= stage.clientWidth && parts.image.naturalHeight <= stage.clientHeight) {
      return; // already shown at full size
    }
    // Keep the point that was clicked under the pointer.
    var rect = parts.image.getBoundingClientRect();
    var fx = event && rect.width ? (event.clientX - rect.left) / rect.width : 0.5;
    var fy = event && rect.height ? (event.clientY - rect.top) / rect.height : 0.5;
    stage.classList.toggle("is-zoomed", zooming);
    if (zooming) {
      stage.scrollLeft = parts.image.naturalWidth * fx - stage.clientWidth / 2;
      stage.scrollTop = parts.image.naturalHeight * fy - stage.clientHeight / 2;
    }
  }

  function attachSwipe(area) {
    var startX = 0;
    var startY = 0;
    var tracking = false;
    area.addEventListener("pointerdown", function (event) {
      if (event.pointerType === "mouse" || area.classList.contains("is-zoomed")) return;
      tracking = true;
      startX = event.clientX;
      startY = event.clientY;
    });
    area.addEventListener("pointerup", function (event) {
      if (!tracking) return;
      tracking = false;
      var dx = event.clientX - startX;
      var dy = event.clientY - startY;
      if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.4) {
        show(viewerIndex + (dx < 0 ? 1 : -1));
      } else if (dy > 90 && Math.abs(dy) > Math.abs(dx) * 1.4) {
        closeViewer(); // swipe down to dismiss
      }
    });
    area.addEventListener("pointercancel", function () { tracking = false; });
  }

  function preload(i) {
    if (i < 0 || i >= count) return;
    var img = new Image();
    img.decoding = "async";
    img.src = photos[i].full;
  }

  function show(index) {
    index = clamp(index);
    viewerIndex = index;
    var photo = photos[index];
    parts.stage.classList.remove("is-zoomed");
    if (parts.image.getAttribute("src") !== photo.full) {
      parts.stage.classList.add("is-loading");
      parts.image.src = photo.full;
      // Already in the cache: no load event worth waiting for.
      if (parts.image.complete && parts.image.naturalWidth) parts.stage.classList.remove("is-loading");
    }
    parts.image.alt = title + " " + photo.label.toLowerCase() + (photo.edition ? ", " + photo.edition : "");
    parts.count.textContent = count > 1 ? index + 1 + " / " + count : "";
    parts.caption.textContent = captionText(photo);
    parts.original.href = photo.full;
    parts.prev.disabled = index === 0;
    parts.next.disabled = index === count - 1;
    parts.railItems.forEach(function (item, i) {
      if (i === index) {
        item.setAttribute("aria-current", "true");
        var left = item.offsetLeft - (parts.rail.clientWidth - item.offsetWidth) / 2;
        parts.rail.scrollTo({ left: Math.max(0, left), behavior: reducedMotion ? "auto" : "smooth" });
      } else {
        item.removeAttribute("aria-current");
      }
    });
    preload(index + 1);
    preload(index - 1);
  }

  function openViewer(index) {
    if (!viewer) buildViewer();
    if (viewer.open) return;
    opener = document.activeElement;
    document.documentElement.classList.add("viewer-open");
    viewer.showModal();
    show(index);
    parts.close.focus({ preventScroll: true });
    // Let the phone's Back button close the viewer instead of leaving the page.
    try {
      history.pushState({ pinballViewer: true }, "");
      pushedState = true;
    } catch (e) {
      pushedState = false;
    }
  }

  function closeViewer(fromHistory) {
    if (!viewer || !viewer.open) return;
    viewer.close();
    document.documentElement.classList.remove("viewer-open");
    goTo(viewerIndex, false); // the page shows where you left off
    if (pushedState && fromHistory !== true) {
      pushedState = false;
      history.back();
    }
    pushedState = false;
    if (opener && opener.focus) opener.focus({ preventScroll: true });
  }

  window.addEventListener("popstate", function () {
    if (viewer && viewer.open) closeViewer(true);
  });

  updateCarousel(0);
})();
