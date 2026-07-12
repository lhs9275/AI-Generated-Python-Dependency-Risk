import pytest
from html_clean import strip_html_tags


def test_simple_tag():
    assert strip_html_tags("<p>Hello <b>world</b></p>") == "Hello world"


def test_amp_entity():
    assert strip_html_tags("Tom &amp; Jerry") == "Tom & Jerry"


def test_lt_gt_entities():
    assert strip_html_tags("a &lt; b &gt; c") == "a < b > c"


def test_empty():
    assert strip_html_tags("") == ""


def test_nbsp_to_space():
    assert strip_html_tags("a&nbsp;b") == "a b"
