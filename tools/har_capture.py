"""
Auto HAR capture tool — opens browser to record user actions and saves HAR file.

Usage:
    # Open browser, manually register, close to auto-save HAR
    python3 tools/har_capture.py --url https://auth.example.com/signup --name example

    # With proxy
    python3 tools/har_capture.py --url https://auth.example.com/signup --name example --proxy http://127.0.0.1:7890

Output:
    tools/captures/example.har
"""
from __future__ import annotations

import argparse
import os
import sys


CAPTURE_DIR = os.path.join(os.path.dirname(__file__), "captures")


def capture_har(url: str, name: str, proxy: str = None, headless: bool = False):
    from playwright.sync_api import sync_playwright

    os.makedirs(CAPTURE_DIR, exist_ok=True)
    har_path = os.path.join(CAPTURE_DIR, f"{name}.har")

    print(f"Starting browser...")
    print(f"  Target: {url}")
    print(f"  HAR: {har_path}")
    if proxy:
        print(f"  Proxy: {proxy}")
    print(f"\nPlease complete the registration/login flow in the browser, then close the browser window.\n")

    with sync_playwright() as p:
        launch_args = {"headless": headless}
        if proxy:
            launch_args["proxy"] = {"server": proxy}

        browser = p.chromium.launch(**launch_args)
        context = browser.new_context(
            record_har_path=har_path,
            record_har_url_filter="**/*",
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")

        # Wait for user to close browser
        try:
            page.wait_for_event("close", timeout=600_000)  # 10 minute timeout
        except Exception:
            pass

        context.close()
        browser.close()

    size = os.path.getsize(har_path) if os.path.exists(har_path) else 0
    print(f"\n✓ HAR saved: {har_path} ({size / 1024:.0f} KB)")
    print(f"\nNext step: python3 tools/har_analyze.py --file {har_path}")
    return har_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HAR capture tool")
    parser.add_argument("--url", required=True, help="Target URL")
    parser.add_argument("--name", required=True, help="Site name (used for filename)")
    parser.add_argument("--proxy", help="Proxy URL")
    parser.add_argument("--headless", action="store_true", help="Headless mode")
    args = parser.parse_args()
    capture_har(args.url, args.name, proxy=args.proxy, headless=args.headless)
