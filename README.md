# Product Searches

Monitors online stores for product availability and sends email notifications when new items appear.

## Supported Sites

| Site | Command | What it monitors |
|------|---------|------------------|
| Jonas Brothers Store | `jonas` | Signed items at shop.jonasbrothers.com |
| Banquet Records (Noah Kahan) | `noah` | Signed Noah Kahan items at banquetrecords.com |
| Noah Kahan Official Store | `noah-store` | Signed items at noahkahan.com |


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
python run_checker.py jonas
python run_checker.py noah

# Run quietly (for cron)
python run_checker.py --quiet

# List available sites
python run_checker.py --list

# Run all available sites
python run_checker.py --all
```

## Adding a New Site

1. Create a new file in `sites/` (e.g., `sites/taylor_swift.py`)
2. Inherit from `ProductChecker` and implement:
   - `site_name` - Human-readable name
   - `search_url` - URL to check
   - `base_url` - Base URL for link resolution
   - `parse_products(soup)` - Parse HTML and return list of products
   - `get_email_subject()` - Email subject line
   - `get_email_intro()` - Email intro text

3. Register in `run_checker.py`:
   ```python
   CHECKERS = {
       'jonas': ('sites.jonas_brothers', 'JonasBrothersChecker'),
       'noah': ('sites.banquet_records', 'NoahKahanChecker'),
       'taylor': ('sites.taylor_swift', 'TaylorSwiftChecker'),  # Add your new site
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
├── sites/                  # Site-specific parsers
│   ├── base.py             # Base ProductChecker class
│   ├── jonas_brothers.py   # Jonas Brothers store checker
│   └── banquet_records.py  # Banquet Records (Noah Kahan) checker
└── data/                   # Data files (not in git)
    ├── logs/               # Per-site log files
    └── seen/               # Seen products JSON + lock files
```

## Cron Setup

To run every minute (checks all default sites):
```bash
* * * * * cd /path/to/product_searches && /path/to/product_searches/venv/bin/python run_checker.py --quiet
```
