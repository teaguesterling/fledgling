# The Quartermaster Pattern: Fledgling as Subagent Framework

## The Problem

When an agent spawns subagents, each subagent sees every available tool
across every MCP server. There's no selection pressure toward the right
tool for the task. The agent has to discover, orient, and choose before
it can work. That's wasted effort — like a carpenter visiting the full
workshop before every nail.

## Three Roles

1. **Primary agent** — knows the goal ("refactor auth module")
2. **Quartermaster** — knows the tools and their history, assembles a kit
3. **Worker agent** — knows the craft, uses what it's given

Currently all three roles collapse into a single agent. The quartermaster
pattern separates tool selection from tool use.

## How Fledgling Fits

Fledgling is the warehouse the quartermaster draws from:

- **SQL macros** are the inventory — well-typed, named, composable parts
- **Tool publications** are pre-assembled kits for common jobs
- **Profiles** (core/analyst) are coarse job categories
- **Conversation analytics** are the shipping history — what worked before

The quartermaster needs:

### 1. Kit Manifests (declarative configuration)

Instead of writing SQL boilerplate, the quartermaster describes a kit:

```yaml
tools: [ReadLines, CodeStructure, complexity_hotspots]
context:
  - run: changed_function_summary('HEAD~5', 'HEAD', 'src/**/*.py')
    as: recent_changes
scope: src/**/*.py
```

Fledgling reads this and configures itself — which tools are published,
what context is pre-computed, what file scope applies. No SQL authoring.

### 2. Conversation-Informed Selection

The quartermaster queries previous sessions:

```sql
-- What tools were used for similar tasks?
SELECT tool_name, avg(call_count) AS avg_calls
FROM tool_frequency() tf
JOIN sessions() s ON s.session_id = tf.session_id
WHERE s.slug ILIKE '%refactor%'
GROUP BY tool_name
ORDER BY avg_calls DESC
```

This is why the conversation tools belong in Fledgling — they're not
user-facing analytics. They're the quartermaster's memory.

### 3. Continuation Passing (tool requests)

When a worker agent needs a tool it wasn't given, it doesn't fail.
It passes a continuation to the quartermaster:

```
request_tool(
  name="module_dependencies",
  reason="Found circular import, need dependency graph",
  state=current_context
)
```

The quartermaster can:
- Hot-load the tool into the current session
- Note the gap for future kit assembly
- Decide the tool isn't available and explain why

This closes the learning loop: the quartermaster's future kits improve
based on what workers actually needed, not just what they used.

## What Fledgling Needs to Support This

### Already present
- Typed macros queryable via `duckdb_functions()` and `describe`
- Conversation analytics (session history, tool frequency, search)
- Profile system for coarse tool surface control
- SQL composability for ad-hoc quartermaster queries

### Needs building
- Kit manifest format and loader (declarative, not SQL)
- Dynamic tool publication (add/remove tools mid-session)
- A `request_tool` meta-tool for worker→quartermaster signaling
- Kit effectiveness metrics (did the kit lead to task completion?)

### Design principle
Fledgling's job is to be a good warehouse with a good inventory system.
It doesn't need to be smart about selection — that's the quartermaster's
job. It needs to be *legible* to the quartermaster: predictable inputs,
predictable outputs, clear capabilities, well-defined boundaries.
