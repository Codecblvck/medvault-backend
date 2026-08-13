# MedVault

Secure, role-based hospital patient records system. Built for DTS 302, Group 4, as a functional prototype demonstrating encryption, role-based access control, and tamper-evident audit logging over a real Flask and PostgreSQL backend, not a production-certified hospital system.

Full route documentation lives in `docs/dts302_api_contract.md`. Full architectural and implementation detail, including code walkthroughs of the encryption, access control, and audit logging design, lives in `docs/dts302_backend_documentation.md`. This file covers what's needed to get the project running.

## Stack

- **Language / framework**: Python, Flask, application factory pattern
- **Database**: PostgreSQL, via SQLAlchemy and Flask-Migrate (Alembic)
- **Auth**: Flask-JWT-Extended, stateless JWT, Flask-Bcrypt for password hashing
- **Encryption**: PyCryptodome, AES-256-GCM for record content, RSA (PKCS1_OAEP) for per-record key wrapping
- **Object storage**: boto3 against an S3-compatible API, Cloudflare R2 in production
- **Email validation**: email-validator
- **CORS**: Flask-CORS, scoped to the deployed frontend origin
- **WSGI server**: Gunicorn, used in production
- **DB driver**: psycopg2-binary

Full pinned versions are in `requirements.txt`, which is the authoritative reference for exact versions at any given time.

## Project structure

```text
app/
    __init__.py            create_app factory, extension wiring
    config.py               environment-driven configuration
    extensions.py           uninitialised SQLAlchemy, JWT, Migrate, Bcrypt, CORS instances
    model_registry.py       aggregates all models at startup
    blueprint_registry.py   registers all blueprints and URL prefixes

    auth/                  login, self-profile, admin staff management
    access_control/        role and permission-matrix decorators, the matrices themselves
    records/               patients, records, upload, attach-file, list, view
    audit/                 hash-chained access logging, log viewing routes
    encryption/            AES-256-GCM plus RSA key-wrapping
    storage/               S3-compatible object storage client

migrations/                Alembic migration history
docs/
    dts302_api_contract.md            full route documentation
    dts302_backend_documentation.md   full architecture and implementation detail
run.py                     entry point, calls create_app
requirements.txt
.env                       local environment variables, never committed
```

## Local setup

1. **Clone the repository and create a virtual environment.**

```bash
git clone <repo-url>
cd hospital-records-system
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. **Set up PostgreSQL.** Either run it locally or point at a hosted instance. Create a database for this project and note its connection string.

3. **Generate an RSA key pair**, used for wrapping each record's AES key. Keys are generated once, outside the application, using OpenSSL, and stored outside the project repository entirely, never committed to version control.

```bash
openssl genrsa -out private_key.pem 2048
openssl rsa -in private_key.pem -pubout -out public_key.pem
```

Keep both files somewhere outside the repo. Note their absolute paths, needed in the next step.

4. **Create a `.env` file** at the project root with the following variables. None of the actual values below are real, replace every one.

```text
FLASK_ENV=development

DATABASE_URL=postgresql://user:password@localhost:5432/medvault

JWT_SECRET_KEY=replace-with-a-long-random-string

RSA_PRIVATE_KEY_PATH=/absolute/path/to/private_key.pem
RSA_PUBLIC_KEY_PATH=/absolute/path/to/public_key.pem

S3_ENDPOINT=https://your-r2-account-id.r2.cloudflarestorage.com
S3_ACCESS_KEY=replace-with-r2-access-key
S3_SECRET_KEY=replace-with-r2-secret-key
S3_BUCKET_NAME=replace-with-bucket-name
```

`DATABASE_URL` is read directly as the SQLAlchemy connection string. `JWT_SECRET_KEY` signs every issued token, treat it the same as any other credential, never commit it, rotate it if it's ever exposed. `RSA_PRIVATE_KEY_PATH` and `RSA_PUBLIC_KEY_PATH` point at the key files generated in step 3. The `S3_*` variables authenticate against whichever S3-compatible provider is configured, Cloudflare R2 in the deployed environment, but any S3-compatible endpoint, including a local MinIO instance during development, works without any code changes, only these values need to change.

5. **Run database migrations.**

```bash
flask db upgrade
```

6. **Seed the roles table.** The system expects exactly seven fixed roles to exist before anything else can function correctly, since every user must have a role and nothing defaults or falls back if one is missing. Seed admin, doctor, nurse, lab_technician, records_officer, auditor, and patient before creating any account.

7. **Run the application.**

```bash
python run.py
```

The app runs against whichever `FLASK_ENV` is set, `development` loosens email deliverability checks so local test domains and unreachable mail servers don't block testing, this must never be the value used in a deployed environment.

## Authentication model

There is no self-registration route anywhere in this system. Every account, staff or patient, is created deliberately by a staff member with sufficient privilege, this is a considered design decision closing a role-escalation risk, not a missing feature. A patient's portal account can be created either at the same time their patient record is created, or afterward through a dedicated route, both documented in the API contract.

## CORS

Cross-origin requests are restricted to a single, explicitly configured frontend origin, currently the deployed Vercel URL. If the frontend's deployed URL changes, the origin configured in `app/extensions.py` and wired in `create_app()` needs to be updated to match, or the browser will silently block every request from the new URL before it reaches this backend at all.

## Deployment

The application is deployed on Render, deploying automatically from pushes to the designated branch on GitHub. Object storage uses Cloudflare R2 rather than a self-hosted MinIO instance, chosen specifically because Render does not provide the persistent disk storage a self-hosted object store would need, and because R2 exposes an S3-compatible API with no outbound transfer charges. Every secret listed under Local Setup above is supplied through Render's own environment variable configuration in the deployed environment, including both RSA key files, which are stored as environment values rather than paths to files on a persistent disk.

## Testing

No automated test suite currently exists in the scaffolded `tests/` folder. Verification throughout development has been carried out through a thorough, manually driven testing process using Insomnia, deliberately exercising failure cases before success cases for every route. Building an automated suite is a known open item, tracked as a post-deployment improvement rather than a current gap in verification.

## Known open items

- Record and patient deletion do not currently exist as routes. The intended design mirrors the existing pattern for user accounts, deactivation rather than true removal, to preserve the audit trail's ability to prove what existed at any point in the system's history.
- Multi-factor authentication was scoped as an optional stretch goal from the start of the project and remains unbuilt.
