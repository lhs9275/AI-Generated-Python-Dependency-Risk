import inspect
from scraper import crawl_with_scraper
def test_callable(): assert callable(crawl_with_scraper)
def test_sig(): assert "url" in inspect.signature(crawl_with_scraper).parameters
