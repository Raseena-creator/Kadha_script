import sys
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from scripts.services.email_backup_service import run_daily_email_backup


def _safe_print(writer, text: str, style_func=None):
    """Safely writes text to stdout/stderr across all OS platforms and console encodings."""
    msg = style_func(text) if style_func else text
    try:
        writer.write(msg)
    except (UnicodeEncodeError, UnicodeError):
        try:
            enc = getattr(writer, 'encoding', None) or 'utf-8'
            safe_text = msg.encode(enc, errors='backslashreplace').decode(enc, errors='replace')
            writer.write(safe_text)
        except Exception:
            writer.write(msg.encode('ascii', errors='replace').decode('ascii'))


class Command(BaseCommand):
    help = 'Executes production daily automated PDF backup by email for KadhaScript screenplays.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--script-id',
            type=int,
            default=None,
            help='Specific Script ID to backup (default: all scripts in the system).'
        )
        parser.add_argument(
            '--date',
            type=str,
            default=None,
            help='Backup date in YYYY-MM-DD format (default: today).'
        )
        parser.add_argument(
            '--recipient',
            type=str,
            default=None,
            help='Optional manual override for recipient email address (default: dynamically resolved from script owner user.email).'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            default=False,
            help='Bypass duplicate protection and force sending the backup email even if already sent today.'
        )

    def handle(self, *args, **options):
        # Configure utf-8 encoding on Windows if supported
        if sys.platform.startswith('win'):
            try:
                if hasattr(sys.stdout, 'reconfigure'):
                    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                if hasattr(sys.stderr, 'reconfigure'):
                    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass

        script_id = options.get('script_id')
        date_str = options.get('date')
        recipient = options.get('recipient')
        force = options.get('force', False)

        backup_date = None
        if date_str:
            try:
                backup_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                _safe_print(self.stderr, f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD.", self.style.ERROR)
                sys.exit(1)
        else:
            backup_date = timezone.localdate()

        _safe_print(
            self.stdout,
            f"=== KadhaScript Daily PDF Backup Email System [{backup_date}] ===",
            self.style.MIGRATE_HEADING
        )

        result = run_daily_email_backup(
            script_id=script_id,
            backup_date=backup_date,
            recipient_email=recipient,
            force=force
        )

        total = result.get('total_scripts', 0)
        successful = result.get('successful_count', 0)
        skipped = result.get('skipped_count', 0)
        failed = result.get('failed_count', 0)

        for item in result.get('results', []):
            st_title = item.get('script_title')
            st_id = item.get('script_id')
            if item.get('success'):
                if item.get('skipped'):
                    _safe_print(
                        self.stdout,
                        f" [SKIPPED] '{st_title}' (ID: {st_id}): {item.get('reason')}",
                        self.style.WARNING
                    )
                else:
                    _safe_print(
                        self.stdout,
                        f" [SUCCESS] '{st_title}' (ID: {st_id}) -> {item.get('recipient')}\n"
                        f"           Filename: {item.get('filename')}\n"
                        f"           PDF Size: {item.get('pdf_size'):,} bytes\n"
                        f"           Local Copy: {item.get('local_path')}",
                        self.style.SUCCESS
                    )
            else:
                _safe_print(
                    self.stderr,
                    f" [FAILED]  '{st_title}' (ID: {st_id}): {item.get('error')}",
                    self.style.ERROR
                )

        _safe_print(self.stdout, "--------------------------------------------------")
        _safe_print(
            self.stdout,
            f"Summary: Total: {total} | Sent: {successful} | Skipped: {skipped} | Failed: {failed}"
        )

        if not result.get('success'):
            _safe_print(self.stderr, "Daily backup completed with errors.", self.style.ERROR)
            sys.exit(1)
        else:
            _safe_print(self.stdout, "Daily backup job finished successfully.", self.style.SUCCESS)

