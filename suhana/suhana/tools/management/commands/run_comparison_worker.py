import logging
import threading
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from tools.models import ComparisonQueueControl
from tools.processing_jobs import (
    MAX_CONCURRENT_COMPARISON_JOBS,
    claim_next_job,
    cleanup_expired_jobs,
    process_comparison_job,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run isolated asynchronous image/PDF comparison and compression workers."

    def add_arguments(self, parser):
        parser.add_argument("--workers", type=int, default=MAX_CONCURRENT_COMPARISON_JOBS)
        parser.add_argument("--poll-interval", type=float, default=1.0)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        workers = options["workers"]
        poll_interval = options["poll_interval"]
        if workers < 1 or workers > MAX_CONCURRENT_COMPARISON_JOBS:
            raise CommandError(
                f"--workers must be between 1 and {MAX_CONCURRENT_COMPARISON_JOBS}."
            )
        if poll_interval < 0.1 or poll_interval > 10:
            raise CommandError("--poll-interval must be between 0.1 and 10 seconds.")
        if not ComparisonQueueControl.objects.filter(pk=1).exists():
            raise CommandError(
                "Apply the async comparison database migration before starting workers."
            )
        cleanup_expired_jobs()

        if options["once"]:
            self.process_one_job()
            return

        stop = threading.Event()
        threads = [
            threading.Thread(
                target=self.run_worker,
                args=(stop, poll_interval),
                name=f"comparison-worker-{index + 1}",
            )
            for index in range(workers)
        ]
        for thread in threads:
            thread.start()
        self.stdout.write(
            self.style.SUCCESS(
                f"Comparison worker started with concurrency capped at {workers}."
            )
        )
        try:
            for thread in threads:
                thread.join()
        except KeyboardInterrupt:
            stop.set()
            for thread in threads:
                thread.join(timeout=30)

    def process_one_job(self):
        close_old_connections()
        job_id = claim_next_job()
        if job_id is not None:
            process_comparison_job(job_id)
        close_old_connections()

    def run_worker(self, stop, poll_interval):
        cleanup_at = time.monotonic() + 60
        while not stop.is_set():
            close_old_connections()
            now = time.monotonic()
            if now >= cleanup_at:
                cleanup_expired_jobs()
                cleanup_at = now + 60
            job_id = claim_next_job()
            if job_id is None:
                close_old_connections()
                stop.wait(poll_interval)
                continue
            try:
                process_comparison_job(job_id)
            except Exception:
                logger.exception("Comparison worker failed while processing %s.", job_id)
            finally:
                close_old_connections()
