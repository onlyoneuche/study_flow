/* Cache only the public offline page. Never cache API responses or user data. */
const CACHE = "studyflow-offline-v1";
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.add("/offline.html")));
});
self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((key) => key.startsWith("studyflow-offline-") && key !== CACHE).map((key) => caches.delete(key)),
  )).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate" || event.request.method !== "GET") return;
  event.respondWith(fetch(event.request).catch(async () => {
    return await caches.match("/offline.html") || Response.error();
  }));
});
