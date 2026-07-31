from app.extensions import db


# lockout helpers
def is_account_locked(user):
    return user.is_locked

def register_failed_attempt(user):
    user.failed_login_count += 1
    if user.failed_login_count >= 5:
        user.is_locked = True
        
    db.session.commit()

def reset_failed_attempts(user):
    user.failed_login_count = 0
    db.session.commit()
