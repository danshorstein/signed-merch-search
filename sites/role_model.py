"""
Role Model Store product checker.
Monitors signed items at shop.heyrolemodel.com

Regex-based detection finds product URLs, then checks each product page
for sold-out status. Uses requests first, Playwright fallback.
"""
import re
import time

from .base import ProductChecker


class RoleModelChecker(ProductChecker):
    """
    Checker for signed Role Model merchandise.

    Target: https://shop.heyrolemodel.com/search?q=signed

    Note: Excludes /products/rx-signed-cd which is a known
    non-relevant result.
    """

    use_playwright = True

    EXCLUDE_URLS = [
        'https://shop.heyrolemodel.com/products/rx-signed-cd',
    ]

    @property
    def site_name(self) -> str:
        return "Role Model"

    @property
    def search_url(self) -> str:
        return "https://shop.heyrolemodel.com/search?q=signed"

    @property
    def base_url(self) -> str:
        return "https://shop.heyrolemodel.com"

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

        self.log(f"Found {len(items)} product URLs to check")
        products = []

        for item_url in items:
            clean_url = item_url.split('?')[0]
            if clean_url in self.EXCLUDE_URLS or item_url in self.EXCLUDE_URLS:
                self.log(f"Skipping excluded: {clean_url}")
                continue

            time.sleep(2)

            html = self.fetch_url(item_url)
            if not html:
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
                    'url': clean_url,
                    'image_url': '',
                })
                self.log(f"Found in-stock: {title}")
            else:
                self.log(f"Sold out: {title}")

        return products

    def parse_products(self, soup) -> list:
        return []

    def get_email_subject(self, new_products: list, timestamp: str) -> str:
        return f"🎸 Role Model SIGNED Items Alert! - {len(new_products)} item(s) - {timestamp}"

    def get_email_intro(self) -> str:
        return "SIGNED ROLE MODEL ITEMS ARE AVAILABLE! 🎸\n"


def run_checker(quiet: bool = False):
    checker = RoleModelChecker(quiet=quiet)
    checker.run()


if __name__ == "__main__":
    run_checker()
