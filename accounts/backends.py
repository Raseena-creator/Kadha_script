from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

UserModel = get_user_model()


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Authenticates against settings.AUTH_USER_MODEL using email address.
    Matches primarily by case-insensitive email address (with surrounding whitespace stripped).
    Falls back to case-insensitive username for backward compatibility and admin access.
    Safely rejects ambiguous duplicate emails and empty credentials.
    """

    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        candidate = email or username or kwargs.get('email')
        if not candidate or not password:
            return None

        credential = str(candidate).strip()
        if not credential or not str(password):
            return None

        # 1. Look up by email (case-insensitive)
        matching_users = list(UserModel.objects.filter(email__iexact=credential))

        # 2. If no email matches, fallback to username for legacy/admin access
        if not matching_users:
            matching_users = list(UserModel.objects.filter(username__iexact=credential))

        if not matching_users:
            # Run the default password hasher once to reduce timing difference for nonexistent users
            UserModel().set_password(password)
            return None

        # 3. Check duplicate-email ambiguity
        # Check active users that match the password
        valid_users = [
            user for user in matching_users
            if user.check_password(password) and self.user_can_authenticate(user)
        ]

        # Authenticate if and only if exactly one user matches
        if len(valid_users) == 1:
            return valid_users[0]

        # If zero or multiple users match, fail safely
        return None
