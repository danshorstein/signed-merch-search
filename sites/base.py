"""
Base class for product checkers.
All site-specific checkers should inherit from this.
"""
import os
import sys
import json
import time
import smtplib
from abc import ABC, abstractmethod
from email.mime.text import MIMEText
from pathlib import Path

import requests
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = DATA_DIR / "logs"
SEEN_DIR = DATA_DIR / "seen"


class ProductChecker(ABC):
    """
    Abstract base class for product availability checkers.
    
    Subclasses must implement:
        - site_name: str property
        - search_url: str property
        - base_url: str property
        - parse_products(soup) -> list[dict]
        - get_email_subject(new_products, timestamp) -> str
        - get_email_intro() -> str
    """
    
    # Common HTTP headers to look like a browser
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    def __init__(self, quiet: bool = False):
        """
        Initialize the checker.
        
        Args:
            quiet: If True, suppress verbose logging
        """
        self.quiet = quiet
        self._ensure_directories()
        
        # Email config from environment
        self.email_sender = os.getenv('EMAIL_SENDER')
        self.email_password = os.getenv('EMAIL_PASSWORD')
        self.email_recipients = os.getenv('EMAIL_RECIPIENTS', '').split(',')
    
    def _ensure_directories(self):
        """Ensure data directories exist."""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        SEEN_DIR.mkdir(parents=True, exist_ok=True)
    
    # --- Abstract properties that subclasses must implement ---
    
    @property
    @abstractmethod
    def site_name(self) -> str:
        """Human-readable site name (e.g., 'Jonas Brothers')"""
        pass
    
    @property
    @abstractmethod
    def search_url(self) -> str:
        """URL to check for products"""
        pass
    
    @property
    @abstractmethod
    def base_url(self) -> str:
        """Base URL for the site (for relative link resolution)"""
        pass
    
    @abstractmethod
    def parse_products(self, soup) -> list:
        """
        Parse products from BeautifulSoup object.
        
        Returns:
            List of dicts with at least: title, price, url, image_url
        """
        pass
    
    @abstractmethod
    def get_email_subject(self, new_products: list, timestamp: str) -> str:
        """Return the email subject line for notifications."""
        pass
    
    @abstractmethod
    def get_email_intro(self) -> str:
        """Return the intro text for the notification email."""
        pass
    
    # --- File paths based on site name ---
    
    @property
    def _safe_name(self) -> str:
        """Site name safe for file paths (lowercase, underscores)."""
        return self.site_name.lower().replace(' ', '_').replace("'", "")
    
    @property
    def seen_products_file(self) -> Path:
        return SEEN_DIR / f"{self._safe_name}_seen.json"
    
    @property
    def lock_file(self) -> Path:
        return SEEN_DIR / f"{self._safe_name}_sent.lock"
    
    @property
    def log_file(self) -> Path:
        return LOGS_DIR / f"{self._safe_name}.log"
    
    # --- Core functionality ---
    
    def log(self, message: str):
        """Log a message with timestamp."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_line = f"[{timestamp}] {message}"
        
        if not self.quiet:
            print(log_line)
        
        # Also write to log file
        with open(self.log_file, 'a') as f:
            f.write(log_line + '\n')
    
    def load_seen_products(self) -> set:
        """Load the list of previously seen product URLs."""
        if self.seen_products_file.exists():
            try:
                with open(self.seen_products_file, 'r') as f:
                    return set(json.load(f))
            except (json.JSONDecodeError, Exception):
                return set()
        return set()
    
    def save_seen_products(self, seen_products: set):
        """Save the list of seen product URLs."""
        with open(self.seen_products_file, 'w') as f:
            json.dump(list(seen_products), f, indent=2)
    
    def fetch_products(self) -> list:
        """
        Fetch and parse products from the search URL.
        
        Returns:
            List of product dicts with: title, price, url, image_url
        """
        from bs4 import BeautifulSoup
        
        products = []
        
        try:
            # Add timestamp to URL to bypass caching
            url = self.search_url
            cache_buster = f"&t={int(time.time())}" if "?" in url else f"?t={int(time.time())}"
            url_with_timestamp = f"{url}{cache_buster}"
            
            r = requests.get(url_with_timestamp, headers=self.HEADERS, timeout=15)
            
            if r.status_code != 200:
                self.log(f"ERROR: Status code {r.status_code}")
                return products
            
            soup = BeautifulSoup(r.text, 'html.parser')
            products = self.parse_products(soup)
            
        except Exception as e:
            self.log(f"ERROR fetching products: {e}")
        
        return products
    
    def send_email(self, subject: str, body: str) -> bool:
        """Send email notification."""
        try:
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = self.email_sender
            msg['To'] = ', '.join(self.email_recipients)
            
            self.log("Connecting to SMTP server...")
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp_server:
                smtp_server.login(self.email_sender, self.email_password)
                smtp_server.sendmail(self.email_sender, self.email_recipients, msg.as_string())
                self.log("Email sent successfully!")
            return True
        except Exception as e:
            self.log(f"Failed to send email: {e}")
            return False
    
    def build_email_body(self, new_products: list) -> str:
        """Build the email body for new products."""
        lines = [
            self.get_email_intro(),
            "=" * 50,
            ""
        ]
        
        for i, product in enumerate(new_products, 1):
            lines.append(f"{i}. {product['title']}")
            lines.append(f"   Price: {product['price']}")
            lines.append(f"   Link: {product['url']}")
            lines.append("")
        
        lines.append("=" * 50)
        lines.append(f"\nSearch page: {self.search_url}")
        lines.append("\n(You will only be notified about NEW items)")
        
        return "\n".join(lines)
    
    def run(self):
        """Main execution logic."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        
        # Load previously seen products
        seen_products = self.load_seen_products()
        
        # Fetch current products
        products = self.fetch_products()
        
        if not products:
            self.log("No products found or fetch failed")
            return
        
        # Find NEW products
        new_products = []
        all_current_urls = set()
        
        for product in products:
            # Clean URL for comparison
            clean_url = product['url'].split('?')[0]
            all_current_urls.add(clean_url)
            
            if clean_url not in seen_products:
                new_products.append(product)
        
        if new_products:
            # Send notification
            subject = self.get_email_subject(new_products, timestamp)
            body = self.build_email_body(new_products)
            
            if self.send_email(subject, body):
                # Update seen products only after successful email
                seen_products.update(all_current_urls)
                self.save_seen_products(seen_products)
                self.log(f"Updated seen products with {len(all_current_urls)} URLs")
                
                # Create lock file
                with open(self.lock_file, 'w') as f:
                    f.write(f'sent at {timestamp}\nNew items: {len(new_products)}')
        else:
            self.log(f"OK - {len(products)} items, no new products")
            # Still save in case we need to update the file
            self.save_seen_products(seen_products)
