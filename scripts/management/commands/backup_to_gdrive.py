import sys
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from scripts.services.gdrive_backup_service import run_daily_screenplay_backup, BACKUP_RETENTION_COUNT


class Command(BaseCommand):
    help = 'Performs daily automated PDF backup of the KadhaScript screenplay to Google Drive with 30-day retention.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--script-id',
            type=int,
            default=None,
            help='Specific Script ID to backup (default: most recently updated script).'
        )
        parser.add_argument(
            '--date',
            type=str,
            default=None,
            help='Backup date in YYYY-MM-DD format (default: today).'
        )
        parser.add_argument(
            '--retention',
            type=int,
            default=BACKUP_RETENTION_COUNT,
            help='Number of daily backups to keep on Google Drive (default: 30).'
        )

    def handle(self, *args, **options):
        script_id = options.get('script_id')
        date_str = options.get('date')
        retention = options.get('retention', BACKUP_RETENTION_COUNT)

        backup_date = None
        if date_str:
            try:
                backup_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                self.stderr.write(self.style.ERROR(f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD."))
                sys.exit(1)
        else:
            backup_date = timezone.localdate()

        self.stdout.write(self.style.MIGRATE_HEADING(f"Starting KadhaScript Daily PDF Backup for {backup_date}..."))

        result = run_daily_screenplay_backup(
            script_id=script_id,
            backup_date=backup_date,
            keep_count=retention
        )

        if result['success']:
            self.stdout.write(self.style.SUCCESS(
                f"[SUCCESS] Screenplay backup completed successfully!\n"
                f"  - Filename: {result['filename']}\n"
                f"  - Script: {result.get('script_title')} (ID: {result.get('script_id')})\n"
                f"  - PDF Size: {result.get('pdf_size')} bytes\n"
                f"  - Drive File ID: {result.get('drive_file_id')}\n"
                f"  - Local Copy: {result.get('local_path')}\n"
                f"  - Old Backups Pruned: {result.get('pruned_count')}"
            ))
        else:
            self.stderr.write(self.style.ERROR(
                f"[FAILURE] Daily backup failed: {result.get('error')}\n"
                f"  - Filename: {result.get('filename')}\n"
                f"  - Local Copy Saved: {result.get('local_path')}"
            ))
            # Exit with non-zero code for monitoring / cron alerting
            sys.exit(1)
