"""Tests for radar.config — Settings validation."""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError


def make_settings(**kwargs):
    """Create a Settings instance with given overrides, no env bleed."""
    from radar.config import Settings
    return Settings(**kwargs)


class TestWeightValidation:
    def test_valid_weights_sum_to_one(self):
        s = make_settings(influence_weight=0.4, engagement_weight=0.6)
        assert abs(s.influence_weight + s.engagement_weight - 1.0) < 1e-6

    def test_invalid_weights_raise(self):
        with pytest.raises(ValidationError, match="sum to 1.0"):
            make_settings(influence_weight=0.5, engagement_weight=0.6)

    def test_equal_weights_valid(self):
        s = make_settings(influence_weight=0.5, engagement_weight=0.5)
        assert s.influence_weight == 0.5

    def test_custom_valid_weights(self):
        s = make_settings(influence_weight=0.3, engagement_weight=0.7)
        assert abs(s.influence_weight + s.engagement_weight - 1.0) < 1e-6


class TestSMTPValidation:
    def test_email_disabled_no_smtp_required(self):
        """No SMTP validation fires when email_enabled=False."""
        s = make_settings(email_enabled=False)
        assert not s.email_enabled

    def test_email_enabled_requires_recipients(self):
        with pytest.raises(ValidationError, match="RADAR_EMAIL_TO"):
            make_settings(
                email_enabled=True,
                smtp_host="smtp.example.com",
                smtp_user="user",
                smtp_password="pass",
                # no email_to
            )

    def test_email_enabled_localhost_no_user_raises(self):
        with pytest.raises(ValidationError):
            make_settings(
                email_enabled=True,
                smtp_host="localhost",
                email_to=["test@example.com"],
                # no smtp_user
            )

    def test_email_enabled_with_all_credentials_ok(self):
        s = make_settings(
            email_enabled=True,
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="user@example.com",
            smtp_password="secret",
            email_to=["recipient@example.com"],
        )
        assert s.email_enabled is True


class TestRedditValidation:
    def test_reddit_disabled_no_creds_ok(self):
        s = make_settings(reddit_enabled=False)
        assert not s.reddit_enabled

    def test_reddit_enabled_requires_credentials(self):
        with pytest.raises(ValidationError, match="RADAR_REDDIT_CLIENT"):
            make_settings(reddit_enabled=True)

    def test_reddit_enabled_with_creds_ok(self):
        s = make_settings(
            reddit_enabled=True,
            reddit_client_id="abc",
            reddit_client_secret="xyz",
        )
        assert s.reddit_enabled is True


class TestEmailListParser:
    def test_comma_string_parsed(self):
        s = make_settings(email_enabled=False, email_to="a@x.com,b@x.com")
        assert s.email_to == ["a@x.com", "b@x.com"]

    def test_list_accepted(self):
        s = make_settings(email_enabled=False, email_to=["a@x.com"])
        assert s.email_to == ["a@x.com"]

    def test_empty_string_gives_empty_list(self):
        s = make_settings(email_enabled=False, email_to="")
        assert s.email_to == []


class TestSecretMasking:
    def test_repr_masks_password(self):
        s = make_settings(smtp_password="supersecret")
        assert "supersecret" not in repr(s)
        assert "***" in repr(s)

    def test_repr_masks_client_secret(self):
        s = make_settings(reddit_enabled=False, reddit_client_secret="mysecret")
        assert "mysecret" not in repr(s)

    def test_str_same_as_repr(self):
        s = make_settings()
        assert str(s) == repr(s)


class TestDefaults:
    def test_default_weights(self):
        s = make_settings()
        assert s.influence_weight == 0.4
        assert s.engagement_weight == 0.6

    def test_default_report_size(self):
        s = make_settings()
        assert s.report_size == 5

    def test_default_duplicate_hours(self):
        s = make_settings()
        assert s.duplicate_run_hours == 20

    def test_db_path_default(self):
        s = make_settings()
        assert "catalog.db" in s.db_path
