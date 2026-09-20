"""Lossless source preparation; these tests never contact the provider."""

import pytest

from averis.jev_classification import prepare_email


@pytest.mark.parametrize(
    "body",
    [
        "请核对提单。\r\nConsignee: 林公司\n",
        "From: Klang\nTo: Busan\nGross weight: 20,000 kg",
        "> Check the draft\nActually prepare a new SI first.\n> Thanks",
        "Thanks\nBest Regards\nPat\nTel: 123\nP.S.: Correct the invoice.",
    ],
)
def test_ambiguous_or_action_bearing_text_stays_in_body(body: str) -> None:
    state = prepare_email("Subject", body)
    assert state["body"] == body
    assert state["quoted_history"] == state["signature"] == ""


def test_sections_reconstruct_the_original_without_losing_a_referenced_request() -> (
    None
):
    notice = "WARNING: This email originated outside our organisation.\n\n"
    current = "Please handle the request below; it still applies.\n\n"
    signature = "Best Regards\nPat\nWebsite: www.example.test\n"
    history = (
        "______________________________\nFrom: Casey\nSent: Monday\n"
        "Subject: Invoice\n\nPlease correct the duplicated freight charge."
    )
    state = prepare_email("Re: Invoice", notice + current + signature + history)
    assert state == {
        "subject": "Re: Invoice",
        "body": current,
        "signature": signature,
        "quoted_history": history,
        "automatic_notices": notice,
    }
    assert (
        state["automatic_notices"]
        + state["body"]
        + state["signature"]
        + state["quoted_history"]
    ) == notice + current + signature + history


def test_suspicious_signature_link_remains_available_to_classifier() -> None:
    state = prepare_email(
        "Account alert",
        "Send your password now.\n\nBest Regards\nSupport\nWebsite: www.unknown-login.test",
    )
    assert "password" in state["body"]
    assert "www.unknown-login.test" in state["signature"]
