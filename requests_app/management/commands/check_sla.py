from django.core.management.base import BaseCommand
from requests_app.models import MaintenanceRequest, Notification

class Command(BaseCommand):
    help = 'Marks overdue maintenance requests as SLA breached and notifies assigned staff.'
    def handle(self, *args, **options):
        count = 0
        for obj in MaintenanceRequest.objects.exclude(status__in=['closed','cancelled','verified']):
            if obj.mark_sla_if_breached():
                count += 1
                if obj.assigned_staff:
                    Notification.objects.create(user=obj.assigned_staff, title='SLA breached', message=f'Request #{obj.id} has exceeded its SLA deadline.', request=obj)
        from requests_app.services import chase_stalled_jobs
        chased = chase_stalled_jobs()
        self.stdout.write(self.style.SUCCESS(f'{count} request(s) marked as SLA breached; {chased} contractor reminder(s) sent.'))
