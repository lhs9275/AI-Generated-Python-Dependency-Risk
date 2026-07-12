import inspect
from scraper import crawl_with_scraper
def test_url_str():
    ann = inspect.signature(crawl_with_scraper).parameters["url"].annotation
    assert ann in (str, "str")
