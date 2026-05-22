"""
Gracie Abrams Store product checker.
Monitors signed items at shop.gracieabrams.com

Regex-based detection finds product URLs, then checks each product page
for sold-out status. Uses requests first, Playwright fallback.
"""
import re
import time

from .base import ProductChecker


class GracieAbramsChecker(ProductChecker):
    """
    Checker for signed Gracie Abrams merchandise.

    Target: https://shop.gracieabrams.com/search?q=signed
    """

    use_playwright = True

    @property
    def site_name(self) -> str:
        return "Gracie Abrams"

    @property
    def search_url(self) -> str:
        return "https://shop.gracieabrams.com/search?q=signed"

    @property
    def base_url(self) -> str:
        return "https://shop.gracieabrams.com"

    def fetch_products(self) -> list:
        search_term = 'signed'

        search_html = self.fetch_url(self.search_url)
        if not search_html:
            return []

        url_re = re.compile(
            rf'(/products/[^"\s?]*?{search_term}[^"\s?]*)',
            flags=re.IGNORECASE
        )

        matches = list(set(url_re.findall(search_html)))
        items = [
            self.base_url + m if not m.startswith('http') else m
            for m in matches
        ]

        self.last_fetch_had_results = True
        self.log(f"Found {len(items)} product URLs to check")
        products = []

        for item_url in items:
            time.sleep(2)

            html = self.fetch_url(item_url)
            if not html:
                continue

            if '404 not found' in html.lower() or 'page not found' in html.lower():
                self.log(f"404 Not Found: {item_url}")
                continue

            is_sold_out = (
                '<strong>Sorry Sold out</strong>' in html or
                'aria-disabled="true"' in html or
                'sold-out' in html.lower() or
                'sold_out' in html.lower()
            )
            sold_out_count = html.lower().count('sold out')

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
        return []

    def get_email_subject(self, new_products: list, timestamp: str) -> str:
        return f"✨ Gracie Abrams SIGNED Items Alert! - {len(new_products)} item(s) - {timestamp}"

    def get_email_intro(self) -> str:
        return "SIGNED GRACIE ABRAMS ITEMS ARE AVAILABLE! ✨\n"


def run_checker(quiet: bool = False):
    checker = GracieAbramsChecker(quiet=quiet)
    checker.run()


if __name__ == "__main__":
    run_checker()
