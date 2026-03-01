# Code Tier Validation

## FindDefinitions

### 2.1 All definitions in a file

```
Use Fledgling FindDefinitions to find all definitions in tests/conftest.py.

Expected: Returns function definitions including load_sql, call_tool,
mcp_request, list_tools, md_row_count, and fixture functions. Each row
should have file_path, name, kind, start_line, end_line, and signature.
```

### 2.2 Filtered by name pattern

```
Use Fledgling FindDefinitions on tests/conftest.py with name_pattern=test_%

Expected: Returns only definitions whose names start with "test_". These
should be test helper functions if any exist.
```

### 2.3 Glob pattern across files

```
Use Fledgling FindDefinitions on tests/test_*.py with name_pattern=%sandbox%

Expected: Returns definitions with "sandbox" in the name from test files.
```

### 2.4 SQL file definitions

```
Use Fledgling FindDefinitions on sql/sandbox.sql.

Expected: Returns the CREATE macro definition. Kind should be
DEFINITION_CLASS or similar for SQL CREATE statements.
```

## FindCalls

### 2.5 Find calls to a specific function

```
Use Fledgling FindCalls on tests/conftest.py with name_pattern=load_sql.

Expected: Returns all call sites where load_sql() is invoked. Should show
20+ calls with file_path, name, start_line, and call_expression columns.
```

### 2.6 Find calls across multiple files

```
Use Fledgling FindCalls on tests/test_*.py with name_pattern=call_tool.

Expected: Returns all test files that call call_tool(), showing the
file path, line number, and call expression for each invocation.
```

## FindImports

### 2.7 Python imports

```
Use Fledgling FindImports on tests/conftest.py.

Expected: Returns import statements including json, os, pytest, duckdb.
Each row should have file_path, name, import_statement, and start_line.
```

### 2.8 Imports across multiple files

```
Use Fledgling FindImports on tests/test_*.py.

Expected: Returns imports from all test files. Should include conftest
imports (call_tool, list_tools, etc.) and standard library imports.
```

## CodeStructure

### 2.9 Python file structure

```
Use Fledgling CodeStructure on tests/conftest.py.

Expected: Returns top-level structural elements: the module, function
definitions, and class definitions with start_line, end_line, and
line_count. Should NOT include implementation details — just the
structural overview.
```

### 2.10 Structure of multiple files

```
Use Fledgling CodeStructure on sql/*.sql.

Expected: Returns structural overview of all SQL macro files. Should
show CREATE statements as top-level definitions.
```
