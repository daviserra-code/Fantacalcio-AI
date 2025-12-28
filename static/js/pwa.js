// PWA Registration and Management
(function() {
    'use strict';

    // Register service worker
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/static/sw.js')
                .then(registration => {
                    console.log('[PWA] Service Worker registered:', registration.scope);
                    
                    // Check for updates
                    registration.addEventListener('updatefound', () => {
                        const newWorker = registration.installing;
                        newWorker.addEventListener('statechange', () => {
                            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                                showUpdateNotification();
                            }
                        });
                    });
                })
                .catch(error => {
                    console.error('[PWA] Service Worker registration failed:', error);
                });
        });
    }

    // Install prompt
    let deferredPrompt;
    window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault();
        deferredPrompt = e;
        showInstallButton();
    });

    function showInstallButton() {
        const installBtn = document.getElementById('pwa-install-btn');
        if (installBtn) {
            installBtn.style.display = 'block';
            installBtn.addEventListener('click', async () => {
                if (deferredPrompt) {
                    deferredPrompt.prompt();
                    const { outcome } = await deferredPrompt.userChoice;
                    console.log('[PWA] Install prompt outcome:', outcome);
                    deferredPrompt = null;
                    installBtn.style.display = 'none';
                }
            });
        }
    }

    function showUpdateNotification() {
        if (confirm('Nuova versione disponibile! Vuoi aggiornare?')) {
            window.location.reload();
        }
    }

    // Check if app is installed
    window.addEventListener('appinstalled', () => {
        console.log('[PWA] App installed successfully');
        // Track installation analytics
        if (typeof gtag !== 'undefined') {
            gtag('event', 'pwa_install', {
                'event_category': 'engagement',
                'event_label': 'PWA Installation'
            });
        }
    });

    // Detect if running as PWA
    function isStandalone() {
        return (window.matchMedia('(display-mode: standalone)').matches) || 
               (window.navigator.standalone) || 
               document.referrer.includes('android-app://');
    }

    if (isStandalone()) {
        document.body.classList.add('pwa-mode');
        console.log('[PWA] Running in standalone mode');
    }

    // Handle online/offline status
    window.addEventListener('online', () => {
        showConnectionStatus('online');
        syncOfflineData();
    });

    window.addEventListener('offline', () => {
        showConnectionStatus('offline');
    });

    function showConnectionStatus(status) {
        const statusBar = document.getElementById('connection-status');
        if (statusBar) {
            statusBar.className = `connection-status ${status}`;
            statusBar.textContent = status === 'online' ? 
                '✓ Connesso' : '⚠ Modalità offline';
            statusBar.style.display = 'block';
            
            setTimeout(() => {
                statusBar.style.display = 'none';
            }, 3000);
        }
    }

    async function syncOfflineData() {
        if ('serviceWorker' in navigator && 'sync' in ServiceWorkerRegistration.prototype) {
            try {
                const registration = await navigator.serviceWorker.ready;
                await registration.sync.register('sync-chat-messages');
                console.log('[PWA] Background sync registered');
            } catch (error) {
                console.error('[PWA] Background sync failed:', error);
            }
        }
    }

    // Request notification permission
    async function requestNotificationPermission() {
        if ('Notification' in window && Notification.permission === 'default') {
            const permission = await Notification.requestPermission();
            console.log('[PWA] Notification permission:', permission);
            return permission === 'granted';
        }
        return Notification.permission === 'granted';
    }

    // Expose PWA utilities globally
    window.FantaCalcioPWA = {
        isInstalled: isStandalone,
        requestNotifications: requestNotificationPermission,
        sync: syncOfflineData
    };

})();
