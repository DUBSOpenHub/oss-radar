"""SMTP email sender with Jinja2 templates for OSS Radar reports."""

from __future__ import annotations

import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)

from radar.config import Settings
from radar.models import DailyReport, WeeklyReport

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


class EmailSender:
    """Renders Jinja2 templates and dispatches via SMTP with STARTTLS.

    Retries SMTP send once after 60 seconds on failure.
    """

    def __init__(self, config: Settings) -> None:
        self.config = config
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml", "j2"]),
            undefined=StrictUndefined,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_daily(self, report: DailyReport, dry_run: bool = False) -> bool:
        """Render daily template and send.  Returns True on success."""
        date_str = report.report_date.strftime("%Y-%m-%d")
        subject = f"[OSS Radar] Daily Intel — {date_str}"
        html = self._render("daily.html.j2", {"report": report, "date_str": date_str})
        return self._dispatch(subject=subject, html=html, dry_run=dry_run)

    def send_weekly(self, report: WeeklyReport, dry_run: bool = False) -> bool:
        """Render weekly template and send.  Returns True on success."""
        date_str = report.week_start.strftime("%Y-%m-%d")
        subject = f"[OSS Radar] Weekly Digest — Week of {date_str}"
        html = self._render("weekly.html.j2", {"report": report, "date_str": date_str})
        return self._dispatch(subject=subject, html=html, dry_run=dry_run)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _render(self, template_name: str, context: dict) -> str:
        """Load and render a Jinja2 template; returns HTML string."""
        template = self._env.get_template(template_name)
        return template.render(**context)

    def _dispatch(self, subject: str, html: str, dry_run: bool = False) -> bool:
        """Send multipart MIME email; retry once on failure."""
        if dry_run:
            logger.info("dry_run_email_skipped", extra={"subject": subject})
            return True

        recipients = self.config.get_recipients()
        if not recipients:
            logger.warning("no_recipients_configured")
            return False

        msg = self._build_mime(subject=subject, html=html, recipients=recipients)

        for attempt in range(1, 3):
            try:
                self._send_smtp(msg, recipients)
                logger.info(
                    "email_sent",
                    extra={"subject": subject, "recipients": recipients},
                )
                return True
            except Exception as exc:
                logger.warning(
                    "smtp_send_failed",
                    extra={"attempt": attempt, "error": str(exc)},
                )
                if attempt < 2:
                    logger.info("smtp_retry_wait", extra={"seconds": 60})
                    time.sleep(60)

        logger.error("smtp_exhausted", extra={"subject": subject})
        return False

    def _build_mime(
        self, subject: str, html: str, recipients: List[str]
    ) -> MIMEMultipart:
        """Build a multipart/alternative MIME message."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.config.email_from or self.config.smtp_user
        msg["To"] = ", ".join(recipients)

        plain = self._plaintext_fallback(html)
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
        return msg

    def _send_smtp(self, msg: MIMEMultipart, recipients: List[str]) -> None:
        """Connect to SMTP and send; uses STARTTLS when configured."""
        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
            server.ehlo()
            if self.config.smtp_use_tls:
                server.starttls()
                server.ehlo()
            if self.config.smtp_user and self.config.smtp_password:
                server.login(self.config.smtp_user, self.config.smtp_password)
            server.sendmail(
                from_addr=msg["From"],
                to_addrs=recipients,
                msg=msg.as_string(),
            )

    @staticmethod
    def _plaintext_fallback(html: str) -> str:
        """Strip HTML tags to produce a plain-text fallback."""
        import re

        text = re.sub(r"<[^>]+>", "", html)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&quot;", '"', text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
