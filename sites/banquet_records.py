"""
Banquet Records store product checker.
Monitors signed items at banquetrecords.com

This store requires checking the product detail page to determine
if signed variants are actually in stock, since the search page
only shows if a product has signed options, not their availability.
"""
import time
import requests
from bs4 import BeautifulSoup

from .base import ProductChecker


class BanquetRecordsChecker(ProductChecker):
    """
    Checker for signed items at Banquet Records.
    
    Note: This checker does a two-step process:
    1. Search for products tagged as signed
    2. Check each product page for in-stock signed variants
    
    This is necessary because the search page doesn't show variant availability.
    """
    
    def __init__(self, artist: str = None, quiet: bool = False):
        """
        Initialize the Banquet Records checker.
        
        Args:
            artist: Optional artist name to filter search (e.g., "Noah Kahan")
            quiet: If True, suppress verbose logging
        """
        self.artist = artist
        super().__init__(quiet=quiet)
    
    @property
    def site_name(self) -> str:
        if self.artist:
            return f"Banquet Records - {self.artist}"
        return "Banquet Records"
    
    @property
    def search_url(self) -> str:
        if self.artist:
            # URL encode the artist name
            artist_query = self.artist.replace(' ', '+')
            return f"https://www.banquetrecords.com/search?q={artist_query}&t=signed"
        return "https://www.banquetrecords.com/search?t=signed"
    
    @property
    def base_url(self) -> str:
        return "https://www.banquetrecords.com"
    
    def parse_products(self, soup) -> list:
        """
        Parse Banquet Records search results.
        
        This gets the list of products from the search page, then checks
        each product's detail page for in-stock signed variants.
        
        Structure:
            a.card.item
                span.artist
                span.title
                span.formats
                span.promo.signed
                img (src)
        """
        products = []
        products_checked = 0
        
        # Find all product cards
        product_cards = soup.find_all('a', class_='card')
        
        for card in product_cards:
            try:
                # Check if this is an "item" card (not a category card)
                if 'item' not in card.get('class', []):
                    continue
                
                # Get product URL
                product_path = card.get('href', '')
                if not product_path:
                    continue
                product_url = self.base_url + '/' + product_path.lstrip('/')
                
                # Get artist
                artist_tag = card.find('span', class_='artist')
                artist = artist_tag.get_text(strip=True) if artist_tag else "Unknown Artist"
                
                # Get title
                title_tag = card.find('span', class_='title')
                title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"
                
                # Get formats
                formats_tag = card.find('span', class_='formats')
                formats = formats_tag.get_text(strip=True) if formats_tag else ""
                
                # Get image
                img_tag = card.find('img')
                image_url = ""
                if img_tag:
                    src = img_tag.get('src', '')
                    if src:
                        if src.startswith('http'):
                            image_url = src
                        else:
                            image_url = self.base_url + '/' + src.lstrip('/')
                
                # Check for signed badge (should always be present due to &t=signed filter)
                signed_badge = card.find('span', class_='signed')
                if not signed_badge:
                    continue  # Skip non-signed items
                
                products_checked += 1
                self.log(f"Checking: {artist} - {title}")
                
                # Now check the product detail page for in-stock signed variants
                signed_variants = self._check_product_page(product_url)
                
                if signed_variants:
                    # Add each in-stock signed variant as a separate product
                    for variant in signed_variants:
                        products.append({
                            'title': f"{artist} - {title}",
                            'variant': variant['name'],
                            'price': variant['price'],
                            'url': product_url,
                            'image_url': image_url,
                            'formats': formats
                        })
                else:
                    self.log(f"  -> No signed variants in stock")
                
            except Exception as e:
                if not self.quiet:
                    self.log(f"Error parsing product card: {e}")
                continue
        
        self.log(f"Checked {products_checked} products, found {len(products)} in-stock signed variants")
        return products
    
    def _check_product_page(self, url: str) -> list:
        """
        Check a product detail page for in-stock signed variants.
        
        Returns:
            List of dicts with variant info: name, price
        """
        signed_variants = []
        
        try:
            # Add cache buster
            cache_buster = f"?t={int(time.time())}" if "?" not in url else f"&t={int(time.time())}"
            url_with_timestamp = f"{url}{cache_buster}"
            
            r = requests.get(url_with_timestamp, headers=self.HEADERS, timeout=15)
            
            if r.status_code != 200:
                return signed_variants
            
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Find all variant rows
            variant_rows = soup.find_all('div', class_='row')
            
            for row in variant_rows:
                # Check if this is a format row
                if 'format' not in row.get('class', []):
                    continue
                
                # Get variant name
                name_div = row.find('div', class_='name')
                if not name_div:
                    continue
                variant_name = name_div.get_text(strip=True)
                
                # Check if this is a signed variant (case insensitive)
                if 'signed' not in variant_name.lower():
                    continue
                
                # Check if it's in stock (has "Add to cart" link)
                add_to_cart = row.find('a', id=lambda x: x and x.startswith('add'))
                if not add_to_cart:
                    # Check for "SOLD OUT" text
                    options_div = row.find('div', class_='options')
                    if options_div and 'sold out' in options_div.get_text().lower():
                        continue
                    # Also check copies div
                    copies_div = row.find('div', class_='copies')
                    if copies_div and '0 left' in copies_div.get_text().lower():
                        continue
                    # No add button found, skip
                    continue
                
                # Get price
                price_div = row.find('div', class_='price')
                price = price_div.get_text(strip=True) if price_div else "Price N/A"
                
                signed_variants.append({
                    'name': variant_name,
                    'price': price
                })
                
        except Exception as e:
            if not self.quiet:
                self.log(f"Error checking product page {url}: {e}")
        
        return signed_variants
    
    def get_email_subject(self, new_products: list, timestamp: str) -> str:
        artist_text = f" {self.artist}" if self.artist else ""
        return f"🎵 Banquet Records{artist_text} SIGNED Alert! - {len(new_products)} item(s) - {timestamp}"
    
    def get_email_intro(self) -> str:
        if self.artist:
            return f"SIGNED {self.artist.upper()} ITEMS ARE IN STOCK AT BANQUET RECORDS! 🎵\n"
        return "SIGNED ITEMS ARE IN STOCK AT BANQUET RECORDS! 🎵\n"
    
    def build_email_body(self, new_products: list) -> str:
        """Override to include variant info."""
        lines = [
            self.get_email_intro(),
            "=" * 50,
            ""
        ]
        
        for i, product in enumerate(new_products, 1):
            lines.append(f"{i}. {product['title']}")
            if product.get('variant'):
                lines.append(f"   Variant: {product['variant']}")
            lines.append(f"   Price: {product['price']}")
            lines.append(f"   Link: {product['url']}")
            lines.append("")
        
        lines.append("=" * 50)
        lines.append(f"\nSearch page: {self.search_url}")
        lines.append("\n(You will only be notified about NEW items)")
        
        return "\n".join(lines)


# Convenience class for Noah Kahan specifically
class NoahKahanChecker(BanquetRecordsChecker):
    """Checker specifically for Noah Kahan signed items."""
    
    def __init__(self, quiet: bool = False):
        super().__init__(artist="Noah Kahan", quiet=quiet)


# Convenience function for direct execution
def run_checker(quiet: bool = False):
    """Run the Noah Kahan checker."""
    checker = NoahKahanChecker(quiet=quiet)
    checker.run()


if __name__ == "__main__":
    run_checker()
