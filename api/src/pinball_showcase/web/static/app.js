/* Registers the service worker that makes the site installable and keeps recently
   viewed pages and photos available offline. */
(function () {
  "use strict";
  if (!("serviceWorker" in navigator) || location.protocol !== "https:" && location.hostname !== "localhost" && location.hostname !== "127.0.0.1") {
    return;
  }
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {
      /* Offline support is a bonus; the site works the same without it. */
    });
  });
})();
