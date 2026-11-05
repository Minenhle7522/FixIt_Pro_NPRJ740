from requests_app.models import MaintenanceRequest


def sla_badge_counts(request):
    """Provide counts for SLA 'at risk' and 'breached' requests for navbar badges."""
    try:
        qs = MaintenanceRequest.objects.exclude(status__in=['closed', 'cancelled', 'verified'])
        breached = qs.filter(sla_breached=True).count()
        at_risk = 0
        # Iterate active requests and use model logic to determine 'at_risk'
        for r in qs.only('sla_deadline', 'sla_hours', 'sla_breached'):
            if r.sla_breached:
                continue
            state = r.sla_state
            if state == 'at_risk':
                at_risk += 1
    except Exception:
        breached = 0
        at_risk = 0
    unread = 0
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        try:
            unread = user.notifications.filter(is_read=False).count()
        except Exception:
            unread = 0
    return {'sla_breached_count': breached, 'sla_at_risk_count': at_risk, 'unread_notifications': unread}
