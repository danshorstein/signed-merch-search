"""
Taylor Swift Store product checker.
Monitors ALL new products at store.taylorswift.com and gives
special alerts for signed items (with 2-hour recheck window).

Uses Shopify's JSON API for speed — fetches all ~273 products
in ~1 second via 2 API calls instead of scraping 12 HTML pages.
"""
import json
import time
from pathlib import Path

import requests

from .base import ProductChecker, SEEN_DIR


# How long (seconds) before a signed item alert can fire again.
# This lets us re-alert on restocks without pinging every minute.
SIGNED_COOLDOWN_SECONDS = 2 * 60 * 60  # 2 hours


class TaylorSwiftChecker(ProductChecker):
    """
    Checker for the Taylor Swift Official Store.

    Two notification types:
      1. NEW ITEM alert  — any product that hasn't been seen before
      2. SIGNED ITEM alert — signed items that are in stock,
         re-checks every 2 hours so restocks get caught
    """

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
        """Separate file for signed items with timestamps."""
        return SEEN_DIR / f"{self._safe_name}_signed_seen.json"

    def _load_signed_seen(self) -> dict:
        """Load signed items seen dict: {url: last_alerted_timestamp}."""
        if self._signed_seen_file.exists():
            try:
                with open(self._signed_seen_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, Exception):
                return {}
        return {}

    def _save_signed_seen(self, data: dict):
        """Save signed items seen dict."""
        with open(self._signed_seen_file, 'w') as f:
            json.dump(data, f, indent=2)

    # --- Product fetching via JSON API ---

    def fetch_products(self) -> list:
        """
        Fetch ALL products from the Shopify JSON API.
        Returns list of product dicts with title, price, url, image_url,
        plus extra fields: is_signed, is_available.
        """
        all_products = []
        page = 1

        while True:
            url = f"{self.search_url}&page={page}&t={int(time.time())}"
            try:
                r = requests.get(url, headers=self.HEADERS, timeout=15)
                if r.status_code != 200:
                    self.log(f"ERROR: Status code {r.status_code} on page {page}")
                    break

                data = r.json()
                products = data.get('products', [])

                if not products:
                    break  # No more pages

                for p in products:
                    title = p.get('title', 'Unknown')
                    handle = p.get('handle', '')
                    variants = p.get('variants', [])

                    # Check availability across ALL variants
                    is_available = any(v.get('available', False) for v in variants)

                    # Get price from first variant
                    price = 'Price N/A'
                    if variants:
                        raw_price = variants[0].get('price', '')
                        if raw_price:
                            price = f"${float(raw_price):.2f}"

                    # Get image
                    image_url = ''
                    images = p.get('images', [])
                    if images:
                        image_url = images[0].get('src', '')

                    # Check if signed
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

                self.log(f"Page {page}: fetched {len(products)} products")
                page += 1

            except Exception as e:
                self.log(f"ERROR fetching page {page}: {e}")
                break

        self.log(f"Total: {len(all_products)} products fetched")
        return all_products

    def parse_products(self, soup) -> list:
        """Not used — fetch_products uses JSON API."""
        return []

    # --- Custom run logic for dual notifications ---

    def run(self):
        """
        Custom run with two notification types:
        1. New items (any product not seen before)
        2. Signed items in stock (re-alerts every 2 hours)
        """
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        now = time.time()

        # Load tracking data
        seen_products = self.load_seen_products()
        signed_seen = self._load_signed_seen()

        # Fetch all products
        products = self.fetch_products()
        if not products:
            self.log("No products found or fetch failed")
            return

        # Categorize
        new_products = []
        signed_in_stock = []
        all_current_urls = set()

        for product in products:
            clean_url = product['url'].split('?')[0]
            all_current_urls.add(clean_url)

            # Track new items (any product not seen before)
            if clean_url not in seen_products:
                new_products.append(product)

            # Track signed items that are in stock and past cooldown
            if product.get('is_signed') and product.get('is_available'):
                last_alerted = signed_seen.get(clean_url, 0)
                if (now - last_alerted) >= SIGNED_COOLDOWN_SECONDS:
                    signed_in_stock.append(product)

        # --- Send SIGNED item alert (priority) ---
        if signed_in_stock:
            subject = f"🚨 SIGNED Taylor Swift Items IN STOCK! - {len(signed_in_stock)} item(s) - {timestamp}"
            body = self._build_signed_email(signed_in_stock)
            if self.send_email(subject, body):
                for p in signed_in_stock:
                    signed_seen[p['url'].split('?')[0]] = now
                self._save_signed_seen(signed_seen)
                self.log(f"SIGNED ALERT sent for {len(signed_in_stock)} item(s)")

        # --- Send NEW item alert ---
        if new_products:
            # Filter out signed items from new-item email if they were
            # already covered by the signed alert above
            signed_urls = {p['url'].split('?')[0] for p in signed_in_stock}
            new_non_signed = [p for p in new_products if p['url'].split('?')[0] not in signed_urls]

            if new_non_signed:
                subject = self.get_email_subject(new_non_signed, timestamp)
                body = self.build_email_body(new_non_signed)
                if self.send_email(subject, body):
                    self.log(f"NEW ITEMS alert sent for {len(new_non_signed)} item(s)")

            # Update seen products after successful processing
            seen_products.update(all_current_urls)
            self.save_seen_products(seen_products)
            self.log(f"Updated seen products ({len(all_current_urls)} total)")
        else:
            self.log(f"OK - {len(products)} items, no new products")
            self.save_seen_products(seen_products)

    def _build_signed_email(self, signed_products: list) -> str:
        """Build a special email body for signed items."""
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
    """Run the Taylor Swift checker."""
    checker = TaylorSwiftChecker(quiet=quiet)
    checker.run()


if __name__ == "__main__":
    run_checker()
