# ARCHIVE INDEX - Project Lucca documentation snapshot (pre Phase-4 audit)

> **STATUS: READ-ONLY. SUPERSEDED.**
> This directory is a frozen snapshot of everything that lived under `docs/` immediately before the enterprise-grade audit began. Nothing in it is authoritative any more. Do not edit, do not cite as current truth, do not restore without an explicit user decision.

- **Archive timestamp (UTC):** 2026-09-17T23:56:15Z
- **Git HEAD at archive time:** `ed14f6b44fc233c94f01c9f9f3c1f68619e026e7`
- **Git branch:** master
- **Working tree:** dirty at archive time (verbatim `git status --porcelain` is recorded in `docs/audit/03_BASELINE.md`)
- **Files archived:** 47
- **Total bytes:** 512415

## Provenance of the previous docs set

- The previous precedence roots were `13_decisions_log.md` and `07_contradiction_register.md`; they overrode docs 00-05 wherever they conflicted. Read order for implementers was 13 -> 07 -> `08_adr/` -> `09_developer_spec/` -> 10 -> 11.
- That precedence chain is now historical. The new documentation set will be re-derived from code truth (`src/`, `tests/`, `config/`, `docker/`, `scripts/`, `packaging/`) as part of the audit programme scaffolded under `docs/audit/`.
- Every file listed below has the NTFS read-only attribute set. The SHA-256 digests allow later verification that the snapshot has not drifted.

## Manifest

| Relative path | Bytes | SHA-256 | Description (first heading) |
|---|---:|---|---|
| `00_original_build_brief.md` | 12387 | `27f80b4ea1a1085ec833b0151e58188ec5c1445f39ae457d47920dd028ccb64c` | Project Lucca — Local Desktop Companion Agent |
| `00_START_HERE_implementer.md` | 5166 | `6798d69f8b6f8e7dc13808ff47adb617925dcd31f85e0714b642529167a94249` | START HERE — Implementer Entry Point (Project Lucca) |
| `01_recursive_architecture_audit_and_flaw_analysis.md` | 24387 | `b459e770db8513fab0a46b2ce719d7475618d40ee46f1233c99c3f1c0ceff188` | Project Lucca — Recursive Architecture Audit & Flaw Analysis |
| `02_systems_research_prior_art_and_alternatives.md` | 14869 | `2234fed81b3716f2a0a00f7fb7a3ba2bdbb9d495d1ff8c68cac174eb2487ced5` | Project Lucca — Systems Research, Prior Art & Alternative Proposals |
| `03_enterprise_hardware_topology_and_ipc_spec.md` | 11922 | `10528389f23fdb73c281ab4bc7955671f6cfdb9122a82615126088ccb7c461b6` | Project Lucca — Enterprise Hardware Topology & IPC Specification |
| `04_deep_mechanical_testing_and_verification_matrix.md` | 10981 | `32587a365d97bb155660665ccc1c344a19fa4183a838e6c6fa25c379aa76ade0` | Project Lucca — Deep Mechanical Testing & Verification Matrix |
| `05_lucca_system_architecture_master_spec.md` | 10357 | `ff42eeea6e1e6f9635f5687a304c3ddcaa6e442e332460128723e68532f6cd80` | Project Lucca — System Architecture Master Specification |
| `06_critical_review_findings.md` | 7088 | `5f9fef142c5be9a124e2b0bcf8526fd2e09303ea753820de19b61e8dcef0a85f` | 06 — Critical Review Findings & Code-Fix Issue List |
| `07_contradiction_register.md` | 16743 | `7ff6bbcb53103f58ef1802a122a70dd12b59407229da7e5f424660265e556384` | 07 — Contradiction Register & Canonical Values |
| `08_adr/ADR-001_inference_engine.md` | 8009 | `f4ea008065d3b13faee315709acf3dac2d4c243e5396d86ea77effefbb8b34a1` | ADR-001 — Inference Engine: `llama-server` on Windows serving Ultravox Q6_K GGUF, with cascade as a config-switch fallback |
| `08_adr/ADR-002_memory_storage.md` | 6095 | `4bec21ba0aed74655d87e73160896726dfd80fd0679b9f64eec0d2e84fde3913` | ADR-002 — Memory Storage: single SQLite file (WAL) with FTS5 + `sqlite-vec`; networkx as in-memory view only |
| `08_adr/ADR-003_sandbox_egress_policy.md` | 5042 | `d47397c05b9ccf65f4459a28cee5ecb67764c0127d9a8b1623c79e0be6d79fb4` | ADR-003 — Sandbox Egress: Docker CE in Ubuntu WSL2, ordered `DOCKER-USER` allow-list with default DROP, IPv6 disabled |
| `08_adr/ADR-004_split_sandbox_containers.md` | 3915 | `76b111cab2d9f37de7ceff2c090219632bea7e60c3012065f5dea81154c8443f` | ADR-004 — Two sandboxes: `file-sandbox` (workspace, no network) and `web-sandbox` (network, no files) |
| `08_adr/ADR-005_ui_framework.md` | 2276 | `ef29a69c404bd531281be8060077c95b77fa8791515d474ef30270c9b3d48ca2` | ADR-005 — UI: PyQt6 overlay in its own process; RMS-envelope lip-sync in Phase 1 |
| `08_adr/ADR-006_provenance_tiers_and_signers.md` | 5710 | `6e2adf19778c809d00f2a9e5532592c8304be40ca3d371972fa87c272eb13fec` | ADR-006 — Provenance: two-tier user provenance, content/structure split for tools, per-provenance capability signers |
| `08_adr/ADR-007_rules_as_pure_plans.md` | 6569 | `f81de2d4bf327d862d70dcc8293f03348201b1ff33ebe864c08d2c81745daeb1` | ADR-007 — Compiled rules are pure `State → Plan` functions; the orchestrator executes plans under a risk policy |
| `08_adr/ADR-008_process_topology.md` | 4119 | `e41d527fab810aaf13138c617f7f3d71d5d49f27338b4e3986383b2b833d138f` | ADR-008 — Process topology: four Lucca processes + external `llama-server`, ZeroMQ IPC, shared-memory audio ring |
| `08_adr/ADR-010_larger_models_after_64GB_upgrade.md` | 13023 | `3766b8e93f35d6e13f6a41a2bd49386ea45b4cc602dfe937b1ff65a671d9015d` | ADR-010 — Larger / MoE models after the 64 GB system-RAM upgrade (incl. predictive expert-paging runtimes) |
| `09_developer_spec/01_process_topology_and_ipc.md` | 9276 | `8a68b8c3d87b5da4887e81297974fccc15b0f923f6df0b2022387988fd7e804d` | Spec 01 — Process Topology, IPC Contracts, Startup/Shutdown |
| `09_developer_spec/02_ports_and_interfaces.md` | 6327 | `97bbfc56e06fa7f6ac7e99ab5219acffd1d0573cbcd5553adbafa5f19e66a0cb` | Spec 02 — Ports (hexagonal boundaries) and Adapter Contracts |
| `09_developer_spec/03_provenance_model.md` | 8444 | `a7e6cd6bea53ea2101c3297fad60d139833390af3b87ac802fbe352c5941b925` | Spec 03 — Provenance Model, Signers, Gate, Extraction |
| `09_developer_spec/04_memory_storage_schema.md` | 12391 | `b58f30aa2cbd785250d4d7e9c5498c626fb546a3e5341d44a8b29ed48aff6277` | Spec 04 — Memory Storage Schema, Retrieval, Temporal Facts, Backups |
| `09_developer_spec/05_rule_dsl_grammar_and_lifecycle.md` | 12388 | `de4a003a5359445f6b0138ffc3a43b466ed17b5bd8579b340ab685b4df4ee013` | Spec 05 — Rule DSL (MicroScheme v2), State Schema, Evaluation, Lifecycle, Reflection |
| `09_developer_spec/06_router_classifier_and_labeling.md` | 9549 | `8552ff534c6d48a1d2ed2f96427b82ad45149aa3eeb905d6e53dc85cc871addd` | Spec 06 — Executive Router, Decision Logging, Labeling Protocol, Classifier & Conformal Guard |
| `09_developer_spec/07_audio_pipeline_and_barge_in.md` | 8552 | `8be1e43c897d7f10dcd96768b8194402578615fd084a6fe69e02b1a29dd97670` | Spec 07 — Audio Pipeline: PTT, Capture, VAD, ASR (NPU), TTS device ladder, Playback, Barge-in |
| `09_developer_spec/08_streaming_chunker_spec.md` | 6317 | `3a9547ccd490e7ef376b47aee2d177f0038e5235e9f3f0cc4403c580296976ec` | Spec 08 — Streaming Text Chunker and Tool-Call Demultiplexer |
| `09_developer_spec/09_sandbox_hardening.md` | 11762 | `e786001c0b2226efaf8bde12f7ed407d75282dcb3087750bc5c2e426a428e31d` | Spec 09 — Sandbox Hardening: containers, RPC, file tool, web tool, launcher, egress verification |
| `09_developer_spec/10_latency_trace_and_budgets.md` | 4976 | `46c6535ca137ddb0428fefacd9dab4c037ff78304bf5bd690c7850759be66f62` | Spec 10 — Latency Trace Schema, Per-Stage Budgets, Context Budget |
| `09_developer_spec/11_observability_config_and_lifecycle.md` | 7811 | `ec60c03be25a879b4f2e7f3756ba13acff4b15da1009ec5ca5c94038b7047bac` | Spec 11 — Configuration, Observability, RAM Budget, Dependencies, Static Gates, Admin CLI |
| `09_developer_spec/12_threat_model.md` | 7107 | `7d1ab6d697eaf064a58088c2a078eb00b67b978d7515e161566d4bbb9ffc20e2` | Spec 12 — Threat Model (STRIDE-lite), Trust Boundaries, Risk Policy |
| `10_testing_matrix_v2.md` | 10235 | `579de86d91e9a307d25ffc299e87f6f33c19ce2c259778b6c7e84950b06973b9` | 10 — Deep Mechanical Testing Matrix v2 |
| `11_phase_plan_v2.md` | 7211 | `a6f97b4d6d772936bb2b5b2d551ce8b5c59f7502a5b83b7e9f6506155a759589` | 11 — Phase Plan v2 (Phase 0 spikes, human gates, deferred scope) |
| `12_prior_art_survey.md` | 8010 | `b1469ebadef9dc0301ecd674dbdb6b50b232be8a99dea915bc7e5fbe67db90f3` | 12 — Prior Art, Comparable Projects, and Alternatives Survey |
| `13_decisions_log.md` | 12191 | `ea3ac59ca1c34455ba1f74ccd937da86548384d3863f535009816450ad3358e0` | 13 — Decisions Log |
| `14_blockers.md` | 4203 | `cbc73f32e121fac5d8a49c35f045c2bc345b995705d08852e0ce58f2e2b10167` | Phase 0 Blockers & Threshold Discrepancy Report |
| `14_phase0_results.md` | 7226 | `3aeb38537f1d260fab8e285b6a245e77a7e60f2d6d2cb795cc70da719dca2e4f` | Phase 0 Feasibility Spike Results & Hardware Measurements |
| `14_second_pass_review.md` | 6437 | `53a8615cfbbd2976f9a0d5b8ae977a9f0ab3da00e84425f051bc07dc31df82b2` | 14 — Second-Pass Review of the 2026-09-17 Document Set |
| `16_user_guide_onboarding.md` | 8024 | `bb3329cd6516f7300fb1b64735c83695dc6c25242e676d9289c86e675b0fe3ad` | 16 — User Guide: Living with Lucca (onboarding, personality, moods) |
| `17_project_summary_and_positioning.md` | 13827 | `8f851f84a7601a91608485c15039c3a31ea0717ce6f76ab9bed8af92939d1373` | 17 — Project Lucca: What It Is, What v1.0 Delivers, Where It Can Go, and How It Compares |
| `18_roadmap_plain_and_technical.md` | 18367 | `811438dc35b09d49e8d5ebd4d40dbd5e5da7e65a4c5edda21efed17be8e00ef0` | 18 — The Lucca Roadmap, Explained Twice |
| `HANDOVER_2026-09-17_critical_review.md` | 42009 | `a0311be34cbd1d63f26519a181cef292f301d398b6ad9d9f4318281820712363` | HANDOVER — Critical Architecture Review (Interrupted Session) |
| `IMPLEMENTATION_PROMPT_2026-09-17_persona_llm_ui.md` | 14965 | `df99c88f6035a8a36515ffe7f67908c3cb607049da071533a80ca6d5ee53db6e` | Implementation Prompt — Persona Tab Enrichment & LLM Tab Honesty Pass |
| `project_lucca_architecture_review.md` | 20356 | `110ff964df8a84b992498de2e4aaab1082d6925ebad140d29b33b74e304aec34` | Project Lucca — Architectural Research & Technical Deep-Dive |
| `RESEARCH_PROMPT_2026-09-17_engine_decision.md` | 10640 | `99234a7e3ec8bff893e7f1936ab911d97806532857578c2c1929ff51c89729e0` | Research Prompt — Verify Facts Blocking Lucca's Inference-Engine Decision |
| `RESEARCH_REPORT_2026-09-17_engine_decision.md` | 27951 | `696f6be0f5455a86c5f933dc024be45b57578f8cd4ae1338a4d25385b5f103c9` | Research Report — Verification of Facts Blocking Lucca's Inference-Engine Decision |
| `RESEARCH_REPORT_2026-09-17_review_notes.md` | 9659 | `62b30ea45f761a7e2b12ac04b8437af37d164409d13270bf20bd6555686c0458` | Review Notes on `RESEARCH_REPORT_2026-09-17_engine_decision.md` |
| `UI_USER_GUIDE.md` | 17546 | `280c419aab5a418ecd47a2235542717587d55f16e64cffe6d18f01e02d9d0806` | Project Lucca — User Interface Guide & Reference Manual |
