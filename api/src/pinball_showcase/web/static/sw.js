/* Pinball Showcase service worker (served at /sw.js; __VERSION__ is filled in per deploy).

   - Pages: network first, so content is always current; falls back to the last copy
     of that page, then to /offline.
   - /static: cache first (URLs carry ?v=<version>, so a deploy brings new files).
   - OPDB photos: cache first, at most MAX_PHOTOS kept.
   - /api and anything else: straight to the network, never cached (TRMNL's data feed
     and search must always be live). */
"use strict";

var VERSION = "__VERSION__";
var SHELL = "shell-" + VERSION;
var PAGES = "pages-" + VERSION;
var PHOTOS = "photos-v1";
var MAX_PAGES = 40;
var MAX_PHOTOS = 150;
var PRECACHE = [
  "/offline",
  "/static/site.css?v=" + VERSION,
  "/static/search.js?v=" + VERSION,
  "/static/gallery.js?v=" + VERSION,
  "/static/app.js?v=" + VERSION,
  "/static/logo.svg?v=" + VERSION,
  "/static/icon-192.png?v=" + VERSION,
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(SHELL).then(function (cache) { return cache.addAll(PRECACHE); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (event) {
  var keep = [SHELL, PAGES, PHOTOS];
  event.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(names.filter(function (n) { return keep.indexOf(n) < 0; })
        .map(function (n) { return caches.delete(n); }));
    }).then(function () { return self.clients.claim(); })
  );
});

function trim(cacheName, max) {
  return caches.open(cacheName).then(function (cache) {
    return cache.keys().then(function (keys) {
      if (keys.length <= max) return;
      return Promise.all(keys.slice(0, keys.length - max).map(function (k) { return cache.delete(k); }));
    });
  });
}

function networkFirstPage(request) {
  return fetch(request).then(function (response) {
    if (response.ok && response.type === "basic") {
      var copy = response.clone();
      caches.open(PAGES).then(function (cache) {
        cache.put(request, copy).then(function () { trim(PAGES, MAX_PAGES); });
      });
    }
    return response;
  }).catch(function () {
    return caches.match(request).then(function (cached) {
      return cached || caches.match("/offline");
    });
  });
}

function cacheFirst(request, cacheName, max) {
  return caches.match(request).then(function (cached) {
    if (cached) return cached;
    return fetch(request).then(function (response) {
      // Opaque (cross-origin image) responses are fine to keep; errors are not.
      if (response.ok || response.type === "opaque") {
        var copy = response.clone();
        caches.open(cacheName).then(function (cache) {
          cache.put(request, copy).then(function () { if (max) trim(cacheName, max); });
        });
      }
      return response;
    });
  });
}

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") return;
  var url = new URL(request.url);

  if (url.origin === self.location.origin) {
    if (url.pathname.indexOf("/api/") === 0 || url.pathname === "/sw.js") return;
    if (request.mode === "navigate") {
      event.respondWith(networkFirstPage(request));
      return;
    }
    if (url.pathname.indexOf("/static/") === 0) {
      event.respondWith(cacheFirst(request, SHELL));
    }
    return;
  }
  if (url.hostname === "img.opdb.org" && request.destination === "image") {
    event.respondWith(cacheFirst(request, PHOTOS, MAX_PHOTOS));
  }
});
