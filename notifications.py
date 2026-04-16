from datetime import datetime, timezone
from app.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3)
def send_push_notification(self, user_id: str, title: str, message: str, data: dict = None):
    """
    Send a push notification to a user via FCM/APNs.
    In production: integrate with Firebase Cloud Messaging or APNs.
    """
    try:
        # Placeholder - replace with real FCM/APNs call
        print(f"[PUSH] user={user_id} title={title!r} body={message!r} data={data}")
        # Example FCM integration:
        # import firebase_admin
        # from firebase_admin import messaging
        # msg = messaging.Message(
        #     notification=messaging.Notification(title=title, body=message),
        #     data=data or {},
        #     token=fcm_token,
        # )
        # messaging.send(msg)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task(bind=True, max_retries=3)
def send_email_notification(self, to_email: str, subject: str, body_html: str):
    """Send a transactional email via SMTP."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from app.config import settings

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_USER
        msg["To"] = to_email
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_USER, to_email, msg.as_string())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)


@celery_app.task
def notify_new_follower(follower_id: str, followed_id: str):
    """Persist + push notification when someone new follows a user."""
    from app.tasks._db import run_in_sync_session
    from app.models import Notification, User

    def _work(session):
        follower = session.get(User, follower_id)
        if not follower:
            return
        notif = Notification(
            user_id=followed_id,
            type="follow",
            title="Nuevo seguidor",
            message=f"{follower.username} ha empezado a seguirte",
            data={"follower_id": follower_id},
        )
        session.add(notif)
        session.commit()

    run_in_sync_session(_work)
    send_push_notification.delay(
        followed_id,
        "Nuevo seguidor",
        "Alguien ha empezado a seguirte",
    )


@celery_app.task
def notify_post_like(liker_id: str, post_id: str, post_author_id: str):
    """Notify post author when their post gets a like."""
    from app.tasks._db import run_in_sync_session
    from app.models import Notification, User

    if liker_id == post_author_id:
        return  # Don't notify self-likes

    def _work(session):
        liker = session.get(User, liker_id)
        if not liker:
            return
        notif = Notification(
            user_id=post_author_id,
            type="like",
            title="Me gusta",
            message=f"A {liker.username} le ha gustado tu publicación",
            data={"post_id": post_id, "liker_id": liker_id},
        )
        session.add(notif)
        session.commit()

    run_in_sync_session(_work)


@celery_app.task
def notify_new_comment(commenter_id: str, post_id: str, post_author_id: str, comment_preview: str):
    """Notify post author of a new comment."""
    from app.tasks._db import run_in_sync_session
    from app.models import Notification, User

    if commenter_id == post_author_id:
        return

    def _work(session):
        commenter = session.get(User, commenter_id)
        if not commenter:
            return
        notif = Notification(
            user_id=post_author_id,
            type="comment",
            title="Nuevo comentario",
            message=f"{commenter.username}: {comment_preview[:80]}",
            data={"post_id": post_id, "commenter_id": commenter_id},
        )
        session.add(notif)
        session.commit()

    run_in_sync_session(_work)


@celery_app.task
def cleanup_expired_tokens():
    """Purge revoked/expired refresh tokens older than 7 days."""
    from app.tasks._db import run_in_sync_session
    from app.models import RefreshToken
    from sqlalchemy import delete
    from datetime import timedelta

    def _work(session):
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        session.execute(
            delete(RefreshToken).where(
                (RefreshToken.revoked == True) | (RefreshToken.expires_at < cutoff)
            )
        )
        session.commit()

    run_in_sync_session(_work)
