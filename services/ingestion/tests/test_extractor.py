from ingestion.extractors.web_extractor import WebExtractor


def test_web_extractor_pulls_main_content():
    html = b"""
    <html><head><title>Doc Title</title></head>
    <body>
      <nav>menu menu menu</nav>
      <main><h1>Hello</h1><p>This is the main body content of the page that should be extracted properly by the extractor library.</p></main>
      <footer>copyright</footer>
    </body></html>
    """
    res = WebExtractor().extract("https://example.com/x", html)

    # Main body extracted, boilerplate stripped
    assert "main body content" in res.text
    assert "menu menu menu" not in res.text
    assert "copyright" not in res.text

    # Title is populated with something reasonable from the document.
    # trafilatura may prefer <title>, <h1>, or og:title depending on heuristics —
    # we don't lock to a specific one, just verify it's non-empty.
    assert res.title
    assert res.title in {"Doc Title", "Hello"}

    # Extension is correctly classified
    assert res.raw_ext == "html"
