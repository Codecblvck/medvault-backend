import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=45)

    RSA_PUBLIC_KEY_PATH = os.environ.get("RSA_PUBLIC_KEY_PATH")
    RSA_PRIVATE_KEY_PATH = os.environ.get("RSA_PRIVATE_KEY_PATH")

    S3_ENDPOINT = os.environ.get("S3_ENDPOINT")
    S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY")
    S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY")
    S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")

    # Email validation
    # Accept real domains and .test simulator domains.
    # DNS deliverability is intentionally disabled because
    # simulator accounts do not need to receive email.
    EMAIL_CHECK_DELIVERABILITY = False
    EMAIL_ALLOW_TEST_DOMAINS = True


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
