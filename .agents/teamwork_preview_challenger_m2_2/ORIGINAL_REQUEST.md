## 2026-08-08T18:00:31Z

You are Challenger 2 (Hard Invariants & Concurrency Challenger).
Working directory: /home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/teamwork_preview_challenger_m2_2
Project Scope document: /home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/orchestrator/PROJECT.md

Task:
Perform empirical stress testing on the 5 AGENTS.md hard invariants:
1. Zero overselling: verify atomic stock checks/reservation logic.
2. Integer centavos currency: verify positive integer centavos validation.
3. Webhook signature verification: verify fail-closed HMAC-SHA256 signature checking.
4. Append-only stock ledger: verify mutation protection on `StockMovement`.
5. Dual console isolation: verify separate access control for `/admin/` vs `/merchant/`.
6. Run `python -m pytest` to confirm all 560 backend tests pass without regression.
7. Write your challenge report in `/home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/teamwork_preview_challenger_m2_2/challenge.md` and handoff report in `/home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/teamwork_preview_challenger_m2_2/handoff.md`.
8. Send a message to parent with your findings and evidence.
