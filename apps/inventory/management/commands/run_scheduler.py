"""Run the single in-process job scheduler (reservation sweep + low-stock scan).

Deploy exactly one instance of this command per environment; see
jobs/scheduler.py for why duplication is forbidden.
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from django.core.management.base import BaseCommand

from jobs.scheduler import build_scheduler


class Command(BaseCommand):
    help = "Run MetroDrip's background jobs (blocks until interrupted)."

    def handle(self, *args, **options):
        # Blocking variant: this process exists only to run jobs, so it should
        # foreground them and die visibly if the scheduler stops.
        scheduler = build_scheduler(scheduler_class=BlockingScheduler)
        self.stdout.write("Starting scheduler (Ctrl+C to stop).")
        try:
            scheduler.start()
        except KeyboardInterrupt:
            self.stdout.write("Scheduler stopped.")
