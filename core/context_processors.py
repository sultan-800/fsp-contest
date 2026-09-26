from django.conf import settings


def site(request):
    ctx = {"SITE_NAME": settings.SITE_NAME, "unread_notifications": 0, "panel_pending": 0}
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        ctx["unread_notifications"] = user.notifications.filter(is_read=False).count()
        if user.is_organizer and request.path.startswith("/panel/"):
            from competitions.models import Submission
            ctx["panel_pending"] = Submission.objects.filter(status=Submission.Status.PENDING).count()
    return ctx
