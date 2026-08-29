from flask import current_app
from email_validator import validate_email, EmailNotValidError


def is_valid_email(email):
    """
    Validate email syntax using the email-validator library.

    Both normal email domains and .test domains are accepted.
    DNS deliverability checks are disabled because the application
    uses simulated accounts.
    """
    try:
        check_dns = current_app.config.get("EMAIL_CHECK_DELIVERABILITY", False)
        allow_test = current_app.config.get("EMAIL_ALLOW_TEST_DOMAINS", True)

        result = validate_email(
            email,
            check_deliverability=check_dns,
            test_environment=allow_test,
        )

        return True, result.normalized

    except EmailNotValidError as e:
        return False, str(e)
