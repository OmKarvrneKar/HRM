"""Bootstrap the first HR account securely from the command line.

    python manage.py create_hr --username hr_admin --email hr@example.com

The command prompts for the password so it never appears in shell history.
The account is created as a superuser (internal admin access) AND with the HR
business role, and is forced to change its temporary password on first login.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role


class Command(BaseCommand):
    help = "Create the initial HR account (HR role + superuser) with a temporary password."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", default="")

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        email = options["email"]

        if User.objects.filter(username=username).exists():
            raise CommandError(f"A user named '{username}' already exists.")

        from getpass import getpass

        password = getpass("Password: ")
        confirm = getpass("Confirm password: ")
        if password != confirm:
            raise CommandError("Passwords did not match.")

        user = User.objects.create_superuser(
            username=username, email=email, password=password
        )
        user.role = Role.HR
        user.must_change_password = True
        user.save(update_fields=["role", "must_change_password"])

        self.stdout.write(
            self.style.SUCCESS(f"HR account '{username}' created. Change password on first login.")
        )
