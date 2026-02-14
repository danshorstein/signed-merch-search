#!/usr/bin/env python3
"""
Product Availability Checker
Run specific site checkers or all enabled sites.

Usage:
    python run_checker.py                    # Run all enabled sites
    python run_checker.py jonas              # Run Jonas Brothers only
    python run_checker.py --list             # List available sites
    python run_checker.py --quiet jonas      # Run quietly (minimal output)
"""
import argparse
import os
import sys

# Change to script directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Registry of available checkers
CHECKERS = {
    'jonas': ('sites.jonas_brothers', 'JonasBrothersChecker'),
    'noah': ('sites.banquet_records', 'NoahKahanChecker'),
    'noah-store': ('sites.noah_kahan_store', 'NoahKahanStoreChecker'),
    'benson': ('sites.benson_boone', 'BensonBooneChecker'),
    'gracie': ('sites.gracie_abrams', 'GracieAbramsChecker'),
    'rolemodel': ('sites.role_model', 'RoleModelChecker'),
    'taylor': ('sites.taylor_swift', 'TaylorSwiftChecker'),
    # Add more sites here as you create them:
}

# Sites to run by default (when no specific site is specified)
DEFAULT_SITES = ['jonas', 'noah', 'noah-store', 'benson', 'gracie', 'rolemodel', 'taylor']



def get_checker_class(site_key: str):
    """Dynamically import and return a checker class."""
    if site_key not in CHECKERS:
        print(f"Error: Unknown site '{site_key}'")
        print(f"Available sites: {', '.join(CHECKERS.keys())}")
        sys.exit(1)
    
    module_name, class_name = CHECKERS[site_key]
    
    try:
        import importlib
        module = importlib.import_module(module_name)
        return getattr(module, class_name)
    except Exception as e:
        print(f"Error loading checker for '{site_key}': {e}")
        sys.exit(1)


def list_sites():
    """Print available sites."""
    print("Available sites:")
    for key, (module, cls) in CHECKERS.items():
        default_marker = " (default)" if key in DEFAULT_SITES else ""
        print(f"  {key}{default_marker}")


def main():
    parser = argparse.ArgumentParser(
        description="Check product availability across multiple sites"
    )
    parser.add_argument(
        'sites',
        nargs='*',
        help='Site(s) to check (default: all enabled sites)'
    )
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List available sites'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Quiet mode (minimal output)'
    )
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Run all available sites'
    )
    
    args = parser.parse_args()
    
    if args.list:
        list_sites()
        return
    
    # Determine which sites to run
    if args.all:
        sites_to_run = list(CHECKERS.keys())
    elif args.sites:
        sites_to_run = args.sites
    else:
        sites_to_run = DEFAULT_SITES
    
    # Run each checker
    for site_key in sites_to_run:
        if not args.quiet:
            print(f"\n{'='*50}")
            print(f"Checking: {site_key}")
            print(f"{'='*50}")
        
        CheckerClass = get_checker_class(site_key)
        checker = CheckerClass(quiet=args.quiet)
        checker.run()


if __name__ == "__main__":
    main()
