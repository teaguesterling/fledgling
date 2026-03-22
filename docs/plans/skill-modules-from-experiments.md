# Fledgling Modules as Skills

*Each Fledgling capability area can be a Skill — a named configuration that loads the right tools and sets the right strategy for a task type.*

## Why Skills, not just tools

Fledgling currently exposes ~60 tools. An agent connecting to the full MCP server sees all of them. Experiments showed this is problematic:

- **Haiku with 9 tools: 40% pass rate. With 5 tools + one sentence of strategy: 100%.** More tools = more decision overhead for weaker models.
- **Over-specification hurts.** Detailed strategy instructions (+56% cost) were worse than a one-sentence principle (-16% cost). Skills should be minimal.
- **The agent selects well when given the right set.** Sonnet with file tools + bash naturally used structured tools for reading/editing and bash only for running tests. The skill's job is to present the right options, not dictate the workflow.

A Skill is a lens over Fledgling's tool catalog — it selects a subset and adds a task-appropriate strategy instruction.

## Skill structure

```yaml
name: diagnose-bugs
description: "Debug failing tests in a Python codebase"
tools:
  - ReadSource       # read file with line-centered context
  - CodeStructure    # structural overview — classes, functions, nesting
  - FindDefinitions  # where things are defined
  - FindCallers      # who calls a function
strategy: "Understand all failures before fixing any."
model_notes:
  haiku: "Essential — without the strategy, Haiku wastes 60% of its turns"
  sonnet: "Helpful — 16% cost reduction"
  opus: "Optional — Opus plans naturally"
```

## Candidate Skills from Fledgling modules

### `/diagnose` — Bug diagnosis
```yaml
tools: [ReadSource, ReadContext, CodeStructure, FindDefinitions, FindCallers]
strategy: "Understand all failures before fixing any."
```
*Why these tools:* Bug diagnosis requires understanding code structure (what calls what, where things are defined) more than text search. `CodeStructure` gives the map. `FindCallers` traces the chain from symptom to cause. `ReadContext` focuses on the failure location.

### `/navigate` — Code exploration
```yaml
tools: [CodeStructure, FindDefinitions, FindImports, ModuleDependencies, ReadSource]
strategy: "Map the structure before reading implementation details."
```
*Why these tools:* Exploration is about orientation — understanding what exists before diving in. `ModuleDependencies` shows the import graph. `CodeStructure` shows the hierarchy. Individual file reading comes after the map is built.

### `/review` — Code review
```yaml
tools: [ReadSource, FileDiff, ChangedFunctionSummary, RecentChanges, CodeStructure]
strategy: "Review the change set as a whole before evaluating individual changes."
```
*Why these tools:* Review needs the diff (what changed), the context (what was there before), and the structure (how the change fits). `ChangedFunctionSummary` connects diffs to function-level understanding.

### `/refactor` — Safe refactoring
```yaml
tools: [FindDefinitions, FindCallers, FindImports, ModuleDependencies, CodeStructure, ReadSource]
strategy: "Map all references before making any changes."
```
*Why these tools:* Refactoring requires knowing every reference to the thing being changed. `FindCallers` + `FindDefinitions` together cover the reference graph. `ModuleDependencies` catches cross-file impacts.

### `/analyze` — Codebase analysis
```yaml
tools: [CodeStructure, ComplexityHotspots, FunctionMetrics, NestingAnalysis, ReadSource]
strategy: "Measure before judging — let the metrics guide attention."
```
*Why these tools:* Analysis is quantitative — complexity scores, nesting depth, function size. The semantic tools compute these from the AST, not from line-counting heuristics.

### `/history` — Git-aware investigation
```yaml
tools: [RecentChanges, FileChanges, FileDiff, FileAtVersion, BranchList, ReadSource]
strategy: "Understand what changed and when before diagnosing why."
```
*Why these tools:* History investigation traces bugs to the change that introduced them. `FileAtVersion` lets you compare current vs past. `FileChanges` shows what was touched.

## Model-aware tool loading

Each Skill should adjust based on the model running it:

```yaml
# Full configuration with model awareness
name: diagnose-bugs
tools:
  core: [ReadSource, CodeStructure, FindDefinitions]
  extended: [FindCallers, FindImports, ReadContext]  # added for capable models
strategy: "Understand all failures before fixing any."
model_config:
  haiku:
    use: core                  # fewer tools, less decision surface
    strategy_required: true    # haiku needs the principle to succeed
  sonnet:
    use: core + extended       # full tool set, agent self-selects
    strategy_required: false   # helpful but not essential
  opus:
    use: core + extended
    strategy_required: false
```

## What this means for Fledgling

1. **Skills are views over the tool catalog.** Each skill selects a subset of Fledgling's ~60 tools. The rest are hidden — not denied, absent from the tool descriptions.

2. **Strategy instructions are part of the Skill, not separate.** The one-sentence principle travels with the tool selection. They're the two products of the ratchet: tools AND strategy.

3. **Model awareness is a property of the Skill, not the tool.** The same `find_definitions` tool works for any model. The Skill decides whether to include it based on whether the model can use it effectively.

4. **Conversation analytics inform Skill design.** Which tools did the agent actually use? Which did it ignore? Which tasks succeeded? The analytics are the ratchet's observation phase — they tell you which Skills need updating.

## Implementation path

1. **Define 4-6 Skills as YAML manifests** in `docs/skills/` or `skills/`
2. **Skill loader** reads the manifest, configures Fledgling's tool publication to expose only the listed tools
3. **Strategy injection** adds the principle to the MCP server's instructions field
4. **Model detection** checks which model is connecting and adjusts the tool list
5. **Skill invocation** via `/diagnose`, `/review`, `/refactor` in Claude Code's skill system
