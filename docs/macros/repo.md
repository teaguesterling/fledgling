# Repository Intelligence

**Extension**: [`duck_tails`](https://github.com/teaguesterling/duck_tails)

Structured access to git repository state. Replaces git CLI commands with composable, queryable results.

## `recent_changes`

What changed recently in the repository.

```sql
recent_changes(n := 10, repo := '.')
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n` | `integer` | `10` | Number of commits to return |
| `repo` | `string` | `'.'` | Repository path |

**Returns**: `hash` (8-char), `author`, `date`, `message`

```sql
-- Last 10 commits
SELECT * FROM recent_changes();

-- Last 5 commits
SELECT * FROM recent_changes(5);
```

## `branch_list`

List all branches with current branch marked.

```sql
branch_list(repo := '.')
```

**Returns**: `branch_name`, `hash`, `is_current`, `is_remote`

Ordered with current branch first, then local before remote.

```sql
SELECT * FROM branch_list();
```

## `tag_list`

List all tags with metadata.

```sql
tag_list(repo := '.')
```

**Returns**: `tag_name`, `hash`, `tagger_name`, `tagger_date`, `message`, `is_annotated`

```sql
SELECT * FROM tag_list();
```

## `repo_files`

List all tracked files at a given revision.

```sql
repo_files(rev := 'HEAD', repo := '.')
```

**Returns**: `file_path`, `file_ext`, `size_bytes`, `kind`, `is_text`

```sql
-- All files at HEAD
SELECT * FROM repo_files();

-- Files at a specific tag
SELECT * FROM repo_files('v1.0');
```

## `file_at_version`

Read a file as it existed at a specific revision.

```sql
file_at_version(file, rev, repo := '.')
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file` | `string` | required | File path (relative to repo root) |
| `rev` | `string` | required | Commit hash, branch, or tag |
| `repo` | `string` | `'.'` | Repository path |

**Returns**: `file_path`, `ref`, `size_bytes`, `content`

```sql
-- Read README at previous commit
SELECT * FROM file_at_version('README.md', 'HEAD~1');

-- Read file at a tag
SELECT * FROM file_at_version('src/main.py', 'v1.0');
```
