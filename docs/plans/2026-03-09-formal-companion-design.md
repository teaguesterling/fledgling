# Formal Companion Design

## Purpose

Rigorous formalization of the framework developed in blog posts 0-9. Companion
document — assumes the reader has the blog for motivation and examples. Follows
mathematical dependency order. Uses labeled environments (Definition,
Proposition, Conjecture, Convention) and is honest about gaps as a TODO list
for future tightening.

## Constraints

- **File:** `docs/blog2/formal-companion.md`
- **Target:** ~800-1000 lines
- **Voice:** Pure formal development. No narrative, no worked examples (those
  live in the blog). Cross-references blog posts for context.
- **Relationship to blog:** Companion, not standalone. Formalizes concepts the
  blog introduces informally.
- **Relationship to formal-framework.md:** Rewrite/successor. Starts from
  Conv_State (no substrate shift). Integrates blog insights (grade lattice,
  algebraic effects, fold model, computation channels, specified band).
- **LaTeX:** Use where it helps clarity; not required.

## Labeled Environments

- **Definition** — precise formal statement
- **Proposition** — proven or provable claim
- **Conjecture** — stated precisely but open
- **Convention** — modeling choice, not a truth claim

Gaps are marked honestly — they serve as a TODO list for future tightening.

## Structure (13 sections, mathematical dependency order)

### 1. Preliminaries
Conversation log, four actor roles, scopes, scope lattice, boundary
decomposition. (~60 lines)

### 2. The Conversation Monad
Conv_State as substrate from the start. Scoped computation. Kleisli category.
Graded bind. (~80 lines)

### 3. The Store Comonad and Duality
Store comonad for Harness. extract/duplicate. Monad-comonad duality
(expansion/compression). Turn cycle. (~70 lines)

### 4. The Grade Lattice
W x D product lattice. Decision surface definition. Composition as join.
Supermodularity (Conjecture). Interface vs internal ma. Co-domain funnels.
(~100 lines)

### 5. The Configuration Lattice and Harness Control
Configuration as (Scope x P(Tools)). Causal chain: Configuration -> Grade ->
Interface ma. (~60 lines)

### 6. The Monad Morphism Preorder
M <= N via monad morphism. Actor ordering. Three conditions for prediction.
Trust/opacity flow. Star topology derivation. Convention for
Inferencer/Principal. (~80 lines)

### 7. Algebraic Effects and Handler Structure
Effect signatures. Raising vs handling. Permission gates as pattern matching.
Context reconstruction. Regulation != prediction. (~80 lines)

### 8. The Fold Model and Conversation Dynamics
Conversations as folds. d_total vs d_reachable. Composite entity type. Coupled
recurrence. Compaction. (~90 lines)

### 9. Computation Channels and Trajectory Dynamics
Data vs computation channels. Computation level as derivative. Phase
transitions. Sandbox as dynamics controller. Halting-problem shape
(Conjecture). (~80 lines)

### 10. The Specified Band
Characterizability vs auditability. OS existence proof. Layered regulation.
Variety reduction. (~70 lines)

### 11. Session Types for the Permission Protocol
Star topology encoded as session types. Permission modes as branching. (~70
lines)

### 12. Open Problems and Extensions
Prioritized: coupled recurrence convergence, computation channel algebra,
supermodularity proof, parallel execution / pi-calculus (non-determinism layer),
distributive law, promises, mechanical verification. (~60 lines)

### 13. References
(~30 lines)

## Key Changes from formal-framework.md

- Start from Conv_State, not M* (no substrate shift)
- Integrate grade lattice (post 2), algebraic effects (post 4), fold model
  (post 6), computation channels (post 7), specified band (post 8)
- Soften Prop 12.14 (grade bounds interface ma) — define f or weaken to bound
- Note Prop 12.15 / computation channel tension explicitly
- Convention 13.3a for Inferencer/Principal monad assignment (modeling choice)
- Pi-calculus noted as open problem (adds non-determinism to trajectories,
  doesn't change framework structure)
- Drop: worked example (post 1), design principles (post 9), quartermaster
  section (post 3), fractal architecture (remark)
