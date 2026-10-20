# ADR-008: Database Migrations

Date: 2026-10-20

Status: Accepted

## Context

We are currently using two SQLite databases to store PACS and worklist data. As our application evolves, we need to make changes to the database schema, such as adding new tables, modifying existing ones, or removing obsolete structures. To manage these changes effectively and ensure that our database remains consistent with the application code. We need a database migration strategy which allows us to release schema changes alongside code changes.

Currently we archive the database on a weekly basis, this means that a breaking schema change would need to be released a week before or after the code change.
We have considered using Alembic for database migrations, but it would require a dual setup for the two SQLite databases, which would add complexity and bloat to the released application.

## Decision

We've decided to implement a custom database migration system that will allow us to manage schema changes for both SQLite databases without the overhead of a dual setup.

Migrations are handled in applicaton code when the relevant database storage class is initialized. The migration system will check the current schema version of the database via the user_version pragma and apply any necessary migrations to bring it up to date with the latest schema defined in the application code.

This offers us a relatively simple and lightweight solution for managing database schema changes, while still allowing us to release code and schema changes together.


### Positive Consequences

Migrations are organised into a directory structure, with each migration represented by a sql file which should be prefixed with a version number.
We track the version number in the database using the user_version pragma, which allows us to determine which migrations need to be applied when the application starts up.

### Negative Consequences

Migrations need to be written in sql files using SQLite compatible dialect.
File names need to adhere to a strict naming convention to ensure that they are applied in the correct order.
