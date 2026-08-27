# Evidence levels

Use one label on every substantive literature claim.

| Label | Directly inspected | Allowed claims | Not allowed |
|---|---|---|---|
| `[题录]` | Search result or bibliographic metadata | Identity, title, authors, source, year if present | Method, data, result, mechanism |
| `[摘要]` | Paper abstract | What the abstract explicitly reports about question, broad method/data, and conclusions | Unreported specification detail, coefficient, robustness, full limitations |
| `[全文]` | Validated paper PDF and relevant pages | Page-specific method, data, estimates, mechanisms, caveats | Claims outside inspected passages |
| `[推断]` | Model interpretation grounded in listed records | Clearly worded synthesis or hypothesis | Presenting inference as an author's finding |
| `[待核验]` | Conflicting, missing, or inaccessible evidence | A precise verification task | Treating the item as settled fact |

Rules:

- Evidence level attaches to the claim, not permanently to the paper. One paper
  may support a title claim at `[题录]` and a result claim at `[全文]`.
- A higher-level artifact does not automatically verify every claim in it; inspect
  the relevant passage.
- Keep exact source metadata separate from model-authored notes.
- A citation count is a platform/time-specific signal, not paper quality.
- A frequent author in one session is not automatically an important field
  scholar. Explain the selection basis.
