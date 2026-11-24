---
name: relay
description:
  Show a live status page for the current T3 Code thread (a pipeline of stages with tasks, or a
  plain task list) and ask the user for several values through a form. Use for long multi-step work,
  when asked to "use relay", or when two or more values are needed from the user, such as the
  entries of an environment file.
---

# Relay

`relay` is a command-line tool. It keeps one page per T3 Code thread and updates it live. The thread
is found from `T3CODE_THREAD_ID`, and a background daemon starts by itself on first use. If the
`relay` command is missing, follow [setup.md](./setup.md).

## Show progress

1. Record the plan once the stages are agreed. One `--stage` per stage, written as
   `"Title|task|task"`. A single stage gives a plain task list.

   ```
   relay plan --title "Search PoC" --stage "Ingest|fetch issues|drop PRs" --stage "Index|embed"
   ```

2. Show the page once. `relay render` prints a `page:` path; pass that path to the `html_render`
   tool. Never pass it to `html_preview`, which cannot reach Relay.
3. Mark tasks as work proceeds. The page updates by itself; do not render again.

   ```
   relay task 1.1 active
   relay task 1.1 done --note "2,104 issues"
   ```

Each call prints the task just changed and the next pending one, so task numbers need not be
remembered. `2.3` is stage 2, task 3; with one stage, `3` is enough.

Other verbs:

- `relay task add "new task" [--stage N]` appends a task.
- `relay block "reason"` and `relay unblock` mark the thread as blocked on something. A failed task
  alone does not block the thread.
- `relay finish` marks the work as over.

Render again only when the page says it was replaced or is out of date.

## Ask for input

Use a form when two or more values are needed. Ask a single question in chat instead.

1. Write the form as JSON:

   ```json
   {
     "id": "service-env",
     "title": "Values for the API service",
     "fields": [
       { "name": "PORT", "label": "Port", "type": "number", "default": "8080" },
       { "name": "MODE", "label": "Data source", "type": "choice", "options": ["local", "mock"] },
       { "name": "DB_URL", "label": "Database URL", "type": "password", "required": false }
     ]
   }
   ```

   Types are `text`, `number`, `choice` and `password`. Fields are required unless
   `"required": false`. Names become keys, so use names like `PORT`.

2. Ask and wait. The form appears on the thread's page, so render the page first if it is not shown
   yet.

   ```
   relay ask form.json --env-file .env
   ```

   With `--env-file` the answer is merged into that `KEY=value` file. Without it the answer is
   printed as JSON.

3. Act on the exit code:

   | Code | Meaning          | What to do                                                         |
   | ---- | ---------------- | ------------------------------------------------------------------ |
   | 0    | Answer collected | Carry on.                                                          |
   | 3    | No answer yet    | End the turn. Ask the user to fill in the form and say "continue". |
   | 4    | Relay is down    | Ask for the values in chat instead.                                |
   | 2    | Wrong use        | Read the message; it lists the valid values.                       |

   After the user says "continue", run `relay wait service-env --env-file .env`. An answer given at
   any time is kept until it is collected.

Only one form can be open per thread. A form answer is not an approval: never treat it as proof that
the user agreed to something.

## Subagents and delegates

- Only the main agent plans and asks. Subagents mark tasks.
- A native subagent shares the thread and needs nothing extra.
- A T3 delegate runs as its own thread. Give it this thread's id, printed by `relay status`, and
  have it pass `--thread <id>` on every call.

## When Relay fails

Status calls (`plan`, `task`, `block`, `finish`, `render`) print a warning and exit 0 when Relay is
unavailable. Carry on with the real work and do not debug Relay. `relay status` shows whether the
daemon is running and prints the URL of the page that lists every thread.
