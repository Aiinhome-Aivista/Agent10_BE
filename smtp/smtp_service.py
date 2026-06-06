import asyncio
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import aiosmtplib
from configs.base import settings

logger = logging.getLogger(__name__)


class SMTPService:

    async def send(self, to: str, subject: str, html_body: str, max_retry: int = 3) -> bool:
        msg = MIMEMultipart("alternative")
        msg["From"]    = settings.SMTP_FROM_EMAIL
        msg["To"]      = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        for attempt in range(1, max_retry + 1):
            try:
                await aiosmtplib.send(
                    msg,
                    hostname=settings.SMTP_HOST,
                    port=settings.SMTP_PORT,
                    username=settings.SMTP_USERNAME,
                    password=settings.SMTP_PASSWORD,
                    use_tls=settings.SMTP_SSL,
                    start_tls=settings.SMTP_TLS,
                )
                logger.info(f"Email sent to {to} (attempt {attempt})")
                return True
            except Exception as e:
                logger.warning(f"SMTP attempt {attempt} failed: {e}")
                if attempt < max_retry:
                    await asyncio.sleep(2 ** attempt)
        logger.error(f"Failed to send email to {to} after {max_retry} attempts")
        return False

    async def send_otp(self, to: str, otp_code: str, case_number: str) -> bool:
        subject = f"Q2P Platform — Your OTP for Case {case_number}"
        body = f"""
        <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:32px;
                    background:#f9fafb;border-radius:12px;">
            <h2 style="color:#6366f1;margin-bottom:8px;">Q2P Insurance Platform</h2>
            <p style="color:#374151;">Your One-Time Password for policy consent on case
               <strong>{case_number}</strong> is:</p>
            <div style="font-size:36px;font-weight:800;letter-spacing:10px;color:#111827;
                        text-align:center;padding:20px;background:#fff;border-radius:8px;
                        margin:20px 0;">{otp_code}</div>
            <p style="color:#6b7280;font-size:13px;">
                This OTP expires in <strong>10 minutes</strong>.<br>
                Do not share it with anyone.
            </p>
        </div>"""
        return await self.send(to, subject, body)

    async def send_escalation(self, to: str, case_number: str, stage: str, level: str) -> bool:
        subject = f"⚠️ Escalation Alert — Case {case_number} | {level}"
        body = f"""
        <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:32px;
                    background:#fff7ed;border-radius:12px;border:1px solid #fed7aa;">
            <h2 style="color:#ea580c;">Escalation Alert — {level}</h2>
            <p>Case <strong>{case_number}</strong> has been escalated at stage
               <strong>{stage}</strong>.</p>
            <p>Please take immediate action in the Q2P platform.</p>
        </div>"""
        return await self.send(to, subject, body)


smtp_service = SMTPService()
