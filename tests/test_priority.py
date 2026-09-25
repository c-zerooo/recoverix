import pytest
from backend.app.scoring.priority import determine_priority

def test_priority_unrecoverable():
    assert determine_priority("DOCUMENT", "password", "UNRECOVERABLE") == "LOW"

def test_priority_critical():
    assert determine_priority("DOCUMENT", "user password=secret", "FULLY_RECOVERED") == "CRITICAL"
    assert determine_priority("SYSTEM_TRACE", "sudo_exec /bin/bash", "PARTIALLY_RECOVERED") == "CRITICAL"

def test_priority_high():
    assert determine_priority("DATABASE_LOG", "transaction amount 500", "FULLY_RECOVERED") == "HIGH"
    assert determine_priority("SYSTEM_TRACE", "auth_failure for admin", "FULLY_RECOVERED") == "HIGH"
    assert determine_priority("PHOTO_MEDIA", None, "FULLY_RECOVERED") == "HIGH"

def test_priority_medium():
    assert determine_priority("DOCUMENT", "regular notes", "FULLY_RECOVERED") == "MEDIUM"
    assert determine_priority("DATABASE_LOG", "empty log", "FULLY_RECOVERED") == "MEDIUM"
    assert determine_priority("SYSTEM_TRACE", "system boot", "FULLY_RECOVERED") == "MEDIUM"

def test_priority_low():
    assert determine_priority("BINARY_ARCHIVE", None, "FULLY_RECOVERED") == "LOW"
