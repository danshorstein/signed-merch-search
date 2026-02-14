"""
Benson Boone Store product checker.
Monitors signed items at store.bensonboone.com

Reuses the regex-based detection approach from the original benson.py script,
wrapped in the ProductChecker framework for consistent email handling and
seen-product tracking.
"""
import re

import requests

from .base import ProductChecker


class BensonBooneChecker(ProductChecker):
    """
    Checker for signed Benson Boone merchandise.

    Uses regex to find product URLs containing the search term on the
    search results page, then visits each product page individually
    to check stock status — same approach as the original benson.py.
    """

    @property
    def site_name(self) -> str:
        return "Benson Boone"

    @property
    def search_url(self) -> str:
        return "https://store.bensonboone.com/search?q=signed"

    @property
    def base_url(self) -> str:
        return "https://store.bensonboone.com"

    def fetch_products(self) -> list:
        """
        Override the default BeautifulSoup-based fetch with the regex approach
        from benson.py. Finds product URLs via regex, then checks each product
        page for sold-out status.
        """
        search_term = 'signed'

        try:
            r = requests.get(self.search_url, headers=self.HEADERS, timeout=15)
            if r.status_code != 200:
                self.log(f"ERROR: Status code {r.status_code}")
                return []
        except Exception as e:
            self.log(f"ERROR fetching search page: {e}")
            return []

        # Regex to find product URLs containing the search term
        url_re = re.compile(
            rf'(/products/[^"\s?]*?{search_term}[^"\s?]*)',
            flags=re.IGNORECASE
        )

        matches = list(set(url_re.findall(r.text)))
        items = [
            self.base_url + m if not m.startswith('http') else m
            for m in matches
        ]

        self.log(f"Found {len(items)} product URLs to check")
        products = []

        for item_url in items:
            try:
                r_item = requests.get(item_url, headers=self.HEADERS, timeout=15)
                if r_item.status_code != 200:
                    continue

                html = r_item.text

                # Sold-out detection (from benson.py)
                is_sold_out = (
                    '<strong>Sorry Sold out</strong>' in html or
                    'aria-disabled="true"' in html or
                    'sold-out' in html.lower() or
                    'sold_out' in html.lower()
                )
                sold_out_count = html.lower().count('sold out')

                if not is_sold_out and sold_out_count < 6:
                    # Extract a clean title from the page <title> tag
                    title = "Signed Item"
                    title_match = re.search(r'<title>(.*?)</title>', html)
                    if title_match:
                        title = title_match.group(1).split('–')[0].split('|')[0].strip()

                    products.append({
                        'title': title,
                        'price': 'See listing',
                        'url': item_url.split('?')[0],
                        'image_url': '',
                    })
                    self.log(f"Found in-stock: {title}")

            except Exception as e:
                self.log(f"Error checking {item_url}: {e}")
                continue

        return products

    def parse_products(self, soup) -> list:
        """Not used — fetch_products is overridden with regex logic."""
        return []

    def get_email_subject(self, new_products: list, timestamp: str) -> str:
        return f"🎤 Benson Boone SIGNED Items Alert! - {len(new_products)} item(s) - {timestamp}"

    def get_email_intro(self) -> str:
        return "SIGNED BENSON BOONE ITEMS ARE AVAILABLE! 🎤\n"


# Convenience function for direct execution
def run_checker(quiet: bool = False):
    """Run the Benson Boone checker."""
    checker = BensonBooneChecker(quiet=quiet)
    checker.run()


if __name__ == "__main__":
    run_checker()
