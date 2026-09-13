# KYC Document Storage Design — Neon Object Storage

**Date:** 2026-09-13
**Status:** Approved
**Issue:** [#59 KYC-7: Document upload and audited retrieval](https://github.com/Katlego-Sekoele/RemitX/issues/59)
**Supersedes:** the Azure Blob Storage + Azurite plan in
[#57](https://github.com/Katlego-Sekoele/RemitX/issues/57), which predates the
move off Azure ([2026-09-12-render-migration-design.md](./2026-09-12-render-migration-design.md))

## Summary

An applicant uploads an identity document and a proof of address; a reviewer
looks at them. The documents live in **Neon Object Storage** — an S3-compatible
bucket alongside the Neon Postgres the platform already uses — and the database
holds only their metadata.

Nothing in the platform's data protection story is under more pressure than
this feature: it accepts the only untrusted binary input RemitX takes, from
strangers, containing exactly the identity data POPIA and FICA are about, and
renders it back to staff. The design below is mostly a list of the ways that
can go wrong.

## Why Neon rather than Azure Blob Storage

Issue #57 specified an Azure Storage account with Azurite for local
development. Cloud compute has since moved to Render and Azure is being
destroyed, so a storage account would be the last Azure resource standing —
a second cloud account, a second credential model, and a second IaC provider
for one bucket.

Neon Object Storage is S3-compatible, in the same account and project as the
Postgres the platform already depends on, and needs no new provider. Being
S3-compatible is the load-bearing part: **MinIO** serves the same API locally,
so the application code cannot tell the two apart — only the endpoint and the
credentials change — and nobody needs a Neon account to run the KYC flow.

What is lost relative to #57's plan is Azure's managed identity: there is no
"the compute has an identity and requests a delegation key" story here, so the
API holds a long-lived bucket key pair in its environment. Stating that
plainly is the honest version of this trade. It is mitigated by scope — the key
is scoped to one bucket, it reaches only the API service and never the worker,
and the bucket holds nothing but KYC documents — but it is a permanent
credential in an environment variable, and the Azure design would not have had
one.

## The database indexes; the bucket holds bytes

`kyc_documents` rows carry `document_id`, `application_id`, `document_type`,
`status`, `storage_path`, `content_type`, `size_bytes`, `sha256`,
`uploaded_by_user_id`, `uploaded_at` and `stored_at`. No file content in
Postgres — a database dump taken to debug something should not contain
somebody's passport scan — and no file that is not in the table: an orphan
object is invisible to every access control the platform has.

**Object keys are opaque.** `kyc/{application_uuid}/{document_uuid}`, never
`kyc/naidoo-8801015009087-id.pdf`. Keys appear in storage access logs, in
metrics, and in any URL that gets pasted into a chat, so a key containing a
surname and an identity number leaks PII through channels nothing else covers.
Both ids are UUIDv4 — nothing guessable.

## Uploads go through the API

The browser POSTs the file to `POST /kyc/documents`. The API holds the bytes,
checks them, writes the object itself, and only then records the document as
stored. Nothing reaches the bucket that has not been looked at.

The alternative — a presigned URL and a direct browser-to-bucket PUT — was
built first and replaced. It is the standard pattern and it keeps bytes off a
0.5 GiB instance, but it can only ever validate a *declaration*: the client
says "a 40 KB PNG", the signature binds that size and type, and then a second
call has to fetch the object back to find out what actually arrived. Two round
trips to the bucket, a window in which unchecked content is sitting in it, and
a lifecycle with a failure mode at every step. Holding the bytes removes all
of that: there is one call, one decision point, and nothing to take on trust.

What it costs is that the API carries the file, which is why the size limit is
enforced three times over:

1. **`MaxBodySizeMiddleware`**, in front of every route, refuses a body larger
   than the document cap plus slack — before routing, so a request to a path
   that does not exist cannot cost anything either. Without it the limit would
   be a property of one endpoint, and any route taking JSON would happily
   buffer a gigabyte.
2. **`services/upload_stream.py`** refuses the declared `Content-Length`
   before reading a byte, then counts what actually arrives and stops at the
   limit. Chunked transfer encoding sends no length at all, so the running
   total is the real check: an oversized upload costs the bytes already read
   and nothing more.
3. **The controller** checks the length of what it was handed, so a bypass of
   either of the above is a bug rather than a breach.

Multipart is deliberately not used. The framework parses a multipart body into
a spooled temporary file *before* the handler runs, which puts the decision of
when to stop reading in the framework's hands. Here the body is the file —
`fetch(url, {body: file})` sets `Content-Type` and `Content-Length` from the
`File` without the caller doing anything — and the document's metadata travels
in the query string.

## What the API checks, in order

1. The application is the caller's own and still open. Somebody else's
   application id answers `404`, not `403`.
2. It is not already at its document limit: **six per application**, counting
   stored documents. A client cannot create a `pending` row on demand, so
   counting those would spend an applicant's allowance on our own outage.
3. The declared content type is on the allowlist, and **the bytes agree**. The
   type is read from the file's leading bytes — a declared `Content-Type` is a
   client assertion and a filename is a naming convention; `evil.pdf.exe` and
   a mislabelled header both pass an extension check.
   - Accepted: `application/pdf`, `image/jpeg`, `image/png`, `image/webp`.
   - **SVG is refused by name**, because it is a scriptable document and these
     files are rendered back to reviewers. "Unsupported file type" is a worse
     answer to that upload than naming it.
   - WebP is in the set because the `kyc_documents` CHECK constraint written
     for #56 already permits it and it is a non-scriptable raster format;
     narrowing it would be a migration for no security gain.
4. The SHA-256 is computed and checked against the application's other
   documents, so a reviewer is never handed two rows holding the same scan.
5. A `pending` row is written and committed, the object is put under that
   row's key, the bucket is asked to confirm what it holds, and the row
   becomes `stored`.

Step 5 is in that order because the row is what makes an object reachable by
anything. Putting the object first and writing the row second would, on a
failed insert, leave an object the database has never heard of — and an orphan
object is invisible to every access control this system has.

The digest is written at the last step rather than the first. A `pending` row
carrying one would collide, through the unique index on
`(application_id, sha256)`, with the retry that replaces it — so the one file
that failed to store would be the one file the applicant could never upload.

**No virus scanning.** Object-storage malware scanning is the real answer and
is out of scope. Type and size checks are not a substitute and are not claimed
to be.

## When storing fails

A `pending` row whose object never arrived is the shape every failure takes.
Nothing serves it, no reviewer sees it, it does not count towards the
applicant's limit, and the same file can be uploaded again. Where a write
half-succeeded — the object is there but smaller than what we sent — the
object is deleted and the row stays `pending`, because `stored` is supposed to
mean "we have seen this object in the bucket", not "the client library did not
raise".

## Retrieval is audited, short-lived and permissioned

`GET /admin/kyc/documents/{id}/url` requires `kyc:document:read`, writes a
`kyc.document.viewed` audit entry naming actor, document and application, and
returns a read-only URL valid five minutes. The applicant reaches their own
documents through the same mechanism, scoped to ownership, and audited the same
way. There is no long-lived URL anywhere and no endpoint that streams bytes
through the API.

Another applicant's document id answers `404`, not `403`: a 403 confirms the id
is real, which is most of what enumerating ids is for.

Reads are the one thing that does *not* go through the API, and for a
mechanical reason: a document is rendered by an `<img>` or a sandboxed
`<iframe>`, and neither can carry an `Authorization` header. Serving those
bytes through the API would mean inventing a signed-URL scheme of our own, so
they use the bucket's. A useful side effect of both decisions together is that
no CORS configuration is needed anywhere: uploads go to an origin the API
already allows, and `<img>`/`<iframe>` reads are not CORS requests.

**The reviewer's viewer is sandboxed.** PDFs render in an `<iframe sandbox="">`
— no scripts, no forms, no same-origin access — and images in an `<img>`.
Nothing is ever injected as HTML. If a browser declines to render a PDF under
the strictest sandbox, that is the safe failure; loosening the sandbox to make
rendering work would defeat it.

## The audit log

#59 cannot record a document view without somewhere to record it, and #54 —
the privileged-action audit log — says its table and `record_audit` helper
stand alone and can be built before the paths that write them. So this change
brings in `audit_log` and that single helper, on the shape #54 specifies:
actor, action, subject, `before`/`after` JSON scrubbed of PII, reason,
request id, created at.

What stays with #54: `GET /admin/audit`, the `/admin/audit` page, the
database-level denial of `UPDATE`/`DELETE`, and every action beyond
`kyc.document.viewed`. The helper stages into the caller's transaction rather
than committing, so an action and its audit entry land together or not at all.

For a read, `after` carries the subject's non-PII locator — which application
the document belongs to — because a document id alone does not answer "whose".

## Request correlation

`RequestIdMiddleware` tags every request and `record_audit` picks the id up
from a ContextVar, so `audit_log.request_id` is populated without every
controller carrying the value down. The id is generated by the API and never
read from the request: an inbound `X-Request-Id` would let a caller choose the
value that correlates their own entries in the audit log, including one that
collides with somebody else's.

## Retention

Deleting an application does not delete its documents. FICA §23 record-keeping
runs five years from the end of the relationship, so removal is a lifecycle
concern and no route offers it. A bucket lifecycle rule is where that expiry
would live; none is configured, because nothing in this project should age out
during it.

## Out of scope

- The applicant-facing upload UI — it belongs to the KYC wizard (#19). The API
  and the client function that posts a `File` to it are here and ready for it.
- The reviewer's application detail page (#20). This change ships the sandboxed
  viewer component and a `/admin/kyc/documents` page that renders documents for
  an application id, which #20 can absorb.
- Virus scanning, and any bucket lifecycle automation.
- Per-user upload rate limiting. The size cap bounds a single request and the
  document cap bounds an application, but nothing bounds how often an
  applicant may upload. Redis is already in the stack, so this is a small
  ticket rather than an architectural gap — it is left out because a limiter
  tuned without traffic to look at is a guess.
- Terraform-managed bucket creation: Neon buckets are created in the Neon
  console or API, and the only infrastructure change here is passing the
  endpoint and credentials to the API service.
