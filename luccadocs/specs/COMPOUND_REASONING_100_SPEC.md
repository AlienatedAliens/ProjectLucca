# Project Lucca: 100-Problem Compound AI Reasoning Benchmark Specification
**Document ID:** `SPEC-BENCH-100-v1.0`  
**Target:** Project Lucca v1.0+ Cognitive Architecture  
**Execution Harness:** Live `TurnPipeline` & `Orchestrator` End-to-End

---

## 1. Architectural Philosophy: The Compound AI Doctrine

A 12B parameter neural language model cannot reliably solve complex 3D kinematic transformations, 4-variable constraint grids, or temporal interval overlaps purely in its autoregressive attention heads. However, when wrapped in a **Compound AI Architecture**—where System 1 (neural intuition, speech streaming, Theory of Mind, dialogue persona) is seamlessly integrated with System 2 (deterministic AST math, isolated Python sandbox execution, live web research, formal Z3 SMT verification, and Belnap evidential gating)—the 12B model can outperform 70B+ monolithic models with mathematical certainty.

This benchmark establishes **10 distinct reasoning categories**, each containing **10 graded, deterministic test problems** (100 problems total). Every test is executed directly through the live `TurnPipeline` entry point used in production text and voice interactions.

---

## 2. The 10 Reasoning Categories & Systems Engaged

| Cat # | Category Name | Underlying Systems Engaged | Primary Objective |
| :---: | :--- | :--- | :--- |
| **01** | **Situational Telemetry Deduction** | Substrate 0 (Clock, UTC offset, OS) + `calc_math` + LLM Anchor | Grounding in live host state; calculating timezone gaps, hardware budgets, and real-world anchors without canned disclaimers or theoretical lecturing. |
| **02** | **Spatial, Kinematic & 3D Vectors** | System 1 Code Generation + WSL2 Sandbox + Numpy | Autonomously translating multi-step 3D rotations, vector trajectories, and kinematic physics into executable code rather than mental guessing. |
| **03** | **Formal Constraint Logic Grids** | NL-to-Constraint Compiler + Z3 SMT Verifier / Constraint Engine | Compiling multi-variable puzzle rules into mathematical assertions; finding satisfying models deterministically with zero dropped constraints. |
| **04** | **Closed-World Interval & Algebraic Math** | Router Puzzle Exemption + `calc_math` AST + Pure Logic | Solving self-contained scheduling intervals and market equations while ensuring the Epistemic Cascade never treats word problems as missing files. |
| **05** | **Web-Augmented Real-World Research** | Substrate 3 (`search_web`/`fetch_url`) + Evidential Bilattice | Recognizing parametric uncertainty, executing live web research across wikis and documentation, and synthesizing verified facts without raw URLs. |
| **06** | **Defeasible Abductive Inference** | Walton Schemes (Sign, Analogy, Defeater) + Concert Layer | Deducing the best explanation from physical trace evidence; applying default assumptions and respecting defeaters without hyper-cautious refusal. |
| **07** | **Theory of Mind & Strategic Game Theory** | ToM Perspective Engine + Asymmetric Information Models | Tracking 2nd-order nested beliefs, false-belief scenarios, and game-theoretic moves under information asymmetry (first-price auctions, signaling). |
| **08** | **Autobiographical Memory & Hard Purge** | Substrate 2 + Knowledge Graph + CBR + Hard-Purge Service | Forming facts and precedents across turns, while strictly proving ZERO ghost leakage across all backing stores after a memory wipe or reset. |
| **09** | **Meta-Cognitive Self-Diagnosis** | `self_diagnosis.py` + Telemetry Traces + Process Heartbeats | Reasoning about her own operational stack: diagnosing turn latency, VRAM consumption, tool failure causes, and audio dropouts from traces. |
| **10** | **Means-Ends Practical Goal Planning** | 8-Step Goal Planner + `ReasoningContext` + Tool Chaining | Decomposing multi-step pair-programming tasks into prerequisite DAGs, sequential tool actions, and verification checks without human micro-management. |

---

## 3. Detailed 100-Problem Benchmark Battery

### Category 01: Situational & Environmental Telemetry Deduction
*Tests the agent's ability to anchor on live workstation state (local time, UTC offset, OS, hardware) and compute situational real-world deductions.*

1. **`CAT01-01` (Timezone Delta Triangulation):** "My friend in London says it is currently 3:00 PM on their clock. Based on our workstation's current local time and UTC offset, what is the exact hour difference between us, and what time is it here?"
2. **`CAT01-02` (Day Boundary Rollover):** "A client says: 'It is 6:00 PM Sunday evening here.' Using our local clock and date, calculate the exact hour gap and deduce which general geographic timezone band they are located in."
3. **`CAT01-03` (Flight Arrival Local Reconciliation):** "A flight departs Singapore (UTC+8) on Tuesday at 23:45 and flies 13 hours and 30 minutes to London Heathrow (UTC+0). What is the local arrival day and time in London?"
4. **`CAT01-04` (VRAM Footprint & Model Fitting):** "We want to load a 14B Q8_0 GGUF model (estimated weights: 14.8 GB) with an 8,192 token context window (KV cache: ~1.2 GB). Based on our workstation's GPU and VRAM telemetry, can this fit entirely in VRAM without CPU offload?"
5. **`CAT01-05` (Quantization Tradeoff Deduction):** "Given our GPU specs, compare running a 32B model at Q4_K_M (~19.5 GB) versus Q8_0 (~34 GB). What hardware constraint makes one viable and the other impossible without offloading?"
6. **`CAT01-06` (Uptime vs. Incident Timeline):** "A teammate reports that a background build crashed 4 hours ago. Check our host workstation uptime. Did this machine boot before or after the reported crash?"
7. **`CAT01-07` (Local Subnet vs. Public Egress):** "Explain whether an IP address of `192.168.1.50` is our public egress location or a private LAN subnet, and how you distinguish between the two."
8. **`CAT01-08` (Platform Path & Binary Compatibility):** "We have a script targeting `/var/run/docker.sock`. Given that our host OS is Windows, explain how our Docker environment communicates with the host."
9. **`CAT01-09` (Thermal Load & Throttling Inference):** "If system telemetry shows GPU temperature at 88°C and core clock drops from 2400MHz to 1100MHz under load, deduce the physical symptom and its effect on compile times."
10. **`CAT01-10` (Multi-Timezone Meeting Anchor):** "Alice is in New York (UTC-4), Bob is in Tokyo (UTC+9), and we are at our current workstation offset. Propose a meeting time that falls between 9:00 AM and 6:00 PM for all three participants, or prove none exists."

---

### Category 02: Spatial, Kinematic & 3D Vector Simulation
*Tests the agent's ability to recognize the limits of neural attention and autonomously compile 3D transformations and vector kinematics into executable Python/numpy code.*

1. **`CAT02-01` (3D Drone Kinematics):** "A drone starts at coordinate (0, 0, 0) facing North (+y), East (+x), Up (+z). Execute in sequence: Forward 6m; Yaw 90° clockwise; Forward 4m; Pitch down 90°; Forward 3m; Roll 180°; Turn 90° local left; Forward 5m. What is its final (x, y, z) and pointing vector?"
2. **`CAT02-02` (2D Grid Obstacle Navigation):** "A robot starts at (1, 1) facing East. Grid contains obstacles at (3, 3) and (2, 4). Execute: Forward 3; Turn left; Forward 2; Turn left; Forward 1. Does the robot hit an obstacle? What is its final coordinate?"
3. **`CAT02-03` (Constant Velocity Intercept):** "Object A starts at (0, 100) moving with velocity (5, -2) m/s. Object B starts at (50, 0) moving with velocity (-2, 4) m/s. Do their paths cross, and if so, at what time and coordinate?"
4. **`CAT02-04` (Die Rolling & Opposite Face Deduction):** "A standard die has opposite faces summing to 7 (1 opposite 6, 2 opposite 5, 3 opposite 4). With 1 on top and 2 facing North, roll the die North once, then East once. What number is now on top?"
5. **`CAT02-05` (3D Ray-Sphere Intersection):** "A ray starts at origin (0, 0, 0) in direction (1, 1, 1)/sqrt(3). A sphere of radius 2 is centered at (5, 5, 5). Does the ray intersect the sphere? If so, at what distance from origin?"
6. **`CAT02-06` (Orbital Period & Centripetal Acceleration):** "A satellite orbits a planet at radius 8,000 km with constant speed 7 km/s. Calculate its orbital period in minutes and its centripetal acceleration in m/s²."
7. **`CAT02-07` (Orthographic Solid Reconstruction):** "A 3D solid's top view is a circle, front view is a triangle, and side view is a triangle. What is the geometric solid and its volume formula given base radius r and height h?"
8. **`CAT02-08` (Counterfactual Gravity Acceleration):** "In a universe where gravitational acceleration is $g(h) = 10 / (1 + 0.1h)$, an object is dropped from height $h = 20$m. Formulate the equation of motion and compute impact velocity."
9. **`CAT02-09` (3D Bounding Box Packing):** "Can 12 rectangular boxes of dimensions 2x3x4 be packed into a container of dimensions 6x6x8 without overlap? Provide the volume check and geometric proof."
10. **`CAT02-10` (Camera-to-World Frame Transform):** "A camera is at world position (0, -10, 5) tilted 30° downward toward origin. A target is detected at camera-relative coordinates (1, 2, 4). Compute its world coordinates."

---

### Category 03: Formal Constraint Logic Grids
*Tests the agent's ability to act as an NL-to-Constraint compiler, turning natural language clues into formal assertions (Z3 / CSP) rather than mentally dropping rules.*

1. **`CAT03-01` (The 4-House Logic Grid):** "Houses 1 to 4 arranged left to right. Colors: Blue, Green, Red, Yellow. Residents: Chef, Doctor, Engineer, Painter. Pets: Bird, Cat, Dog, Fish. Clues: 1. House 1 is Blue. 2. Doctor lives immediately left of Green. 3. Painter in House 3. 4. Dog in an odd house. 5. Engineer owns Cat. 6. Green is right of Red. 7. Yellow resident owns Bird. Determine the exact combination for each house."
2. **`CAT03-02` (Round-Robin Tournament Schedule):** "Four teams (A, B, C, D) play 3 rounds. Each team plays once per round. Team A cannot play Team B in Round 1. Team C plays Team D in Round 2. Construct the valid schedule."
3. **`CAT03-03` (Knights & Knaves Island):** "On an island, Knights always tell the truth and Knaves always lie. A says: 'B is a knave.' B says: 'A and C are of the same type.' C says: 'At least one of us is a knight.' What are A, B, and C?"
4. **`CAT03-04` (Conference Room Time Conflicts):** "Events 1, 2, 3, 4 require rooms. Event 1 (9-11), Event 2 (10-12), Event 3 (11-13), Event 4 (12-14). What is the minimum number of rooms needed so no events overlap in the same room?"
5. **`CAT03-05` (Job-Shop Precedence Scheduling):** "Tasks T1 (2h), T2 (3h), T3 (1h), T4 (2h). Precedences: T1 before T3; T2 before T3 and T4. With two parallel workers, what is the minimum completion time?"
6. **`CAT03-06` (Circular Table Seating):** "Six diplomats (A, B, C, D, E, F) sit around a circular table. A will not sit next to B. C must sit directly opposite D. E must sit next to A. Find a valid clockwise seating order."
7. **`CAT03-07` (Cryptarithmetic Invariant):** "Solve the base-10 addition: AB + BA = CDC, where each letter represents a distinct digit (0-9) and leading digits are non-zero. Find digits A, B, C, D."
8. **`CAT03-08` (Boolean Horn Clause Satisfiability):** "Given clauses: (P -> Q), (Q and R -> S), (not S), (P), (T -> R), (T). Is the system satisfiable? If not, identify the contradiction."
9. **`CAT03-09` (Conditional Negative Grid):** "Three employees (X, Y, Z) assigned to projects (Alpha, Beta, Gamma). Rule 1: If X is on Alpha, Y is not on Beta. Rule 2: Z is on Gamma if and only if X is on Beta. Rule 3: Y is on Alpha. Deduce the exact assignments."
10. **`CAT03-10` (Budget & Resource Optimization):** "Choose integer quantities of items X ($15, 4 weight) and Y ($20, 6 weight) to maximize total value under budget $100 and maximum weight 28. Provide the optimal bundle."

---

### Category 04: Closed-World Interval & Algebraic Word Problems
*Tests that closed-world word problems are shielded from epistemic workspace file searches, and evaluates exact multi-step algebraic manipulation.*

1. **`CAT04-01` (Temporal Event Interval Overlap):** "Events occurred on a single afternoon: Event A (13:00 to 15:30). Event D started when A ended, lasting 40m. Event B lasted half as long as D and finished 15m before A ended. Event C started when B started and finished when D finished. Event E started 10m before A ended and ended 15m after D started. 1. Exact start/end of B and C? 2. Gap or overlap between E and B? 3. Total timespan with active events?"
2. **`CAT04-02` (Market Shock Equilibrium):** "Supply: S = 2P + 10. Demand: D = 100 - 3P - 2T. Baseline T = 5. Shock: capacity capped at S = min(30, 2P + 10), price ceiling P <= 12, tax T = 10. 1. Resulting quantity supplied and demanded? 2. Shortage or surplus by how many units? 3. Causal effect of ceiling on traded volume?"
3. **`CAT04-03` (Latent Binary Operation Discovery):** "Discover binary operation f(a, b) from: f(2, 3) = 13; f(3, 4) = 25; f(4, 1) = 17; f(5, 2) = 29. State formula and compute f(6, 5)."
4. **`CAT04-04` (Exponential Radioactive Decay):** "Substance has half-life 4.5 hours. Initial mass 160 grams. What exact mass remains after 13.5 hours? How long until less than 5 grams remain?"
5. **`CAT04-05` (Coupled Rate-Time-Work):** "Worker A completes a job in 6 hours. Worker B completes it in 8 hours. Worker A works alone for 2 hours, then Worker B joins. How long does the entire job take?"
6. **`CAT04-06` (Cyclical Modular Sequence):** "Sequence defined by $x_{n+1} = (3x_n + 5) \pmod{11}$ with $x_0 = 2$. Find the period length and the value of $x_{1000}$."
7. **`CAT04-07` (Bayesian Medical Probability):** "Disease prevalence is 1%. Test has 95% sensitivity (true positive) and 5% false positive rate. If a patient tests positive, what is the exact posterior probability they have the disease?"
8. **`CAT04-08` (3-Variable Linear System):** "Solve for x, y, z: $2x + 3y - z = 1$; $4x - y + 2z = 16$; $x + 2y + 3z = 8$."
9. **`CAT04-09` (Allen's Interval Relation Deduction):** "Interval I1 takes place during [10, 20]. Interval I2 takes place during [15, 25]. Interval I3 takes place during [22, 30]. Formally state Allen relations: (I1, I2), (I2, I3), and (I1, I3)."
10. **`CAT04-10` (Tax Incidence & Deadweight Loss):** "Supply: P = Q. Demand: P = 120 - 2Q. A per-unit tax of $15 is placed on producers. Calculate: new equilibrium quantity, price paid by buyers, price received by sellers, and deadweight loss."

---

### Category 05: Web-Augmented Real-World Research
*Tests autonomous foraging for external knowledge via `search_web` and `fetch_url`, filtering noise, and speaking clean answers without raw URLs.*

1. **`CAT05-01` (Recent Technical Migration Guide):** "What was the major breaking architectural change in PyTorch 2.0 regarding graph compilation and `torch.compile`?"
2. **`CAT05-02` (Game Mechanics Wiki Lookup):** "In the game Elden Ring, what are the soft caps for the Vigor stat regarding HP scaling?"
3. **`CAT05-03` (Official Registry Fact Verification):** "Search official public records for the Court of Appeals in the Philippines: who was appointed as Presiding Justice in recent appointments?"
4. **`CAT05-04` (Hardware Architecture Specs):** "What is the key architectural difference between Intel Lion Cove P-cores and Skymont E-cores in Lunar Lake / Arrow Lake processors?"
5. **`CAT05-05` (Scientific Consensus / Phenomenon):** "What is the Cherenkov radiation threshold condition in water, and what produces its characteristic blue glow?"
6. **`CAT05-06` (Open Source License Invariants):** "Can code under the AGPLv3 license be incorporated into a proprietary SaaS product without releasing the proprietary server source code?"
7. **`CAT05-07` (Astronomical Calendar Events):** "When is the next total solar eclipse visible from North America, and what is the date of the next major Perseid meteor shower peak?"
8. **`CAT05-08` (Cross-Referencing Historical Dates):** "Did Ada Lovelace's translation and notes on Menabrea's Sketch of the Analytical Engine publish before or after Samuel Morse's first public telegraph demonstration?"
9. **`CAT05-09` (IETF Protocol RFC Semantics):** "According to RFC 9110, what is the exact semantic difference between HTTP 401 Unauthorized and HTTP 403 Forbidden?"
10. **`CAT05-10` (Multi-Source Conflicting Claim Resolution):** "Look up the maximum payload capacity of SpaceX Starship in reusable mode: verify why different sources cite 100t vs 150t vs 200t."

---

### Category 06: Defeasible Reasoning & Abductive Inference
*Tests reasoning to the best explanation from physical trace evidence, weighing default rules against defeaters (Walton schemes).*

1. **`CAT06-01` (Abductive Scene Deduction — Alice's Desk):** "Alice arrives at 09:00. Laptop is open with unsent email blinking mid-sentence. Half-full ceramic mug of coffee measures 34°C (ambient 21°C). Coat and bag on chair; car parked outside. Badge logs: entered at 07:45. Mandatory fire drill scheduled for 08:15 required immediate evacuation without personal items. Alice unseen since 08:15. What is the most plausible explanation for workstation state and whereabouts?"
2. **`CAT06-02` (Defeasible Specificity Defeater):** "Rule: Birds fly. Rule: Penguins are birds. Rule: Penguins do not fly. Fact: Opus is a penguin. Fact: Tweety is a bird. 1. Does Opus fly? 2. Does Tweety fly? 3. Explain which rule defeats which and why."
3. **`CAT06-03` (Hardware Symptom Diagnostic):** "Observed: GPU utilization is 99%, GPU temperature is 68°C, but game framerate drops from 120 FPS to 24 FPS whenever looking at a dense city scene. VRAM usage is 15.8 GB out of 16.0 GB. System RAM allocation is spiking. Abduce the root bottleneck."
4. **`CAT06-04` (Stack Trace Crash Abduction):** "Log: `SIGSEGV in thread 4 at address 0x00000000`. Thread 4 was executing `std::unique_ptr<Session>::operator->()`. Last logged message in thread 2: `SessionManager::invalidate(id)`. Abduce the software bug."
5. **`CAT06-05` (Argument from Expert Opinion Evaluation):** "Expert A (distinguished cryptographer) states Algorithm X is insecure due to side-channel leakage. Vendor B (selling Algorithm X) states Algorithm X passed FIPS-140 compliance. Using Walton's Critical Questions for Expert Opinion, evaluate which claim has higher epistemic weight."
6. **`CAT06-06` (Argument from Analogy):** "We argue: 'Just as database connection pools prevent connection exhaustion under spiky load, rate-limiting tokens prevent LLM API starvation.' Evaluate the strength of this analogy and identify one critical disanalogy."
7. **`CAT06-07` (Argument from Consequence):** "Proposal: 'Disable strict provenance HMAC signatures on memory records to speed up turn latency by 15ms.' Evaluate the consequence argument against the safety invariant."
8. **`CAT06-08` (Mystery Deduction with Missing Clue):** "A room has no windows and one locked door. Safe inside was opened without force. Three people possess the safe combination: Manager, Accountant, Guard. Guard was on camera in lobby. Accountant's electronic keycard was used on the door. Accountant claims keycard was stolen from desk 10 minutes prior. What are the two competing causal hypotheses?"
9. **`CAT06-09` (The Negative Sign / Dog That Didn't Bark):** "A server cluster experienced data corruption across 5 nodes. There are no kernel panic logs, no disk I/O errors, no power flickers, and ECC memory error counters are zero. What does the absence of hardware logs imply about the level of the failure (hardware vs. application software)?"
10. **`CAT06-10` (Defeasible Obligation Conflict):** "Rule 1: As a companion engineer, always execute file cleanup when requested. Rule 2: Never delete system root files or databases without backup. User commands: 'Delete all files in C:\\ProjectLucca\\data to free space.' Resolve the conflict."

---

### Category 07: Theory of Mind & Strategic Game Theory
*Tests tracking 2nd-order nested beliefs and strategic decision-making under information asymmetry.*

1. **`CAT07-01` (Kitchen Chocolate 2nd-Order Belief):** "Mia places chocolate in Blue Cabinet in full view of Leo and Sam. Mia leaves. Leo moves chocolate to Green Drawer (Sam watches). Leo leaves. Sam moves chocolate to Red Pantry (unseen by Mia and Leo). Neither spoke. 1. Where does Leo believe chocolate is? 2. Where does Leo believe Mia thinks it is? 3. Where does Sam believe Leo thinks it is? 4. Where will Mia look first?"
2. **`CAT07-02` (First-Price Auction & Winner's Curse):** "Asset value V is $10M or $30M (50% each). Bidder A knows true V. Bidder B knows only the distribution, but knows A is informed. Bidder B bids $11M. 1. What will A bid if V=$10M? 2. What will A bid if V=$30M? 3. Expected payoff for B from bidding $11M? 4. What fundamental game-theoretic mistake did B commit?"
3. **`CAT07-03` (Vickrey 2nd-Price Auction Dominant Strategy):** "In a second-price sealed-bid auction, prove why bidding exactly your true valuation $v_i$ is a weakly dominant strategy, regardless of what competitors bid."
4. **`CAT07-04` (3rd-Order Recursive Perspective):** "Alice told Bob a secret. Bob promised not to tell Charlie. Bob told Charlie anyway, but made Charlie promise not to let Alice know he knows. Charlie accidentally leaves a related note where Alice finds it. Does Alice know that Charlie knows? Does Charlie know that Alice knows?"
5. **`CAT07-05` (Signaling Game & Costly Signals):** "In an employment market, high-ability workers have cost of education $C_H = 5$, low-ability workers have cost $C_L = 10$. Employers pay wage 100 for college degree, 50 without. Explain why education serves as a separating signal even if it teaches zero productive skills."
6. **`CAT07-06` (Muddy Children Common Knowledge):** "Three children (A, B, C) all have mud on their foreheads. Each can see the others' foreheads, but not their own. Father announces: 'At least one of you has mud on your forehead.' Father asks repeatedly: 'Do you know if you have mud on your forehead?' What do the children answer on Round 1, Round 2, and Round 3?"
7. **`CAT07-07` (Collaborative Debugging Epistemic Gap):** "The user says: 'The server script crashed because Python 3.12 is missing.' You inspect the system and find Python 3.12 is installed, but the virtual environment was deactivated. Model the user's belief, explain the root cause, and address the gap constructively."
8. **`CAT07-08` (Iterated Prisoner's Dilemma & Tit-for-Tat):** "In an infinitely repeated Prisoner's Dilemma with discount factor $\delta = 0.9$, prove why Tit-for-Tat is an equilibrium against a defecting strategy."
9. **`CAT07-09` (Poker Bluffing with Asymmetric Cards):** "Player 1 has either a Nut Hand (50%) or a Bluff (50%). Player 2 has a Medium Hand. Pot is $100. Player 1 bets $100. What is Player 2's pot odds, and what minimum bluffing frequency makes Player 2 indifferent between calling and folding?"
10. **`CAT07-10` (Stag Hunt Coordination Dilemma):** "Two hunters can choose Stag (payoff 10 if both choose Stag, 0 if only one) or Hare (payoff 3 regardless). What are the two pure Nash equilibria? Which is payoff-dominant, and which is risk-dominant?"

---

### Category 08: Autobiographical Memory & Hard-Purge Isolation
*Tests the integrity of memory lifecycle, fact synthesis, belief revision, and the hard-purge barrier against ghost data leaks.*

1. **`CAT08-01` (User Preference Retention):** "Turn 1: 'My favorite programming language is Rust, and I prefer concise docstrings.' Turn 2: General coding banter. Turn 3: 'What is my preferred language and docstring style?'"
2. **`CAT08-02` (Autonomous Belief Revision):** "Turn 1: 'My cat is named Pixel.' Turn 2: 'Actually, I made a typo earlier—my cat's name is Pixelbyte.' Turn 3: 'What is my cat's name?' (Must state Pixelbyte and acknowledge the revision)."
3. **`CAT08-03` (Case-Based Precedent Recall):** "Turn 1: Diagnose a specific bug: 'When running webpack on Node 20, error code ENOSPC was resolved by increasing fs.inotify.max_user_watches.' Turn 2: 5 turns later: 'We are getting ENOSPC again on node watcher, what solved this last time?'"
4. **`CAT08-04` (Multi-Turn Fact Synthesis):** "Turn 1: 'Project Orion is managed by Marcus.' Turn 2: 'Marcus reports to Director Alvarez.' Turn 3: 'Who is the Director overseeing the manager of Project Orion?'"
5. **`CAT08-05` (Temporal Memory Metadata):** "Turn 1: Record a fact about a deployment date. Turn 2: 'When did we discuss the deployment date?' (Must cite session/timestamp relative to local clock)."
6. **`CAT08-06` (Honest Memory Abstention):** "'Do you remember what movie I watched last night?' (Zero records in DB; must answer with calibrated honest abstention without hallucinating)."
7. **`CAT08-07` (THE HARD-PURGE BARRIER — Zero Ghost Leaks):** "1. Teach a unique secret: 'The deployment secret code is CRIMSON-OCTOBER-99.' 2. Verify recall. 3. Execute `factory_reset_memories` with hard purge. 4. Query: 'What is the deployment secret code?' 5. Assert: Must return unknown, and database query across `memories`, `kg_entities`, `decisions`, and `fts` must yield exactly ZERO hits."
8. **`CAT08-08` (Knowledge Graph Integrity):** "Assert that creating an entity fact, modifying it, and deleting it updates both `memories` and `kg_entities`/`kg_edges` synchronously without orphaned edges."
9. **`CAT08-09` (Grounding Eligibility Distinction):** "Verify that an `ASSISTANT_UTTERANCE` (speculative claim) is marked non-grounding in provenance, whereas `USER_EXPLICIT` and `ASSISTANT_ACTION` tool receipts are grounding-eligible."
10. **`CAT08-10` (Contradictory Memory Belnap TOP Handling):** "Two conflicting records exist with equal confidence (Fact A: 'Server runs on port 8080'; Fact B: 'Server runs on port 9000'). Query port: Must detect Belnap TOP (conflict) and report the discrepancy rather than arbitrarily guessing."

---

### Category 09: Meta-Cognitive Diagnostic Self-Reasoning
*Tests Lucca's ability to inspect her own operational telemetry, latency traces, peer heartbeats, and tool receipts to diagnose performance and failures.*

1. **`CAT09-01` (Turn Latency Breakdown):** "'Why did your last response take so long?' (Inspects `TurnTrace`: separates audio ASR time, prompt pre-fill, generation TTFT, tool execution ms, and Kokoro synthesis ms)."
2. **`CAT09-02` (VRAM Saturation Audit):** "'How much VRAM is currently allocated, and how much headroom do we have before out-of-memory?'"
3. **`CAT09-03` (Audio Dropout & Queue Health):** "'My audio just crackled and cut out for a second. What caused that?' (Checks audio buffer underruns, packet drop count, and worker thread priority)."
4. **`CAT09-04` (WSL2 Docker Sandbox Liveness):** "'Is the Docker execution sandbox healthy and running?' (Executes heartbeat/container inspect and reports container status)."
5. **`CAT09-05` (Peer Process Heartbeat Audit):** "'Run a diagnostic check on your supervisor peer processes.' (Reports status of `audio`, `npu`, `ui`, and supervisor sockets)."
6. **`CAT09-06` (Tool Failure Root Cause Introspection):** "After a simulated tool crash: 'Why did that tool call fail?' (Inspects exit code, stderr, and schema validation error rather than guessing)."
7. **`CAT09-07` (Cognitive Bus Rule Audit):** "'Did any active or shadow heuristic rules fire during the last turn?' (Inspects `current_turn_shadow_outcomes` and rule engine trace)."
8. **`CAT09-08` (Proof Trace & Evidential Standard):** "'What standard of proof supports your last assertion?' (Inspects `ReasoningContext` proof trace: Scintilla, Preponderance, Clear & Convincing, or Beyond Reasonable Doubt)."
9. **`CAT09-09` (Context Window Budget Consumption):** "'How many tokens have we consumed in our current context window, and how close are we to the 16K limit?'"
10. **`CAT09-10` (Autonomous Self-Repair Suggestion):** "'The system feels sluggish. What is the recommended remediation?' (Evaluates cache fragmentation, memory leak indicators, and suggests process reboot or prefix cache flush)."

---

### Category 10: Means-Ends Practical Goal Planning
*Tests multi-step action decomposition, prerequisite dependency sequencing, and autonomous tool chaining without hand-holding.*

1. **`CAT10-01` (3-Step Tool Chaining DAG):** "'Inspect `src/lucca/core/config.py`, locate the `max_tokens` field, and verify its current default value.' (Chains `read_file` -> string inspection -> verbal report)."
2. **`CAT10-02` (Prerequisite Enforcement):** "'Execute this Python test script, but only after confirming that the virtual environment is active and pytest is installed.' (Sequences prerequisite check -> execution)."
3. **`CAT10-03` (Rollback on Intermediate Failure):** "Execute a 3-step refactoring plan: 1. Backup file. 2. Apply patch. 3. Run validation. If step 3 fails, restore backup automatically and report the rollback."
4. **`CAT10-04` (Autonomous Multi-File Discovery):** "'Find all files in `src/` that import `EpistemicSubstrate` and summarize how each uses it.' (Grep search -> file read -> structured synthesis)."
5. **`CAT10-05` (Test-Driven Bug Fix Workflow):** "'We have a bug in `test_json_repair.py`. Reproduce it by running the script, explain the failure, and formulate the fix.'"
6. **`CAT10-06` (Environment Verification Workflow):** "'Verify our complete pair-programming toolchain: check git, python, uv, docker, and nvidia-smi in sequence and give a unified status report.'"
7. **`CAT10-07` (Benchmark Execution & Metric Harvest):** "'Run the sandbox latency benchmark, extract median and p95 timings, and compare them against our SLA target (<50ms).'"
8. **`CAT10-08` (Workspace Cleanliness & Hygiene Audit):** "'Scan the workspace for temporary scratch files, untracked logs, and cache artifacts, and list what can be safely cleaned.'"
9. **`CAT10-09` (Multi-Query Research Compilation):** "'Research the difference between Belnap 4-valued logic and Ginsberg bilattices: search both terms, extract formal definitions, and contrast them.'"
10. **`CAT10-10` (Deployment Readiness Gate Checklist):** "'Execute the production release checklist: check git branch, assert clean working tree, verify all unit tests pass, and report release readiness.'"

---

## 4. Benchmark Execution Harness Architecture

The benchmark runner will be implemented in `tests/test_compound_reasoning_benchmark.py`:
- **Execution Mode**: Direct synchronous invocation of `orch.turn_pipeline.run_turn(TurnInput(text=prompt, mode="transcript"))`.
- **Scoring Dimensions**:
  1. *Substrate & Tool Selection Accuracy* (Did it select the right tool / bypass file cascade appropriately?)
  2. *Ground-Truth Solution Accuracy* (Exact numerical, logical, or deductive correctness)
  3. *Zero-Ghost-Leak Invariant* (Zero bleeding across hard-purge barriers)
  4. *Anti-Lecture Compliance* (Did it answer/execute directly without multi-paragraph lecturing?)
- **Reporting**: Full structured JSON output with per-category pass rates, latencies, and tool trace logs.
