# Project rules

These rules apply to every change in this repository. See [README.md](README.md) for the stack, structure and decisions made so far.

## Commits

- Only commit when SPECIFICALLY ASKED. Finishing a task is not a request to commit.
- Before every commit, run the full test suite (`.venv/bin/pytest`). If ANY test fails, stop: do not commit, and report the failing tests.
- Every commit message MUST be useful enough to be reused later in a versioning document (changelog / release notes):
  - Subject line: imperative, up to ~70 characters, saying what changed (e.g. `Add payments table and migration`).
  - Body: what changed and why, the user-visible or schema impact, and any new migration, config or dependency.
- ALWAYS show the full commit message to the user and wait for their approval before committing. Apply any changes they ask for and confirm again.

## Database access

- Absolutely no SQL code outside repositories ([app/db/repositories/](app/db/repositories/)). Endpoints, services, CLI commands and other code never touch the session or build queries; they call repository methods.
- ALWAYS use the repositories for database access. If a query is missing, add a method to the right repository (generic operations go in `BaseRepository`).
- Inside repositories, ALWAYS use the SQLAlchemy query builder / ORM. Never write raw SQL strings.
- Repositories filter out soft-deleted rows by default (see `_query()` in [app/db/repositories/base.py](app/db/repositories/base.py)); keep that behaviour in new queries.
- ALWAYS use a repository inside a `with` statement. When the `with` block ends, the repository commits (or rolls back on error) and closes the session, so every database connection is released properly.
- When more than one repository is needed, the `with` statements MUST be nested, sharing the same session. Only the outermost `with` commits/rolls back and closes the session; an error at any level rolls back everything:
  ```python
  with UserRepository(session) as users:
      with CartRepository(session) as carts:
          ...
  ```
  Never use sequential (non-nested) `with` blocks for work that must be one transaction.
- Exceptions:
  - Alembic migrations in [alembic/versions/](alembic/versions/) define the schema and may use `op.*` operations.
  - The `flask seed` command in [app/cli.py](app/cli.py) may use the session directly, because it only populates the database with sample data.

## Versioned tables

- To keep the history of a table, inherit from `VersionedBaseModel` instead of `BaseModel`, make its repository inherit from `VersionedBaseRepository`, and generate an Alembic migration (it creates `<table>_history`). Backfill a version 1 history row for existing records in that migration.
- Never change a versioned table with bulk statements (`session.execute(update(...))` / `delete(...)`): they skip the history. Always change ORM instances through the repository.
- Handle `StaleDataError` where a concurrent update of a versioned record is possible; never work around it by overwriting.

## Ambiguity

- Don't assume. When an instruction is ambiguous or leaves a decision open, ask before deciding.
- Record the decisions taken in the "Decisions so far" section of the README.

## Code principles

- Follow DRY: reuse existing code (`BaseModel`, `BaseRepository`, schemas, constants in [app/db/constants/](app/db/constants/)) before writing new code.
- Follow KISS: choose the simplest solution that meets the requirement; no speculative features or abstractions.
