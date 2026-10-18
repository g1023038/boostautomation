# Running purchase tests from a Rovo/chat conversation

Goal: a person tells Rovo (or whatever chat agent) something like "buy 1
Plato Coffee and pay with Boost Points" or "buy a R50 KFC voucher, split
half Boosts half card" -- and that triggers a real run of
`scripts/run_purchase_test.py` against a LambdaTest real device, using
exactly the data the person gave, with the result reported back.

## Why this needs a Forge app (confirmed, not assumed)

Rovo itself can't make outbound HTTP calls on its own, and even a Forge
`rovo:action` is a tool *Rovo* calls when a human is chatting with it --
there's no way for an external system to invoke Rovo headlessly (this was
confirmed earlier when we looked at automating test-case generation). But a
`rovo:action`, once triggered by that chat, CAN reach out to external APIs
via `fetch()` -- that's the piece that makes this work: the human supplies
the data in conversation, Rovo recognizes the intent and extracts the
parameters, and the action it calls is what talks to GitHub.

## The flow

1. **Person chats with Rovo**: "Run the Boost Buy test: buy 1 Plato Coffee,
   pay with Boost Points."
2. **Rovo extracts parameters** from that sentence using its own NLU, maps
   them to the schema below, and invokes a custom Forge `rovo:action`
   (e.g. `runPurchaseTest`) with those parameters as its input.
3. **The Forge action calls GitHub's `workflow_dispatch` REST API**
   (`POST /repos/<OWNER>/<REPO>/actions/workflows/run-purchase-test.yml/dispatches`)
   with the parameters as `inputs`. This needs the same GitHub PAT pattern
   already used for `repository_dispatch` (see
   `rovo-handoff/jira-automation-rules.md`) -- stored in the Forge app's own
   secure storage, not hardcoded.
4. **GitHub Actions runs `scripts/run_purchase_test.py`** with those inputs
   as env vars, exactly as it's invoked manually today.
5. **Result comes back** as `result.json` (order id, balance before/after,
   wiCode, pass/fail) -- the workflow posts it to a Confluence page or Jira
   comment (reusing `scripts/confluence_client.py` / `jira_client.py`), since
   `workflow_dispatch` has no built-in way to talk back to the triggering
   chat directly. Rovo can then be asked "what happened with that test" and
   read it from there, or the Forge action can poll the workflow run status
   via GitHub's API and report back directly once interactive polling from
   Forge is wired up.

## Parameter schema (what Rovo needs to extract from chat, and what the
workflow's `workflow_dispatch` inputs mirror exactly)

```yaml
inputs:
  product_name:
    description: "Exact catalog name, e.g. 'Plato Coffee' or 'KFC_Display'"
    required: true
  product_amount:
    description: "Only for variable-denomination products (e.g. KFC_Display)"
    required: false
  payment_method:
    description: "points | card | split"
    required: true
    default: points
  boosts_amount:
    description: "Only for payment_method=split -- the Booosts portion"
    required: false
```

This is a direct mirror of the env vars `run_purchase_test.py` already
takes -- no translation layer needed beyond Rovo's own intent parsing.

## What's real vs. what's still a design

- **Real, verified today**: `scripts/run_purchase_test.py` runs standalone
  with these exact env vars and produces `result.json` (verified for
  `payment_method=points`; `card` and `split` verified manually via
  `explore_app.py` and share the same code path).
- **Not yet built**: the GitHub Actions workflow wrapping this script with
  `workflow_dispatch` inputs (straightforward -- same pattern as the other
  4 workflows in `.github/workflows/`), and the Forge `rovo:action` itself
  (real development work: a Forge app, its manifest, the `fetch()` call,
  and whatever credential storage Forge provides for the GitHub PAT).
- **Open question worth asking Rovo directly**: given a sentence like "buy
  a R50 KFC voucher, split half Boosts half card", can a custom Rovo agent
  reliably extract structured parameters (product name match against a
  known catalog, amount, payment split) before calling the action -- or
  does the action need to handle fuzzy/partial parameter sets and ask
  Rovo's user a follow-up question first? Worth a quick confirmation before
  investing in the Forge app.
