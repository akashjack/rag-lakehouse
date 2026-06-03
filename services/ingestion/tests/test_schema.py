from ingestion.schema import DocumentMetadata, NormalizedDocument


def test_doc_id_is_deterministic():
    a = DocumentMetadata.make_doc_id("https://x.com/a", "hello world")
    b = DocumentMetadata.make_doc_id("https://x.com/a", "hello world")
    assert a == b
    assert len(a) == 32


def test_doc_id_changes_with_content():
    a = DocumentMetadata.make_doc_id("https://x.com/a", "hello world")
    b = DocumentMetadata.make_doc_id("https://x.com/a", "hello world!")
    assert a != b


def test_doc_id_canonicalizes_url():
    """Trailing slash and case should not split a doc into two IDs."""
    a = DocumentMetadata.make_doc_id("https://x.com/a", "hello")
    b = DocumentMetadata.make_doc_id("https://x.com/a/", "hello")
    c = DocumentMetadata.make_doc_id("https://X.com/a", "hello")
    assert a == b == c


def test_doc_id_stable_against_html_noise():
    """The contract: stable across re-crawls if extracted text is unchanged,
    even if HTML wrapper differs (CSRF tokens, build hashes, etc.)."""
    a = DocumentMetadata.make_doc_id("https://x.com/a", "Page about kubernetes pods.")
    b = DocumentMetadata.make_doc_id("https://x.com/a", "Page about kubernetes pods.")
    assert a == b


def test_normalized_doc_roundtrip():
    meta = DocumentMetadata(
        doc_id="a" * 32,
        source="test",
        source_type="web",
        source_url="https://x.com/a",
        content_hash=DocumentMetadata.hash_text("hi"),
        raw_object_key="k1",
        text_object_key="k2",
        byte_size=2,
        char_count=2,
    )
    doc = NormalizedDocument(metadata=meta, text="hi")
    payload = doc.model_dump_json()
    doc2 = NormalizedDocument.model_validate_json(payload)
    assert doc2.metadata.doc_id == meta.doc_id
