# Conversations Are Closures: A Programming Language Framework for Multi-Agent Architecture

*Or: how sixty years of PL theory already solved the agent orchestration problem*

---

You're building a multi-agent system. You need to decide: what context does each agent see? How do agents hand off work? How does the system learn from past interactions? What happens when an agent needs something it wasn't given?

These feel like new problems. They're not. Programming language theory solved the structural versions of all of them decades ago. We just haven't noticed they're the same problems.

## The observation

Here's what a multi-agent conversation looks like in practice:

A primary agent receives a task. It delegates to a subagent, passing along some context — maybe a task description, some relevant files, a set of tools. The subagent works, produces results, and hands them back. Maybe the subagent delegates further. At each handoff, someone decides what context flows forward and what gets left behind.

Now here's what a closure looks like:

A function captures some variables from its enclosing scope. When it executes, it can see those captured variables but not the rest of the environment. It produces a result that becomes available to whoever called it. Closures can nest — an inner closure captures from an outer closure's scope.

These aren't analogous. They're structurally identical.

## The mapping

| Programming Language Concept | Multi-Agent Architecture |
|---|---|
| Shared heap | The full conversation log (append-only) |
| Lexical scope | Visibility rules for each agent |
| Closure | An agent + the context it can see |
| Capture list | What context an agent receives at spawn |
| Continuation passing | Handing the conversation to the next agent |
| Activation frame | An agent's current working window |

Multiple agents operate on a single, growing conversation log. Each agent is a closure: it captures a scoped subset of the log, operates within that scope, adds new state, and passes the whole log forward. The next agent closes over a different subset of the now-larger log.

The conversation is the shared heap. Each agent's visibility is its lexical scope. The handoff between agents is continuation passing.

## Why this framing matters

This isn't just a cute analogy. It's a design framework that gives concrete, testable answers to questions the agent community is currently solving ad hoc.

### "What should a subagent see?"

This is the capture list question. When you spawn a closure, you decide which variables it captures from the enclosing scope. When you spawn a subagent, you decide which conversation history, tools, and context it receives.

Every multi-agent framework has a version of this. OpenAI's Agents SDK has `include_contents` parameters on handoffs. Google's context-aware framework treats context as a "compiled view over a richer stateful system." LangChain lets you scope what a callee sees.

They're all implementing capture lists. The closure framing makes this explicit: you're not "configuring context" — you're defining a scope.

### "How do agents share state?"

They don't share mutable state. They close over a shared, append-only log. Each agent reads from its scope and appends to the log. No coordination protocols, no locking, no race conditions. This is the same insight that makes persistent data structures and event sourcing work: if the log only grows, concurrent readers can't interfere with each other.

The ESAA paper (Santos Filho, 2026) arrives at exactly this architecture — agents emit structured intentions, a deterministic orchestrator persists events in an append-only log, and downstream agents read materialized views. They frame it as event sourcing. We're framing it as closure semantics. Same structure, different vocabulary.

### "What happens when an agent gets stuck?"

In the traditional call-stack model, a stuck subagent fails, the error propagates up, the parent re-evaluates, and maybe retries with different parameters. Context is lost. Work is repeated.

In the closure/continuation model, a stuck agent doesn't fail. It passes a continuation: "Here's my state, here's what I need, resume me when you can provide it." The handler (what we've been calling the "quartermaster" — more on that below) fulfills the request and the agent continues from where it left off. No unwinding, no lost context, no re-derivation.

This is literally continuation passing style (CPS) from PL theory, applied to agent orchestration. The conversation log preserves the agent's full state. The continuation is a request for resources plus a pointer to where to resume.

### "How does the system improve over time?"

Query the log. The conversation log isn't just state — it's training data. Past closures' contributions (which tools were used, which were requested but missing, how many steps each task took) inform how future agents are scoped.

This closes a learning loop that most frameworks leave open: the system doesn't just execute tasks, it accumulates evidence about what works. A "quartermaster" agent can query past sessions to assemble better tool kits for future workers, the same way a DBA queries past shipping records to pick the right box size instead of calculating from first principles.

## The quartermaster pattern

This framing suggests a natural architecture for multi-agent systems with three roles:

**The primary agent** knows the goal. It operates at the level of intent — "refactor the auth module," "review this pull request."

**The quartermaster** knows the tools and their history. It doesn't do the work — it assembles the right kit for the job. It reads the task description, queries past sessions for what tools were effective on similar tasks, and constructs a capture list: here are your tools, here's your initial context, here's your scope.

**The worker agent** knows the craft. It receives a scoped view of the conversation (its closure), does the work using the tools it was given, and adds its findings to the log.

The quartermaster's scope includes tool performance history and task patterns but not the worker's line-by-line analysis. The worker's scope includes the immediate code context and its assigned tools but not the quartermaster's selection rationale. The primary agent sees the task and the final result but not the intermediate steps.

They're all operating on the same growing log with different visibility. Three closures over one heap.

And critically: when the worker needs a tool it wasn't given, it doesn't fail. It passes a continuation to the quartermaster — "I need the dependency graph, here's why, here's my current state." The quartermaster fulfills the request, and the worker resumes. The quartermaster notes the gap for next time. The system learns.

## The conversation IS the program

Here's where it gets interesting.

Lisp's fundamental insight was homoiconicity: code and data have the same structure. A Lisp program can inspect and transform itself because there's no structural distinction between "the program" and "the data the program operates on."

A conversation log has this property. The log is both:
- **Data**: what happened, what was said, what tools were used
- **Program**: the instructions for how to scope future agents, what tools to provide, what context matters

When the quartermaster reads past sessions to configure a new worker, the log is functioning as code. When the worker adds findings that future quartermasters will read, data is becoming code. The conversation is simultaneously the execution trace AND the source of future behavior.

This is why macros and idioms matter in this context. A pre-composed operation like "find the most complex functions in recently changed files" isn't just a query — it's an encoded pattern of expert thinking, compressed into a reusable form. That's what macros do in Lisp. They compress a way of thinking into something that can be applied without understanding its internals.

The conversation log accumulates these patterns. Each successful task completion adds an example of "here's how this kind of problem was solved." Future agents close over these examples. The system's vocabulary grows.

## What's already here, and what's missing

The individual pieces of this framework are appearing independently across the agent ecosystem:

- **Append-only event logs**: ESAA, Akka's event sourcing for agents
- **Scoped context visibility**: Google's compiled context views, OpenAI's handoff parameters
- **Continuation-style handoffs**: OpenAI Agents SDK, LangChain multi-agent
- **Closures in agent languages**: Pel (a Lisp-inspired language for agent orchestration)
- **Session analytics for optimization**: various framework-specific implementations

What's missing is the recognition that these are all the same structure — that closure semantics from programming language theory provides a unified framework for reasoning about all of them simultaneously.

The PL theory community has spent sixty years refining the semantics of closures, continuations, and scoping. The agent architecture community is rediscovering these ideas empirically. Connecting the two would mean the agent community doesn't have to re-derive every property from scratch. Questions about scope safety, capture semantics, and continuation behavior already have formal answers.

## A practical implication

If conversations are closures, then the meta-structure of agent communication wants to be something Lisp-like. Not the syntax — nobody's writing S-expressions in chat. But the structural properties:

- **Uniform representation**: messages, tool calls, context rules, and scoping annotations all in the same substrate
- **First-class closures**: agents as composable, scopable units
- **Macros**: encoded patterns that transform conversation structure before agents process it
- **Homoiconicity**: the log is both the record and the program

The content stays natural language. The plumbing — who sees what, how context flows, where continuations point — becomes formal. Not because formalism is inherently better, but because the problems it solves (scope safety, capture correctness, continuation semantics) are exactly the problems agent architects are struggling with today.

## The punchline

Every multi-agent framework is implementing closures. They just don't know it yet.

The scoping decisions, the context management, the handoff protocols, the learning loops — they're all ad hoc implementations of concepts that have rigorous foundations in programming language theory. Church gave us lambda calculus in the 1930s. Landin gave us closures in the 1960s. The agent community is building the same structures ninety years later, without the shared vocabulary that would let them reason about them formally.

The invitation is simple: look at your agent architecture through the lens of closure semantics. The conversation is the heap. The agents are closures. The handoffs are continuations. The scoping rules are capture lists.

You already know how this works. You just didn't know you knew.

---

*This idea emerged from a conversation about SQL macros, tool composition, and what it means for an AI agent to "reach for the right tool." Sometimes you find programming language theory where you least expect it — in the space between a code intelligence server and a glass of whiskey.*
