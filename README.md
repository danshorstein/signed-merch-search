# Product Searches

Monitors online stores for signed merchandise availability and sends email notifications when new items appear.

## Supported Sites

| Site | Command | What it monitors |
|------|---------|------------------|
| Jonas Brothers Store | `jonas` | Signed items at shop.jonasbrothers.com |
| Banquet Records (Noah Kahan) | `noah` | Signed Noah Kahan items at banquetrecords.com |
| Noah Kahan Official Store | `noah-store` | Signed items at noahkahan.com |
| Benson Boone Store | `benson` | Signed items at store.bensonboone.com |
| Gracie Abrams Store | `gracie` | Signed items at shop.gracieabrams.com |
| Role Model Store | `rolemodel` | Signed items at shop.heyrolemodel.com |
| Taylor Swift Official Store | `taylor` | All new items + signed restock alerts at store.taylorswift.com |


## Setup

1. **Install dependencies:**
   ```bash
   pip3 install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your email credentials
   ```

## Usage

```bash
# Run all enabled sites
python run_checker.py

# Run a specific site
python run_checker.py benson
python run_checker.py gracie rolemodel

# Run quietly (for cron)
python run_checker.py --quiet

# List available sites
python run_checker.py --list

# Run all available sites
python run_checker.py --all
```

## Adding a New Site

1. Create a new file in `sites/` (e.g., `sites/new_artist.py`)
2. Inherit from `ProductChecker` and implement:
   - `site_name` — Human-readable name
   - `search_url` — URL to check
   - `base_url` — Base URL for link resolution
   - `parse_products(soup)` — Parse HTML and return list of products
   - `get_email_subject()` — Email subject line
   - `get_email_intro()` — Email intro text

   **Tip:** For Shopify stores, you can override `fetch_products()` with regex-based detection instead of BeautifulSoup parsing. See `benson_boone.py` for an example.

3. Register in `run_checker.py`:
   ```python
   CHECKERS = {
       ...
       'new-artist': ('sites.new_artist', 'NewArtistChecker'),
   }
   ```

## Project Structure

```
product_searches/
├── .env                    # Email credentials (not in git)
├── .env.example            # Template for .env
├── .gitignore
├── requirements.txt
├── run_checker.py          # Main entry point
├── sites/                  # Site-specific checkers
│   ├── base.py             # Base ProductChecker class (with 30-day log rotation)
│   ├── jonas_brothers.py   # Jonas Brothers store
│   ├── banquet_records.py  # Banquet Records (Noah Kahan)
│   ├── noah_kahan_store.py # Noah Kahan official store
│   ├── benson_boone.py     # Benson Boone store
│   ├── gracie_abrams.py    # Gracie Abrams store
│   ├── role_model.py       # Role Model store
│   └── taylor_swift.py     # Taylor Swift store (uses JSON API)
├── archive/                # Retired standalone scripts (not in git)
└── data/                   # Runtime data (not in git)
    ├── logs/               # Per-site log files (auto-rotated at 30 days)
    └── seen/               # Seen products JSON + lock files
```

## Cron Setup

To run every minute (checks all default sites):
```bash
* * * * * cd /path/to/product_searches && /path/to/product_searches/venv/bin/python run_checker.py --quiet
```

