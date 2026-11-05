
// DEBA PORTFÖY - Telefon bildirimleri

self.addEventListener('push', function(event) {
    let data = {};

    if (event.data) {
        try {
            data = event.data.json();
        } catch (error) {
            data = {
                body: event.data.text()
            };
        }
    }

    const title = data.title || 'DEBA PORTFÖY';

    const options = {
        body: data.body || 'Yeni bir bildiriminiz var.',
        icon: '/static/Bordo%20Zeminli%20Modern%20Gayrimenkul%20Logosu.png',
        badge: '/static/Bordo%20Zeminli%20Modern%20Gayrimenkul%20Logosu.png',
        data: {
            url: data.url || '/'
        }
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

// Bildirime dokunulduğunda uygulamayı aç
self.addEventListener('notificationclick', function(event) {
    event.notification.close();

    const targetUrl = new URL(
        event.notification.data?.url || '/',
        self.location.origin
    );

    if (targetUrl.origin !== self.location.origin) {
        return;
    }

    event.waitUntil(
        clients.openWindow(targetUrl.href)
    );
});
