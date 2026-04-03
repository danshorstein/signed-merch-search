"""
Taylor Swift Store product checker.
Monitors ALL new products at store.taylorswift.com and gives
special alerts for signed items (with 2-hour recheck window).

Uses Shopify's JSON API. Tries requests first, falls back to
Playwright if blocked by bot protection.
"""
import json
import time
from pathlib import Path

import requests

from .base import ProductChecker, SEEN_DIR


# How long (seconds) before a signed item alert can fire again.
SIGNED_COOLDOWN_SECONDS = 2 * 60 * 60  # 2 hours


class TaylorSwiftChecker(ProductChecker):
    """
    Checker for the Taylor Swift Official Store.

    Two notification types:
      1. NEW ITEM alert  — any product that hasn't been seen before
      2. SIGNED ITEM alert — signed items that are in stock,
         re-checks every 2 hours so restocks get caught
    """

    use_playwright = True  # enable fallback

    @property
    def site_name(self) -> str:
        return "Taylor Swift"

    @property
    def search_url(self) -> str:
        return "https://store.taylorswift.com/products.json?limit=250"

    @property
    def base_url(self) -> str:
        return "https://store.taylorswift.com"

    # --- Signed-item timestamp tracking ---

    @property
    def _signed_seen_file(self) -> Path:
        return SEEN_DIR / f"{self._safe_name}_signed_seen.json"

    def _load_signed_seen(self) -> dict:
        if self._signed_seen_file.exists():
            try:
                with open(self._signed_seen_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, Exception):
                return {}
        return {}

    def _save_signed_seen(self, data: dict):
        with open(self._signed_seen_file, 'w') as f:
            json.dump(data, f, indent=2)

    # --- Product fetching via JSON API ---

    def _fetch_json_via_requests(self) -> list | None:
        """Try fetching JSON API directly via requests."""
        all_products_raw = []
        page_num = 1

        while True:
            url = f"{self.search_url}&page={page_num}&t={int(time.time())}"
            try:
                r = requests.get(url, headers=self.HEADERS, timeout=15)
                if self._is_blocked(r) or r.status_code != 200:
                    # If we already got some products, return them
                    # Otherwise signal to try Playwright
                    return all_products_raw if all_products_raw else None

                data = r.json()
                products = data.get('products', [])
                if not products:
                    break

                all_products_raw.extend(products)
                self.log(f"Page {page_num}: fetched {len(products)} products via requests")
                page_num += 1

            except Exception:
                return all_products_raw if all_products_raw else None

        return all_products_raw

    def _fetch_json_via_playwright(self) -> list | None:
        """Fetch JSON API using Playwright as fallback."""
        self.log("Falling back to Playwright for JSON API")
        all_products_raw = []
        page_num = 1

        try:
            self._start_browser()
        except Exception:
            return None

        # Load homepage first to pass bot protection
        homepage_html = self.get_page_html(self.base_url, wait_ms=2000)
        if not homepage_html:
            self.log("ERROR: Could not load store homepage via Playwright")
            return None

        while True:
            time.sleep(1)
            url = f"{self.search_url}&page={page_num}&t={int(time.time())}"

            try:
                json_text = self._page.evaluate(f"""
                    async () => {{
                        const response = await fetch("{url}");
                        if (!response.ok) return null;
                        return await response.text();
                    }}
                """)

                if not json_text:
                    self.log(f"ERROR: Could not fetch JSON on page {page_num}")
                    break

                data = json.loads(json_text)
                products = data.get('products', [])
                if not products:
                    break

                all_products_raw.extend(products)
                self.log(f"Page {page_num}: fetched {len(products)} products via Playwright")
                page_num += 1

            except Exception as e:
                self.log(f"ERROR fetching page {page_num}: {e}")
                break

        return all_products_raw

    def _parse_raw_products(self, raw_products: list) -> list:
        """Convert raw Shopify JSON products to our standard format."""
        all_products = []

        for p in raw_products:
            title = p.get('title', 'Unknown')
            handle = p.get('handle', '')
            variants = p.get('variants', [])

            is_available = any(v.get('available', False) for v in variants)

            price = 'Price N/A'
            if variants:
                raw_price = variants[0].get('price', '')
                if raw_price:
                    price = f"${float(raw_price):.2f}"

            image_url = ''
            images = p.get('images', [])
            if images:
                image_url = images[0].get('src', '')

            search_text = f"{title} {handle}".lower()
            is_signed = 'signed' in search_text or 'autograph' in search_text

            product_url = f"{self.base_url}/products/{handle}"

            all_products.append({
                'title': title,
                'price': price,
                'url': product_url,
                'image_url': image_url,
                'is_signed': is_signed,
                'is_available': is_available,
            })

        return all_products

    def fetch_products(self) -> list:
        """Fetch all products. Requests first, Playwright fallback."""
        raw = self._fetch_json_via_requests()
        if raw is None and self.use_playwright:
            raw = self._fetch_json_via_playwright()
        if raw is None:
            return []

        products = self._parse_raw_products(raw)
        self.log(f"Total: {len(products)} products fetched")
        return products

    def parse_products(self, soup) -> list:
        return []

    # --- Custom run logic ---

    def run(self):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        now = time.time()

        try:
            seen_products = self.load_seen_products()
            signed_seen = self._load_signed_seen()

            products = self.fetch_products()
            if not products:
                self.log("No products found or fetch failed")
                self._record_failure(f"No products returned from {self.search_url}")
                return

            self._record_success()

            new_products = []
            signed_in_stock = []
            all_current_urls = set()

            for product in products:
                clean_url = product['url'].split('?')[0]
                all_current_urls.add(clean_url)

                if clean_url not in seen_products:
                    new_products.append(product)

                if product.get('is_signed') and product.get('is_available'):
                    last_alerted = signed_seen.get(clean_url, 0)
                    if (now - last_alerted) >= SIGNED_COOLDOWN_SECONDS:
                        signed_in_stock.append(product)

            # Signed item alert (priority)
            if signed_in_stock:
                subject = f"🚨 SIGNED Taylor Swift Items IN STOCK! - {len(signed_in_stock)} item(s) - {timestamp}"
                body = self._build_signed_email(signed_in_stock)
                if self.send_email(subject, body):
                    for p in signed_in_stock:
                        signed_seen[p['url'].split('?')[0]] = now
                    self._save_signed_seen(signed_seen)
                    self.log(f"SIGNED ALERT sent for {len(signed_in_stock)} item(s)")

            # New item alert
            if new_products:
                signed_urls = {p['url'].split('?')[0] for p in signed_in_stock}
                new_non_signed = [p for p in new_products if p['url'].split('?')[0] not in signed_urls]

                if new_non_signed:
                    subject = self.get_email_subject(new_non_signed, timestamp)
                    body = self.build_email_body(new_non_signed)
                    if self.send_email(subject, body):
                        self.log(f"NEW ITEMS alert sent for {len(new_non_signed)} item(s)")

                seen_products.update(all_current_urls)
                self.save_seen_products(seen_products)
                self.log(f"Updated seen products ({len(all_current_urls)} total)")
            else:
                self.log(f"OK - {len(products)} items, no new products")
                self.save_seen_products(seen_products)

        finally:
            self._stop_browser()

    def _build_signed_email(self, signed_products: list) -> str:
        lines = [
            "🚨 SIGNED TAYLOR SWIFT ITEMS ARE IN STOCK! 🚨",
            "",
            "GO GO GO! These signed items are currently showing as AVAILABLE:",
            "",
            "=" * 50,
            "",
        ]

        for i, product in enumerate(signed_products, 1):
            lines.append(f"{i}. {product['title']}")
            lines.append(f"   Price: {product['price']}")
            lines.append(f"   Link: {product['url']}")
            avail = "✅ IN STOCK" if product.get('is_available') else "❌ Sold Out"
            lines.append(f"   Status: {avail}")
            lines.append("")

        lines.append("=" * 50)
        lines.append(f"\nStore: {self.base_url}")
        lines.append("\n(You will be re-alerted every 2 hours while items remain in stock)")

        return "\n".join(lines)

    def get_email_subject(self, new_products: list, timestamp: str) -> str:
        return f"🎵 {len(new_products)} New Taylor Swift Store Item(s)! - {timestamp}"

    def get_email_intro(self) -> str:
        return "New items just appeared in the Taylor Swift Official Store!\n"


def run_checker(quiet: bool = False):
    checker = TaylorSwiftChecker(quiet=quiet)
    checker.run()


if __name__ == "__main__":
    run_checker()
