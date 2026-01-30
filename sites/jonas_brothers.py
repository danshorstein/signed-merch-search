"""
Jonas Brothers Store product checker.
Monitors signed items at shop.jonasbrothers.com
"""
from .base import ProductChecker


class JonasBrothersChecker(ProductChecker):
    """
    Checker for signed Jonas Brothers merchandise.
    
    Target: https://shop.jonasbrothers.com/search?type=product&q=signed*&filter.v.availability=1
    """
    
    @property
    def site_name(self) -> str:
        return "Jonas Brothers"
    
    @property
    def search_url(self) -> str:
        return "https://shop.jonasbrothers.com/search?type=product&q=signed*&filter.v.availability=1"
    
    @property
    def base_url(self) -> str:
        return "https://shop.jonasbrothers.com"
    
    def parse_products(self, soup) -> list:
        """
        Parse Jonas Brothers store search results.
        
        Structure:
            div.grid-product__content
                a.grid-product__link (href)
                div.grid-product__title (title)
                div.grid-product__price (price)
                img.grid__image-contain (image)
        """
        products = []
        
        product_cards = soup.find_all('div', class_='grid-product__content')
        
        for card in product_cards:
            try:
                # Get the main product link
                link_tag = card.find('a', class_='grid-product__link')
                if not link_tag:
                    continue
                
                product_url = link_tag.get('href', '')
                if product_url and not product_url.startswith('http'):
                    product_url = self.base_url + product_url
                
                # Get title
                title_tag = card.find('div', class_='grid-product__title')
                title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"
                
                # Get price
                price_tag = card.find('div', class_='grid-product__price')
                price = price_tag.get_text(strip=True) if price_tag else "Price N/A"
                
                # Get image URL
                img_tag = card.find('img', class_='grid__image-contain')
                image_url = ""
                if img_tag:
                    # Try srcset first, fall back to src
                    image_url = img_tag.get('srcset', img_tag.get('data-srcset', img_tag.get('src', '')))
                    # Get first image from srcset if it contains multiple
                    if ',' in image_url:
                        image_url = image_url.split(',')[0].strip().split(' ')[0]
                    if image_url and not image_url.startswith('http'):
                        image_url = 'https:' + image_url
                
                products.append({
                    'title': title,
                    'price': price,
                    'url': product_url,
                    'image_url': image_url
                })
                
            except Exception as e:
                if not self.quiet:
                    self.log(f"Error parsing product card: {e}")
                continue
        
        return products
    
    def get_email_subject(self, new_products: list, timestamp: str) -> str:
        return f"🎸 Jonas Brothers SIGNED Items Alert! - {len(new_products)} item(s) - {timestamp}"
    
    def get_email_intro(self) -> str:
        return "NEW SIGNED JONAS BROTHERS ITEMS ARE AVAILABLE! 🎸\n"


# Convenience function for direct execution
def run_checker(quiet: bool = False):
    """Run the Jonas Brothers checker."""
    checker = JonasBrothersChecker(quiet=quiet)
    checker.run()


if __name__ == "__main__":
    run_checker()
