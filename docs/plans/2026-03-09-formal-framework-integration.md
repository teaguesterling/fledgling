# Formal Framework Integration Pass

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update formal-framework.md to incorporate insights from the blog series: grade lattice, raising/handling (algebraic effects), conversation dynamics (fold model, computation channels, specified band).

**Architecture:** Surgical edits to 8 existing sections plus one new section (§12.9 Grade Lattice). The new material is referenced, not reproduced — the blog posts contain the full treatments.

**Key files:**
- Modify: `docs/blog/formal-framework.md`
- Reference: `docs/blog/the-grade-lattice.md`, `docs/blog/raising-and-handling.md`, `docs/blog/conversations-are-folds.md`, `docs/blog/computation-channels.md`, `docs/blog/the-specified-band.md`, `docs/blog/self-critique-formalisms.md`

---

### Task 1: §10.5 — Two-level structure → Raising/handling

**Files:**
- Modify: `docs/blog/formal-framework.md:330-344`

**What to change:**

Replace the two-level structure framing with the algebraic effects reframing. The core content (object-level operations are monotone, meta-operations may break monotonicity) is preserved — what changes is the framing from "two levels" to "raising vs handling."

**Step 1: Rewrite Definition 10.6**

Replace "Two-level structure" with "Raising and handling." The two roles:

1. **Raising** — actors raise effects: appending to the log, proposing tool calls, producing output. This is monotone — the log grows, budget decreases, scopes widen within a phase. The graded monad captures it.

2. **Handling** — the Harness handles raised effects: interpreting tool calls, gating permissions, compacting, reconfiguring scope and tools. Not necessarily monotone — compaction breaks prefix ordering, budget reclamation reverses the budget trajectory, scope can be reconfigured between phases.

The **monotonicity boundary** is between raising and handling, not between two "levels."

**Step 2: Update the Remark about phase boundaries**

The remark about meta-level operations as phase boundaries becomes: handling operations are the phase boundaries where monotonicity is suspended and re-established on new ground. Same content, new framing.

**Step 3: Update the quartermaster Remark**

The quartermaster doesn't "straddle two levels." It's an actor with delegated handler privileges — it raises effects in one capacity (reading the log, producing a kit) and handles effects in another (configuring the worker's tool set). This is handler composition/delegation, standard in algebraic effects.

**Step 4: Add connection to algebraic effects literature**

Add a remark noting the mapping to algebraic effects (Plotkin & Pretnar 2009): tool signatures = operation declarations, session type branches = handler cases, handler's own IO = handler effectfulness. Reference [Raising and Handling](raising-and-handling.md) for the full treatment.

**Step 5: Verify consistency**

Check that §10.6 (four actors table) still reads correctly with the new framing. The "Level" column becomes less relevant — replace with "Role" column using "raises" / "handles" / "raises (via Harness)".

---

### Task 2: §10.6 — Fix actor table

**Files:**
- Modify: `docs/blog/formal-framework.md:346-367`

**What to change:**

Update the four-actors table to reflect corrected interface types and the raising/handling framing.

**Step 1: Update the table**

| Actor | Read scope | Write scope | Role | Interface type |
|---|---|---|---|---|
| **Principal** | Terminal rendering (formatted markdown, tool summaries) | `MultimodalMessage` = text + images + files + structured selections | Raises (unhandled context) | `MultimodalMessage` |
| **Harness** | `Conv_State` (compartments, token counts, budget, tool registry) | Meta-operations (compaction, tool loading, context management) | Handles raised effects | `HarnessAction` (enumerable tagged union) |
| **Inferencer** | Token vector (flattened, tokenized conversation filtered through scope) | `Response` = text blocks + tool call proposals | Raises effects (tool calls as proposals) | `Response` |
| **Executor** | Arguments + sandbox (just its inputs) | `Either E Result` (text, structured data, binary, error) | Raises (invoked by handler) | `Either E Result` |

Key corrections: Principal writes `MultimodalMessage` not just "Natural language text." Inferencer writes `Response` not "Structured responses + tool calls." Add Interface type column.

---

### Task 3: §11.1 — Fix interface monad table

**Files:**
- Modify: `docs/blog/formal-framework.md:412-419`

**What to change:**

The actor-to-monad mapping table has stale interface types. Update to reflect the raising/handling refinement.

**Step 1: Update the table**

| Actor | Interface monad | Co-domain characterizability |
|---|---|---|
| **Executor** | `Either E Result` (result or error) | Low — output type + error type |
| **Harness** | `StateT Conv_State IO` (manages state, lives in IO) | Low — enumerable given rules |
| **Inferencer** | `Response` (text blocks + tool call proposals) | High — one sample from opaque process |
| **Principal** | `IO` (depends on the world) | Maximal — requires the person |

Key corrections: Harness is `StateT Conv_State IO` not `State Conv_State`. Inferencer is `Response` not `Distribution`. Add remark: the Inferencer's interface is `Response` not `Distribution(TokenSeq)` — sampling has already happened. The handler receives the structured output, not the distribution. Convention 13.3a (modeling the Inferencer's effects *as if* drawn from a distribution) is sufficient for the handler's purpose.

---

### Task 4: §12.2 — Store comonad `extend` honesty remark

**Files:**
- Modify: `docs/blog/formal-framework.md:522-531`

**What to change:**

The `extend` remark over-promises. It says `extend infer` gives "what would the Inferencer produce under each possible scoping?" — a counterfactual the handler can't compute.

**Step 1: Update the extend interpretation**

Replace the current `extend infer` interpretation with the honest version:

- `extend f` where `f` is a comonadic operation captures "what would each actor *see* under each possible scoping?" — the handler's design space.
- The handler CAN compute this — it's just `view(s)` for each `s`.
- The actor's *response* to each view is opaque (internal ma, behind the interface boundary).
- `extend` captures the handler's ability to evaluate the design space it navigates. The actor's response to each possible view is what the handler optimizes for heuristically — choosing a scope that it expects (but cannot prove) will produce good results.

**Step 2: Update the Remark after the comonad operations**

The final paragraph of the Remark (line 530-531) should distinguish what the Harness CAN do (compute every possible extraction) from what it CANNOT do (predict what the actor will do with each extraction). Reference [Raising and Handling](raising-and-handling.md) for the regulation ≠ prediction distinction.

---

### Task 5: §12.7 — Harness type correction

**Files:**
- Modify: `docs/blog/formal-framework.md:591-631`

**What to change:**

The Harness's implementation type throughout §12.7 is `State Conv_State`. It should be `StateT Conv_State IO` — the Harness manages conversation state AND lives in IO (process dispatch, file loading, image processing).

**Step 1: Update Definition 12.5 Remark**

Change "The Harness is a `State Conv_State` computation" to "The Harness is a `StateT Conv_State IO` computation — it reads and writes `Conv_State` while raising its own effects in `IO` (process dispatch, file loading, image processing). In algebraic effects terms: the Harness handles conversation effects (`State Conv_State`) while raising its own effects in `IO`."

**Step 2: Update Proposition 12.7**

Change "The Harness inhabits `State Conv_State`" to "The Harness inhabits `StateT Conv_State IO`". The interface type `HarnessAction` is unchanged — the `IO` is the handler's own effect, not visible at the interface.

---

### Task 6: §12.9 (NEW) — The Grade Lattice

**Files:**
- Modify: `docs/blog/formal-framework.md` — insert new section after §12.8 (after line ~667), before §13

**What to add:**

A new section that introduces the grade lattice into the formal framework, connecting the configuration lattice (§12.8) to the interface ordering (§11). This is the key missing piece identified in self-critique point 8.

**Step 1: Write section header and motivation**

### 12.9 The grade lattice

The configuration lattice (§12.8) describes what the Harness gives each actor. The monad morphism preorder (§11) describes what others see at the interface. Between them: the actor's computation — its path space. The grade lattice formalizes this missing middle.

**Step 2: Write the grade definition**

**Definition 12.12 (Grade lattice).** The *ma* grade of an actor A is:

    ma(A) = (w_A, d_A) ∈ W × D

where W (world coupling) and D (decision surface) are join-semilattices ordered by inclusion/capacity:

    W: sealed ≤ pinhole ≤ scoped ≤ broad ≤ open
    D: literal ≤ specified ≤ configured ≤ trained ≤ evolved

The product lattice W × D is ordered componentwise. Decision surface is formalized as the log of the number of distinguishable input-dependent execution paths through the computation.

**Step 3: Write the three-orderings relationship**

**Proposition 12.13 (Configuration bounds grade).** For an actor A with Harness configuration (s, T):

    config₁ ≤ config₂  ⟹  grade(A, config₁) ≤ grade(A, config₂)

The configuration lattice is the Harness's lever — it controls the effective grade from outside.

**Proposition 12.14 (Grade bounds interface ma).** The actor's grade sets an upper bound on interface effects:

    interface_ma(A) ≤ f(grade(A))    for some monotone f

with equality when the interface is unconstrained, and strict inequality at co-domain funnels (§13.3).

**Step 4: Write the composition formula**

**Proposition 12.15 (Composition is join).** When actor A uses tool B:

    ma(A using B) = (w_A ∨ w_B, d_A ∨ d_B)

Join is well-defined on any lattice, commutative, associative, idempotent.

**Remark.** The characterization difficulty of the resulting grade is supermodular — the marginal effect of increasing one axis is greater when the other is already high. This is the formal content of "restriction is the load-bearing operation." See [The Grade Lattice](the-grade-lattice.md) for the full analysis.

**Step 5: Write the Harness as grade-reducing functor**

**Proposition 12.16 (Harness as grade reduction).** A Harness operation H applied to actor B produces:

    ma(H(B)) ≤ ma(B)   componentwise

Sandboxing reduces w. Tool restriction reduces effective w and d. The Harness is a grade-reducing functor — it maps high-grade computations to lower-grade ones.

**Remark.** In conversations, grade reduction is not one-shot but ongoing. The grade evolves via a coupled recurrence `g(n+1) = F(g(n), config(n))` where the Harness controls `config(n)`. Compaction is the Harness applying grade reduction mid-conversation. The dynamics of this recurrence depend on the computation level of the tool set — bounded for data channels, self-amplifying for Turing-complete computation channels. See [Conversations Are Folds](conversations-are-folds.md) and [Computation Channels](computation-channels.md).

**Step 6: Write connection to the three orderings**

**Remark (Three orderings, one causal chain).** The framework now has three orderings that form a causal chain:

    Configuration lattice → Grade lattice → Monad morphism preorder
    (S × P(Tools))          (W × D)          (M, ≤_ma)
    What the Harness gives   What the actor IS  What others see

Configuration bounds grade (Prop. 12.13). Grade bounds interface ma (Prop. 12.14). The co-domain funnel (§13.3) is the mechanism that makes the second bound strict — high grade mapped to low interface ma through a constrained interface type.

---

### Task 7: §13.1 — Fix implementation monad for Harness

**Files:**
- Modify: `docs/blog/formal-framework.md:676-700`

**What to change:**

**Step 1: Fix the Harness implementation monad**

Line 679: Change `State Conv_State` to `StateT Conv_State IO`. Add: "The Harness handles conversation state while raising its own effects in IO (process dispatch, file loading)."

**Step 2: Fix the Inferencer description**

Line 684: Update to note that the interface is `Response` (text blocks + tool call proposals), not `Distribution`. "We model the interface as `Response` — one structured sample from the internal process. Sampling has already happened."

**Step 3: Fix Prop 13.3 examples**

Line 698: Change "Harness (`State Conv_State ~> HarnessAction`)" to "Harness (`StateT Conv_State IO ~> HarnessAction`)" and add: "The Harness's `IO` is the handler's own effect — visible at the implementation level but not at the interface."

---

### Task 8: §17 — New design principles

**Files:**
- Modify: `docs/blog/formal-framework.md:1109-1157`

**What to add:**

Add three new principles derived from the trilogy, after existing Principle 5.

**Step 1: Write Principle 6 — The Harness is a trajectory controller**

### Principle 6: The Harness manages trajectories, not just configurations

From §12.9 and [Conversations Are Folds](conversations-are-folds.md): the Harness doesn't just set the initial configuration — it steers the grade trajectory over the life of the conversation. Compaction is grade reduction applied mid-conversation. Tool grants/revocations change the trajectory's direction. Context management controls both world coupling (what data is visible) and reachable decision surface (how many paths through the weights are exercised).

*Design test*: does your Harness have a strategy for managing the conversation's grade over time, or does it just set initial configuration and hope? Compaction thresholds, progressive tool grants, and scope adjustment are trajectory management.

**Step 2: Write Principle 7 — Stay in the specified band**

### Principle 7: The regulator stays specified

From [The Specified Band](the-specified-band.md): the OS proves that `(open, specified)` is viable — vast world coupling with transparent decision surface. The threat to the regulator is never broader world coupling; it's higher decision surface. An "intelligent" Harness that replaces specified rules with trained models becomes as hard to characterize as what it regulates.

*Design test*: is every decision in your Harness traceable to a specified rule? If you're using ML-based anomaly detection or learned heuristics in the orchestration layer, you've left the specified band. Add monitoring (observation, specified) instead.

**Step 3: Write Principle 8 — Know your computation level**

### Principle 8: Computation channels determine dynamics

From [Computation Channels](computation-channels.md): the most important property of your tool set is whether any tool accepts agent-generated text as executable specification. Data channels (file read, SQL) create bounded dynamics. Turing-complete channels (Bash, `python -c`) create self-amplifying dynamics. The computation level determines the trajectory's derivative, not a new grade axis.

*Design test*: classify each tool by computation level. If you have level 4+ tools (Bash, eval), your regulatory model needs the sandbox as backstop — the Harness alone can't mediate everything. If you can stay at level 0 (SQL, structured queries), you get convergent dynamics for free.

---

### Task 9: §18 — Update assessments

**Files:**
- Modify: `docs/blog/formal-framework.md:1160-1228`

**What to change:**

**Step 1: Update "What might be novel" list**

Add after item 12:

13. **The grade lattice** (Section 12.9). Ma as a 2D grade `(w, d) ∈ W × D` with decision surface formalized as log of distinguishable execution paths. Composition is join. Characterization difficulty is supermodular. Connects to Ashby's variety, VC dimension, and Montufar et al. (2014).

14. **The raising/handling reframing** (Section 10.5). Two-level structure dissolved into algebraic effects. Raising (monotone) vs handling (may break monotonicity). The Harness IS the handler. Session types ARE handler pattern matching. Connects to Plotkin & Pretnar (2009).

15. **The fold model for conversations** (Section 12.9 Remark). Each inference call is stateless. The conversation is a fold over managed state. Reachable vs total decision surface. The Harness as dynamical system controller.

16. **Computation channel taxonomy**. Tools classified by whether they accept agent-generated executable specifications. Determines the dynamics of the grade recurrence — bounded or self-amplifying.

17. **The specified band**. `(open, specified)` as the viable region for regulators. The OS as existence proof. Layered regulation (constraint, observation, policy). The Ashby resolution via variety reduction rather than variety matching.

**Step 2: Update item 11 in "What might be novel"**

Item 11 currently says "The two-level structure." Update to: "The raising/handling reframing (Section 10.5). Originally 'two-level structure' — now dissolved into algebraic effects. Raising (monotone) vs handling (may break monotonicity). The Harness IS the handler."

**Step 3: Update "What needs further work"**

Update items 3 and 4 to reflect partial resolution:

Item 3: "The meta-level's algebraic structure" → now partially addressed by the raising/handling reframing (§10.5). Handler composition laws from algebraic effects provide the structure. Remains: formal verification that the mapping is exact.

Item 4: "The graded monad needs mid-computation scope change" → the raising/handling framing makes this natural: scope change is the handler reconfiguring between handled effects. Remains: formal treatment of handler-mediated scope change within the graded monad.

Add new items:

11. **The coupled recurrence needs characterization.** `g(n+1) = F(g(n), config(n))` is stated but F is not given a type or constraints. Under what conditions does the trajectory converge? What determines the rate of grade inflation? The dynamical systems theory of grade trajectories is sketched in [Conversations Are Folds](conversations-are-folds.md) but not formalized.

12. **Computation channel taxonomy needs formal grounding.** The levels (0–8) are descriptive. A formal characterization — perhaps via the expressiveness of the specification language accepted by each tool — would connect to computability theory and give precise phase transition boundaries.

13. **The supermodularity claim needs proof or counterexample.** Is characterization difficulty literally supermodular on W × D, or approximately so? A formal proof would require defining χ precisely. An empirical test (measuring observer surprise as axes vary) could provide evidence.

---

### Task 10: References — Add new citations

**Files:**
- Modify: `docs/blog/formal-framework.md:1232-1248`

**What to add:**

Insert alphabetically:

- Ashby, W. R. (1956). *An Introduction to Cybernetics*. Chapman & Hall.
- Bauer, A. (2018). What is algebraic about algebraic effects and handlers? *arXiv:1807.05923*.
- Conant, R. C., & Ashby, W. R. (1970). Every good regulator of a system must be a model of that system. *International Journal of Systems Science*, 1(2).
- Miller, M. S. (2006). *Robust Composition: Towards a Unified Approach to Access Control and Concurrency Control*. PhD thesis, Johns Hopkins University.
- Montufar, G. F., Pascanu, R., Cho, K., & Bengio, Y. (2014). On the number of linear regions of deep neural networks. *NeurIPS*.
- Plotkin, G., & Power, J. (2003). Algebraic operations and generic effects. *Applied Categorical Structures*, 11(1).
- Plotkin, G., & Pretnar, M. (2009). Handlers of algebraic effects. *ESOP*.
- Saltzer, J. H., & Schroeder, M. D. (1975). The protection of information in computer systems. *Proceedings of the IEEE*, 63(9).

---

### Execution Order

Tasks are independent enough to execute in sequence. Recommended order follows the document's structure:

1. §10.5 (raising/handling) — foundational reframing
2. §10.6 (actor table) — depends on new framing
3. §11.1 (interface types) — depends on corrected types
4. §12.2 (extend honesty) — independent
5. §12.7 (Harness type) — independent
6. §12.9 (NEW grade lattice) — the big addition
7. §13.1 (implementation monads) — depends on corrected types
8. §17 (new principles) — depends on §12.9
9. §18 (assessments) — depends on everything above
10. References — independent

After all tasks: read the full document to verify consistency and flow.
