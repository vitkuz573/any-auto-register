from __future__ import annotations

import concurrent.futures
import requests
import threading

from core.proxy_pool import proxy_pool
from domain.proxies import ProxyBulkCreateCommand, ProxyCheckSummary, ProxyCreateCommand, ProxyRecord
from infrastructure.proxies_repository import ProxiesRepository


_PROXY_SOURCES = [
    {
        "name": "http_public",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "parser": lambda text: [f"http://{line.strip()}" for line in text.strip().splitlines() if line.strip()],
    },
    {
        "name": "socks5_public",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "parser": lambda text: [f"socks5://{line.strip()}" for line in text.strip().splitlines() if line.strip()],
    },
    {
        "name": "https_public",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
        "parser": lambda text: [f"socks4://{line.strip()}" for line in text.strip().splitlines() if line.strip()],
    },
]

_TEST_URL = "https://httpbin.org/ip"


class ProxiesService:
    def __init__(self, repository: ProxiesRepository | None = None):
        self.repository = repository or ProxiesRepository()

    def list_proxies(self) -> list[dict]:
        return [self._serialize(item) for item in self.repository.list()]

    def create_proxy(self, command: ProxyCreateCommand) -> dict | None:
        item = self.repository.create(command)
        return self._serialize(item) if item else None

    def bulk_create_proxies(self, command: ProxyBulkCreateCommand) -> dict:
        result = self.repository.bulk_create(command.proxies, command.region)
        return result

    def delete_proxy(self, proxy_id: int) -> dict:
        return {"ok": self.repository.delete(proxy_id)}

    def toggle_proxy(self, proxy_id: int) -> dict | None:
        value = self.repository.toggle(proxy_id)
        if value is None:
            return None
        return {"is_active": value}

    def trigger_check(self) -> dict:
        threading.Thread(target=proxy_pool.check_all, daemon=True, name="proxy-check").start()
        return {"message": "Proxy check task started"}

    def scan_public_proxies(self, target_count: int = 10, test_timeout: int = 10, region: str = "public") -> dict:
        """Fetch public proxy lists, test them, and add working ones to the database."""
        all_proxies = []
        for source in _PROXY_SOURCES:
            try:
                r = requests.get(source["url"], timeout=30)
                if r.status_code == 200:
                    proxies = source["parser"](r.text)
                    all_proxies.extend(proxies)
            except Exception:
                pass

        # Deduplicate
        seen = set()
        unique = []
        for p in all_proxies:
            if p not in seen:
                seen.add(p)
                unique.append(p)

        working = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = {executor.submit(self._test_proxy, p, test_timeout): p for p in unique}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    working.append(result)
                if len(working) >= target_count:
                    for f in futures:
                        f.cancel()
                    break

        result = {"added": 0, "skipped": 0}
        if working:
            result = self.repository.bulk_create(working, region)

        return {
            "scanned": len(unique),
            "working": len(working),
            "added": result["added"],
            "skipped": result["skipped"],
            "proxies": working[:target_count],
        }

    @staticmethod
    def _test_proxy(proxy_url: str, timeout: int) -> str | None:
        try:
            proxies = {"http": proxy_url, "https": proxy_url}
            r = requests.get(_TEST_URL, proxies=proxies, timeout=timeout)
            if r.status_code == 200:
                return proxy_url
        except Exception:
            pass
        return None

    @staticmethod
    def _serialize(item: ProxyRecord) -> dict:
        return {
            "id": item.id,
            "url": item.url,
            "region": item.region,
            "success_count": item.success_count,
            "fail_count": item.fail_count,
            "is_active": item.is_active,
            "last_checked": item.last_checked,
        }
