"""Anti-detection and stealth measures for web scraping."""

import random
from typing import Dict, List, Optional
import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)


# Common desktop user agents (updated for 2024)
DESKTOP_USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    # Safari on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

# Mobile user agents
MOBILE_USER_AGENTS = [
    # Chrome on Android
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    # Safari on iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
]

# Tablet user agents
TABLET_USER_AGENTS = [
    "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; SM-X900) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# Common screen resolutions
DESKTOP_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
    {"width": 2560, "height": 1440},
]

MOBILE_VIEWPORTS = [
    {"width": 390, "height": 844},   # iPhone 14 Pro
    {"width": 393, "height": 873},   # Pixel 7
    {"width": 412, "height": 915},   # Samsung S21
    {"width": 375, "height": 812},   # iPhone X
]

TABLET_VIEWPORTS = [
    {"width": 820, "height": 1180},  # iPad Air
    {"width": 768, "height": 1024},  # iPad Mini
    {"width": 800, "height": 1280},  # Android tablet
]


class StealthConfig:
    """Configuration and application of stealth measures."""

    # JavaScript to inject for anti-detection
    STEALTH_SCRIPTS = """
    // Override webdriver property
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });

    // Override plugins to look realistic
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            return [
                {
                    name: 'Chrome PDF Plugin',
                    description: 'Portable Document Format',
                    filename: 'internal-pdf-viewer',
                    length: 1,
                },
                {
                    name: 'Chrome PDF Viewer',
                    description: '',
                    filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                    length: 1,
                },
                {
                    name: 'Native Client',
                    description: '',
                    filename: 'internal-nacl-plugin',
                    length: 2,
                },
            ];
        },
    });

    // Override languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });

    // Override platform (if needed)
    // Object.defineProperty(navigator, 'platform', {
    //     get: () => 'Win32',
    // });

    // Override permissions
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );

    // Override Chrome property
    window.chrome = {
        runtime: {},
    };

    // Override connection info
    Object.defineProperty(navigator, 'connection', {
        get: () => ({
            effectiveType: '4g',
            rtt: 50,
            downlink: 10,
            saveData: false,
        }),
    });

    // Add missing properties that headless browsers often lack
    if (!window.outerWidth) {
        window.outerWidth = window.innerWidth;
    }
    if (!window.outerHeight) {
        window.outerHeight = window.innerHeight + 85;
    }

    // Override hairline detection
    Object.defineProperty(window, 'devicePixelRatio', {
        get: () => 1,
    });
    """

    def __init__(
        self,
        device_type: str = "desktop",
        language: str = "en-US",
        timezone: str = "America/New_York",
    ):
        self.device_type = device_type
        self.language = language
        self.timezone = timezone

    def get_random_user_agent(self, device: Optional[str] = None) -> str:
        """Get a random, realistic user agent for the device type."""
        device = device or self.device_type

        if device == "mobile":
            return random.choice(MOBILE_USER_AGENTS)
        elif device == "tablet":
            return random.choice(TABLET_USER_AGENTS)
        else:
            return random.choice(DESKTOP_USER_AGENTS)

    def get_realistic_viewport(self, device: Optional[str] = None) -> Dict[str, int]:
        """Get common viewport dimensions with slight randomization."""
        device = device or self.device_type

        if device == "mobile":
            base = random.choice(MOBILE_VIEWPORTS)
        elif device == "tablet":
            base = random.choice(TABLET_VIEWPORTS)
        else:
            base = random.choice(DESKTOP_VIEWPORTS)

        # Add slight randomization (±10 pixels)
        return {
            "width": base["width"] + random.randint(-10, 10),
            "height": base["height"] + random.randint(-10, 10),
        }

    def get_browser_context_options(self, device: Optional[str] = None) -> dict:
        """Get options for creating a stealthy browser context."""
        device = device or self.device_type
        viewport = self.get_realistic_viewport(device)
        user_agent = self.get_random_user_agent(device)

        options = {
            "viewport": viewport,
            "user_agent": user_agent,
            "locale": self.language,
            "timezone_id": self.timezone,
            "color_scheme": "light",
            "reduced_motion": "no-preference",
            "forced_colors": "none",
            "extra_http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": f"{self.language},en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            },
            "permissions": [],
            "geolocation": None,
            "offline": False,
            "http_credentials": None,
            "device_scale_factor": 1,
            "is_mobile": device in ("mobile", "tablet"),
            "has_touch": device in ("mobile", "tablet"),
        }

        return options

    async def apply_stealth(self, page: Page) -> None:
        """Apply all stealth measures to a Playwright page."""
        # Inject anti-detection JavaScript
        await page.add_init_script(self.STEALTH_SCRIPTS)

        logger.debug("Applied stealth configuration to page")

    async def simulate_human_behavior(self, page: Page) -> None:
        """
        Add human-like behavior patterns to the page.

        This includes random mouse movements and scroll behavior.
        """
        viewport = page.viewport_size or {"width": 1920, "height": 1080}

        # Random initial mouse position
        x = random.randint(100, viewport["width"] - 100)
        y = random.randint(100, viewport["height"] - 100)
        await page.mouse.move(x, y)

        # Small random mouse movements
        for _ in range(random.randint(2, 5)):
            dx = random.randint(-50, 50)
            dy = random.randint(-50, 50)
            new_x = max(0, min(viewport["width"], x + dx))
            new_y = max(0, min(viewport["height"], y + dy))
            await page.mouse.move(new_x, new_y)
            x, y = new_x, new_y

        # Optional: random scroll
        if random.random() < 0.3:
            scroll_y = random.randint(100, 300)
            await page.evaluate(f"window.scrollBy(0, {scroll_y})")

        logger.debug("Simulated human behavior on page")

    @staticmethod
    def get_random_delay() -> float:
        """Get a random delay that mimics human reaction time."""
        # Human reaction times typically 200-500ms
        base = random.uniform(0.2, 0.5)
        # Add some variance
        variance = random.uniform(0, 0.3)
        return base + variance


class StealthBrowserLauncher:
    """Helper class for launching stealth-configured browsers."""

    def __init__(self, config: Optional[StealthConfig] = None):
        self.config = config or StealthConfig()

    def get_launch_options(self) -> dict:
        """Get browser launch options for stealth."""
        return {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-breakpad",
                "--disable-component-extensions-with-background-pages",
                "--disable-component-update",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-features=TranslateUI",
                "--disable-hang-monitor",
                "--disable-ipc-flooding-protection",
                "--disable-popup-blocking",
                "--disable-prompt-on-repost",
                "--disable-renderer-backgrounding",
                "--disable-sync",
                "--enable-features=NetworkService,NetworkServiceInProcess",
                "--force-color-profile=srgb",
                "--metrics-recording-only",
                "--no-first-run",
                "--password-store=basic",
                "--use-mock-keychain",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        }
