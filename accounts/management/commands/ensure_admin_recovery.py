import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = (
        "Safely and idempotently provisions an initial administrative superuser "
        "in production when explicitly enabled via environment variables."
    )

    def handle(self, *args, **options):
        # 1. Guard check: Recovery must be explicitly enabled
        enabled_val = os.environ.get('ADMIN_RECOVERY_ENABLED', '').strip().lower()
        if enabled_val not in ('true', '1'):
            self.stdout.write("Admin recovery mode is disabled. No database changes performed.")
            return

        # 2. Extract and validate required configuration from environment
        username = os.environ.get('ADMIN_RECOVERY_USERNAME', '').strip()
        email = os.environ.get('ADMIN_RECOVERY_EMAIL', '').strip().lower()
        password = os.environ.get('ADMIN_RECOVERY_PASSWORD', '')

        if not username or not email or not password:
            self.stdout.write(
                self.style.WARNING(
                    "Admin recovery is enabled, but one or more required environment variables "
                    "(ADMIN_RECOVERY_USERNAME, ADMIN_RECOVERY_EMAIL, ADMIN_RECOVERY_PASSWORD) "
                    "are missing or empty. No database changes performed."
                )
            )
            return

        User = get_user_model()

        # 3. Collision checks: Query database for existing username or email
        existing_by_username = User.objects.filter(username__iexact=username).first()
        existing_by_email = User.objects.filter(email__iexact=email).first()

        # Case A: Repeat execution where the exact recovery superuser already exists
        if existing_by_username and existing_by_email and existing_by_username.pk == existing_by_email.pk:
            if existing_by_username.is_superuser and existing_by_username.is_staff:
                self.stdout.write(
                    self.style.WARNING(
                        f"Admin recovery: Superuser account '{username}' already exists. "
                        "Idempotent skip: no account modifications or password resets performed. "
                        "Please remove ADMIN_RECOVERY_ENABLED from your deployment environment."
                    )
                )
                return

        # Case B: Collision with any existing account (different user or non-superuser)
        if existing_by_username or existing_by_email:
            self.stdout.write(
                self.style.ERROR(
                    f"Admin recovery: Account collision detected for username '{username}' or the provided email. "
                    "To prevent unintended privilege escalation or password overwrites on existing accounts, "
                    "existing accounts cannot be modified. Recovery halted without making any changes."
                )
            )
            return

        # Case C: Both username and email are completely unused -> Safely create superuser
        User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Admin recovery: Successfully created administrative superuser '{username}'. "
                "Verify login immediately, then deactivate ADMIN_RECOVERY_ENABLED in your environment."
            )
        )
