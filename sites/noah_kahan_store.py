"""
Noah Kahan Official Store product checker.
Monitors signed items at noahkahan.com

This is a Shopify-based store, similar to many artist merch stores.
"""
from .base import ProductChecker


class NoahKahanStoreChecker(ProductChecker):
    """
    Checker for signed items at Noah Kahan's official store.
    
    Target: https://noahkahan.com/search?q=signed
    
    This store uses Shopify with product cards that have:
    - .product_card container
    - .product_card--sold-out class when sold out
    - div.card__title p for title
    - span.price__current for price
    """
    
    @property
    def site_name(self) -> str:
        return "Noah Kahan Store"
    
    @property
    def search_url(self) -> str:
        return "https://noahkahan.com/search?q=signed"
    
    @property
    def base_url(self) -> str:
        return "https://noahkahan.com"
    
    def parse_products(self, soup) -> list:
        """
        Parse Noah Kahan store search results.
        
        Structure (Shopify-based):
            div.product_card (or .product_card--sold-out if out of stock)
                a[href*="/products/"] - product link
                div.card__title p - title
                span.price__current - price
                img - product image
        """
        products = []
        
        # Find all product cards - they have class 'product_card'
        # We need to find elements that have product_card in their class list
        product_cards = soup.find_all('div', class_=lambda c: c and 'product_card' in c)
        
        if not product_cards:
            # Try alternate selectors for Shopify stores
            product_cards = soup.find_all('div', class_='product-card')
            
        if not product_cards:
            # Try finding by product links
            product_links = soup.find_all('a', href=lambda h: h and '/products/' in h)
            for link in product_links:
                # Find the parent card container
                parent = link.find_parent('div', class_=lambda c: c and ('product' in str(c).lower() or 'card' in str(c).lower()))
                if parent and parent not in product_cards:
                    product_cards.append(parent)
        
        self.log(f"Found {len(product_cards)} product cards")
        
        for card in product_cards:
            try:
                # Check if sold out
                card_classes = ' '.join(card.get('class', []))
                if 'sold-out' in card_classes.lower() or 'sold_out' in card_classes.lower():
                    # Skip sold out items
                    continue
                
                # Also check for sold out badge/tag
                sold_out_tag = card.find(class_=lambda c: c and ('sold-out' in str(c).lower() or 'sold_out' in str(c).lower()))
                if sold_out_tag:
                    continue
                
                # Get product link
                link_tag = card.find('a', href=lambda h: h and '/products/' in h)
                if not link_tag:
                    continue
                
                product_path = link_tag.get('href', '')
                if not product_path:
                    continue
                
                if product_path.startswith('http'):
                    product_url = product_path
                else:
                    product_url = self.base_url + product_path
                
                # Get title - try multiple selectors
                title = "Unknown Title"
                title_tag = card.find('p', class_=lambda c: c and 'text_body' in str(c))
                if not title_tag:
                    title_tag = card.find('div', class_='card__title')
                    if title_tag:
                        title_tag = title_tag.find('p') or title_tag
                if not title_tag:
                    title_tag = card.find('h2') or card.find('h3')
                if title_tag:
                    title = title_tag.get_text(strip=True)
                
                # Only include items with "signed" in the title
                if 'signed' not in title.lower():
                    continue
                
                # Get price
                price = "Price N/A"
                price_tag = card.find('span', class_=lambda c: c and 'price' in str(c).lower())
                if not price_tag:
                    price_tag = card.find(class_=lambda c: c and 'price' in str(c).lower())
                if price_tag:
                    price = price_tag.get_text(strip=True)
                
                # Get image
                image_url = ""
                img_tag = card.find('img')
                if img_tag:
                    src = img_tag.get('src', img_tag.get('data-src', ''))
                    if src:
                        if src.startswith('//'):
                            image_url = 'https:' + src
                        elif src.startswith('http'):
                            image_url = src
                        else:
                            image_url = self.base_url + src
                
                products.append({
                    'title': title,
                    'price': price,
                    'url': product_url,
                    'image_url': image_url
                })
                
                self.log(f"Found in-stock: {title} @ {price}")
                
            except Exception as e:
                if not self.quiet:
                    self.log(f"Error parsing product card: {e}")
                continue
        
        self.log(f"Found {len(products)} in-stock signed items")
        return products
    
    def get_email_subject(self, new_products: list, timestamp: str) -> str:
        return f"🎵 Noah Kahan Store SIGNED Alert! - {len(new_products)} item(s) - {timestamp}"
    
    def get_email_intro(self) -> str:
        return "SIGNED NOAH KAHAN ITEMS ARE AVAILABLE AT THE OFFICIAL STORE! 🎵\n"


# Convenience function for direct execution
def run_checker(quiet: bool = False):
    """Run the Noah Kahan Store checker."""
    checker = NoahKahanStoreChecker(quiet=quiet)
    checker.run()


if __name__ == "__main__":
    run_checker()
