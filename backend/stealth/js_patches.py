"""
Flight Finder — JavaScript Anti-Detection Patches
Injected into every browser context to defeat bot detection systems.
"""

JS_PATCHES = """
// ══════════════════════════════════════════════════════════
// Flight Finder — Stealth JavaScript Patches
// Injected via context.add_init_script() before any page load
// ══════════════════════════════════════════════════════════

// 1. Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => false });

// 2. Override chrome object (Chromium detection)
window.chrome = {
    runtime: {},
    loadTimes: function() {
        return {
            requestTime: Date.now() / 1000 - Math.random() * 10,
            startLoadTime: Date.now() / 1000 - Math.random() * 5,
            commitLoadTime: Date.now() / 1000 - Math.random() * 2,
            finishDocumentLoadTime: Date.now() / 1000 - Math.random(),
            finishLoadTime: Date.now() / 1000,
            firstPaintTime: Date.now() / 1000 - Math.random() * 3,
            firstPaintAfterLoadTime: 0,
            navigationType: 'Other',
            wasFetchedViaSpdy: false,
            wasNpnNegotiated: true,
            npnNegotiatedProtocol: 'h2',
            wasAlternateProtocolAvailable: false,
            connectionInfo: 'h2'
        };
    },
    csi: function() {
        return {
            startE: Date.now(),
            onloadT: Date.now(),
            pageT: Date.now() - Math.random() * 5000,
            tran: 15
        };
    },
    app: {
        isInstalled: false,
        InstallState: { INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
        RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
        getDetails: function() { return null; },
        getIsInstalled: function() { return false; },
    }
};

// 3. Override permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (params) =>
    params.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(params);

// 4. Override plugins (real browsers have these)
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
        ];
        plugins.length = 3;
        return plugins;
    }
});

// 5. Override languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en', 'hi']
});

// 6. Override connection info
Object.defineProperty(navigator, 'connection', {
    get: () => ({
        effectiveType: '4g',
        rtt: 50,
        downlink: 10,
        saveData: false,
    })
});

// 7. Override hardware concurrency (consistent with real devices)
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => window.__FINGERPRINT__?.hardware?.cores || (4 + Math.floor(Math.random() * 5))
});

// 8. Override device memory
Object.defineProperty(navigator, 'deviceMemory', {
    get: () => window.__FINGERPRINT__?.hardware?.memory || [4, 8, 16][Math.floor(Math.random() * 3)]
});

// 9. Canvas fingerprint noise injection
const origGetContext = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(type, ...args) {
    const ctx = origGetContext.call(this, type, ...args);
    if (type === '2d' && ctx) {
        const origGetImageData = ctx.getImageData;
        ctx.getImageData = function(...gdArgs) {
            const imageData = origGetImageData.apply(this, gdArgs);
            // Add subtle seeded noise to canvas fingerprint
            const seed = window.__FINGERPRINT__?.canvas_noise_seed || 42;
            for (let i = 0; i < imageData.data.length; i += 4) {
                const noiseR = ((i * 12345 + seed) % 3) - 1;
                const noiseG = (((i + 1) * 12345 + seed) % 3) - 1;
                const noiseB = (((i + 2) * 12345 + seed) % 3) - 1;
                imageData.data[i] += noiseR;
                imageData.data[i+1] += noiseG;
                imageData.data[i+2] += noiseB;
            }
            return imageData;
        };
    }
    return ctx;
};

// 10. WebGL fingerprint protection
const origGetParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(param) {
    // Randomize UNMASKED vendor/renderer strings
    if (param === 37445) return window.__FINGERPRINT__?.webgl?.vendor || 'Google Inc. (Intel)';
    if (param === 37446) return window.__FINGERPRINT__?.webgl?.renderer || 'ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0)';
    return origGetParameter.call(this, param);
};

// 11. Prevent iframe detection
try {
    if (window.self !== window.top) {
        // We're in an iframe, override to make it look like top-level
        Object.defineProperty(window, 'self', { get: () => window.top });
    }
} catch(e) {}

// 12. Override toString to hide modifications
const nativeToString = Function.prototype.toString;
const overrides = new Map();

function mockToString(fn, str) {
    overrides.set(fn, str);
}

Function.prototype.toString = function() {
    if (overrides.has(this)) return overrides.get(this);
    return nativeToString.call(this);
};

// Mock critical overridden functions
mockToString(navigator.permissions.query, 'function query() { [native code] }');

// 13. Prevent detection via Error stack traces
const origError = Error;
window.Error = function(...args) {
    const err = new origError(...args);
    // Clean automation-related entries from stack
    if (err.stack) {
        err.stack = err.stack.replace(/playwright|puppeteer|selenium|webdriver/gi, 'browser');
    }
    return err;
};
window.Error.prototype = origError.prototype;

// 14. AudioContext fingerprint protection
const origGetChannelData = AudioBuffer.prototype.getChannelData;
AudioBuffer.prototype.getChannelData = function(channel) {
    const data = origGetChannelData.call(this, channel);
    // Add subtle seeded noise to audio fingerprint data
    const seed = window.__FINGERPRINT__?.audio_noise_seed || 42;
    for (let i = 0; i < Math.min(data.length, 1000); i++) {
        const noise = (((i * 12345 + seed) % 1000) / 10000000000);
        data[i] += noise;
    }
    return data;
};

const origCopyFromChannel = AudioBuffer.prototype.copyFromChannel;
AudioBuffer.prototype.copyFromChannel = function(destination, channelNumber, startInChannel) {
    origCopyFromChannel.call(this, destination, channelNumber, startInChannel);
    const seed = window.__FINGERPRINT__?.audio_noise_seed || 42;
    for (let i = 0; i < Math.min(destination.length, 1000); i++) {
        const noise = (((i * 12345 + seed) % 1000) / 10000000000);
        destination[i] += noise;
    }
};

// 15. Screen parameter spoofing
const screenWidth = window.__FINGERPRINT__?.screen?.width || [1920, 1440, 1366, 1536][Math.floor(Math.random() * 4)];
const screenHeight = window.__FINGERPRINT__?.screen?.height || { 1920: 1080, 1440: 900, 1366: 768, 1536: 864 }[screenWidth] || 1080;

Object.defineProperty(window.screen, 'width', { get: () => screenWidth });
Object.defineProperty(window.screen, 'height', { get: () => screenHeight });
Object.defineProperty(window.screen, 'availWidth', { get: () => screenWidth });
Object.defineProperty(window.screen, 'availHeight', { get: () => screenHeight - 40 });
Object.defineProperty(window.screen, 'colorDepth', { get: () => 24 });
Object.defineProperty(window.screen, 'pixelDepth', { get: () => 24 });

Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth + 16 });
Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight + 80 });

console.log('🛫 Flight Finder stealth patches applied');
"""
