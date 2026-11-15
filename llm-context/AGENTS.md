# llm-context

Context written for agents: runbooks, styles and guidance. Browsed in Obsidian. `index.md` lists the
pages and sets the page conventions.

Agents may add or change pages here, but tell the user what was added or changed. **Never commit or
push without the user's permission**, however small the change.

Pages are often distilled from the user's notes in `../reference/` and `../permanent/`. Read those
only when told to, and never edit anything outside this folder.

## Adding context

Agents load these pages as context, so every line costs tokens and dilutes attention.

- Keep pages short. Leave out anything an agent would do anyway.
- State things directly: "keep it short", not "the owner wants it short".
- Prefer bullet points to tables.
- List every page in `index.md`, except files that belong to a workflow, with a short, accurate
  description. Agents use it to find a page without opening others, so the description must say what
  the page holds.
- Keep each list of pages in alphabetical order.
