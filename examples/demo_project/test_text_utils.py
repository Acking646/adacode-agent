from text_utils import slugify


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"


def test_slugify_removes_punctuation():
    assert slugify("Hello, World!") == "hello-world"


def test_slugify_collapses_separators():
    assert slugify("  Hello   World  ") == "hello-world"

