"""HTML email templates for transactional emails."""

BRAND_BASE_CSS = """
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #FAF7F0; margin: 0; padding: 24px; color: #1F1F26; }
  .wrap { max-width: 560px; margin: 0 auto; background: #FFFFFF; border-radius: 16px; overflow: hidden; box-shadow: 0 6px 30px rgba(0,0,0,0.06); }
  .head { padding: 28px 32px 18px; border-bottom: 1px solid #EEEEF1; display: flex; align-items: center; gap: 10px; }
  .mark { width: 30px; height: 30px; background: linear-gradient(135deg, #0D9488, #14B8A6); border-radius: 6px; }
  .brand { font-weight: 700; font-size: 16px; }
  .brand .c { color: #0D9488; }
  .body { padding: 28px 32px; }
  h1 { font-family: Georgia, serif; font-size: 28px; line-height: 1.15; margin: 0 0 14px; color: #0B0B0F; }
  p { font-size: 15px; line-height: 1.6; margin: 0 0 14px; color: #2E2E37; }
  .btn { display: inline-block; background: #0B0B0F; color: #FFFFFF !important; text-decoration: none; padding: 12px 22px; border-radius: 999px; font-weight: 600; font-size: 14px; margin-top: 6px; }
  .panel { background: #FAF7F0; border: 1px solid #EEEEF1; border-radius: 10px; padding: 14px 18px; margin: 18px 0; font-size: 13px; color: #4A4A55; }
  .panel b { color: #0B0B0F; font-weight: 600; }
  .foot { padding: 18px 32px; border-top: 1px solid #EEEEF1; color: #74747F; font-size: 12px; }
  .foot a { color: #0D9488; text-decoration: none; }
  .eyebrow { font-family: ui-monospace, monospace; font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase; color: #0D9488; margin-bottom: 8px; font-weight: 600; }
"""


def _layout(content_html: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>{BRAND_BASE_CSS}</style></head>
<body>
  <div class="wrap">
    <div class="head">
      <div class="mark"></div>
      <div class="brand">Unique <span class="c">Type</span></div>
    </div>
    <div class="body">
      {content_html}
    </div>
    <div class="foot">
      Unique Type · AI bid team for Indian government tenders<br>
      Questions? Reply to this email or write to <a href="mailto:admin@example.com">admin@example.com</a>
    </div>
  </div>
</body></html>"""


def welcome_email(full_name: str, company_name: str) -> tuple[str, str]:
    """Returns (subject, html) for a welcome email to a new user."""
    name = (full_name or "there").split()[0] if full_name else "there"
    body = f"""
      <p class="eyebrow">Welcome aboard</p>
      <h1>Hi {name}, your AI bid team is ready.</h1>
      <p>Your 7-day trial of Unique Type just started{' for ' + company_name if company_name else ''}. All eleven specialist AI agents are unlocked — Bid Manager, Technical Expert, Finance, Legal, QA, and the rest.</p>
      <div class="panel">
        <p style="margin: 0;"><b>Quick start (3 minutes):</b></p>
        <p style="margin: 8px 0 0;">
          1. Fill in your Company Profile (turnover, GST, certifications) so every agent has context.<br>
          2. Open <b>Bid Pipeline</b> or <b>Analysis</b>, paste a real tender, hit run.<br>
          3. Within 8 minutes, you'll have a full bid blueprint + MD-grade recommendation.
        </p>
      </div>
      <p><a href="http://localhost:5173/app/dashboard" class="btn">Open my dashboard →</a></p>
      <p style="font-size: 13px; color: #74747F; margin-top: 22px;">
        Your trial expires in 7 days. Cancel anytime — no card required. If you have questions, just reply to this email and we'll get back within a working day.
      </p>
    """
    return ("Welcome to Unique Type — your AI bid team is ready", _layout(body))


def verification_code_email(full_name: str, code: str) -> tuple[str, str]:
    """Email with a 6-digit verification code, big and centered."""
    name = (full_name or "there").split()[0] if full_name else "there"
    body = f"""
      <p class="eyebrow">Verify your email</p>
      <h1>Hi {name}, here's your code.</h1>
      <p>Enter this 6-digit code on the verification screen to activate your Unique Type account.</p>
      <div style="margin: 28px 0; padding: 24px; background: #0B0B0F; border-radius: 12px; text-align: center;">
        <div style="font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 38px; font-weight: 700; letter-spacing: 0.5em; color: #FFFFFF; padding-left: 0.5em;">{code}</div>
        <div style="font-family: ui-monospace, monospace; font-size: 11px; letter-spacing: 0.18em; color: #A9A9B5; text-transform: uppercase; margin-top: 8px;">Verification code</div>
      </div>
      <p style="font-size: 13px; color: #74747F;">This code expires in 60 minutes. If you didn't sign up for Unique Type, you can safely ignore this email.</p>
    """
    return ("Your Unique Type verification code", _layout(body))


def admin_new_signup_email(full_name: str, email: str, company_name: str, phone: str = "") -> tuple[str, str]:
    body = f"""
      <p class="eyebrow">New signup</p>
      <h1>{full_name or 'Someone'} just joined.</h1>
      <p>A new user has signed up on Unique Type.</p>
      <div class="panel">
        <p style="margin: 0;"><b>Name:</b> {full_name or '—'}</p>
        <p style="margin: 4px 0;"><b>Email:</b> <a href="mailto:{email}">{email}</a></p>
        <p style="margin: 4px 0;"><b>Company:</b> {company_name or '—'}</p>
        {f'<p style="margin: 4px 0;"><b>Phone:</b> {phone}</p>' if phone else ''}
        <p style="margin: 4px 0 0;"><b>Plan:</b> Trial (7 days)</p>
      </div>
      <p><a href="http://localhost:5173/app/admin/users" class="btn">View all users →</a></p>
    """
    return (f"[Unique Type] New signup: {full_name or email}", _layout(body))
