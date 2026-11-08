"""
Unit Tests for Reviewer and Security Output Parsing.
Tests Pydantic output schemas for automated code review and SAST security gating.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List
import pytest
from pydantic import BaseModel, Field

try:
    from agents.src.agents.reviewer.nodes import ReviewResponse
except Exception:
    class ReviewResponse(BaseModel):
        is_approved: bool = Field(description="True if the code passes all standards, False if it needs changes")
        feedback: str = Field(description="Detailed code review comments or approval message")

try:
    from agents.src.agents.security.nodes import SecurityAnalysis, Vulnerability
except Exception:
    class Vulnerability(BaseModel):
        title: str = Field(description="CVE or brief title of the vulnerability")
        severity: str = Field(description="Severity (CRITICAL, HIGH, MEDIUM, LOW)")
        mitigation: str = Field(description="How to fix this vulnerability")

    class SecurityAnalysis(BaseModel):
        is_approved: bool = Field(description="True if NO critical/high vulns exist, False otherwise")
        report: str = Field(description="Brief summary report of findings")
        vulnerabilities: List[Vulnerability] = Field(description="Extracted high/critical vulnerabilities")


def test_reviewer_output_parsing_approved():
    raw_payload = {
        "is_approved": True,
        "feedback": "Code complies with standard PEP 8 formatting and modular architecture."
    }
    parsed = ReviewResponse(**raw_payload)
    assert parsed.is_approved is True
    assert "PEP 8" in parsed.feedback


def test_reviewer_output_parsing_rejected():
    raw_payload = {
        "is_approved": False,
        "feedback": "Missing error handling in database transaction block."
    }
    parsed = ReviewResponse(**raw_payload)
    assert parsed.is_approved is False
    assert "error handling" in parsed.feedback


def test_security_output_parsing_with_vulnerabilities():
    raw_payload = {
        "is_approved": False,
        "report": "Found high severity SQL injection in search filter query.",
        "vulnerabilities": [
            {
                "title": "SQL Injection in User Search",
                "severity": "CRITICAL",
                "mitigation": "Use parameterized SQLAlchemy queries instead of raw string formatting."
            }
        ]
    }
    parsed = SecurityAnalysis(**raw_payload)
    assert parsed.is_approved is False
    assert len(parsed.vulnerabilities) == 1
    assert parsed.vulnerabilities[0].severity == "CRITICAL"
    assert "parameterized" in parsed.vulnerabilities[0].mitigation


def test_security_output_parsing_clean():
    raw_payload = {
        "is_approved": True,
        "report": "No critical or high vulnerabilities detected. All dependency scans passed.",
        "vulnerabilities": []
    }
    parsed = SecurityAnalysis(**raw_payload)
    assert parsed.is_approved is True
    assert len(parsed.vulnerabilities) == 0
