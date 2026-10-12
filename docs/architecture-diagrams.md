# Architecture diagrams

The [`.omm/`](../.omm/) folder holds RemitX's architecture as Mermaid diagrams
with notes, generated with [oh-my-mermaid](https://www.npmjs.com/package/oh-my-mermaid)
(`omm`). Each top-level folder is one way of looking at the system:

| Perspective | What it answers |
|---|---|
| `overall-architecture` | What exists and how the pieces relate (drills into the API, worker, frontend, infra) |
| `request-lifecycle` | How one HTTP request travels from the SPA through auth, RLS and the controllers |
| `orchestration` | How remittance settlement runs through Celery + Redis, and how lost work is reclaimed |
| `state-transitions` | Status changes for KYC, documents, deposits, quotes, ledger legs, bank accounts, withdrawals |
| `data-flow` | How money moves through the ledger, from deposit to payout to withdrawal |
| `route-page-map` | Frontend pages and navigation, with the permission each admin page needs |
| `external-integrations` | Clerk, ExchangeRate-API, XRPL / XRPL EVM, Neon, Render, HCP Terraform |
| `storage` | Postgres tables by domain, the KYC bucket, Redis, encrypted keys, migrations |

Each element has a `description.md`, and some also have `context.md`,
`constraint.md`, `concern.md` (known risks), `todo.md` and `note.md`. A
`diagram.mmd` means the element has its own sub-diagram.

## Viewing them

You need Node.js (any recent LTS).

```bash
npm install -g oh-my-mermaid   # once
cd RemitX                      # the repo root, where .omm/ lives
omm view                       # opens http://localhost:3000
```

Click a node in a diagram to open its sub-diagram and notes. Use
`omm view --port 3001` if port 3000 is taken.

Without installing anything, you can still read the notes as Markdown on
GitHub, or paste a `diagram.mmd` into [mermaid.live](https://mermaid.live).

## Keeping them current

The diagrams describe the code as of 2026-10-12. After a significant change
(new service, new task, new page group), update them with the `omm-scan`
skill in Claude Code, or by hand with `omm write <path> <field> -`. Run
`omm validate` before committing.
