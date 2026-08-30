self.addEventListener("install", (e) => {
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(clients.claim());
});

self.addEventListener("push", (e) => {
  const data = e.data ? e.data.json() : {};
  const title = data.title || "LPR1 Monitor";
  const body = data.body || "Новое уведомление";
  const url = data.url || "/";

  e.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: "/static/icon-192.png",
      badge: "/static/icon-192.png",
      vibrate: [200, 100, 200],
      tag: "lpr1-alert",
      renotify: true,
      data: { url },
    })
  );
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = e.notification.data?.url || "/";
  e.waitUntil(
    clients.matchAll({ type: "window" }).then((list) => {
      for (const client of list) {
        if (client.url.includes(self.location.origin) && "focus" in client) {
          return client.focus();
        }
      }
      return clients.openWindow(url);
    })
  );
});
