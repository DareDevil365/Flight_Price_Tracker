"""
Flight Finder — Fingerprint Rotation
Generates randomized browser fingerprints (viewport, user-agent, geolocation,
canvas, WebGL, audio, fonts) for each browser session.
"""

import random
from typing import Optional


# Common Indian city geolocations for realistic fingerprinting
INDIAN_GEOLOCATIONS = [
    {"latitude": 28.6139, "longitude": 77.2090},   # Delhi
    {"latitude": 19.0760, "longitude": 72.8777},   # Mumbai
    {"latitude": 12.9716, "longitude": 77.5946},   # Bangalore
    {"latitude": 17.3850, "longitude": 78.4867},   # Hyderabad
    {"latitude": 13.0827, "longitude": 80.2707},   # Chennai
    {"latitude": 22.5726, "longitude": 88.3639},   # Kolkata
    {"latitude": 23.0225, "longitude": 72.5714},   # Ahmedabad
    {"latitude": 18.5204, "longitude": 73.8567},   # Pune
    {"latitude": 26.9124, "longitude": 75.7873},   # Jaipur
    {"latitude": 15.2993, "longitude": 74.1240},   # Goa
]

# Real-world viewport sizes
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
    {"width": 1600, "height": 900},
    {"width": 1280, "height": 800},
    {"width": 1680, "height": 1050},
    {"width": 1360, "height": 768},
    {"width": 1280, "height": 1024},
]

# Real Chrome user agents (updated regularly)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0",
]

# WebGL vendor/renderer pairs
WEBGL_PROFILES = [
    {
        "vendor": "Google Inc. (Intel)",
        "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "vendor": "Google Inc. (NVIDIA)",
        "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "vendor": "Google Inc. (AMD)",
        "renderer": "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "vendor": "Google Inc. (Intel)",
        "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "vendor": "Google Inc. (NVIDIA)",
        "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
]

# Common font sets (varies by OS)
FONT_SETS = [
    # Windows 10/11
    ["Arial", "Calibri", "Cambria", "Comic Sans MS", "Consolas", "Courier New",
     "Georgia", "Impact", "Lucida Console", "Segoe UI", "Tahoma", "Times New Roman",
     "Trebuchet MS", "Verdana"],
    # Windows with Indian fonts
    ["Arial", "Calibri", "Cambria", "Consolas", "Courier New", "Georgia",
     "Mangal", "Nirmala UI", "Segoe UI", "Tahoma", "Times New Roman", "Verdana"],
]


def generate_random_fingerprint() -> dict:
    """Generate a complete randomized browser fingerprint."""
    viewport = random.choice(VIEWPORTS)
    geo = random.choice(INDIAN_GEOLOCATIONS)

    # Add small random offset to geolocation (within ~5km)
    geo = {
        "latitude": geo["latitude"] + random.uniform(-0.05, 0.05),
        "longitude": geo["longitude"] + random.uniform(-0.05, 0.05),
    }

    fingerprint = {
        "viewport": viewport,
        "user_agent": random.choice(USER_AGENTS),
        "geolocation": geo,
        "webgl": random.choice(WEBGL_PROFILES),
        "fonts": random.choice(FONT_SETS),
        "screen": {
            "width": viewport["width"],
            "height": viewport["height"],
            "color_depth": random.choice([24, 32]),
            "pixel_ratio": random.choice([1.0, 1.25, 1.5, 2.0]),
        },
        "hardware": {
            "cores": random.choice([4, 6, 8, 12]),
            "memory": random.choice([4, 8, 16]),
        },
        "canvas_noise_seed": random.randint(1, 100000),
        "audio_noise_seed": random.random() * 0.0001,
    }

    return fingerprint
