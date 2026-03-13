from __future__ import annotations

import random

from playwright.async_api import Page

# Realistic user agents matching modern Chromium versions
USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

STEALTH_SCRIPT = """
() => {
    // 1. Override navigator.webdriver
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true,
    });

    // 2. Realistic navigator.plugins
    const pluginData = [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
    ];
    const pluginArray = pluginData.map(p => {
        const plugin = Object.create(Plugin.prototype);
        Object.defineProperty(plugin, 'name', { get: () => p.name });
        Object.defineProperty(plugin, 'filename', { get: () => p.filename });
        Object.defineProperty(plugin, 'description', { get: () => p.description });
        return plugin;
    });
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const arr = Object.create(PluginArray.prototype);
            pluginArray.forEach((p, i) => arr[i] = p);
            Object.defineProperty(arr, 'length', { get: () => pluginArray.length });
            return arr;
        },
        configurable: true,
    });

    // 3. mimeTypes
    Object.defineProperty(navigator, 'mimeTypes', {
        get: () => {
            const arr = Object.create(MimeTypeArray.prototype);
            Object.defineProperty(arr, 'length', { get: () => 0 });
            return arr;
        },
        configurable: true,
    });

    // 4. Canvas fingerprint randomization
    const originalGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, ...args) {
        const ctx = originalGetContext.call(this, type, ...args);
        if (ctx && type === '2d') {
            const originalFillText = ctx.fillText.bind(ctx);
            ctx.fillText = function(...textArgs) {
                ctx.shadowBlur = Math.random() * 0.1;
                return originalFillText(...textArgs);
            };
        }
        return ctx;
    };

    // 5. WebGL vendor/renderer spoofing
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter.call(this, parameter);
    };

    // 6. Hide automation-related properties
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;

    // 7. Realistic screen dimensions
    Object.defineProperty(screen, 'availWidth', { get: () => 1366 });
    Object.defineProperty(screen, 'availHeight', { get: () => 768 });
}
"""


def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)


async def apply_stealth_settings(page: Page) -> None:
    await page.add_init_script(STEALTH_SCRIPT)
