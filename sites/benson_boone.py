"""
Benson Boone Store product checker.
Monitors signed items at store.bensonboone.com

Regex-based detection finds product URLs, then checks each product page
for sold-out status. Uses requests first, Playwright fallback.
"""
import re
import time

from .base import ProductChecker


class BensonBooneChecker(ProductChecker):
    """
    Checker for signed Benson Boone merchandise.

    Uses regex to find product URLs containing the search term on the
    search results page, then visits each product page individually
    to check stock status.
    """

    use_playwright = True  # enable Playwright fallback

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
        Fetch search page, find product URLs via regex, then check each
        product page for sold-out status. Uses fetch_url() which tries
        requests first and falls back to Playwright if blocked.
        """
        search_term = 'signed'

        # Fetch search page (requests first, Playwright fallback)
        search_html = self.fetch_url(self.search_url)
        if not search_html:
            return []

        # Regex to find product URLs containing the search term
        url_re = re.compile(
            rf'(/products/[^"\s?]*?{search_term}[^"\s?]*)',
            flags=re.IGNORECASE
        )

        matches = list(set(url_re.findall(search_html)))
        items = [
            self.base_url + m if not m.startswith('http') else m
            for m in matches
        ]

        self.log(f"Found {len(items)} product URLs to check")
        products = []

        for item_url in items:
            time.sleep(2)  # polite delay between product pages

            html = self.fetch_url(item_url)
            if not html:
                continue

            # Sold-out detection
            is_sold_out = (
                '<strong>Sorry Sold out</strong>' in html or
                'aria-disabled="true"' in html or
                'sold-out' in html.lower() or
                'sold_out' in html.lower()
            )
            sold_out_count = html.lower().count('sold out')

            # Extract title
            title = "Signed Item"
            title_match = re.search(r'<title>(.*?)</title>', html)
            if title_match:
                title = title_match.group(1).split('–')[0].split('|')[0].strip()

            if not is_sold_out and sold_out_count < 6:
                products.append({
                    'title': title,
                    'price': 'See listing',
                    'url': item_url.split('?')[0],
                    'image_url': '',
                })
                self.log(f"Found in-stock: {title}")
            else:
                self.log(f"Sold out: {title}")

        return products

    def parse_products(self, soup) -> list:
        """Not used — fetch_products is overridden."""
        return []

    def get_email_subject(self, new_products: list, timestamp: str) -> str:
        return f"🎤 Benson Boone SIGNED Items Alert! - {len(new_products)} item(s) - {timestamp}"

    def get_email_intro(self) -> str:
        return "SIGNED BENSON BOONE ITEMS ARE AVAILABLE! 🎤\n"


def run_checker(quiet: bool = False):
    checker = BensonBooneChecker(quiet=quiet)
    checker.run()


if __name__ == "__main__":
    run_checker()
