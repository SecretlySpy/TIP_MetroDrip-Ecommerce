## 2026-08-09T02:00:31Z
<USER_REQUEST>
You are Forensic Auditor (Integrity Forensic Audit).
Working directory: /home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/teamwork_preview_auditor
Project Scope document: /home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/orchestrator/PROJECT.md

Task:
Perform an independent forensic integrity verification of all work products in the codebase.
1. Check for any hardcoded test results, expected return strings, or fabricated outputs.
2. Check for dummy/facade implementations or skipped logic in web app, mobile app, sidecars, or scripts.
3. Inspect `docker/Dockerfile.services`, `services/`, `mobile/`, and Django apps to verify authentic implementation.
4. Issue a explicit verdict: CLEAN or INTEGRITY VIOLATION.
5. Write your audit report in `/home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/teamwork_preview_auditor/audit.md` and handoff report in `/home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/teamwork_preview_auditor/handoff.md`.
6. Send a message to parent with your verdict, evidence chain, and report path.
</USER_REQUEST>
