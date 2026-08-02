# DTS 302, API Contract Documentation
## Secure Cloud Based Big Data Storage System, Hospital Patient Records, MedVault, Group 4

This document defines every backend route currently implemented, with exact request and response shapes. This is the agreement between backend and frontend, both sides build against this document, not against assumptions.

All routes are prefixed by blueprint. All protected routes require a JWT in the Authorization header, format `Authorization: Bearer <token>`. A missing or malformed Authorization header returns a 401 before the route itself is ever reached, and this happens outside of the audit log entirely, since no authenticated user exists yet to attribute the attempt to.

There is no patient self-registration route. Every account in this system, staff or patient, is created by a staff member with sufficient privilege. This is a deliberate design decision, made to close a role escalation risk that open self-registration would otherwise introduce. If a patient needs portal access, staff creates it for them, either at the same time the patient record itself is created, or afterward through a dedicated route described below.

## Auth routes, prefix /auth

### POST /auth/login
Purpose, login for all roles, staff and patient. This is the only entry point into the system for an existing account.

Request body
```json
{
  "email": "string",
  "password": "string"
}
```

Response, 200 OK
```json
{
  "token": "jwt string",
  "user": {
    "id": "integer",
    "first_name": "string",
    "last_name": "string",
    "email": "string",
    "role": "string"
  }
}
```

Response, 400, invalid email format or missing fields
Response, 401, invalid credentials, or account is deactivated. Both cases return the identical message and status code deliberately, so a caller probing the endpoint cannot tell an unrecognized email apart from a correct email with the wrong password, or a deactivated account from either.
Response, 423, account locked after five consecutive failed login attempts

### GET /auth/me
Purpose, fetch the logged in user's own profile.

Response, 200 OK
```json
{
  "id": "integer",
  "first_name": "string",
  "last_name": "string",
  "email": "string",
  "role": "string",
  "phone": "string or null",
  "department": "string or null",
  "license_number": "string or null"
}
```

### PATCH /auth/me
Purpose, self profile update. A user can only edit their own row, and only two fields.

Request body, at least one of the two fields required
```json
{
  "phone": "string",
  "department": "string"
}
```

Note, role, is_active, is_locked, and license_number are not editable through this route under any circumstance, admin only, through the user management routes below.

Response, 200 OK
```json
{
  "id": "integer",
  "phone": "string",
  "department": "string",
  "message": "Profile updated"
}
```

Response, 400, neither phone nor department provided

## Admin user management routes, prefix /auth, admin only

### POST /auth/users
Purpose, admin creates a staff account and assigns a role.

Request body
```json
{
  "first_name": "string",
  "last_name": "string",
  "email": "string",
  "password": "string",
  "role": "doctor, nurse, lab_technician, records_officer, auditor, admin",
  "department": "string, optional",
  "license_number": "string, optional"
}
```

Note, submitting "patient" as the role here is explicitly rejected, patient-role accounts are only ever created through the patient routes below, never through this staff route, since patient accounts always carry a linked patient_id and staff accounts never do.

Response, 201 Created
```json
{
  "user_id": "integer",
  "message": "Staff account created"
}
```

Response, 400, missing fields, invalid email format, invalid role, patient role submitted, or email already registered

### PATCH /auth/users/<id>
Purpose, admin edits any user, including role, active status, and lock status.

Request body, all fields optional, at least one required
```json
{
  "role": "string",
  "is_active": "boolean",
  "is_locked": "boolean",
  "department": "string",
  "license_number": "string"
}
```

Note, setting is_locked to false also resets the user's failed login counter to zero in the same operation, so an admin unlocking an account does not leave a stale failed count sitting behind it.

Response, 200 OK
```json
{
  "id": "integer",
  "message": "User updated",
  "fields_updated": ["array of field names actually changed"]
}
```

Response, 404, user not found
Response, 400, invalid role specified, or no recognized fields provided

### GET /auth/users
Purpose, admin lists all staff accounts. Patient-role accounts are excluded from this listing entirely, this route is for staff management only.

Query parameters, optional
```
page, integer, default 1
limit, integer, default 10
```

Response, 200 OK
```json
{
  "total": "integer",
  "page": "integer",
  "limit": "integer",
  "has_more": "boolean",
  "users": [
    {
      "id": "integer",
      "first_name": "string",
      "last_name": "string",
      "email": "string",
      "role": "string",
      "department": "string or null",
      "is_active": "boolean",
      "is_locked": "boolean",
      "created_at": "timestamp"
    }
  ]
}
```

## Patient routes, prefix /records

### POST /records/patients
Purpose, create a new patient record, and optionally, in the same call, create and link a portal account for that patient. Restricted to admin, doctor, nurse, and records officer.

Request body
```json
{
  "first_name": "string",
  "last_name": "string",
  "full_name": "string, optional alternative to first_name and last_name, split on the first space",
  "age": "integer, required",
  "gender": "string, optional",
  "phone": "string, optional",
  "address": "string, optional",
  "national_id": "string, optional, must be unique if provided",
  "assigned_doctor_id": "integer, optional, the id of the user this patient is primarily assigned to",
  "portal_email": "string, optional",
  "portal_password": "string, optional, only meaningful if portal_email is also present"
}
```

Note, if portal_email is present without portal_password, or portal_password without portal_email, no account is created and no error is raised, the patient record alone is still created successfully. Both fields must be present together for an account to be created.

Note, if national_id is provided and already exists on another patient, the request is rejected outright with a 409, since national_id is treated as a hard, non-negotiable duplicate signal. Separately, if first_name, last_name, age, and phone together match an existing patient, the record is still created, but the response carries a soft duplicate_warning for staff to review manually, since this kind of match is common enough in real intake scenarios that it should not block the action outright.

Response, 201 Created
```json
{
  "patient_id": "uuid",
  "hospital_id": "string, format MR-000001",
  "message": "Patient record created",
  "portal_account": "string, only present if an account was created",
  "duplicate_warning": "string, only present if a soft demographic match was found"
}
```

Response, 400, missing required fields, or invalid portal_email format
Response, 409, national_id already exists on another patient

### POST /records/patients/<id>/portal-account
Purpose, create and link a portal account for a patient who does not currently have one. This is the route to use when a patient's record was created without an account initially, and staff later decides to grant portal access. Restricted to the same roles as patient creation.

Request body
```json
{
  "portal_email": "string, required",
  "portal_password": "string, required"
}
```

Response, 201 Created
```json
{
  "user_id": "integer",
  "patient_id": "uuid",
  "message": "Portal account created and linked"
}
```

Response, 400, missing fields, patient already has a linked account, invalid email format, or email already registered to another account
Response, 404, patient not found
Response, 409, a concurrent request linked this patient to an account first. This is a genuine race condition guard, not a generic conflict, if two requests attempt to link the same patient at nearly the same moment, the database's own unique constraint on the link is what ultimately decides which one wins, and the loser receives this response rather than silently corrupting the link.

## Record routes, prefix /records

### GET /records
Purpose, list records visible to the logged in user, filtered server side by role before any client-supplied filter is even read. A patient account only ever sees records linked to their own patient_id, and this scoping cannot be widened by any combination of query parameters supplied by that same patient.

Query parameters, optional
```
page, integer, default 1
limit, integer, default 10
patient_id, uuid
record_type, string, see valid values below
date_from, date
date_to, date
```

Response, 200 OK
```json
{
  "total": "integer",
  "page": "integer",
  "limit": "integer",
  "has_more": "boolean",
  "records": [
    {
      "id": "uuid",
      "patient_name": "string",
      "record_type": "string",
      "uploaded_by_name": "string",
      "department": "string or null",
      "file_size": "integer or null",
      "created_at": "timestamp"
    }
  ]
}
```

Note, this list view never returns encrypted_data or a decrypted view of any kind, metadata only. Decryption only ever happens on the single-record view below.

Response, 403, patient account with no linked patient_id attempted to list records
Response, 400, malformed patient_id or invalid record_type supplied as a filter

### POST /records/upload
Purpose, upload a new patient record. A record may optionally include an attached file at the point of upload, or the file may be added afterward through the attach-file route below. Access is restricted in two layers, first by a general permission check confirming the role may upload records at all, second by a specific check confirming that role may upload this particular record_type.

Request, multipart form data
```
patient_id: uuid, required
record_type: string, required, see valid values below
data: json object as a string, required, the clinical content, encrypted before storage
file: binary file, optional
```

Valid record_type values, current
```
Lab Report
Imaging
Prescription
Discharge Summary
Vitals
Clinical Notes
```

Note, record_type upload permission by role, current
```
Doctor: Lab Report, Imaging, Prescription, Discharge Summary
Nurse: Vitals, Clinical Notes
Lab technician: Lab Report
Records officer: none, read only for all record types
```

Response, 201 Created
```json
{
  "record_id": "uuid",
  "checksum": "sha256 string",
  "message": "Record uploaded successfully."
}
```

Response, 400, missing required fields, invalid record_type, malformed patient_id, or data is not valid JSON
Response, 403, role not permitted to upload this specific record_type
Response, 502, the storage layer could not be reached, the record was not saved. This is distinct from a 500 deliberately, a 502 here specifically means the file storage backend itself was unreachable, not a database problem, and no partial record is left behind in either case.
Response, 500, a database failure occurred after a successful file upload, the uploaded file is automatically removed to avoid an orphaned file with no corresponding record

### PATCH /records/<id>/attach-file
Purpose, attach a file to an existing record that does not yet have one. This route intentionally cannot be used to replace a file already attached to a record, and it never modifies a record's encrypted_data or checksum under any circumstance. If the wrong file was attached, or if a record was uploaded with an error, this route is not the way to correct it, since correcting an existing entry in place would break the integrity guarantee the checksum exists to provide. The current design also has no separate correction workflow yet, this is flagged as an open item for the team below.

Request, multipart form data
```
file: binary file, required
```

Response, 200 OK
```json
{
  "record_id": "uuid",
  "file_path": "string",
  "message": "File attached successfully."
}
```

Response, 400, no file provided, or the record already has a file attached
Response, 403, role not permitted to upload this record's record_type
Response, 404, record not found
Response, 502, storage layer unreachable, no change was made
Response, 500, database failure after a successful file upload, the uploaded file is automatically removed

### GET /records/<id>
Purpose, view one specific record, decrypted for an authorized viewer only.

Response, 200 OK
```json
{
  "id": "uuid",
  "patient_id": "uuid",
  "patient_name": "string",
  "record_type": "string",
  "uploaded_by_name": "string",
  "department": "string or null",
  "data": "decrypted json object, the clinical content",
  "checksum": "sha256 string",
  "file_path": "string or null",
  "file_url": "string or null, a temporary signed URL valid for one hour, present only if a file is attached and the storage layer is reachable",
  "created_at": "timestamp"
}
```

Response, 403, a patient account attempted to view a record outside their own linked patient identity
Response, 404, record not found
Response, 500, either a checksum mismatch was detected on retrieval, meaning the stored data may have been corrupted or tampered with, or the record could not be decrypted at all, meaning a key mismatch or corruption occurred. Both cases are logged with full detail in the audit trail, the response to the caller intentionally does not distinguish between them, so as not to hand a potential attacker any information about which failure mode they triggered.

## Audit routes, prefix /audit, admin and auditor only

### GET /audit/logs
Purpose, view access logs.

Query parameters, optional
```
page, integer, default 1
limit, integer, default 10
user_id, integer
action, string, one of the audit action labels, see below
status, string, Success, Failed, Blocked, Error, or Review
date_from, date
date_to, date
```

Response, 200 OK
```json
{
  "total": "integer",
  "page": "integer",
  "limit": "integer",
  "has_more": "boolean",
  "logs": [
    {
      "id": "integer",
      "user_name": "string, or 'Unknown or unauthenticated' if the attempt was not tied to a real account",
      "role_at_time": "string",
      "action": "string",
      "record_id": "uuid or null",
      "ip_address": "string",
      "status": "string",
      "timestamp": "timestamp"
    }
  ]
}
```

### GET /audit/report/<record_id>
Purpose, generate a full access history for one specific patient record on demand.

Response, 200 OK
```json
{
  "record_id": "uuid",
  "total_accesses": "integer",
  "access_history": [
    {
      "user_name": "string",
      "action": "string",
      "status": "string",
      "timestamp": "timestamp"
    }
  ]
}
```

Response, 404, record not found

## Audit action labels

These are the exact string values stored in the action column and returned by the audit routes above, useful for building any filter dropdown on the frontend.

```
Login Success
Login Failed
Account Locked
Account Unlocked
Record Viewed
Record Uploaded
Permission Denied
User Created
User Updated
Role Changed
Patient Created
Duplicate Patient Warning
Audit Logs Viewed
Audit Report Viewed
```

## Error response shape, applies across all routes

```json
{
  "error": "short message describing what went wrong"
}
```

Standard status codes in use across this API, 200 success, 201 created, 400 bad request or validation error, 401 not authenticated, 403 authenticated but not permitted, 404 not found, 409 conflict, 423 account locked, 500 internal error, 502 an external dependency, currently only object storage, could not be reached.

## Open items for the team to confirm

Whether a formal correction or supersede workflow is needed for a record uploaded with genuinely wrong data, since the attach-file route deliberately does not solve this, and the current position is that a mistaken entry is followed by a new, correct entry rather than an edit to the old one, consistent with how paper and electronic medical records are corrected in practice, but this has not been discussed directly with the wider team.

Whether record and patient deletion should be built as a true delete or a soft delete, following the same pattern already used for user accounts, where a record is deactivated rather than removed, to preserve the audit trail's ability to prove what existed. No delete route currently exists for either records or patients.

Confirm the exact record_type and role permission mapping above against what the frontend has been designing toward, since Vitals and Clinical Notes were added to the original four record types partway through backend implementation.
