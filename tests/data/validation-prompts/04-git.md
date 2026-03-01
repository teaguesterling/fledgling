# Git Tier Validation

## GitChanges

### 4.1 Default commit history

```
Use Fledgling GitChanges with no arguments.

Expected: Returns the 10 most recent commits with hash, author, date,
and message columns. Most recent commit should be first.
```

### 4.2 Limited count

```
Use Fledgling GitChanges with count=3.

Expected: Returns exactly 3 commits.
```

### 4.3 Path-scoped history

```
Use Fledgling GitChanges with path=sql/ and count=5.

Expected: Returns up to 5 commits that touched files under sql/.
These should only be commits that modified SQL files.
```

## GitBranches

### 4.4 List all branches

```
Use Fledgling GitBranches.

Expected: Returns all local and remote branches with branch_name, hash,
is_current, and is_remote columns. The current branch
(chore/P2-008-mvp-validation or equivalent) should have is_current=true.
Exactly one branch should be marked current.
```
