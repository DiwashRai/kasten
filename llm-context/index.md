---
type: index
updated: 2026-11-17
---

# LLM context

Knowledge written for agents to apply.

## Conventions

- Pages apply only when a workflow points to them or the user asks.
- One topic per page. File names are lowercase-kebab (`frontend-layering.md`), and pages link to
  each other with `[[frontend-layering]]`. Links are what build the graph, so link generously.
- Every page starts with frontmatter: `type` (person, decision, topic) and `updated` (date).
- Facts that last go in the kasten. Working state (what's on hold today) stays in each agent's
  `memory/` notes.

## Pages

- `python-style/`: a skill folder for writing good Python. Copy the whole folder into
  `.claude/skills/`. Holds the style guidelines, layout rules and the lint scripts.
- [[writing-skills]]: writing good, token-efficient skills.

## Writing styles

A style covers the prose asked for, not code, commands or quotes.

- [[bluf-writing-style]]: conclusion first. Combines with other styles.
- [[runbook-writing-style]]: pages that tell an agent what to do.
- [[ste-writing-style]]: Simplified Technical English, for strict procedures and specs.
- [[telegraphic-writing-style]]: periodic reviews and status notes.
