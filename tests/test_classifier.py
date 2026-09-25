import pytest
from backend.app.scoring.classifier import classify_artifact

def test_classify_photo():
    assert classify_artifact("png") == "PHOTO_MEDIA"
    assert classify_artifact("jpg") == "PHOTO_MEDIA"

def test_classify_binary():
    assert classify_artifact("exe") == "BINARY_ARCHIVE"
    assert classify_artifact("zip") == "BINARY_ARCHIVE"

def test_classify_database():
    assert classify_artifact("csv") == "DATABASE_LOG"
    assert classify_artifact("sqlite") == "DATABASE_LOG"

def test_classify_system_trace():
    assert classify_artifact("txt", "Failed auth_success from 192.168.1.1") == "SYSTEM_TRACE"
    assert classify_artifact("log", "sudo execution") == "SYSTEM_TRACE"

def test_classify_document():
    assert classify_artifact("txt", "Just a regular document.") == "DOCUMENT"
    assert classify_artifact("doc", None) == "DOCUMENT"
