from flask import current_app
from email_validator import validate_email, EmailNotValidError


def is_valid_email(email):
    """
    Validates an email address's format properly, per RFC standards,
    rather than a hand-written regex. Returns (True, normalized_email)
    on success, (False, error_message) on failure.

    check_deliverability defaults to True in email-validator, which
    performs a DNS lookup confirming the domain can actually receive
    mail, e.g. catches typos like "gmail.com". Set to False here since
    a DNS check on every registration adds latency and an external
    dependency, format validation alone is a reasonable bar for this
    project, worth reconsidering if genuinely deliverable emails matter
    more than fast response times.
    """
    try:
        # Defaults to production rules if flags aren't explicitly found
        check_dns = current_app.config.get("EMAIL_CHECK_DELIVERABILITY", True)
        allow_test = current_app.config.get("EMAIL_ALLOW_TEST_DOMAINS", False)

        result = validate_email(
            email, check_deliverability=check_dns, test_environment=allow_test
        )
        return True, result.normalized
    except EmailNotValidError as e:
        return False, str(e)
