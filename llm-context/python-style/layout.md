# Layout

Read before creating, moving or splitting a file. In an existing project, follow its layout.

- **Pure by default.** A file is pure unless its path matches `impure` under `[tool.layout]` in
  `pyproject.toml` (usually `["*_io.py"]`). Pure means no I/O, environment, clock, randomness, `Any`
  or untyped dicts, and imports only of pure files. Pass values such as today's date in.
- **Calling a client is I/O**, even when the client is passed in or typed as a `Protocol`.
- **Impure files are thin.** One talks to a system (`confluence_io.py`) or runs a subject's steps
  (`page_write_io.py`). It carries out what pure functions decide and never chooses what happens
  next.
- **One file per subject**, named as a change request would name it (`search.py`, `page_write.py`),
  with its types and functions together. Never split by kind: `model`, `rules`, `utils`, `inputs`,
  `results`.
- **Start flat.** A few lines do not earn a file. A subject gets a folder once it spans several
  files. Split a large file into two subjects, never into types and functions.
- **A likely change should touch one or two files.** More means a subject is spread across stages.
- **Folder imports are declared** in `[tool.layout.imports]` (`orders = ["payments"]`), with no
  cycles.

Never add an impure pattern or an import declaration to pass a check. When unsure, choose the
simpler structure.

## Three sizes

Shapes, not templates. Impure files are marked `*`.

### A single-file script

```text
tools/sync_labels.py
  constants and types
  pure functions         parse, compare, decide what to change
  main()                 reads arguments and files, calls the pure functions, writes the result
```

### A small project

```text
src/wiki_cli/
  errors.py            WikiError, error codes, exit table
  config.py            Config, BaseUrl, validating the URL, token and timeout
  confluence.py        response records and their parsing, endpoint paths, status to error code
  confluence_io.py  *  the only code that sends HTTP
  pages.py             PageId, selectors, URL parsing, checks on a fetched page
  search.py            query escaping, space filtering, search input and result
  page_write.py        create and update: inputs, checks, payloads, progress, results, label rule
  page_write_io.py  *  the create and update steps: fetch, check, send, label
  cli.py               the argument parser, and parsed arguments into a typed command
  main_io.py        *  environment, files and stdin, output, one call per read command
```

### A larger project

```text
src/shop/
  errors.py
  money.py                  Money, rounding, conversion at a rate that is passed in
  catalog.py                products and pricing rules
  main_io.py             *  startup: settings, clients, routes
  orders/
    order.py                Order, line items, totals, state changes
    discounts.py            discount rules and how they stack
    fulfilment.py           what ships when, splitting and merging shipments
    checkout_io.py       *  the checkout steps: price, discount, charge, store
    orders_store_io.py   *  SQL for orders
    orders_api_io.py     *  request handlers: turn a request into a call, and the result into JSON
  payments/
    payment.py              Payment, refunds, retry decisions
    stripe.py               records parsed from Stripe, status mapping
    stripe_io.py         *  the only code that calls Stripe
```

`catalog` is still one file. `orders` declares its import of `payments`.

## Bad and good

### Category names, and a folder for a small subject

Bad:

```text
selectors/
  model.py       ById, BySpaceTitle
  rules.py       parse --page-id, --url, --space-key and --title
```

Good:

```text
pages.py         PageId, ById, BySpaceTitle, selector and URL parsing
```

### The same split under new names

Bad:

```text
confluence/
  records.py     typed response records
  responses.py   parse and validate responses
```

Good:

```text
confluence.py    response records and the parsing that validates them
```

### A feature sliced by stage

Bad: a new field on update touches three files.

```text
operations/
  inputs.py         validated inputs of every operation
  results.py        results of every operation
  write_policy.py   version, parent and title checks
  progress.py       write progress and its errors
  search.py         query escaping, space filtering
```

Good:

```text
page_write.py    create and update: inputs, checks, payloads, progress, results
search.py        query escaping, space filtering, search input and result
```

### Hidden I/O

Bad: `writes.py` passes the purity check, yet reaches the network.

```text
operations/
  writes.py      checked as pure: calls the client that is passed in
confluence/
  client.py   *  the HTTP client
```

Good:

```text
page_write_io.py  *  the create and update steps; takes the client
confluence_io.py  *  the only code that sends HTTP
```

### Catch-all

Bad:

```text
core.py          errors, exit codes, PageId, JSON types
```

Good:

```text
errors.py        WikiError, error codes, exit table
pages.py         PageId, with the rest of what concerns a page
confluence.py    the JSON value type, with the parsing that narrows it
```
