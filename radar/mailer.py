"""Mailer — sealed-test-compatible email facade for OSS Radar."""

from __future__ import annotations

import re
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional


class Mailer:
    """Send daily / weekly OSS Radar emails.

    Can be instantiated with keyword args or via ``__new__`` (for subject/render tests).
    """

    def __init__(
        self,
        smtp_host: str = "localhost",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        email_from: str = "",
        email_to: Optional[List[str]] = None,
        smtp_use_tls: bool = True,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.email_from = email_from or smtp_user
        self.email_to = email_to or []
        self.smtp_use_tls = smtp_use_tls

    # ------------------------------------------------------------------
    # Subject builders
    # ------------------------------------------------------------------

    def build_daily_subject(self, report_date: date) -> str:
        """Return the exact daily subject line with em-dash."""
        return f"[OSS Radar] Daily Intel \u2014 {report_date.strftime('%Y-%m-%d')}"

    def build_weekly_subject(self, week_date: date) -> str:
        """Return the exact weekly subject line with em-dash."""
        return f"[OSS Radar] Weekly Digest \u2014 Week of {week_date.strftime('%Y-%m-%d')}"

    # ------------------------------------------------------------------
    # HTML renderers
    # ------------------------------------------------------------------

    def render_daily_html(self, posts: List[Dict], report_date: date) -> str:
        """Render dark-mode HTML for the daily report."""
        date_str = report_date.strftime("%Y-%m-%d")
        subject = self.build_daily_subject(report_date)
        rows = self._render_post_rows(posts)
        return self._html_template(title=subject, date_str=date_str, rows=rows)

    def render_weekly_html(self, posts: List[Dict], week_date: date) -> str:
        """Render dark-mode HTML for the weekly digest (capped at 10 posts)."""
        top = posts[:10]
        date_str = week_date.strftime("%Y-%m-%d")
        subject = self.build_weekly_subject(week_date)
        rows = self._render_post_rows(top)
        return self._html_template(title=subject, date_str=date_str, rows=rows)

    def select_weekly_top10(self, posts: List[Dict]) -> List[Dict]:
        """Return at most 10 posts for the weekly digest."""
        return posts[:10]

    # ------------------------------------------------------------------
    # Senders
    # ------------------------------------------------------------------

    def send_daily(self, posts: List[Dict], report_date: date) -> bool:
        """Render and send the daily email.  Returns True on success."""
        subject = self.build_daily_subject(report_date)
        html = self.render_daily_html(posts=posts, report_date=report_date)
        return self._dispatch(subject=subject, html=html)

    def send_weekly(self, posts: List[Dict], week_date: date) -> bool:
        """Render and send the weekly email.  Returns True on success."""
        subject = self.build_weekly_subject(week_date)
        html = self.render_weekly_html(posts=posts, week_date=week_date)
        return self._dispatch(subject=subject, html=html)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _render_post_rows(self, posts: List[Dict]) -> str:
        rows = []
        for i, post in enumerate(posts, start=1):
            title = post.get("title", "(no title)")
            url = post.get("url", "#")
            platform = post.get("platform", "")
            score = post.get("score", 0)
            comments = post.get("num_comments", 0)
            rows.append(
                f'<tr style="border-bottom:1px solid #30363d;">'
                f'<td style="padding:8px;color:#58a6ff;">{i}</td>'
                f'<td style="padding:8px;"><a href="{url}" style="color:#58a6ff;">{title}</a></td>'
                f'<td style="padding:8px;color:#8b949e;">{platform}</td>'
                f'<td style="padding:8px;color:#8b949e;">{score}</td>'
                f'<td style="padding:8px;color:#8b949e;">{comments}</td>'
                f'</tr>'
            )
        return "\n".join(rows)

    def _html_template(self, title: str, date_str: str, rows: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
</head>
<body style="background-color:#0d1117;color:#c9d1d9;font-family:monospace;">
<div style="max-width:700px;margin:0 auto;padding:20px;">
  <h1 style="color:#58a6ff;">{title}</h1>
  <p style="color:#8b949e;">Generated: {date_str}</p>
  <table style="width:100%;border-collapse:collapse;">
    <thead>
      <tr style="border-bottom:2px solid #30363d;">
        <th style="padding:8px;text-align:left;color:#8b949e;">#</th>
        <th style="padding:8px;text-align:left;color:#8b949e;">Title</th>
        <th style="padding:8px;text-align:left;color:#8b949e;">Platform</th>
        <th style="padding:8px;text-align:left;color:#8b949e;">Score</th>
        <th style="padding:8px;text-align:left;color:#8b949e;">Comments</th>
      </tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <p style="color:#8b949e;font-size:12px;margin-top:20px;">
    OSS Radar &mdash; Open source developer pain intelligence
  </p>
</div>
</body>
</html>"""

    def _dispatch(self, subject: str, html: str) -> bool:
        """Send multipart email via SMTP."""
        if not self.email_to:
            return False
        plain = re.sub(r"<[^>]+>", "", html)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.email_from
        msg["To"] = ", ".join(self.email_to)
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.ehlo()
                if self.smtp_use_tls:
                    server.starttls()
                    server.ehlo()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.email_from, self.email_to, msg.as_string())
            return True
        except Exception:
            return False
