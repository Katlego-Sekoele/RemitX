# Clerk Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A signed-in browser session produces a verified caller identity inside FastAPI, backed by a `users` row.

**Architecture:** Clerk owns credentials. The SPA embeds Clerk's sign-in/sign-up components behind dedicated routes and guards app pages with a protected layout. Every API call carries a Clerk session token as a Bearer header; FastAPI verifies it with the official `clerk-backend-api` SDK and provisions a local `users` row just-in-time on first contact.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, `clerk-backend-api` (Python), React Router v7 (SPA mode), `@clerk/react-router` 3.6.14, TanStack Query.

**Spec:** [docs/superpowers/specs/2026-08-19-clerk-auth-design.md](../specs/2026-08-19-clerk-auth-design.md)

## Global Constraints

- **Python floor is 3.11.** `requires-python = ">=3.11"`, ruff `target-version = "py311"`. PEP 604 unions and `match` are legal from Task 2 onward.
- **Local Python is 3.9.6.** The venv MUST be rebuilt against a 3.11 interpreter before Task 2's tests can run. Alternative: run the API through Docker Compose, already on 3.11.
- **Clerk SDK pin:** `clerk-backend-api>=7.0.0,<8`.
- **Alembic owns the Postgres schema.** A new table needs an ORM model AND a migration. `alembic check` must report no drift.
- **Every ORM model inherits `Base` from `remitx_api/extensions.py` and is imported in `remitx_api/models/orm/__init__.py`**, or its table is invisible to SQLAlchemy metadata.
- **`remitx_api/__init__.py` eagerly imports `create_app`.** `remitx_worker` may import `remitx_api`; never the reverse.
- **`Repository.save`/`delete` commit internally.** Multi-entity transactions use `db.session` directly in the controller.
- **Frontend Prettier:** no semicolons, double quotes, 2-space indent, 80 cols. The pre-commit hook rewrites files otherwise.
- **UI standard:** compose from shadcn/ui and Aceternity. Tailwind for layout only — no ad-hoc component styling.
- **XRPL Testnet only. Secrets never logged, returned, or committed.**

---

### Task 1: Revert unrelated working-tree drift

The branch carries compose changes unrelated to auth. Starting from a clean base keeps the auth diff reviewable.

**Files:**
- Modify: `docker-compose.dev.yml`
- Modify: `docker-compose.yml`
- Modify: `frontend/Dockerfile.dev`

**Interfaces:**
- Consumes: nothing
- Produces: a clean base; frontend image installs dependencies at build time, not container start

- [ ] **Step 1: Inspect the drift**

```bash
git diff docker-compose.dev.yml docker-compose.yml frontend/Dockerfile.dev
```

Expected: three changes — `depends_on: api` removed from the dev compose frontend service, and `npm ci &&` prepended to the start command in both compose files and the Dockerfile.

- [ ] **Step 2: Restore the frontend service's `depends_on` in the dev compose**

In `docker-compose.dev.yml`, the frontend service must read:

```yaml
    volumes:
      - ./frontend:/app
      - frontend_node_modules:/app/node_modules
    depends_on:
      - api
    stdin_open: true
    tty: true
```

- [ ] **Step 3: Revert the start commands**

In `frontend/Dockerfile.dev`, restore:

```dockerfile
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
```

In `docker-compose.yml` and `docker-compose.dev.yml`, delete the added `command: sh -c "npm ci && npm run dev -- --host 0.0.0.0 --port 5173"` lines entirely. The image's `CMD` is correct.

- [ ] **Step 4: Rebuild the frontend image so the Clerk dependency lands in it**

Run: `docker compose -f docker-compose.dev.yml build frontend`
Expected: build succeeds, `@clerk/react-router` installed during `npm ci` in the image layer.

- [ ] **Step 5: Verify the diff is now auth-only**

```bash
git diff --stat docker-compose.dev.yml docker-compose.yml frontend/Dockerfile.dev
```

Expected: no output — all three files match HEAD.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.dev.yml docker-compose.yml frontend/Dockerfile.dev
git commit -m "chore: revert unrelated compose drift"
```

---

### Task 2: Python 3.11 floor, Clerk SDK, and config

**Files:**
- Modify: `api/pyproject.toml`
- Modify: `api/remitx_api/config.py`
- Modify: `CLAUDE.md`
- Test: `api/tests/test_config.py` (create)

**Interfaces:**
- Consumes: nothing
- Produces: `Config.CLERK_SECRET_KEY: str` (empty string when unset), `TestConfig.CLERK_SECRET_KEY = "sk_test_fake"`

- [ ] **Step 1: Rebuild the virtualenv on Python 3.11**

The system interpreter is 3.9.6 and cannot install the SDK. Confirm a 3.11 interpreter exists:

```bash
python3.11 --version
```

If missing, install it (`brew install python@3.11` or `pyenv install 3.11`). Then:

```bash
cd api && rm -rf .venv && python3.11 -m venv .venv && source .venv/bin/activate && python --version
```

Expected: `Python 3.11.x`

- [ ] **Step 2: Write the failing test**

Create `api/tests/test_config.py`:

```python
from remitx_api.config import Config, TestConfig


def test_clerk_secret_key_defaults_to_empty(monkeypatch):
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    assert Config().CLERK_SECRET_KEY == ""


def test_clerk_secret_key_reads_env(monkeypatch):
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_abc")
    assert Config().CLERK_SECRET_KEY == "sk_test_abc"


def test_test_config_supplies_a_fake_secret():
    assert TestConfig().CLERK_SECRET_KEY == "sk_test_fake"
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd api && pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: type object 'Config' has no attribute 'CLERK_SECRET_KEY'`

- [ ] **Step 4: Read the env var as a class attribute, not a frozen default**

`Config` reads env vars at class-definition time, so `monkeypatch.setenv` inside a test would not be seen by an already-imported class attribute. Make it a property-backed read.

In `api/remitx_api/config.py`, add to `Config`:

```python
    # Read per-instance rather than at class-definition time: tests
    # monkeypatch the environment after import, and a class attribute would
    # freeze whatever was set when the module first loaded.
    @property
    def CLERK_SECRET_KEY(self) -> str:
        return os.getenv("CLERK_SECRET_KEY", "")
```

And to `TestConfig`:

```python
    # Verification is always mocked in tests; this only has to be non-empty
    # so the "not configured" guard in auth/clerk.py does not trip.
    CLERK_SECRET_KEY = "sk_test_fake"
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd api && pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 6: Bump the Python floor and add the SDK**

In `api/pyproject.toml`:

```toml
requires-python = ">=3.11"
```

Add to `dependencies`:

```toml
    "clerk-backend-api>=7.0.0,<8",
```

Under `[tool.ruff]`:

```toml
target-version = "py311"
```

- [ ] **Step 7: Install and verify the whole suite still passes**

```bash
cd api && source .venv/bin/activate && pip install -e '.[dev]'
pytest
ruff check .
```

Expected: all tests pass, ruff clean.

- [ ] **Step 8: Update CLAUDE.md**

Replace the paragraph beginning `**Python version:** `requires-python >= 3.9`` with:

```markdown
**Python version:** `requires-python >= 3.11`, ruff targets `py311`, and the
Docker image is `python:3.11` — local venvs, CI, and production all run the
same minor. The floor is 3.11 because `clerk-backend-api` requires >= 3.10;
match the Docker image rather than the SDK minimum so no version gap can open
between local and production.
```

- [ ] **Step 9: Commit**

```bash
git add api/pyproject.toml api/remitx_api/config.py api/tests/test_config.py CLAUDE.md
git commit -m "feat: bump to Python 3.11 and add Clerk backend SDK"
```

---

### Task 3: User ORM model and migration

**Files:**
- Create: `api/remitx_api/models/orm/user.py`
- Modify: `api/remitx_api/models/orm/__init__.py`
- Create: `api/alembic/versions/V<timestamp>__create_users.py` (generated)
- Test: `api/tests/test_user_model.py` (create)

**Interfaces:**
- Consumes: `Base` from `remitx_api.extensions`
- Produces: `User` with fields `id: uuid.UUID`, `clerk_user_id: str`, `email: str | None`, `created_at: datetime`, `updated_at: datetime`; table `users`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_user_model.py`:

```python
import uuid

import pytest
from remitx_api.extensions import db
from remitx_api.models.orm.user import User
from sqlalchemy.exc import IntegrityError


def test_user_persists_with_generated_id(app_context):
    user = User(clerk_user_id="user_abc", email="a@example.com")
    db.session.add(user)
    db.session.commit()

    assert isinstance(user.id, uuid.UUID)
    assert user.created_at is not None
    assert user.updated_at is not None


def test_email_is_optional(app_context):
    user = User(clerk_user_id="user_no_email")
    db.session.add(user)
    db.session.commit()

    assert user.email is None


def test_clerk_user_id_is_unique(app_context):
    db.session.add(User(clerk_user_id="user_dupe"))
    db.session.commit()

    db.session.add(User(clerk_user_id="user_dupe"))
    with pytest.raises(IntegrityError):
        db.session.commit()
```

- [ ] **Step 2: Add the `app_context` fixture**

These tests need a database session outside an HTTP request. Add to `api/tests/conftest.py`:

```python
@pytest.fixture
def app_context():
    """Open a DB session outside a request, for repository/model tests.

    The app's session middleware only runs per-request, so anything touching
    db.session directly has to open one itself.
    """
    app = create_app(TestConfig)
    with TestClient(app):
        token = db.open_session()
        try:
            yield
        finally:
            db.close_session(token)
```

Add the import at the top of `conftest.py`:

```python
from remitx_api.extensions import db
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd api && pytest tests/test_user_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'remitx_api.models.orm.user'`

- [ ] **Step 4: Create the model**

Create `api/remitx_api/models/orm/user.py`:

```python
"""Application user, mirrored from Clerk.

Clerk owns credentials and profile data. This table exists so domain records
(beneficiaries, wallets, transfers) have a stable local foreign key, and so
queries can join on identity without calling out to Clerk.

Rows are created just-in-time on the first authenticated request — see
remitx_api/controllers/user_controller.py.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


# Defined here rather than imported from integration_message.py: that model is
# marked THROWAWAY and gets deleted once real remittance flows land, and this
# one must not depend on a file scheduled for removal.
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    # Clerk's `sub` claim. Unique so just-in-time provisioning can rely on the
    # database to arbitrate concurrent first requests from the same caller.
    clerk_user_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
        index=True,
    )
    # Nullable: not every Clerk sign-in strategy yields an email claim.
    email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
```

- [ ] **Step 5: Register the model**

Rewrite `api/remitx_api/models/orm/__init__.py`:

```python
"""SQLAlchemy ORM models. Import models here so metadata is registered."""

from remitx_api.extensions import Base
from remitx_api.models.orm.integration_message import IntegrationMessage
from remitx_api.models.orm.user import User

__all__ = ["Base", "IntegrationMessage", "User"]
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd api && pytest tests/test_user_model.py -v`
Expected: 3 passed

- [ ] **Step 7: Generate the migration**

The dev database must be running and at head first:

```bash
docker compose -f docker-compose.dev.yml up -d postgres
cd api && source .venv/bin/activate
alembic upgrade head
alembic revision --autogenerate -m "create users"
```

- [ ] **Step 8: Review the generated migration**

Open the new file in `api/alembic/versions/`. Confirm it creates the `users` table with a unique constraint and index on `clerk_user_id`, and that `down_revision` points at the integration-messages revision. Autogenerate sometimes emits a redundant index alongside `unique=True` — remove the duplicate if present.

- [ ] **Step 9: Verify no drift**

```bash
cd api && alembic upgrade head && alembic check
```

Expected: `No new upgrade operations detected.`

- [ ] **Step 10: Commit**

```bash
git add api/remitx_api/models/orm/ api/alembic/versions/ api/tests/test_user_model.py api/tests/conftest.py
git commit -m "feat: add User model and users migration"
```

---

### Task 4: User repository and just-in-time provisioning

**Files:**
- Create: `api/remitx_api/repositories/user_repository.py`
- Create: `api/remitx_api/controllers/user_controller.py`
- Test: `api/tests/test_user_provisioning.py` (create)

**Interfaces:**
- Consumes: `User` from Task 3
- Produces: `UserRepository.get_by_clerk_id(clerk_user_id: str) -> User | None`; `UserController.ensure_provisioned(clerk_user_id: str, resolve_email: Callable[[], str | None]) -> User`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_user_provisioning.py`:

```python
import pytest
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.user import User
from remitx_api.repositories.user_repository import UserRepository
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def test_get_by_clerk_id_returns_none_when_absent(app_context):
    assert UserRepository().get_by_clerk_id("user_missing") is None


def test_first_call_inserts_the_user(app_context):
    user = UserController().ensure_provisioned(
        "user_new", lambda: "new@example.com"
    )

    assert user.clerk_user_id == "user_new"
    assert user.email == "new@example.com"
    assert UserRepository().get_by_clerk_id("user_new") is not None


def test_email_resolver_runs_only_on_insert(app_context):
    """Returning users must not trigger a Clerk API call."""
    calls = {"n": 0}

    def resolve():
        calls["n"] += 1
        return "once@example.com"

    controller = UserController()
    controller.ensure_provisioned("user_once", resolve)
    controller.ensure_provisioned("user_once", resolve)

    assert calls["n"] == 1


def test_repeat_call_is_idempotent(app_context):
    controller = UserController()
    first = controller.ensure_provisioned("user_same", lambda: "same@example.com")
    second = controller.ensure_provisioned("user_same", lambda: "same@example.com")

    assert first.id == second.id
    rows = db.session.scalars(
        select(User).where(User.clerk_user_id == "user_same")
    ).all()
    assert len(rows) == 1


def test_lost_insert_race_returns_the_winning_row(app_context, monkeypatch):
    """Two concurrent first requests: the loser must get the winner's row.

    Simulated by making the repository's save raise IntegrityError once, as
    the database would when the unique constraint rejects the second insert,
    while the winning row already exists.
    """
    controller = UserController()
    winner = controller.ensure_provisioned("user_race", lambda: "race@example.com")

    calls = {"n": 0}
    original_save = UserRepository.save

    def flaky_save(self, entity):
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError("duplicate key", None, Exception())
        return original_save(self, entity)

    monkeypatch.setattr(UserRepository, "save", flaky_save)

    loser = UserController().ensure_provisioned(
        "user_race", lambda: "race@example.com"
    )
    assert loser.id == winner.id


def test_race_reraises_when_no_row_appears(app_context, monkeypatch):
    """An IntegrityError that is not a lost race must not be swallowed."""

    def always_fails(self, entity):
        raise IntegrityError("some other constraint", None, Exception())

    monkeypatch.setattr(UserRepository, "save", always_fails)

    with pytest.raises(IntegrityError):
        UserController().ensure_provisioned("user_broken", lambda: None)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd api && pytest tests/test_user_provisioning.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'remitx_api.repositories.user_repository'`

- [ ] **Step 3: Create the repository**

Create `api/remitx_api/repositories/user_repository.py`:

```python
import uuid
from typing import Optional

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.user import User
from remitx_api.repositories.repository import Repository


class UserRepository(Repository[User, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(User)

    def get_by_clerk_id(self, clerk_user_id: str) -> Optional[User]:
        return db.session.scalars(
            select(User).where(User.clerk_user_id == clerk_user_id)
        ).first()
```

- [ ] **Step 4: Create the controller**

Create `api/remitx_api/controllers/user_controller.py`:

```python
from typing import Callable, Optional

from sqlalchemy.exc import IntegrityError

from remitx_api.extensions import db
from remitx_api.models.orm.user import User
from remitx_api.repositories.user_repository import UserRepository


class UserController:
    def __init__(self) -> None:
        self._users = UserRepository()

    def ensure_provisioned(
        self,
        clerk_user_id: str,
        resolve_email: Callable[[], Optional[str]],
    ) -> User:
        """Return the local row for a Clerk identity, creating it on first sight.

        Clerk is the source of truth for who a user is; this row exists so
        domain records have a local foreign key to hang off.

        `resolve_email` is a callable rather than a value because resolving it
        costs a Clerk API call — email is not a session-token claim. Returning
        users short-circuit above, so the call happens once per user lifetime
        and never on the hot path.
        """
        existing = self._users.get_by_clerk_id(clerk_user_id)
        if existing is not None:
            return existing

        try:
            return self._users.save(
                User(clerk_user_id=clerk_user_id, email=resolve_email())
            )
        except IntegrityError:
            # A concurrent first request from the same caller won the insert.
            # The unique constraint on clerk_user_id is what arbitrates; roll
            # back the failed transaction and take the winner's row.
            db.session.rollback()
            winner = self._users.get_by_clerk_id(clerk_user_id)
            if winner is None:
                # Not a lost race — some other constraint failed. Surface it.
                raise
            return winner
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd api && pytest tests/test_user_provisioning.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add api/remitx_api/repositories/user_repository.py api/remitx_api/controllers/user_controller.py api/tests/test_user_provisioning.py
git commit -m "feat: add user repository and just-in-time provisioning"
```

---

### Task 5: Clerk token verification

**Files:**
- Create: `api/remitx_api/auth/__init__.py`
- Create: `api/remitx_api/auth/clerk.py`
- Test: `api/tests/test_clerk_verification.py` (create)

**Interfaces:**
- Consumes: `Config.CLERK_SECRET_KEY`, `Config.CORS_ORIGINS`
- Produces: `ClerkClaims(clerk_user_id: str, email: str | None)`; `verify_request(request: Request, config: Config) -> ClerkClaims`; `fetch_user_email(clerk_user_id: str, config: Config) -> str | None`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_clerk_verification.py`:

```python
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from remitx_api.auth import clerk as clerk_module
from remitx_api.auth.clerk import ClerkClaims, fetch_user_email, verify_request
from remitx_api.config import TestConfig


class _FakeRequest:
    """Minimal stand-in for a Starlette Request."""

    def __init__(self, headers=None):
        self.method = "GET"
        self.url = "http://testserver/integration-messages"
        self.headers = headers or {}


def _stub_sdk(monkeypatch, state):
    """Replace the Clerk SDK with one returning a fixed request state."""
    sdk = SimpleNamespace(authenticate_request=lambda request, options: state)
    monkeypatch.setattr(clerk_module, "_sdk", lambda secret_key: sdk)


def test_returns_claims_for_a_signed_in_request(monkeypatch):
    _stub_sdk(
        monkeypatch,
        SimpleNamespace(
            is_signed_in=True,
            payload={"sub": "user_abc", "email": "a@example.com"},
        ),
    )

    claims = verify_request(_FakeRequest(), TestConfig())

    assert claims == ClerkClaims(clerk_user_id="user_abc", email="a@example.com")


def test_email_is_optional(monkeypatch):
    _stub_sdk(
        monkeypatch,
        SimpleNamespace(is_signed_in=True, payload={"sub": "user_abc"}),
    )

    assert verify_request(_FakeRequest(), TestConfig()).email is None


def test_rejects_a_signed_out_request(monkeypatch):
    _stub_sdk(monkeypatch, SimpleNamespace(is_signed_in=False, payload=None))

    with pytest.raises(HTTPException) as caught:
        verify_request(_FakeRequest(), TestConfig())

    assert caught.value.status_code == 401
    assert caught.value.headers["WWW-Authenticate"] == "Bearer"


def test_rejects_a_token_without_a_subject(monkeypatch):
    _stub_sdk(
        monkeypatch,
        SimpleNamespace(is_signed_in=True, payload={"email": "a@example.com"}),
    )

    with pytest.raises(HTTPException) as caught:
        verify_request(_FakeRequest(), TestConfig())

    assert caught.value.status_code == 401


def test_fetch_user_email_reads_the_primary_address(monkeypatch):
    """Email is not a session-token claim, so it comes from the Backend API."""
    user = SimpleNamespace(
        primary_email_address_id="idn_1",
        email_addresses=[
            SimpleNamespace(id="idn_0", email_address="old@example.com"),
            SimpleNamespace(id="idn_1", email_address="primary@example.com"),
        ],
    )
    sdk = SimpleNamespace(users=SimpleNamespace(get=lambda user_id: user))
    monkeypatch.setattr(clerk_module, "_sdk", lambda secret_key: sdk)

    assert fetch_user_email("user_abc", TestConfig()) == "primary@example.com"


def test_fetch_user_email_returns_none_when_lookup_fails(monkeypatch):
    """A profile lookup failure must not block sign-in — email is optional."""

    def explode(user_id):
        raise RuntimeError("clerk is down")

    sdk = SimpleNamespace(users=SimpleNamespace(get=explode))
    monkeypatch.setattr(clerk_module, "_sdk", lambda secret_key: sdk)

    assert fetch_user_email("user_abc", TestConfig()) is None


def test_raises_when_the_secret_key_is_not_configured():
    class Unconfigured(TestConfig):
        CLERK_SECRET_KEY = ""

    with pytest.raises(RuntimeError, match="CLERK_SECRET_KEY"):
        verify_request(_FakeRequest(), Unconfigured())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd api && pytest tests/test_clerk_verification.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'remitx_api.auth'`

- [ ] **Step 3: Create the package marker**

Create `api/remitx_api/auth/__init__.py`:

```python
"""Authentication: Clerk token verification and FastAPI dependencies.

Cross-cutting, so it sits beside the route/controller/repository layers
rather than inside one of them.
"""
```

- [ ] **Step 4: Create the verifier**

Create `api/remitx_api/auth/clerk.py`:

```python
"""Verify Clerk session tokens.

The SDK takes an httpx.Request rather than a Starlette one, so this module
adapts between them and converts Clerk's request state into a small domain
object. Nothing outside this module needs to know Clerk exists.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import httpx
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
from fastapi import HTTPException, status


@dataclass(frozen=True)
class ClerkClaims:
    clerk_user_id: str
    email: Optional[str]


def _unauthorized() -> HTTPException:
    # A fresh instance per call: FastAPI mutates nothing here, but a shared
    # module-level exception object is a trap waiting for the first handler
    # that attaches request-specific detail.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


@lru_cache(maxsize=1)
def _sdk(secret_key: str) -> Clerk:
    """One SDK instance per secret key.

    Cached because the client holds a connection pool and Clerk's JWKS cache;
    building one per request would refetch signing keys constantly.
    """
    return Clerk(bearer_auth=secret_key)


def _to_httpx(request) -> httpx.Request:
    """Adapt a Starlette request to the httpx one the Clerk SDK expects.

    Deliberately bodyless: verification reads only the method, URL, and
    headers. Consuming the request stream here would leave the route handler
    with nothing to read.
    """
    return httpx.Request(
        method=request.method,
        url=str(request.url),
        headers=list(request.headers.items()),
    )


def verify_request(request, config) -> ClerkClaims:
    """Return the caller's claims, or raise 401.

    Raises RuntimeError — not 401 — when the secret key is missing: that is a
    deployment fault, and returning 401 would disguise it as a client error.
    """
    secret_key = config.CLERK_SECRET_KEY
    if not secret_key:
        raise RuntimeError("CLERK_SECRET_KEY is not configured")

    state = _sdk(secret_key).authenticate_request(
        _to_httpx(request),
        AuthenticateRequestOptions(
            # Reuses CORS_ORIGINS: both answer "which browser origins are
            # legitimate", so one list cannot drift from the other.
            authorized_parties=config.CORS_ORIGINS,
            accepts_token=["session_token"],
        ),
    )

    if not state.is_signed_in:
        raise _unauthorized()

    payload = state.payload or {}
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise _unauthorized()

    return ClerkClaims(
        clerk_user_id=clerk_user_id,
        # Absent from Clerk's default session token. Present only if someone
        # adds a JWT template claim; fetch_user_email is the reliable path.
        email=payload.get("email"),
    )


def fetch_user_email(clerk_user_id: str, config) -> Optional[str]:
    """Look up a user's primary email via Clerk's Backend API.

    Email is not a default session-token claim, so it cannot come from
    verification. Called only when provisioning a new local row — never on the
    hot path — so the network cost is once per user lifetime.

    Returns None rather than raising: a profile lookup failing is not a reason
    to reject an otherwise valid session, and the column is nullable.
    """
    try:
        user = _sdk(config.CLERK_SECRET_KEY).users.get(user_id=clerk_user_id)
        primary_id = getattr(user, "primary_email_address_id", None)
        addresses = getattr(user, "email_addresses", None) or []
        for address in addresses:
            if address.id == primary_id:
                return address.email_address
        return addresses[0].email_address if addresses else None
    except Exception:
        # Deliberately broad: any SDK or transport failure degrades to "no
        # email on file" rather than a failed sign-in.
        return None
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd api && pytest tests/test_clerk_verification.py -v`
Expected: 5 passed

- [ ] **Step 6: Confirm the SDK's import paths are real**

The import paths matter and vary between SDK majors. Verify:

```bash
cd api && python -c "
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
print('imports ok')
print([p for p in dir(Clerk) if 'authenticate' in p.lower()])
"
```

Expected: `imports ok` and a list containing `authenticate_request`. If either import fails, find the correct path with `python -c "import clerk_backend_api, pkgutil; print([m.name for m in pkgutil.walk_packages(clerk_backend_api.__path__, 'clerk_backend_api.')])"` and fix the module's imports before continuing.

- [ ] **Step 7: Commit**

```bash
git add api/remitx_api/auth/ api/tests/test_clerk_verification.py
git commit -m "feat: verify Clerk session tokens"
```

---

### Task 6: Current-user dependency and protected endpoints

**Files:**
- Create: `api/remitx_api/auth/dependencies.py`
- Modify: `api/remitx_api/routes/integration_messages.py`
- Modify: `api/tests/conftest.py`
- Test: `api/tests/test_auth_dependency.py` (create)

**Interfaces:**
- Consumes: `verify_request`, `fetch_user_email`, `ClerkClaims` (Task 5); `UserController.ensure_provisioned` (Task 4)
- Produces: `get_current_user(request) -> User` for `Depends`; `client` fixture authenticated by default; `anonymous_client` fixture unauthenticated

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_auth_dependency.py`:

```python
def test_list_requires_authentication(anonymous_client):
    response = anonymous_client.get("/integration-messages")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_create_requires_authentication(anonymous_client):
    response = anonymous_client.post(
        "/integration-messages",
        json={"body": "hello"},
    )

    assert response.status_code == 401


def test_health_stays_public(anonymous_client):
    # Container Apps probes this endpoint without credentials.
    assert anonymous_client.get("/health").status_code == 200


def test_authenticated_client_can_list(client):
    assert client.get("/integration-messages").status_code == 200
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd api && pytest tests/test_auth_dependency.py -v`
Expected: FAIL — `anonymous_client` fixture does not exist, and the endpoints return 200 rather than 401.

- [ ] **Step 3: Create the dependency**

Create `api/remitx_api/auth/dependencies.py`:

```python
"""FastAPI dependencies exposing the authenticated caller.

Handlers receive a User, never a token or a raw claim dict, so no route has
to know that Clerk is the identity provider.
"""

from fastapi import Request

from remitx_api.auth.clerk import fetch_user_email, verify_request
from remitx_api.controllers.user_controller import UserController
from remitx_api.models.orm.user import User

_users = UserController()


def get_current_user(request: Request) -> User:
    config = request.app.state.config
    claims = verify_request(request, config)

    # Passed as a callable, not a value: provisioning only invokes it when it
    # actually has to insert, so returning users cost no Clerk API call.
    def resolve_email():
        return claims.email or fetch_user_email(claims.clerk_user_id, config)

    return _users.ensure_provisioned(claims.clerk_user_id, resolve_email)
```

- [ ] **Step 4: Protect the endpoints**

In `api/remitx_api/routes/integration_messages.py`, add the imports:

```python
from fastapi import APIRouter, Depends, Query, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.models.orm.user import User
```

Then add the dependency to both handlers:

```python
@router.post(
    "",
    response_model=IntegrationMessageRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_integration_message(
    payload: IntegrationMessageCreate,
    user: User = Depends(get_current_user),
):
    return controller.create(payload)


@router.get("", response_model=list[IntegrationMessageRead])
def list_integration_messages(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    user: User = Depends(get_current_user),
):
    return controller.list_recent(limit)
```

`user` is intentionally unused for now — the messages are not yet scoped per user. It is declared so the dependency runs and the endpoint is gated.

- [ ] **Step 5: Update the fixtures**

In `api/tests/conftest.py`, add the imports:

```python
import uuid

from remitx_api.auth.dependencies import get_current_user
from remitx_api.models.orm.user import User
```

Replace the `client` fixture and add its anonymous sibling:

```python
@pytest.fixture
def current_user():
    """The caller every authenticated test acts as.

    Not persisted: no endpoint reads it back from the database yet. The first
    route that scopes data per user will need this inserted instead.
    """
    return User(
        id=uuid.uuid4(),
        clerk_user_id="user_test",
        email="test@example.com",
    )


@pytest.fixture
def client(current_user):
    """Authenticated client. Token verification is bypassed, not faked —
    exercising real Clerk verification is test_clerk_verification.py's job."""
    app = create_app(TestConfig)
    app.dependency_overrides[get_current_user] = lambda: current_user
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def anonymous_client():
    """Client with no auth override, so the real dependency runs and rejects."""
    app = create_app(TestConfig)
    with TestClient(app) as test_client:
        yield test_client
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd api && pytest tests/test_auth_dependency.py -v`
Expected: 4 passed

- [ ] **Step 7: Run the whole suite**

Run: `cd api && pytest && ruff check .`
Expected: all pass. Pre-existing integration-message tests keep working through the authenticated `client` fixture.

- [ ] **Step 8: Commit**

```bash
git add api/remitx_api/auth/dependencies.py api/remitx_api/routes/integration_messages.py api/tests/conftest.py api/tests/test_auth_dependency.py
git commit -m "feat: require authentication on integration-message endpoints"
```

---

### Task 7: Frontend token plumbing

**Files:**
- Modify: `frontend/app/lib/api.ts`
- Create: `frontend/app/lib/use-api.ts`
- Modify: `frontend/app/lib/query-client.ts`
- Create: `frontend/app/components/auth-error-bridge.tsx`
- Modify: `frontend/app/routes/integration-test.tsx`

**Interfaces:**
- Consumes: `useAuth`, `useClerk` from `@clerk/react-router`
- Produces: `type GetToken = () => Promise<string | null>`; `useApi()` returning `{ listIntegrationMessages: () => Promise<IntegrationMessage[]>, sendIntegrationMessage: (body: string) => Promise<IntegrationMessage> }`; `setSessionExpiredHandler(handler: (() => void) | null)`; `<AuthErrorBridge />`

- [ ] **Step 1: Thread a token getter through `request`**

In `frontend/app/lib/api.ts`, add the type above `request`:

```ts
export type GetToken = () => Promise<string | null>
```

Change `request` to take it and set the header:

```ts
async function request<T>(
  getToken: GetToken,
  path: string,
  init?: RequestInit
): Promise<T> {
  const token = await getToken()

  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        // Only when there is a body to describe. `application/json` is not a
        // CORS-safelisted content type, so sending it on a bodyless GET forces
        // an OPTIONS preflight — two round trips per poll, once a second.
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        // Authorization is never CORS-safelisted, so this preflights
        // regardless. The response is cacheable, so it costs one extra round
        // trip per origin per max-age, not one per request.
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError(`Could not reach the API at ${API_URL}`, 0)
  }

  if (!response.ok) {
    throw new ApiError(await describeFailure(response), response.status)
  }

  return (await response.json()) as T
}
```

- [ ] **Step 2: Update the two exported functions**

```ts
export function listIntegrationMessages(
  getToken: GetToken
): Promise<IntegrationMessage[]> {
  return request<IntegrationMessage[]>(getToken, "/integration-messages")
}

export function sendIntegrationMessage(
  getToken: GetToken,
  body: string
): Promise<IntegrationMessage> {
  return request<IntegrationMessage>(getToken, "/integration-messages", {
    method: "POST",
    body: JSON.stringify({ body }),
  })
}
```

- [ ] **Step 3: Create the hook**

Create `frontend/app/lib/use-api.ts`:

```ts
import { useAuth } from "@clerk/react-router"
import { useMemo } from "react"

import {
  listIntegrationMessages,
  sendIntegrationMessage,
  type IntegrationMessage,
} from "~/lib/api"

/**
 * Binds the API functions to the current Clerk session.
 *
 * Memoised on getToken so the returned object is referentially stable —
 * an unstable identity here would retrigger every TanStack Query that
 * uses one of these as its queryFn.
 */
export function useApi() {
  const { getToken } = useAuth()

  return useMemo(
    () => ({
      listIntegrationMessages: (): Promise<IntegrationMessage[]> =>
        listIntegrationMessages(getToken),
      sendIntegrationMessage: (body: string): Promise<IntegrationMessage> =>
        sendIntegrationMessage(getToken, body),
    }),
    [getToken]
  )
}
```

- [ ] **Step 4: Point the integration-test route at the hook**

In `frontend/app/routes/integration-test.tsx`, replace the `~/lib/api` import with:

```ts
import { MESSAGE_MAX_LENGTH, type IntegrationMessage } from "~/lib/api"
import { useApi } from "~/lib/use-api"
```

Inside `IntegrationTest`, add below `const queryClient = useQueryClient()`:

```ts
  const api = useApi()
```

Change the two call sites:

```ts
    queryFn: api.listIntegrationMessages,
```

```ts
    mutationFn: api.sendIntegrationMessage,
```

- [ ] **Step 5: Route 401s to the sign-in redirect**

An expired session is expected, not an error to render. Handle it once in the
query cache so routes added later inherit the behaviour.

Replace `frontend/app/lib/query-client.ts`:

```ts
import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query"

import { ApiError } from "~/lib/api"

// Set by <AuthErrorBridge /> once Clerk context exists. The QueryClient is a
// module singleton built outside React — QueryClientProvider lives in root's
// Layout, outside ClerkProvider — so it cannot call Clerk hooks itself.
let onSessionExpired: (() => void) | null = null

export function setSessionExpiredHandler(handler: (() => void) | null) {
  onSessionExpired = handler
}

function handleError(error: unknown) {
  if (error instanceof ApiError && error.status === 401) {
    onSessionExpired?.()
  }
}

export const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: handleError }),
  mutationCache: new MutationCache({ onError: handleError }),
  defaultOptions: {
    queries: {
      // Never retry a 4xx: the answer will not change, and retrying a 401
      // doubles every request made with a dead session.
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
          return false
        }
        return failureCount < 1
      },
      refetchOnWindowFocus: false,
    },
  },
})
```

- [ ] **Step 6: Create the bridge component**

Create `frontend/app/components/auth-error-bridge.tsx`:

```tsx
import { useAuth, useClerk } from "@clerk/react-router"
import { useEffect } from "react"

import { setSessionExpiredHandler } from "~/lib/query-client"

/**
 * Sends API 401s to Clerk's sign-in redirect.
 *
 * Renders nothing. Exists because the query cache is created outside React
 * and cannot reach Clerk's context on its own.
 */
export function AuthErrorBridge() {
  const { isSignedIn } = useAuth()
  const clerk = useClerk()

  useEffect(() => {
    setSessionExpiredHandler(() => {
      // Already signed out: a 401 here is expected and redirecting would
      // loop against the sign-in page's own requests.
      if (!isSignedIn) return
      clerk.redirectToSignIn()
    })
    return () => setSessionExpiredHandler(null)
  }, [clerk, isSignedIn])

  return null
}
```

It gets mounted inside `ClerkProvider` in Task 8, Step 1.

- [ ] **Step 7: Typecheck and format**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no errors. If Prettier reports formatting differences, run `npm run format`.

- [ ] **Step 8: Commit**

```bash
git add frontend/app/lib/api.ts frontend/app/lib/use-api.ts frontend/app/lib/query-client.ts frontend/app/components/auth-error-bridge.tsx frontend/app/routes/integration-test.tsx
git commit -m "feat: send Clerk session token with API requests"
```

---

### Task 8: Frontend routes, sign-in pages, and the protected layout

**Files:**
- Modify: `frontend/app/root.tsx:104-119` (the `App` component) and `:25-31` (the Clerk import)
- Modify: `frontend/app/routes.ts`
- Create: `frontend/app/routes/sign-in.tsx`
- Create: `frontend/app/routes/sign-up.tsx`
- Create: `frontend/app/routes/protected.tsx`

**Interfaces:**
- Consumes: `ClerkProvider`, `Show`, `RedirectToSignIn`, `SignIn`, `SignUp`, `UserButton` from `@clerk/react-router`
- Produces: `/sign-in`, `/sign-up` routes; a protected layout wrapping `/integration-test`

- [ ] **Step 1: Strip the auth chrome out of `root.tsx`**

Replace the Clerk import block (lines 25-31) with:

```ts
import { ClerkProvider } from "@clerk/react-router"

import { AuthErrorBridge } from "~/components/auth-error-bridge"
```

Replace the `App` component (lines 104-119) with:

```tsx
const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

if (!PUBLISHABLE_KEY) {
  // Fail at boot with a readable message. ClerkProvider's own error surfaces
  // deep in a render and reads like a library bug rather than missing config.
  throw new Error(
    "VITE_CLERK_PUBLISHABLE_KEY is not set. Copy .env.example to .env and " +
      "fill it in from the Clerk dashboard."
  )
}

export default function App() {
  return (
    <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/">
      <AuthErrorBridge />
      <Outlet />
    </ClerkProvider>
  )
}
```

The header moves to the protected layout: the public landing page should not render signed-in chrome.

- [ ] **Step 2: Declare the routes**

Replace `frontend/app/routes.ts` with:

```ts
import {
  type RouteConfig,
  index,
  layout,
  route,
} from "@react-router/dev/routes"

export default [
  index("routes/home.tsx"),
  // Splat paths: Clerk's components use sub-paths for multi-step flows
  // (email verification, MFA, SSO callback).
  route("sign-in/*", "routes/sign-in.tsx"),
  route("sign-up/*", "routes/sign-up.tsx"),
  layout("routes/protected.tsx", [
    route("integration-test", "routes/integration-test.tsx"),
  ]),
] satisfies RouteConfig
```

- [ ] **Step 3: Create the sign-in page**

Create `frontend/app/routes/sign-in.tsx`:

```tsx
import { SignIn } from "@clerk/react-router"

import { GridBackground } from "~/components/aceternity/grid-background"
import type { Route } from "./+types/sign-in"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Sign in — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

export default function SignInPage() {
  return (
    <GridBackground>
      <div className="flex flex-1 items-center justify-center px-6 py-16">
        <SignIn signUpUrl="/sign-up" />
      </div>
    </GridBackground>
  )
}
```

- [ ] **Step 4: Create the sign-up page**

Create `frontend/app/routes/sign-up.tsx`:

```tsx
import { SignUp } from "@clerk/react-router"

import { GridBackground } from "~/components/aceternity/grid-background"
import type { Route } from "./+types/sign-up"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Sign up — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

export default function SignUpPage() {
  return (
    <GridBackground>
      <div className="flex flex-1 items-center justify-center px-6 py-16">
        <SignUp signInUrl="/sign-in" />
      </div>
    </GridBackground>
  )
}
```

- [ ] **Step 5: Create the protected layout**

Create `frontend/app/routes/protected.tsx`:

```tsx
import { RedirectToSignIn, Show, UserButton } from "@clerk/react-router"
import { Outlet } from "react-router"

/**
 * Gate for every signed-in page, plus the app shell.
 *
 * <Show> renders null while Clerk is still loading and only falls back once
 * loading has settled, so a signed-in user refreshing the page never flashes
 * the sign-in redirect.
 */
export default function Protected() {
  return (
    <Show when="signed-in" fallback={<RedirectToSignIn />}>
      <div className="flex min-h-svh flex-col">
        {/* pr-16 clears the theme toggle, which root.tsx fixes to top-right. */}
        <header className="flex items-center justify-end px-6 py-4 pr-16">
          <UserButton />
        </header>
        <Outlet />
      </div>
    </Show>
  )
}
```

- [ ] **Step 6: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors. This regenerates `./+types/sign-in`, `./+types/sign-up` — without it those imports do not resolve.

- [ ] **Step 7: Verify the flow in the browser**

```bash
docker compose -f docker-compose.dev.yml up --build
```

Check each of these:
- `http://localhost:5173/` renders the landing page with no auth chrome
- `http://localhost:5173/integration-test` redirects to `/sign-in` when signed out
- Signing up creates a user, then lands back on the app
- `/integration-test` sends a message successfully while signed in
- The Network tab shows `Authorization: Bearer …` on `/integration-messages`
- A hard refresh on `/integration-test` while signed in does NOT flash the sign-in page
- Signing out returns to `/`
- Session expiry redirects rather than showing an error card: with
  `/integration-test` open, sign out in a second tab, then click **List
  messages** in the first. Expected: redirect to `/sign-in`, no error card.

- [ ] **Step 8: Confirm the user row was provisioned**

```bash
docker compose -f docker-compose.dev.yml exec postgres \
  psql -U remitx -d remitx -c "select id, clerk_user_id, email, created_at from users;"
```

Expected: one row matching the account you signed up with. If the database or user name differs, read them from `docker-compose.dev.yml`.

- [ ] **Step 9: Lint and commit**

```bash
cd frontend && npm run lint
git add frontend/app/root.tsx frontend/app/routes.ts frontend/app/routes/sign-in.tsx frontend/app/routes/sign-up.tsx frontend/app/routes/protected.tsx
git commit -m "feat: add sign-in, sign-up, and protected route layout"
```

---

### Task 9: Remove dead CLERK_JWKS_URL config and update docs

The SDK authenticates with the secret key and manages JWKS internally, so `CLERK_JWKS_URL` is now provisioned but unread.

**Files:**
- Modify: `.env.example`
- Modify: `infra/modules/key-vault/main.tf`, `variables.tf`, `outputs.tf`
- Modify: `infra/envs/qa/main.tf`, `variables.tf`
- Modify: `infra/envs/prod/main.tf`, `variables.tf`
- Modify: `docs/DEPLOYMENT.md`

**Interfaces:**
- Consumes: nothing
- Produces: no `clerk_jwks_url` variable anywhere in the tree

- [ ] **Step 1: Find every reference**

```bash
grep -rn "clerk_jwks_url\|CLERK_JWKS_URL\|clerk-jwks-url" --include="*.tf" --include="*.md" --include="*.yml" --include=".env.example" . | grep -v node_modules
```

Record the list — every hit must be gone by Step 5.

- [ ] **Step 2: Remove it from `.env.example`**

Delete the `CLERK_JWKS_URL=` line. The Clerk block becomes:

```bash
# --- Clerk (auth) ---
# Three Clerk applications: Development (local), QA (qa branch), Production (main).
# See docs/DEPLOYMENT.md for which keys go to which environment.
CLERK_SECRET_KEY=
VITE_CLERK_PUBLISHABLE_KEY=
```

- [ ] **Step 3: Remove it from Terraform**

Delete in each file:
- `infra/modules/key-vault/main.tf` — the whole `azurerm_key_vault_secret "clerk_jwks_url"` resource
- `infra/modules/key-vault/variables.tf` — the `clerk_jwks_url` variable block
- `infra/modules/key-vault/outputs.tf` — any `clerk-jwks-url` entry in the `secret_ids` map
- `infra/envs/qa/main.tf` and `infra/envs/prod/main.tf` — the `clerk_jwks_url = var.clerk_jwks_url` argument
- `infra/envs/qa/variables.tf` and `infra/envs/prod/variables.tf` — the `clerk_jwks_url` variable block

- [ ] **Step 4: Validate the Terraform still parses**

```bash
cd infra/envs/qa && terraform init -backend=false && terraform validate
cd ../prod && terraform init -backend=false && terraform validate
```

Expected: `Success! The configuration is valid.` for both.

- [ ] **Step 5: Confirm no references remain**

Re-run the Step 1 grep.
Expected: no output.

- [ ] **Step 6: Update DEPLOYMENT.md**

Delete the `TF_VAR_clerk_jwks_url` row from the secrets table. Then extend the Clerk section:

```markdown
## Clerk

| Environment | Clerk application | Keys in |
|-------------|-------------------|---------|
| Local | Development | root `.env` |
| QA | QA | Key Vault + GitHub secrets for frontend |
| Prod | Production | Key Vault + GitHub secrets for frontend |

Configure allowed origins in the Clerk dashboard (not Terraform). Each
application needs the origins that will call it:

| Environment | Origins |
|-------------|---------|
| Development | `http://localhost:5173` |
| QA | `https://qa.remitx.tech` |
| Production | `https://remitx.tech` |

The API sends the same list to Clerk as `authorized_parties`, sourced from
`CORS_ORIGINS`. If an origin is missing from either side, verification fails
with a 401 that looks like a bad token rather than a misconfiguration.

**Removing a Key Vault secret:** deleting the `clerk_jwks_url` resource leaves
the secret soft-deleted in the vault rather than purged. That is expected and
harmless; it stays recoverable for the vault's retention period.
```

- [ ] **Step 7: Delete the now-unused GitHub secret**

In the repository's **qa** and **prod** environment settings, delete `TF_VAR_clerk_jwks_url`. Terraform no longer declares it, so leaving it would be a dangling credential.

- [ ] **Step 8: Commit**

```bash
git add .env.example infra/ docs/DEPLOYMENT.md
git commit -m "chore: drop unused CLERK_JWKS_URL config"
```

---

## Final verification

- [ ] `cd api && pytest` — all tests pass
- [ ] `cd api && ruff check . && ruff format --check .` — clean
- [ ] `cd api && alembic upgrade head && alembic check` — no drift
- [ ] `cd frontend && npm run lint && npm run typecheck` — clean
- [ ] `python3 -m pre_commit run --all-files` — all hooks pass
- [ ] Full stack up, sign-up → `/integration-test` → message reaches PROCESSED
- [ ] `grep -rn "CLERK_JWKS_URL" . | grep -v node_modules` — no output
