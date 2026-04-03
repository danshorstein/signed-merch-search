"""
Base class for product checkers.
All site-specific checkers should inherit from this.

Fetching strategy (for Shopify sites with use_playwright = True):
  1. Try requests first (fast, lightweight)
  2. If blocked (429 / bot challenge), fall back to Playwright headless browser
  3. Non-Shopify sites always use requests only
"""
import os
import sys
import json
import time
from datetime import datetime, timedelta
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


# How many days of logs to keep
LOG_RETENTION_DAYS = 30

# How many consecutive failures before alerting
FAILURE_ALERT_THRESHOLD = 3


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

    Optional overrides:
        - use_playwright: bool = False  (enables Playwright as fallback)
        - fetch_products() -> list[dict]  (for custom fetch logic)
    """

    # Common HTTP headers to look like a browser
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    }

    # Subclasses set True to enable Playwright fallback for bot-protected sites
    use_playwright = False

    def __init__(self, quiet: bool = False):
        """
        Initialize the checker.

        Args:
            quiet: If True, suppress verbose logging
        """
        self.quiet = quiet
        self._ensure_directories()
        self._rotate_logs()

        # Playwright browser/page managed per run
        self._browser = None
        self._browser_context = None
        self._page = None
        self._playwright = None

        # Email config from environment
        self.email_sender = os.getenv('EMAIL_SENDER')
        self.email_password = os.getenv('EMAIL_PASSWORD')
        self.email_recipients = os.getenv('EMAIL_RECIPIENTS', '').split(',')

    def _ensure_directories(self):
        """Ensure data directories exist."""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        SEEN_DIR.mkdir(parents=True, exist_ok=True)

    def _rotate_logs(self):
        """Remove log entries older than LOG_RETENTION_DAYS."""
        if not self.log_file.exists():
            return

        cutoff = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
        kept_lines = []

        try:
            with open(self.log_file, 'r') as f:
                for line in f:
                    if line.startswith('[') and ']' in line:
                        try:
                            ts_str = line[1:line.index(']')]
                            ts = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
                            if ts >= cutoff:
                                kept_lines.append(line)
                        except ValueError:
                            kept_lines.append(line)
                    else:
                        kept_lines.append(line)

            with open(self.log_file, 'w') as f:
                f.writelines(kept_lines)
        except Exception:
            pass

    # --- Abstract properties ---

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
        """Parse products from BeautifulSoup object."""
        pass

    @abstractmethod
    def get_email_subject(self, new_products: list, timestamp: str) -> str:
        pass

    @abstractmethod
    def get_email_intro(self) -> str:
        pass

    # --- File paths ---

    @property
    def _safe_name(self) -> str:
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

    @property
    def _failure_file(self) -> Path:
        return SEEN_DIR / f"{self._safe_name}_failures.json"

    # --- Playwright browser helpers ---

    def _start_browser(self):
        """Launch a headless Chromium browser for this checker's run."""
        if self._browser is not None:
            return

        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._browser_context = self._browser.new_context(
                user_agent=self.HEADERS['User-Agent']
            )
            self._page = self._browser_context.new_page()
        except ImportError:
            self.log("ERROR: playwright not installed. Run: pip3 install playwright && python -m playwright install chromium")
            raise
        except Exception as e:
            self.log(f"ERROR starting browser: {e}")
            raise

    def _stop_browser(self):
        """Close the browser if running."""
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        finally:
            self._browser = None
            self._browser_context = None
            self._page = None
            self._playwright = None

    def get_page_html(self, url: str, wait_ms: int = 1500) -> str | None:
        """
        Fetch a page's HTML using the Playwright browser.
        Call _start_browser() before using this.

        Args:
            url: The URL to navigate to
            wait_ms: Milliseconds to wait after page load for dynamic content

        Returns:
            The page HTML as a string, or None on failure
        """
        if self._page is None:
            self.log("ERROR: Browser not started. Call _start_browser() first.")
            return None

        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=20000)
            self._page.wait_for_timeout(wait_ms)
            return self._page.content()
        except Exception as e:
            self.log(f"ERROR loading {url}: {e}")
            return None

    # --- HTTP helpers with fallback ---

    def _is_blocked(self, response) -> bool:
        """Check if a requests response indicates bot protection."""
        if response.status_code == 429:
            return True
        if response.status_code == 403:
            return True
        if 'Verifying your connection' in response.text[:500]:
            return True
        if 'challenge' in response.text[:1000].lower() and response.status_code != 200:
            return True
        return False

    def fetch_url(self, url: str, timeout: int = 15) -> str | None:
        """
        Fetch a URL's HTML content. Tries requests first.
        If use_playwright is True and requests is blocked, falls back to Playwright.

        Returns:
            HTML string or None on failure
        """
        # Try requests first
        try:
            r = requests.get(url, headers=self.HEADERS, timeout=timeout)
            if not self._is_blocked(r) and r.status_code == 200:
                return r.text
            else:
                if self.use_playwright:
                    self.log(f"Blocked by requests (status {r.status_code}), falling back to Playwright")
                else:
                    self.log(f"ERROR: Status code {r.status_code}")
                    return None
        except Exception as e:
            if self.use_playwright:
                self.log(f"Requests failed ({e}), falling back to Playwright")
            else:
                self.log(f"ERROR fetching {url}: {e}")
                return None

        # Fallback to Playwright
        try:
            self._start_browser()
            return self.get_page_html(url)
        except Exception as e:
            self.log(f"ERROR: Playwright fallback also failed: {e}")
            return None

    # --- Failure tracking ---

    def _load_failures(self) -> dict:
        if self._failure_file.exists():
            try:
                with open(self._failure_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, Exception):
                return {"count": 0, "alerted": False, "last_error": ""}
        return {"count": 0, "alerted": False, "last_error": ""}

    def _save_failures(self, data: dict):
        with open(self._failure_file, 'w') as f:
            json.dump(data, f, indent=2)

    def _record_failure(self, error_msg: str):
        """Record a fetch failure. Alert after FAILURE_ALERT_THRESHOLD consecutive failures."""
        failures = self._load_failures()
        failures["count"] = failures.get("count", 0) + 1
        failures["last_error"] = error_msg
        failures["last_failure"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        if failures["count"] >= FAILURE_ALERT_THRESHOLD and not failures.get("alerted", False):
            subject = f"⚠️ {self.site_name} checker failing! - {failures['count']} consecutive failures"
            body = (
                f"The {self.site_name} product checker has failed {failures['count']} "
                f"times in a row.\n\n"
                f"Last error: {error_msg}\n"
                f"Search URL: {self.search_url}\n\n"
                f"This may indicate the site has changed its bot protection or structure.\n"
                f"You will not be alerted again until the checker recovers and fails again."
            )
            self.send_email(subject, body)
            failures["alerted"] = True
            self.log(f"FAILURE ALERT sent ({failures['count']} consecutive failures)")

        self._save_failures(failures)

    def _record_success(self):
        """Reset failure counter on successful fetch."""
        if self._failure_file.exists():
            self._save_failures({"count": 0, "alerted": False, "last_error": ""})

    # --- Core functionality ---

    def log(self, message: str):
        """Log a message with timestamp."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_line = f"[{timestamp}] {message}"

        if not self.quiet:
            print(log_line)

        with open(self.log_file, 'a') as f:
            f.write(log_line + '\n')

    def load_seen_products(self) -> set:
        if self.seen_products_file.exists():
            try:
                with open(self.seen_products_file, 'r') as f:
                    return set(json.load(f))
            except (json.JSONDecodeError, Exception):
                return set()
        return set()

    def save_seen_products(self, seen_products: set):
        with open(self.seen_products_file, 'w') as f:
            json.dump(list(seen_products), f, indent=2)

    def fetch_products(self) -> list:
        """
        Fetch and parse products from the search URL.
        Uses requests first; falls back to Playwright if use_playwright=True
        and requests gets blocked.
        """
        from bs4 import BeautifulSoup

        html = self.fetch_url(self.search_url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        return self.parse_products(soup)

    def send_email(self, subject: str, body: str) -> bool:
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

        try:
            seen_products = self.load_seen_products()
            products = self.fetch_products()

            if not products:
                self.log("No products found or fetch failed")
                self._record_failure(f"No products returned from {self.search_url}")
                return

            # Successful fetch
            self._record_success()

            new_products = []
            all_current_urls = set()

            for product in products:
                clean_url = product['url'].split('?')[0]
                all_current_urls.add(clean_url)

                if clean_url not in seen_products:
                    new_products.append(product)

            if new_products:
                subject = self.get_email_subject(new_products, timestamp)
                body = self.build_email_body(new_products)

                if self.send_email(subject, body):
                    seen_products.update(all_current_urls)
                    self.save_seen_products(seen_products)
                    self.log(f"Updated seen products with {len(all_current_urls)} URLs")

                    with open(self.lock_file, 'w') as f:
                        f.write(f'sent at {timestamp}\nNew items: {len(new_products)}')
            else:
                self.log(f"OK - {len(products)} items, no new products")
                self.save_seen_products(seen_products)

        finally:
            # Always clean up browser if it was started
            self._stop_browser()
