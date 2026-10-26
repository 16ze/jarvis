// sw.js — service worker minimal d'Ada.
// But : rendre la web-app INSTALLABLE (critère Chrome : un handler fetch présent),
// SANS cache agressif qui servirait une version périmée du code. On laisse donc
// toutes les requêtes passer au réseau (comportement par défaut du navigateur).
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => { /* réseau par défaut — pas d'interception */ });
