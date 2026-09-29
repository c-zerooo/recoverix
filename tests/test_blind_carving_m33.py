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


# ═════════════════════════════════════════════════════════════════════════════
# BLIND TXT & CSV CANDIDATE GENERATION TESTS (Cases 24 - 41)
# ═════════════════════════════════════════════════════════════════════════════

def test_24_raw_txt_embedded_in_binary_noise():
    """24. Raw unannotated TXT embedded inside arbitrary binary noise."""
    prefix = b"\x00\xFF\xFE\x01\x02\x03\xDE\xAD\xBE\xEF"
    txt_doc = (
        b"Incident Response Forensic Report\n"
        b"Timestamp: 2026-09-29T12:00:00Z\n"
        b"Status: All core subsystem operations verified\n"
    )
    suffix = b"\x12\x34\x56\x78\x9A\xBC\xDE\xF0\xFF\xEE\xDD\xCC"
    evidence = prefix + txt_doc + suffix

    candidates = scan_evidence(evidence)
    txt_cands = [c for c in candidates if c.format == "txt"]

    assert len(txt_cands) == 1
    cand = txt_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(txt_doc)
    assert cand.format == "txt"
    assert cand.mime_type == "text/plain"
    assert cand.category == "text"
    assert cand.detection_method == "heuristic_text_run"

    carved = evidence[cand.offset:cand.estimated_end_offset]
    assert carved == txt_doc

    from backend.app.recovery.validators.text import validate_txt
    val_res = validate_txt(carved)
    assert val_res.valid is True
    assert len(val_res.errors) == 0


def test_25_raw_comma_csv_embedded_in_binary_noise():
    """25. Raw unannotated comma-delimited CSV embedded inside binary noise."""
    prefix = b"\xAA\xBB\xCC\x00\x01\x02\x03"
    csv_doc = (
        b"id,name,role,department\n"
        b"101,Alice,Admin,Security\n"
        b"102,Bob,Analyst,Forensics\n"
        b"103,Charlie,Auditor,Compliance\n"
    )
    suffix = b"\x00\x00\xFF\xFE\xFD\xFC"
    evidence = prefix + csv_doc + suffix

    candidates = scan_evidence(evidence)
    csv_cands = [c for c in candidates if c.format == "csv"]
    txt_cands = [c for c in candidates if c.format == "txt"]

    # Both CSV and TXT candidates are emitted for valid tabular text
    assert len(csv_cands) == 1
    assert len(txt_cands) == 1

    cand = csv_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(csv_doc)
    assert cand.format == "csv"
    assert cand.mime_type == "text/csv"
    assert cand.detection_method == "heuristic_text_run"

    carved = evidence[cand.offset:cand.estimated_end_offset]
    assert carved == csv_doc

    from backend.app.recovery.validators.csv import validate_csv
    val_res = validate_csv(carved)
    assert val_res.valid is True
    assert len(val_res.errors) == 0


def test_26_raw_semicolon_csv_embedded_in_binary_noise():
    """26. Raw semicolon-delimited CSV embedded inside binary noise."""
    prefix = b"\x00\x81\x82\x83\x00\x84"
    csv_doc = (
        b"id;name;department;level\n"
        b"201;Dave;Security;Lead\n"
        b"202;Eve;Engineering;Senior\n"
        b"203;Frank;Operations;Staff\n"
    )
    suffix = b"\x00\x85\x86\x87"
    evidence = prefix + csv_doc + suffix

    candidates = scan_evidence(evidence)
    csv_cands = [c for c in candidates if c.format == "csv"]

    assert len(csv_cands) == 1
    cand = csv_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(csv_doc)

    carved = evidence[cand.offset:cand.estimated_end_offset]
    from backend.app.recovery.validators.csv import validate_csv
    val_res = validate_csv(carved)
    assert val_res.valid is True
    assert val_res.details.get("delimiter") == ";"


def test_27_raw_tsv_embedded_in_binary_noise():
    """27. Raw tab-delimited TSV embedded inside binary noise."""
    prefix = b"\x00\x01\x02\x03\x04"
    csv_doc = (
        b"metric\tvalue\tstatus\n"
        b"cpu_usage\t42.5\tnormal\n"
        b"mem_usage\t68.1\tnormal\n"
        b"disk_io\t12.0\toptimal\n"
    )
    suffix = b"\x00\x05\x06\x07"
    evidence = prefix + csv_doc + suffix

    candidates = scan_evidence(evidence)
    csv_cands = [c for c in candidates if c.format == "csv"]

    assert len(csv_cands) == 1
    cand = csv_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(csv_doc)

    carved = evidence[cand.offset:cand.estimated_end_offset]
    from backend.app.recovery.validators.csv import validate_csv
    val_res = validate_csv(carved)
    assert val_res.valid is True
    assert val_res.details.get("delimiter") == "\t"


def test_28_raw_pipe_delimited_csv_embedded_in_binary_noise():
    """28. Raw pipe-delimited CSV embedded inside binary noise."""
    prefix = b"\xFF\xFE\x00\x01"
    csv_doc = (
        b"trace_id|service|duration_ms\n"
        b"trc-101|auth_gateway|14.2\n"
        b"trc-102|database_proxy|6.8\n"
        b"trc-103|cache_cluster|1.1\n"
    )
    suffix = b"\x00\xFF\xEE"
    evidence = prefix + csv_doc + suffix

    candidates = scan_evidence(evidence)
    csv_cands = [c for c in candidates if c.format == "csv"]

    assert len(csv_cands) == 1
    cand = csv_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(csv_doc)

    carved = evidence[cand.offset:cand.estimated_end_offset]
    from backend.app.recovery.validators.csv import validate_csv
    val_res = validate_csv(carved)
    assert val_res.valid is True
    assert val_res.details.get("delimiter") == "|"


def test_29_multiple_independent_txt_and_csv_artifacts():
    """29. Multiple independent TXT and CSV artifacts in a single evidence dump."""
    noise1 = b"\x00\xFF\xFE\x01\x02"
    txt_doc = (
        b"Log Entry 001\n"
        b"Component: Authentication Service\n"
        b"Event: User login succeeded\n"
    )
    noise2 = b"\x00\x00\xAA\xBB\xCC\x00"
    csv_doc = (
        b"code,description,severity\n"
        b"ERR_01,Connection timeout,HIGH\n"
        b"ERR_02,Buffer overflow,CRITICAL\n"
        b"ERR_03,Resource exhausted,MEDIUM\n"
    )
    noise3 = b"\x00\xFF\x11\x22"
    evidence = noise1 + txt_doc + noise2 + csv_doc + noise3

    candidates = scan_evidence(evidence)

    txt_candidates = [c for c in candidates if c.format == "txt"]
    csv_candidates = [c for c in candidates if c.format == "csv"]

    assert len(csv_candidates) >= 1
    assert any(c.offset == len(noise1) and c.format == "txt" for c in txt_candidates)
    expected_csv_offset = len(noise1) + len(txt_doc) + len(noise2)
    assert any(c.offset == expected_csv_offset and c.format == "csv" for c in csv_candidates)


def test_30_printable_density_below_90_percent_rejected():
    """30. Evidence run with printable density below 90% is rejected."""
    # Construct a 100-byte run with ~25% non-printable control bytes and 2 newlines
    sparse_run = bytearray(b"Line one of data\nLine two of data\n")
    while len(sparse_run) < 100:
        sparse_run.extend(b"\x01\x02\x03\x04ABCD")
    evidence = b"\x00\xFF" + bytes(sparse_run) + b"\x00\xFF"

    candidates = scan_evidence(evidence)
    text_cands = [c for c in candidates if c.format in ("txt", "csv")]
    assert len(text_cands) == 0


def test_31_fewer_than_two_newlines_rejected():
    """31. Text run with fewer than 2 newlines is rejected by heuristic."""
    prefix = b"\x00\xFF\xFE"
    # Over 64 bytes of printable text, but 0 newlines
    single_line = b"This is a long continuous single line text block without any newline characters at all."
    suffix = b"\x00\xFF\xFE"
    evidence = prefix + single_line + suffix

    candidates = scan_evidence(evidence)
    text_cands = [c for c in candidates if c.format in ("txt", "csv")]
    assert len(text_cands) == 0

    # Over 64 bytes with only 1 newline
    one_newline = b"First half of text before the newline\nsecond half of text without trailing newline"
    evidence2 = prefix + one_newline + suffix
    candidates2 = scan_evidence(evidence2)
    text_cands2 = [c for c in candidates2 if c.format in ("txt", "csv")]
    assert len(text_cands2) == 0


def test_32_candidate_shorter_than_64_bytes_rejected():
    """32. Candidate shorter than 64 bytes is rejected even with 2 newlines."""
    prefix = b"\x00\xFF\xFE"
    short_text = b"Line 1: OK\nLine 2: OK\nLine 3: OK\n"  # 33 bytes
    suffix = b"\x00\xFF\xFE"
    evidence = prefix + short_text + suffix

    candidates = scan_evidence(evidence)
    text_cands = [c for c in candidates if c.format in ("txt", "csv")]
    assert len(text_cands) == 0


def test_33_crlf_newlines_handled():
    """33. Text run with CRLF line endings is correctly detected and bounded."""
    prefix = b"\x00\xFF\xFE\x01\x02"
    crlf_doc = (
        b"Configuration Header\r\n"
        b"Parameter_Alpha = Enabled\r\n"
        b"Parameter_Beta = 4096\r\n"
        b"Parameter_Gamma = Verified\r\n"
    )
    suffix = b"\x00\xFF\xFE"
    evidence = prefix + crlf_doc + suffix

    candidates = scan_evidence(evidence)
    txt_cands = [c for c in candidates if c.format == "txt"]

    assert len(txt_cands) == 1
    cand = txt_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(crlf_doc)
    assert evidence[cand.offset:cand.estimated_end_offset] == crlf_doc


def test_34_utf8_multibyte_text():
    """34. Multi-byte UTF-8 characters maintain exact byte offsets without drift."""
    prefix = b"\x00\x01\x02\x03\x04"
    utf8_doc = (
        "Отчёт о расследовании инцидента:\n"
        "Статус: Успешно завершено\n"
        "Подсистема: Защищённое хранилище 🔐\n"
    ).encode("utf-8")
    suffix = b"\x00\x05\x06\x07"
    evidence = prefix + utf8_doc + suffix

    candidates = scan_evidence(evidence)
    txt_cands = [c for c in candidates if c.format == "txt"]

    assert len(txt_cands) == 1
    cand = txt_cands[0]
    assert cand.offset == len(prefix)
    assert cand.estimated_end_offset == len(prefix) + len(utf8_doc)
    carved = evidence[cand.offset:cand.estimated_end_offset]
    assert carved == utf8_doc

    from backend.app.recovery.validators.text import validate_txt
    val_res = validate_txt(carved)
    assert val_res.valid is True


def test_35_ragged_csv_emitted_only_as_txt():
    """35. Text with varying comma counts fails CSV validation and is emitted strictly as TXT."""
    prefix = b"\x00\xFF\xAA\xBB"
    ragged_doc = (
        b"In the beginning, when the system was initialized, nodes reported status OK.\n"
        b"Later, after several minutes, a warning occurred.\n"
        b"Finally, the system recovered successfully.\n"
    )
    suffix = b"\x00\xCC\xDD\xEE"
    evidence = prefix + ragged_doc + suffix

    candidates = scan_evidence(evidence)
    csv_cands = [c for c in candidates if c.format == "csv"]
    txt_cands = [c for c in candidates if c.format == "txt"]

    assert len(csv_cands) == 0
    assert len(txt_cands) == 1
    assert txt_cands[0].offset == len(prefix)


def test_36_embedded_nul_byte_splits_runs():
    """36. Embedded NUL byte acts as a hard boundary separating two independent runs."""
    prefix = b"\x00\x01\x02"
    doc1 = (
        b"Block 1: System analysis report\n"
        b"Date: 2026-09-29\n"
        b"Status: First segment completed\n"
    )
    nul_gap = b"\x00\x00\x00\x00"
    doc2 = (
        b"Block 2: Forensic evidence dump\n"
        b"Date: 2026-09-30\n"
        b"Status: Second segment completed\n"
    )
    suffix = b"\x00\x03\x04"
    evidence = prefix + doc1 + nul_gap + doc2 + suffix

    candidates = scan_evidence(evidence)
    txt_cands = [c for c in candidates if c.format == "txt"]

    assert len(txt_cands) == 2
    assert txt_cands[0].offset == len(prefix)
    assert txt_cands[0].estimated_end_offset == len(prefix) + len(doc1)
    assert b"\x00" not in evidence[txt_cands[0].offset:txt_cands[0].estimated_end_offset]

    expected_offset2 = len(prefix) + len(doc1) + len(nul_gap)
    assert txt_cands[1].offset == expected_offset2
    assert txt_cands[1].estimated_end_offset == expected_offset2 + len(doc2)
    assert b"\x00" not in evidence[txt_cands[1].offset:txt_cands[1].estimated_end_offset]


def test_37_synthetic_harness_unchanged():
    """37. Synthetic harness candidates are preserved without duplicate heuristic candidates."""
    from backend.app.recovery.signatures import SYNTHETIC_START_MARKER, SYNTHETIC_END_MARKER
    synthetic_artifact = (
        SYNTHETIC_START_MARKER
        + b"\nfilename: note.txt\ndata: line 1 content\nline 2 content\n"
        + SYNTHETIC_END_MARKER
    )
    padding = b"\x00" * 32
    evidence = padding + synthetic_artifact + padding

    candidates = scan_evidence(evidence)

    assert len(candidates) == 1
    assert candidates[0].format == "txt"
    assert candidates[0].detection_method == "synthetic_boundary"


def test_38_deterministic_scanning_and_input_immutability():
    """38. Repeated scans produce byte-identical candidate attributes without mutating input."""
    evidence = bytearray(
        b"\x00\xFF"
        + b"id,val,flag\n1,alpha,true\n2,beta,false\n3,gamma,true\n"
        + b"\xAA\xBB"
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

    assert bytes(evidence) == copy_evidence


def test_39_adversarial_printable_ascii_insufficient_newlines():
    """39. Adversarial dense printable ASCII data with only 1 newline is rejected."""
    dense_ascii = (b"A" * 60) + b"\n" + (b"B" * 60)  # 121 bytes, 1 newline
    evidence = b"\x00\xFF" + dense_ascii + b"\x00\xFF"

    candidates = scan_evidence(evidence)
    text_cands = [c for c in candidates if c.format in ("txt", "csv")]
    assert len(text_cands) == 0


def test_40_adversarial_source_code_emitted_as_txt():
    """40. Python source code is detected as TXT and rejected as CSV."""
    prefix = b"\x00\xFF\x01\x02"
    code_doc = (
        b"def process_evidence(buffer, max_len):\n"
        b"    results = []\n"
        b"    for item in buffer:\n"
        b"        results.append(item.strip())\n"
        b"    return results\n"
    )
    suffix = b"\x00\xFE\x03\x04"
    evidence = prefix + code_doc + suffix

    candidates = scan_evidence(evidence)
    csv_cands = [c for c in candidates if c.format == "csv"]
    txt_cands = [c for c in candidates if c.format == "txt"]

    assert len(csv_cands) == 0
    assert len(txt_cands) == 1
    assert txt_cands[0].offset == len(prefix)
    assert txt_cands[0].estimated_end_offset == len(prefix) + len(code_doc)


def test_41_adjacent_text_runs_separated_by_binary_noise():
    """41. Two adjacent text runs separated by binary noise are both detected cleanly."""
    noise_sep = b"\xDE\xAD\xBE\xEF\x01\x02\xFF"
    txt1 = (
        b"Section Alpha: Overview\n"
        b"Timestamp: 2026-09-29\n"
        b"Details: Initialized component\n"
    )
    txt2 = (
        b"Section Beta: Results\n"
        b"Timestamp: 2026-09-30\n"
        b"Details: Verification passed\n"
    )
    evidence = b"\x00" + txt1 + noise_sep + txt2 + b"\x00"

    candidates = scan_evidence(evidence)
    txt_cands = [c for c in candidates if c.format == "txt"]

    assert len(txt_cands) == 2
    assert txt_cands[0].offset == 1
    assert txt_cands[0].estimated_end_offset == 1 + len(txt1)
    expected_offset2 = 1 + len(txt1) + len(noise_sep)
    assert txt_cands[1].offset == expected_offset2
    assert txt_cands[1].estimated_end_offset == expected_offset2 + len(txt2)
