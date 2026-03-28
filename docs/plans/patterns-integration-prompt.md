# Fledgling Integration with Patterns for Toolcraft

*Reference prompt for integrating Fledgling with the design patterns from the Ma experimental program.*

## Before doing anything

Read these files in the judgementalmonad.com repo:

1. `blog/patterns/01-the-quartermaster.md` — **Primary.** Fledgling modules are the kits the Quartermaster selects from. Kit manifests, model-aware configuration, skill mapping.
2. `blog/patterns/08-the-coach.md` — Fledgling provides the code intelligence the Coach uses to generate suggestions. ChatToolUsage, CodeStructure, FindDefinitions feed the Coach's observations.
3. `blog/patterns/03-the-calibration-probe.md` — Fledgling's conversation analytics (ChatSessions, ChatToolUsage) characterize model behavior for the probe.
4. `blog/patterns/02-the-strategy-instruction.md` — Strategy instructions travel with the kit. The Quartermaster selects both tools AND strategy per model.
5. `blog/patterns/06-tool-call-combinators.md` — Combinators compose Fledgling queries. Fledgling stays level 0; combinators operate at the Harness level.

Also read:
6. `~/Projects/source-sextant/main/docs/plans/skill-modules-from-experiments.md` — The existing plan for Fledgling modules as Skills, with experimental data.
7. `~/Projects/source-sextant/main/docs/quartermaster-pattern.md` — The existing quartermaster pattern doc in Fledgling.
8. `experiments/pilot-findings.md` — Sections 8-11 for the evidence.

## Fledgling's role in the pattern ecosystem

Fledgling is intentionally level 0 — read-only SELECT queries over DuckDB. No mutation, no side effects, no computation channels. This is a design strength: Fledgling tools are in the specified band by construction. They can be granted to any agent in any mode without raising the system's grade.

But several patterns need capabilities beyond level 0:
- The Coach needs to **inject suggestions** into the conversation (write to context)
- The Mode Controller needs to **reconfigure tools** (mutate the tool registry)
- The Quartermaster needs to **select and activate** kits (configure the MCP server)

These mutation operations should NOT be added to Fledgling. They belong in an adjacent coordination tool that consumes Fledgling's intelligence and acts on it. Fledgling provides the **observations**. The coordinator provides the **actions**.

```
Fledgling (level 0, read-only)          Coordinator (level 1-2, specified mutation)
├─ CodeStructure                        ├─ switch_mode(mode_name)
├─ FindDefinitions                      ├─ inject_suggestion(text)
├─ FindCallers                          ├─ configure_tools(tool_list)
├─ ChatToolUsage                        ├─ set_strategy(instruction)
├─ ChatSearch                           └─ update_sandbox(spec)
├─ GitDiffSummary
└─ query(sql)                           Consumes Fledgling's output.
                                        Specified mutations only.
   Reads the world.                     Changes the configuration.
   Level 0.                             Level 1-2.
```

The coordinator could be jetsam (it already manages workflow state), a new tool, or part of the Harness itself (Claude Code hooks). The key: Fledgling stays pure.

## What Fledgling should provide

### 1. Skill kits (for the Quartermaster)

Each Fledgling module becomes a named kit with a tool manifest:

```yaml
# In Fledgling's config or a kits/ directory
kits:
  navigate:
    tools: [ReadLines, CodeStructure, FindDefinitions, FindCallers]
    description: "Explore unfamiliar code. Map before reading."

  diagnose:
    tools: [ReadLines, CodeStructure, FindDefinitions, FindCallers, ReadSource]
    description: "Debug failing tests. Trace from symptom to cause."

  review:
    tools: [ReadLines, CodeStructure, FindDefinitions, GitDiffSummary]
    description: "Assess code changes. Structure before opinion."

  analyze:
    tools: [CodeStructure, query]
    description: "Codebase metrics and structural analysis."
```

The Quartermaster reads the kit manifests and selects one per task. Fledgling exposes only the selected kit's tools.

This builds on Fledgling's existing **profile system** (core/analyst) — profiles are coarse kits. The pattern refines them with task-type awareness and model-aware tool counts.

### 2. Behavioral data (for the Calibration Probe)

Fledgling's conversation analytics tell the Probe how the model behaves:

```sql
-- What tools did the model use in the first 5 calls?
SELECT tool_name, arguments, sequence_number
FROM ChatToolUsage
WHERE session_id = current_session()
ORDER BY sequence_number
LIMIT 5;

-- Does the model use Fledgling tools or bash for code navigation?
SELECT
    tool_name,
    count(*) as calls,
    CASE WHEN tool_name LIKE 'mcp__fledgling__%' THEN 'fledgling'
         WHEN tool_name = 'Bash' THEN 'bash'
         ELSE 'other' END as tool_source
FROM ChatToolUsage
WHERE session_id = current_session()
GROUP BY tool_name, tool_source;
```

This is observing what our experiment observed: does the agent use Fledgling or bash? The answer determines the Quartermaster's next configuration.

### 3. Coaching intelligence (for the Coach)

The Coach hook queries Fledgling to generate suggestions:

```sql
-- Agent searched for a function name 3 times via file_search.
-- Suggest FindDefinitions instead.
WITH recent_searches AS (
    SELECT arguments->>'pattern' as pattern, count(*) as times
    FROM ChatToolUsage
    WHERE tool_name = 'file_search'
    AND sequence_number > (SELECT max(sequence_number) - 10 FROM ChatToolUsage)
    GROUP BY pattern
    HAVING count(*) >= 3
)
SELECT pattern, times,
    'Try FindDefinitions(name_pattern="' || pattern || '") — '
    || 'searches all files at once with AST awareness.' as suggestion
FROM recent_searches;
```

Fledgling provides the intelligence. The Coach hook (running as a Claude Code PostToolUse hook) runs the query and injects the suggestion. Fledgling doesn't inject — it queries.

### 4. Kit effectiveness tracking (for the ratchet)

After each session, Fledgling can analyze whether the kit was effective:

```sql
-- Which tools in the kit were actually used?
SELECT
    tool_name,
    count(*) as calls,
    CASE WHEN tool_name IN (kit_tools) THEN 'in_kit' ELSE 'outside_kit' END as status
FROM ChatToolUsage
WHERE session_id = current_session()
GROUP BY tool_name, status;

-- Did the agent request tools not in the kit?
-- (continuation passing from quartermaster-pattern.md)
SELECT tool_name, count(*) as attempts
FROM ChatToolUsage
WHERE session_id = current_session()
AND success = false
AND error_message LIKE '%not available%'
GROUP BY tool_name;
```

Tool requests that fail because the tool isn't in the kit are ratchet data: "this task type needs find_callers but the kit didn't include it." The Quartermaster's next kit revision adds it.

## What Fledgling should NOT do

- **Mutate tool configuration.** Fledgling reads. The coordinator writes. Keeping Fledgling at level 0 means it can always be safely granted.
- **Inject suggestions into the conversation.** The Coach hook does this. Fledgling provides the query results.
- **Switch modes.** The Mode Controller does this. Fledgling's event data feeds the Controller's decision.
- **Run tests or execute code.** That's blq or bash. Fledgling analyzes code structure, not code behavior.

## The adjacent coordinator

The patterns need a mutation layer that Fledgling feeds:

| Pattern | What it needs | Who does it |
|---|---|---|
| Quartermaster | Configure tool registry per task | Harness / MCP server |
| Mode Controller | Switch modes on failure patterns | Claude Code hooks or jetsam |
| Coach | Inject suggestions into conversation | Claude Code PostToolUse hook |
| Strategy Instruction | Add principle to prompt | Harness / system prompt |
| Sandbox Spec | Enforce execution bounds | blq (wraps commands in bwrap) |

Jetsam is the natural candidate for workflow-level mutations (mode switching, save points, transitions). blq is the natural candidate for execution-level mutations (sandbox enforcement, test running). Claude Code hooks are the mechanism for conversation-level mutations (suggestion injection, strategy activation).

Fledgling sits below all of these: the read-only intelligence layer that informs every decision without participating in it.

## Priority for Fledgling

1. **Kit manifests** — define 4-6 kits as structured configuration. This is the Skill integration from `skill-modules-from-experiments.md`, refined with experimental data.
2. **Coaching queries** — pre-built queries the Coach hook can call. Package as Fledgling macros or views.
3. **Kit effectiveness views** — session-level analytics for which tools were used, requested, and missing.
4. **Probe queries** — behavioral classification from the first N tool calls.

## Key experimental findings relevant to Fledgling

1. **Semantic tools (FindDefinitions, CodeStructure) provide capabilities bash can't express.** These are the tools that earn their place — not because they're safer than bash, but because they return information bash can't produce.

2. **Fewer tools is better for weaker models.** Haiku with 9 tools: 40% pass. With 5 tools: could reach 100% with the right 5. Fledgling's kit system should expose the minimum effective tool set, not the full catalog.

3. **The agent naturally uses Fledgling's tools when they're the right tool.** Sonnet/E used structured file tools for reading/editing and bash only for pytest. It didn't need to be told — it selected. The kit's job is to present the right options, not dictate the workflow.

4. **Strategy instructions travel with the kit.** The principle ("understand before editing") is part of the configuration, not separate from it. The kit manifest should include the strategy instruction alongside the tool list.
