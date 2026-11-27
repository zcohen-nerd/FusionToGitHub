# Audit and sprint reports

The permanent record of the v1.0 readiness audit (2026-11-26) and of the
sprints that act on it. The current state of each risk is kept in
[`../RISK_REGISTER.md`](../RISK_REGISTER.md); these reports are snapshots and
are not updated afterwards.

| Document | What it is |
|---|---|
| [FusionToGitHub_v1_Audit_Report.md](FusionToGitHub_v1_Audit_Report.md) | The v1.0 readiness audit: findings, evidence, maintainer questions Q1–Q17 and the sprint plan |
| [annexes/ANNEX-3_Fusion_Platform_UX_workpaper.md](annexes/ANNEX-3_Fusion_Platform_UX_workpaper.md) | Audit workpaper: Fusion platform and user experience |
| [annexes/ANNEX-7_Docs_OSS_Branding_workpaper.md](annexes/ANNEX-7_Docs_OSS_Branding_workpaper.md) | Audit workpaper: documentation, open-source hygiene and branding |
| [S3_Implementation_Report.md](S3_Implementation_Report.md) | Sprint S3: testability and application architecture (developed as 0.5.0, shipped in 0.6.0) |
| [S4_Implementation_Report.md](S4_Implementation_Report.md) | Sprint S4: Fusion integration and export reliability (0.6.0) |
| [workpapers/r21_ext_transport_probe.py](workpapers/r21_ext_transport_probe.py) | Reproduction for risk R-21: repository config starting a program (`ext::`) in a token-carrying Git process |
| [workpapers/r21_probe.py](workpapers/r21_probe.py) | Reproduction for risk R-21: tracing, redirects, another repository on the same host, and the process environment |

## Notes

- The workpaper scripts use **synthetic tokens only**, local servers on
  127.0.0.1 and fake hosts (`git.example.invalid`), with system and global
  Git configuration switched off, so they can't touch real credentials or
  real repositories. Read a script before running it; run it with
  `python -I <script>` from the repository root.
- Local folder paths in these documents (the author's home, temporary and
  session folders) have been replaced with `<home>`, `<temp>`,
  `<scratchpad>` and `<repo>`. Nothing else was changed.
- Only two workstream workpapers were kept as annexes (3 and 7); as the
  report says, everything material from the other five workstreams is
  consolidated in the report itself.
- Statements about Fusion's behaviour in these reports are as tested at the
  time, mostly against simulated Fusion objects. The manual checklist
  ([`../../tests/MANUAL_CHECKLIST.md`](../../tests/MANUAL_CHECKLIST.md)) is
  where live results are recorded.
