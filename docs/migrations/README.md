# Database Migrations

## Directory Structure

Migrations are raw sql files that are stored under `src/database`

```
src/database/
├── pacs/
│   ├── 001_initial_schema.sql
│   ├── 002_add_new_table.sql
│   └── 003_modify_existing_table.sql
└── worklist/
    ├── 001_initial_schema.sql
    ├── 002_add_new_column.sql
    └── 003_remove_obsolete_table.sql
```


### Migration Files

The files are prefixed with a version number to ensure that they are applied in the correct order. The version number is tracked in the database using the `user_version` pragma, which allows us to determine which migrations need to be applied when the application starts up.


### Schema Initialisation

Schema initialisation is handled by the `001_initial_schema.sql` file, which creates the initial tables and sets the `user_version` to 1. Subsequent migrations will increment the `user_version` as they are applied.


### Writing Migrations

Migrations do not need to be idempotent, as they are only applied once when the application starts up. However, care should be taken to ensure that migrations do not break existing data or functionality. It is recommended to test migrations in a development environment before applying them to production databases.

Each migration will be applied in a separate transaction, so if a migration fails, the database will be rolled back to its previous state. This ensures that the database remains consistent even in the event of a migration failure.
