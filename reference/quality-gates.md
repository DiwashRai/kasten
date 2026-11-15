---
type: topic
updated: 2026-11-07
---

# Quality gates for agentic workflows

Quality gates are mandatory checkpoints that an AI agent has to pass to get through to the next
stage of their workflow. These may be programmatic checks, automated LLM-judges or manual
human-in-the-loop reviews.

The goal is for these gates to be robust enough that an agent can be given a task, iterate on the
goal independently so that when the human review does finally happen, the output is already of a
high quality.

## Principles

- Catch problems early; spend human attention last.
- Prefer faster and more programmatic checks over LLM or human reviews.
- Reviews should be used for judgement.
- Have an upperbound on iterations per loop.

## Types of gates

- Programmatic: linters, static analysis tools, automated tests etc.
- LLM judges: an LLM agent grading the output against a predefined rubric or set of criteria
- Human reviewers: manual reviews by humans who consider the output holistically

Wherever possible we should prefer programmatic checks as they are faster, deterministic and less
resource intensive than LLM judges or human reviewers.

### Programmatic gates

#### Metrics

- Cognitive complexity. Cyclomatic complexity is optional.
  - max 15 per function
  - Use a score of functions above 15 as the gate metric
- Nesting depth: max 4
- Code duplication
  - No new code duplication against base branch
- Size backstoips
  - max parameters per function
  - max statements per function
  - max return points per function

#### Linters and static analysis

- Strict typing.
  - No escape hatches such as `any` in public interfaces
- lint rules for common anti-patterns
  - e.g. clang-tidy bugprone-* checks
- Dependency rules
  - The direction of dependencies should be decided by the architecture. Then it can be enforced to
    prevent architectural drift overtime
  - Infrastructure -> application -> core should be the general flow
    - Primitives can be depended on by any layer e.g. utility functions, common data structures

### Soft programmatic gates - Nudges

These are things that are reported by programmatic checks, often with something like pre-commit
hooks, that offer warnings or guidance without actually blocking the agent.
