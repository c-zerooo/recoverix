"""
test_blind_carving_m33.py — Comprehensive test suite for Recoverix Milestone 3.3.1.

Tests blind carving capabilities for:
  - Blind JSON container detection (_scan_json and scan_evidence)
  - XML bounded closing-boundary estimation (_find_xml_closing_boundary and _scan_xml)

Covers all 18+ required verification scenarios:
  1. valid raw JSON object in binary container
  2. valid raw JSON array in binary container
  3. nested object/array
  4. escaped quotes
  5. braces inside strings
  6. multiple JSON containers
  7. truncated JSON
  8. random binary containing accidental braces
  9. invalid JSON grammar
  10. empty object/array behavior
  11. normal XML exact end
  12. nested XML
  13. self-closing root
  14. CDATA containing fake closing tag
  15. comment containing fake closing tag
  16. attribute containing fake closing sequence
  17. truncated XML
  18. XML followed by large binary tail
  19. Candidate offset precision & byte-level bounding
  20. Deterministic scanning & input immutability
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from backend.app.recovery.scanner import (
    Candidate,
    scan_evidence,
    _find_xml_closing_boundary,
    _scan_json,
    _scan_xml,
)
from backend.app.recovery.signatures import XML_HEADER_SIGNATURE


# ═════════════════════════════════════════════════════════════════════════════
# JSON BLIND CONTAINER TESTS (Cases 1 - 10)
# ═════════════════════════════════════════════════════════════════════════════

def test_1_valid_raw_json_object_in_binary_container():
    """1. Valid raw JSON object embedded inside arbitrary binary noise."""
    prefix = b"\x00\xFF\xAA\x55\xDE\xAD\xBE\xEF\x01\x02\x03\x04"
    json_doc = b'{"case_id": "REC-901", "status": "ACTIVE", "score": 98.5, "verified": true}'
    suffix = b"\x12\x34\x56\x78\x9A\xBC\xDE\xF0\xFF\xEE\xDD\xCC"
    evidence = prefix + json_doc + suffix

    candidates = scan_evidence(evidence)
    json_cands = [c for c in candidates if c.format == "json"]

    assert len(json_cands) == 1
    cand = json_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(json_doc)
    assert cand.format == "json"
    assert cand.mime_type == "application/json"
    assert cand.category == "structured"
    assert cand.detection_method == "syntax_boundary"

    carved = evidence[cand.offset:cand.estimated_end_offset]
    assert carved == json_doc
    parsed = json.loads(carved.decode("utf-8"))
    assert parsed["case_id"] == "REC-901"
    assert parsed["score"] == 98.5


def test_2_valid_raw_json_array_in_binary_container():
    """2. Valid raw JSON array embedded inside arbitrary binary noise."""
    prefix = b"\xCA\xFE\xBA\xBE\x00\x00\x00\x00"
    json_doc = b'["item_alpha", 12345, true, null, {"sub_key": "sub_val"}]'
    suffix = b"\xDE\xAD\xC0\xDE\x11\x22\x33\x44"
    evidence = prefix + json_doc + suffix

    candidates = scan_evidence(evidence)
    json_cands = [c for c in candidates if c.format == "json"]

    assert len(json_cands) == 1
    cand = json_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(json_doc)
    assert cand.format == "json"

    carved = evidence[cand.offset:cand.estimated_end_offset]
    assert carved == json_doc
    parsed = json.loads(carved.decode("utf-8"))
    assert isinstance(parsed, list)
    assert len(parsed) == 5
    assert parsed[0] == "item_alpha"


def test_3_nested_object_array_structures():
    """3. Deeply nested JSON object and array structures with mixed nesting."""
    prefix = b"\x00" * 32
    json_doc = (
        b'{"level1": {"level2": [{"level3": [1, 2, {"level4": "deep_val", "active": false}]}]}}'
    )
    suffix = b"\xFF" * 32
    evidence = prefix + json_doc + suffix

    candidates = scan_evidence(evidence)
    json_cands = [c for c in candidates if c.format == "json"]

    assert len(json_cands) == 1
    cand = json_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(json_doc)

    carved = evidence[cand.offset:cand.estimated_end_offset]
    parsed = json.loads(carved.decode("utf-8"))
    assert parsed["level1"]["level2"][0]["level3"][2]["level4"] == "deep_val"


def test_4_escaped_quotes_and_backslashes():
    """4. JSON strings containing escaped quotes (\\\") and escaped backslashes (\\\\)."""
    prefix = b"PREFIX_GARBAGE_123"
    json_doc = b'{"msg": "Hello \\"World\\", with \\\\ backslash and \\"nested quotes\\""}'
    suffix = b"SUFFIX_GARBAGE_456"
    evidence = prefix + json_doc + suffix

    candidates = scan_evidence(evidence)
    json_cands = [c for c in candidates if c.format == "json"]

    assert len(json_cands) == 1
    cand = json_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(json_doc)

    carved = evidence[cand.offset:cand.estimated_end_offset]
    parsed = json.loads(carved.decode("utf-8"))
    assert 'Hello "World"' in parsed["msg"]


def test_5_braces_and_brackets_inside_strings():
    """5. Braces and brackets inside string literals do not corrupt container nesting."""
    prefix = b"\xAA\xBB\xCC\xDD"
    json_doc = (
        b'{"payload": "contains {brace} and [bracket] and }closing brace and ]bracket inside str"}'
    )
    suffix = b"\x11\x22\x33\x44"
    evidence = prefix + json_doc + suffix

    candidates = scan_evidence(evidence)
    json_cands = [c for c in candidates if c.format == "json"]

    assert len(json_cands) == 1
    cand = json_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(json_doc)

    carved = evidence[cand.offset:cand.estimated_end_offset]
    parsed = json.loads(carved.decode("utf-8"))
    assert "{brace}" in parsed["payload"]


def test_6_multiple_json_containers():
    """6. Multiple independent JSON documents in a single raw byte stream."""
    doc1 = b'{"doc_id": 101, "title": "First Document"}'
    gap = b"\x00\x01\x02\x03\x04\x05\x06\x07"
    doc2 = b'[100, 200, 300, 400, 500]'
    gap2 = b"\xFF\xFE\xFD\xFC"
    doc3 = b'{"doc_id": 103, "flag": true}'
    evidence = doc1 + gap + doc2 + gap2 + doc3

    candidates = scan_evidence(evidence)
    json_cands = [c for c in candidates if c.format == "json"]

    assert len(json_cands) == 3

    assert json_cands[0].offset == 0
    assert json_cands[0].estimated_end_offset == len(doc1)
    assert evidence[json_cands[0].offset:json_cands[0].estimated_end_offset] == doc1

    assert json_cands[1].offset == len(doc1) + len(gap)
    assert json_cands[1].estimated_end_offset == len(doc1) + len(gap) + len(doc2)
    assert evidence[json_cands[1].offset:json_cands[1].estimated_end_offset] == doc2

    assert json_cands[2].offset == len(doc1) + len(gap) + len(doc2) + len(gap2)
    assert json_cands[2].estimated_end_offset == len(evidence)
    assert evidence[json_cands[2].offset:json_cands[2].estimated_end_offset] == doc3


def test_7_truncated_json_container():
    """7. Truncated JSON container produces candidate with estimated_end_offset=None."""
    prefix = b"LEAD_BYTES_999"
    truncated = b'{"report_id": 999, "items": [{"id": 1}, {"id": 2'
    evidence = prefix + truncated

    candidates = scan_evidence(evidence)
    json_cands = [c for c in candidates if c.format == "json"]

    assert len(json_cands) == 1
    cand = json_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset is None
    assert cand.format == "json"


def test_8_random_binary_containing_accidental_braces():
    """8. Random binary noise containing '{' or '[' characters is rejected."""
    # Fast lookahead or extent scanner rejects non-JSON characters
    noise1 = b"\x00\x01\x02{" + b"\xFF\xFE\xFD\xFC" * 20 + b"}" + b"\x00\x00"
    noise2 = b"\x80\x81[" + b"\xAA\xBB\xCC\xDD" * 20 + b"]" + b"\xFF\xFF"
    evidence = noise1 + noise2

    candidates = scan_evidence(evidence)
    json_cands = [c for c in candidates if c.format == "json"]
    assert len(json_cands) == 0


def test_9_invalid_json_grammar():
    """9. Non-JSON grammar (unquoted keys, missing colons) is rejected as candidates."""
    bad1 = b"PREFIX {unquoted_key: 1234} SUFFIX"
    bad2 = b"PREFIX [true, false, undefined_symbol] SUFFIX"

    cands1 = [c for c in scan_evidence(bad1) if c.format == "json"]
    assert len(cands1) == 0

    cands2 = [c for c in scan_evidence(bad2) if c.format == "json"]
    assert len(cands2) == 0


def test_10_empty_object_and_array():
    """10. Empty object `{}` and empty array `[]` are valid container candidates."""
    prefix = b"START_"
    evidence = prefix + b"{}" + b"_MID_" + b"[]" + b"_END"

    candidates = scan_evidence(evidence)
    json_cands = [c for c in candidates if c.format == "json"]

    assert len(json_cands) == 2
    assert json_cands[0].offset == len(prefix)
    assert json_cands[0].estimated_end_offset == len(prefix) + 2
    assert evidence[json_cands[0].offset:json_cands[0].estimated_end_offset] == b"{}"

    idx2 = len(prefix) + 2 + len(b"_MID_")
    assert json_cands[1].offset == idx2
    assert json_cands[1].estimated_end_offset == idx2 + 2
    assert evidence[json_cands[1].offset:json_cands[1].estimated_end_offset] == b"[]"


# ═════════════════════════════════════════════════════════════════════════════
# XML BOUNDED END SCANNER TESTS (Cases 11 - 18)
# ═════════════════════════════════════════════════════════════════════════════

def test_11_normal_xml_exact_end():
    """11. Normal XML document with exact closing root tag."""
    prefix = b"\x00\x01\x02\x03\x04"
    xml_doc = b'<?xml version="1.0" encoding="UTF-8"?><root><item>Hello XML</item></root>'
    suffix = b"\x05\x06\x07\x08"
    evidence = prefix + xml_doc + suffix

    candidates = scan_evidence(evidence)
    xml_cands = [c for c in candidates if c.format == "xml"]

    assert len(xml_cands) == 1
    cand = xml_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(xml_doc)
    carved = evidence[cand.offset:cand.estimated_end_offset]
    assert carved == xml_doc


def test_12_nested_xml():
    """12. Nested XML elements correctly match the outermost root closing tag."""
    prefix = b"BINARY_HEAD"
    xml_doc = (
        b'<?xml version="1.0"?>'
        b'<catalog>'
        b'  <book id="bk101">'
        b'    <author>Gambardella, Matthew</author>'
        b'    <title>XML Developer\'s Guide</title>'
        b'    <chapters><chapter num="1">Intro</chapter></chapters>'
        b'  </book>'
        b'</catalog>'
    )
    suffix = b"BINARY_TAIL"
    evidence = prefix + xml_doc + suffix

    candidates = scan_evidence(evidence)
    xml_cands = [c for c in candidates if c.format == "xml"]

    assert len(xml_cands) == 1
    cand = xml_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(xml_doc)
    assert evidence[cand.offset:cand.estimated_end_offset] == xml_doc


def test_13_self_closing_root():
    """13. Self-closing root element `<root ... />` correctly bounds at `/>`."""
    prefix = b"\xFF\xFE\xFD"
    xml_doc = b'<?xml version="1.0" encoding="utf-8"?><manifest package="com.app" version="1.0" />'
    suffix = b"\x00\x00\x00"
    evidence = prefix + xml_doc + suffix

    candidates = scan_evidence(evidence)
    xml_cands = [c for c in candidates if c.format == "xml"]

    assert len(xml_cands) == 1
    cand = xml_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(xml_doc)
    assert evidence[cand.offset:cand.estimated_end_offset] == xml_doc


def test_14_cdata_containing_fake_closing_tag():
    """14. CDATA containing `</root>` does not prematurely terminate root boundary."""
    prefix = b"PREFIX_"
    xml_doc = (
        b'<?xml version="1.0"?>'
        b'<root>'
        b'  <data><![CDATA[ </root> <fake> This is CDATA </root> ]]></data>'
        b'  <actual_child>valid content</actual_child>'
        b'</root>'
    )
    suffix = b"_SUFFIX"
    evidence = prefix + xml_doc + suffix

    candidates = scan_evidence(evidence)
    xml_cands = [c for c in candidates if c.format == "xml"]

    assert len(xml_cands) == 1
    cand = xml_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(xml_doc)
    assert evidence[cand.offset:cand.estimated_end_offset] == xml_doc


def test_15_comment_containing_fake_closing_tag():
    """15. XML comment containing `</root>` does not prematurely terminate root boundary."""
    prefix = b"AAA"
    xml_doc = (
        b'<?xml version="1.0"?>'
        b'<root>'
        b'  <!-- </root> fake closing inside comment -->'
        b'  <real_element>data</real_element>'
        b'</root>'
    )
    suffix = b"BBB"
    evidence = prefix + xml_doc + suffix

    candidates = scan_evidence(evidence)
    xml_cands = [c for c in candidates if c.format == "xml"]

    assert len(xml_cands) == 1
    cand = xml_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(xml_doc)
    assert evidence[cand.offset:cand.estimated_end_offset] == xml_doc


def test_16_attribute_containing_fake_closing_sequence():
    """16. Attributes containing `>` or `</root>` inside quotes do not confuse scanner."""
    prefix = b"CCC"
    xml_doc = (
        b'<?xml version="1.0"?>'
        b'<root config="contains > and </root> in value" test=\'also > here\'>'
        b'  <item>clean</item>'
        b'</root>'
    )
    suffix = b"DDD"
    evidence = prefix + xml_doc + suffix

    candidates = scan_evidence(evidence)
    xml_cands = [c for c in candidates if c.format == "xml"]

    assert len(xml_cands) == 1
    cand = xml_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(xml_doc)
    assert evidence[cand.offset:cand.estimated_end_offset] == xml_doc


def test_17_truncated_xml():
    """17. Truncated XML without closing root tag yields estimated_end_offset=None."""
    prefix = b"LEAD"
    truncated_xml = b'<?xml version="1.0"?><root><item>Head section without closing root'
    evidence = prefix + truncated_xml

    candidates = scan_evidence(evidence)
    xml_cands = [c for c in candidates if c.format == "xml"]

    assert len(xml_cands) == 1
    cand = xml_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset is None


def test_18_xml_followed_by_large_binary_tail():
    """18. XML document followed by large trailing binary garbage does not absorb garbage."""
    xml_doc = b'<?xml version="1.0"?><document><header>Metadata</header><body>Text</body></document>'
    large_tail = b"\xDE\xAD\xBE\xEF" * 10_000  # 40 KB tail
    evidence = xml_doc + large_tail

    candidates = scan_evidence(evidence)
    xml_cands = [c for c in candidates if c.format == "xml"]

    assert len(xml_cands) == 1
    cand = xml_cands[0]
    assert cand.offset == 0
    assert cand.estimated_end_offset == len(xml_doc)
    assert evidence[cand.offset:cand.estimated_end_offset] == xml_doc


# ═════════════════════════════════════════════════════════════════════════════
# ADDITIONAL PRECISION, DETERMINISM & BOUNDING TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_19_composite_dump_with_xml_and_json():
    """19. Composite unannotated evidence dump containing both XML and JSON."""
    noise1 = b"\x10\x20\x30\x40" * 8
    xml_doc = b'<?xml version="1.0"?><entry id="e1"><name>Test</name></entry>'
    noise2 = b"\x99\x88\x77\x66" * 12
    json_doc = b'{"record": "R-100", "active": true, "values": [1, 2, 3]}'
    noise3 = b"\x00" * 32

    evidence = noise1 + xml_doc + noise2 + json_doc + noise3
    candidates = scan_evidence(evidence)

    formats = [c.format for c in candidates]
    assert "xml" in formats
    assert "json" in formats

    xml_cand = next(c for c in candidates if c.format == "xml")
    json_cand = next(c for c in candidates if c.format == "json")

    assert xml_cand.offset == len(noise1)
    assert xml_cand.estimated_end_offset == len(noise1) + len(xml_doc)

    expected_json_offset = len(noise1) + len(xml_doc) + len(noise2)
    assert json_cand.offset == expected_json_offset
    assert json_cand.estimated_end_offset == expected_json_offset + len(json_doc)


def test_20_deterministic_scan_and_input_immutability():
    """20. Scan produces byte-identical Candidate attributes and does not mutate input."""
    evidence = bytearray(
        b"\x00\xFF" + b'{"key": "value"}' + b"\xAA\xBB" + b'<?xml version="1.0"?><r/>'
    )
    copy_evidence = bytes(evidence)

    r1 = scan_evidence(evidence)
    r2 = scan_evidence(evidence)

    assert len(r1) == len(r2)
    for c1, c2 in zip(r1, r2):
        assert c1.candidate_id == c2.candidate_id
        assert c1.format == c2.format
        assert c1.offset == c2.offset
        assert c1.estimated_end_offset == c2.estimated_end_offset
        assert c1.detection_method == c2.detection_method

    # Ensure input was not mutated
    assert bytes(evidence) == copy_evidence


# ═════════════════════════════════════════════════════════════════════════════
# XML SAME-NAME ROOT TAG NESTING & TAG-NAME BOUNDARY REGRESSION TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_21_nested_xml_same_name_elements():
    """21. Nested XML with same-name root tags <root><root><item/></root></root> bounds at outer </root>."""
    prefix = b"\xAA\xBB\xCC"
    xml_doc = b'<?xml version="1.0"?><root><root><item/></root></root>'
    suffix = b"\xDD\xEE\xFF"
    evidence = prefix + xml_doc + suffix

    candidates = scan_evidence(evidence)
    xml_cands = [c for c in candidates if c.format == "xml"]

    assert len(xml_cands) == 1
    cand = xml_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(xml_doc)
    carved = evidence[cand.offset:cand.estimated_end_offset]
    assert carved == xml_doc

    from backend.app.recovery.validators.xml import validate_xml
    val_res = validate_xml(carved)
    assert val_res.valid is True
    assert len(val_res.errors) == 0


def test_22_deep_nested_xml_same_name_with_self_closing():
    """22. Deep nested XML <root><root><root/></root></root> bounds at the final outer </root>."""
    prefix = b"\x11\x22\x33"
    xml_doc = b'<?xml version="1.0"?><root><root><root/></root></root>'
    suffix = b"\x44\x55\x66"
    evidence = prefix + xml_doc + suffix

    candidates = scan_evidence(evidence)
    xml_cands = [c for c in candidates if c.format == "xml"]

    assert len(xml_cands) == 1
    cand = xml_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(xml_doc)
    carved = evidence[cand.offset:cand.estimated_end_offset]
    assert carved == xml_doc

    from backend.app.recovery.validators.xml import validate_xml
    val_res = validate_xml(carved)
    assert val_res.valid is True
    assert len(val_res.errors) == 0


def test_23_xml_tag_name_boundary_matching():
    """23. <root><root_item>value</root_item></root> does not increment root depth for <root_item>."""
    prefix = b"\x99\x88"
    xml_doc = b'<?xml version="1.0"?><root><root_item>value</root_item></root>'
    suffix = b"\x77\x66"
    evidence = prefix + xml_doc + suffix

    candidates = scan_evidence(evidence)
    xml_cands = [c for c in candidates if c.format == "xml"]

    assert len(xml_cands) == 1
    cand = xml_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(xml_doc)
    carved = evidence[cand.offset:cand.estimated_end_offset]
    assert carved == xml_doc

    from backend.app.recovery.validators.xml import validate_xml
    val_res = validate_xml(carved)
    assert val_res.valid is True
    assert len(val_res.errors) == 0

