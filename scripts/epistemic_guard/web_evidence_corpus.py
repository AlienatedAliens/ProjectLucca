"""Strictly disjoint open-web (query, passage) training & validation corpus generator.

Generates 3-class `(query, passage, label)` examples for `web_evidence_int8`:
  - 0: CORROBORATES (on-topic factual support, including agreeing safety prohibitions)
  - 1: IRRELEVANT   (bot-wall stubs, SEO TOC blurbs, entity-swap tangents, off-topic pages)
  - 2: DISPUTES     (myth/misconception refutations, active scientific debates, contradictions)

Enforces 0 normalized query overlap and 0 6-token shingle query overlap against all
locked/benchmark web corpora (`WEB360`, `WEB60`, `real_web_v1`, `real_web_v2`, `R33`).
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Final

WEB_EVIDENCE_LABELS: Final[tuple[str, ...]] = ("CORROBORATES", "IRRELEVANT", "DISPUTES")

# Domain-diverse seed facts authored strictly from general technical/scientific knowledge
# with zero consultation of any locked benchmark queries.
_FACT_SEEDS: Final[list[tuple[str, str, str, str]]] = [
    # (query, corroborating_passage, entity_swap_tangent, dispute_passage)
    (
        "What orbital period does Jupiter's moon Io complete around Jupiter?",
        "Io completes one full orbit around Jupiter every 42.46 hours (1.769 Earth days), locked in a 4:2:1 Laplace resonance with Europa and Ganymede.",
        "Saturn's moon Enceladus vents water-ice plumes from tiger-stripe fractures near its south polar terrain.",
        "Early nineteenth-century visual estimates of Io's rotation were later refuted by spacecraft radiometry, showing synchronous tidal locking rather than rapid independent spin.",
    ),
    (
        "Which crystal structure does pure alpha-iron adopt at room temperature?",
        "At room temperature and standard atmospheric pressure, pure alpha-iron (ferrite) crystallizes in a body-centered cubic (BCC) lattice below 912 degrees Celsius.",
        "Pure copper crystallizes in a face-centered cubic lattice with high electrical conductivity across annealed busbars.",
        "Claims that room-temperature ferrite retains face-centered cubic symmetry without alloying elements have been refuted by X-ray diffraction measurements.",
    ),
    (
        "What default TCP port is assigned to the PostgreSQL wire protocol?",
        "PostgreSQL database servers listen on IANA-registered TCP port 5432 by default for frontend/backend v3 wire protocol connections.",
        "MySQL server instances bind to TCP port 3306 by default when accepting client authentication handshakes.",
        "A circulated setup guide claiming PostgreSQL defaults to port 1521 is inaccurate; port 1521 belongs to Oracle Net Listener.",
    ),
    (
        "Why must sodium hypochlorite cleaners never be combined with hydrochloric acid descalers?",
        "Sodium hypochlorite must never be mixed with hydrochloric acid toilet descalers because protonation of hypochlorite ions immediately liberates toxic chlorine gas.",
        "Sodium bicarbonate paste gently scours enameled cast-iron cookware without scratching vitrified glaze surfaces.",
        "Household cleaning blogs claiming acidic vinegar safely boosts chlorine bleach detergency have been debunked by poison control toxicology advisories.",
    ),
    (
        "Why is intravenous potassium chloride never administered as a rapid undiluted bolus?",
        "Undiluted intravenous potassium chloride must never be pushed as a rapid bolus because abrupt hyperkalemia causes fatal cardiac conduction arrest; infusion requires controlled dilution.",
        "Intravenous normal saline (0.9% sodium chloride) is routinely infused for isotonic extracellular volume resuscitation.",
        "Informal study notes suggesting concentrated potassium ampoules can be injected directly into peripheral lines are dangerous and contradicted by hospital safety standards.",
    ),
    (
        "Why should rifampin not be co-administered with direct oral protease inhibitors without dose review?",
        "Rifampin potently induces hepatic CYP3A4 enzymes and must not be co-administered with boosted protease inhibitors because plasma antiviral trough levels drop precipitously.",
        "Topical mupirocin ointment treats localized impetigo lesions with minimal systemic hepatic metabolism.",
        "Claims that rifampin has negligible interaction with CYP3A4 substrates have been refuted by pharmacokinetic crossover studies.",
    ),
    (
        "What HTTP status code signals permanent redirect while preserving the original request method?",
        "RFC 9110 defines HTTP status code 308 Permanent Redirect to indicate that the target resource has moved permanently and user agents must not change POST to GET.",
        "HTTP status code 206 Partial Content enables byte-range streaming of large video archives over CDN edges.",
        "Tutorials stating that HTTP 301 guarantees preservation of POST request bodies are contradicted by browser implementations and RFC 9110.",
    ),
    (
        "How many bytes make up an uncompressed Ed25519 signature?",
        "An RFC 8032 Ed25519 signature always occupies exactly 64 bytes (512 bits), concatenating the 32-byte encoded curve point R and the 32-byte scalar S.",
        "An uncompressed secp256r1 ECDSA public key requires 65 bytes when prefixed with the 0x04 uncompressed point tag.",
        "Assertions that standard Ed25519 signatures shrink to 32 bytes without batch aggregation are false; 32 bytes is the public key size, not the signature.",
    ),
    (
        "Which enzyme catalyzes carbon fixation in the C3 Calvin cycle?",
        "Ribulose-1,5-bisphosphate carboxylase/oxygenase (RuBisCO) catalyzes the primary carboxylation step of the C3 Calvin-Benson cycle in chloroplast stroma.",
        "DNA gyrase introduces negative supercoils into circular bacterial chromosomes ahead of replication forks.",
        "Whether engineered cyanobacterial RuBisCO variants reliably increase open-field wheat yield remains actively debated across conflicting agronomic trials.",
    ),
    (
        "What melting point is defined for pure gallium at standard pressure?",
        "Pure elemental gallium melts at 29.76 degrees Celsius (85.57 degrees Fahrenheit), allowing solid ingots to liquefy slightly above room temperature.",
        "Elemental tungsten exhibits the highest melting point of pure metals at 3,422 degrees Celsius in vacuum filaments.",
        "Viral videos claiming pure gallium spontaneously boils in warm tap water are staged hoaxes; gallium's boiling point exceeds 2,200 degrees Celsius.",
    ),
    (
        "Why must lithium metal fires never be extinguished with standard water hoses?",
        "Burning metallic lithium reacts exothermically with water to generate flammable hydrogen gas and caustic lithium hydroxide; Class D dry powder agents are required instead.",
        "Deep-cycle lead-acid marine batteries use dilute sulfuric acid electrolyte between lead dioxide plates.",
        "Advice treating metallic lithium ribbon fires identically to lithium-ion electrolyte cooling is disputed by industrial fire protection standards.",
    ),
    (
        "Which register holds the stack pointer in 64-bit x86-64 System V ABI?",
        "Under the x86-64 System V AMD64 ABI, hardware register RSP serves as the 64-bit stack pointer and must remain 16-byte aligned prior to CALL instructions.",
        "In 32-bit ARMv7 Thumb code, register R14 acts as the link register storing subroutine return addresses.",
        "Forum posts claiming RBP is mandatory as a frame pointer in every leaf function under -O2 optimization are contradicted by System V ABI specifications.",
    ),
    (
        "What wavelength corresponds to the hydrogen 21-centimeter hyperfine radio line?",
        "Neutral atomic hydrogen emits radiation at a rest frequency of 1420.405 MHz, corresponding to a vacuum wavelength of 21.106 centimeters from spin-flip transitions.",
        "Sodium vapor street lamps emit prominent yellow-orange doublet lines near 589.0 and 589.6 nanometers.",
        "Early hypotheses that interstellar dust completely blocks 21-centimeter neutral hydrogen emission across the galactic plane were refuted by radio telescope surveys.",
    ),
    (
        "Why are fluoroquinolone antibiotics avoided as routine first-line therapy for uncomplicated sinusitis?",
        "Regulatory safety warnings advise against routine fluoroquinolone use in uncomplicated acute bacterial sinusitis due to disabling tendinopathy and peripheral neuropathy risks.",
        "Saline nasal irrigation clears mucociliary debris without systemic antimicrobial exposure.",
        "Whether short-course systemic corticosteroids meaningfully accelerate symptom resolution in acute sinusitis remains contested across clinical trials.",
    ),
    (
        "Which hashing construction underpins the Argon2id password-hashing function?",
        "Argon2id combines data-independent memory addressing in its first half-pass with data-dependent addressing afterward, using the internal Blake2b compression primitive.",
        "HMAC-SHA512 constructs a keyed message authentication code from two nested SHA-512 compression passes.",
        "Claims that unsalted fast SHA-256 hashes provide equivalent GPU cracking resistance to memory-hard Argon2id are refuted by NIST SP 800-63B guidance.",
    ),
    (
        "What salinity threshold distinguishes freshwater lakes from marine seawater?",
        "Open ocean seawater averages roughly 35 parts per thousand (3.5%) dissolved salts, whereas freshwater lakes contain less than 0.5 parts per thousand dissolved solids.",
        "Subglacial Lake Vostok lies beneath four kilometers of East Antarctic ice sheet overburden.",
        "Competing paleoclimate models still debate how rapidly Mediterranean Messinian salinity crisis basins refilled during the Zanclean flood.",
    ),
    (
        "How many semitones span a perfect fifth in twelve-tone equal temperament?",
        "In twelve-tone equal temperament, a perfect fifth spans exactly seven semitones, corresponding to a frequency ratio of 2^(7/12), or approximately 1.4983.",
        "Concert timpani kettles adjust pitch via foot-pedal tension rings across calfskin or Mylar heads.",
        "The belief that twelve-tone equal temperament produces beatless pure-integer 3:2 fifths is a common musical misconception.",
    ),
    (
        "Why must live mains electrical panels never be probed with unrated multimeter leads?",
        "Unrated bench test leads must never probe live distribution panels because arc-flash transients can ionize air across inadequate insulation; CAT III or CAT IV rated meters are mandatory.",
        "Low-voltage breadboard jumper wires carry 3.3-volt logic signals between microcontroller GPIO pins.",
        "Claims that wrapping vinyl tape around frayed multimeter probes restores CAT IV arc-flash protection are false and violate IEC 61010 safety rules.",
    ),
    (
        "What consensus algorithm coordinates leader election in etcd clusters?",
        "Distributed etcd key-value stores replicate state log entries and elect a single leader using the Raft consensus algorithm across odd-numbered voter quorums.",
        "Memcached shards ephemeral cache keys across client-side consistent hashing rings without disk persistence.",
        "Claims that two-node etcd clusters improve fault tolerance over a single node are a persistent distributed-systems myth because quorum requires two live nodes.",
    ),
    (
        "Which vitamin deficiency precipitates Wernicke encephalopathy in chronic malabsorption?",
        "Severe thiamine (vitamin B1) deficiency precipitates acute Wernicke encephalopathy, classically presenting with oculomotor dysfunction, ataxia, and confusion.",
        "Ascorbic acid (vitamin C) serves as an essential cofactor for prolyl hydroxylase during collagen triple-helix synthesis.",
        "Administering intravenous dextrose before thiamine in severely malnourished patients is contraindicated because glucose metabolism acutely depletes remaining thiamine reserves.",
    ),
    (
        "What maximum transmission unit (MTU) applies to standard untagged Ethernet II frames?",
        "Standard IEEE 802.3 Ethernet II frames carry a maximum Layer-3 IP payload MTU of 1,500 octets excluding the 14-byte header and 4-byte FCS.",
        "InfiniBand HDR fabrics route RDMA queue-pair completions across low-latency cut-through switches.",
        "Whether enabling 9,000-byte jumbo frames improves throughput on mixed WAN links remains debated because PMTUD blackholes frequently degrade TCP performance.",
    ),
    (
        "Why should isotretinoin never be prescribed alongside tetracycline-class antibiotics?",
        "Oral isotretinoin must never be combined with doxycycline or minocycline because both agents synergistically elevate the risk of pseudotumor cerebri (idiopathic intracranial hypertension).",
        "Topical benzoyl peroxide washes oxidize follicular Propionibacterium acnes populations without inducing bacterial resistance.",
        "Online skincare forums claiming low-dose doxycycline safely prevents isotretinoin flares are contradicted by dermatology black-box warnings.",
    ),
    (
        "Which geological epoch immediately preceded the Holocene?",
        "The Pleistocene epoch immediately preceded the Holocene, spanning from approximately 2.58 million years ago until 11,700 years before present.",
        "Ordovician marine strata preserve abundant trilobite and graptolite index fossils in shale beds.",
        "Stratigraphers debated for years whether to formalize a separate Anthropocene epoch, and the International Union of Geological Sciences voted against ratifying the proposal.",
    ),
    (
        "What bit length is used by IPv6 unicast and multicast network addresses?",
        "Every IPv6 address defined in RFC 8200 consists of 128 bits, conventionally formatted as eight colon-separated groups of four hexadecimal digits.",
        "IEEE 802.11ax Wi-Fi access points schedule orthogonal frequency-division multiple access resource units.",
        "Claims that IPv6 eliminates the need for transport-layer TLS encryption are a misconception; IPsec support does not automatically encrypt application sockets.",
    ),
    (
        "Why must cast-iron brake rotors not be lubricated with petroleum grease on friction faces?",
        "Applying grease or oil to brake rotor friction surfaces destroys pad-to-disc friction coefficient and causes severe braking loss; rotors must be cleaned with residue-free solvent.",
        "Silicone caliper slide-pin lubricant protects rubber dust boots on floating brake brackets.",
        "Folk tips suggesting light oil stops brake squeal without increasing stopping distance have been debunked by automotive safety testing.",
    ),
    (
        "Which organelle houses the oxidative phosphorylation electron transport chain in eukaryotes?",
        "In eukaryotic cells, the electron transport chain complexes I through IV and ATP synthase reside embedded within the folded inner mitochondrial membrane (cristae).",
        "Golgi apparatus cisternae modify N-linked oligosaccharide chains on secreted glycoproteins.",
        "Whether mitochondrial reactive oxygen species act primarily as toxic aging drivers or adaptive mitohormesis signals remains contested in longevity research.",
    ),
    (
        "What exit code convention indicates successful command termination on POSIX shells?",
        "On POSIX-compliant Unix and Linux systems, process exit status 0 indicates successful execution, whereas non-zero values (1 through 255) indicate errors or signals.",
        "POSIX symbolic links store target path strings inside inode metadata entries.",
        "Beginners often confuse C boolean truthiness with POSIX shell exit codes, falsely assuming return code 1 means success in bash conditionals.",
    ),
    (
        "Why is raw kidney bean flour unsafe to eat without boiling?",
        "Raw red kidney beans contain high concentrations of phytohaemagglutinin lectin, which causes severe vomiting and enteritis unless destroyed by brisk boiling for at least ten minutes.",
        "Rolled oats soften rapidly in overnight cold milk preparations without lectin toxicity.",
        "Slow-cooker recipes claiming 75-degree-Celsius simmering neutralizes kidney bean phytohaemagglutinin are dangerous; sub-boiling temperatures can increase toxicity fivefold.",
    ),
    (
        "What cryptographic curve is standardized for WireGuard key exchange?",
        "WireGuard VPN tunnels perform Diffie-Hellman key agreement exclusively over Curve25519 (X25519), paired with ChaCha20-Poly1305 authenticated encryption and BLAKE2s hashing.",
        "OpenSSH certificates bind host public keys to principal names signed by a cluster CA key.",
        "Claims that WireGuard negotiates cipher suites dynamically via TLS handshakes are false; WireGuard uses a fixed Noise_IK cryptographic construction.",
    ),
    (
        "Which gas makes up the largest volume fraction of Titan's atmosphere?",
        "Molecular nitrogen (N2) comprises roughly 94% to 98% of Saturn's moon Titan's dense stratosphere, supplemented by methane and trace hydrocarbons.",
        "Venus's super-rotating atmosphere consists of 96.5% carbon dioxide beneath sulfuric acid cloud decks.",
        "Whether transient mid-infrared brightening on Titan reflects active cryovolcanism or seasonal methane cloud convection remains debated among planetary scientists.",
    ),
]

# Additional domain seeds for rich lexical breadth across all 3 classes
_EXTRA_SEEDS: Final[list[tuple[str, str, str, str]]] = [
    (
        "What HTTP header prevents browsers from MIME-sniffing a response away from Content-Type?",
        "Setting the response header X-Content-Type-Options: nosniff instructs browsers not to override the declared Content-Type via payload MIME-sniffing.",
        "The Cache-Control: immutable directive tells browsers not to revalidate versioned static assets before expiry.",
        "Claims that X-Frame-Options blocks cross-site script MIME-sniffing are inaccurate; X-Frame-Options only governs iframe clickjacking.",
    ),
    (
        "Why must nitroglycerin tablets never be taken within 24 hours of sildenafil?",
        "Co-administering organic nitrates such as nitroglycerin with PDE5 inhibitors like sildenafil is strictly contraindicated because synergistic cGMP accumulation causes life-threatening hypotension.",
        "Sublingual cyanocobalamin lozenges supplement vitamin B12 stores in pernicious anemia.",
        "Assertions that spacing sildenafil and sublingual nitroglycerin by two hours eliminates hypotensive shock risk are refuted by cardiology guidelines.",
    ),
    (
        "What SQLite PRAGMA enables concurrent readers alongside an active writer?",
        "Executing PRAGMA journal_mode=WAL switches SQLite from rollback journaling to write-ahead logging, allowing concurrent readers while one writer appends frames.",
        "SQLite's VACUUM command rebuilds the database file to reclaim free pages after bulk deletes.",
        "Blog posts claiming SQLite WAL mode supports multi-host NFS network filesystems safely are false; WAL requires shared-memory mmap on a single host.",
    ),
    (
        "Which physical constant links photon energy directly to electromagnetic frequency?",
        "Planck's constant h (exact SI value 6.62607015e-34 joule-seconds) relates a photon's energy E to its frequency nu through E = h * nu.",
        "Avogadro's constant defines the exact number of elementary entities per mole of substance.",
        "Claims that photon rest mass accounts for radiation pressure in solar sails are a physics myth; massless photons carry momentum E/c.",
    ),
    (
        "Why should aluminum cookware not be soaked overnight in concentrated lye solutions?",
        "Concentrated sodium hydroxide (lye) aggressively dissolves amphoteric aluminum metal while liberating flammable hydrogen gas; never soak aluminum parts in caustic soda.",
        "Austenitic 316 stainless steel resists pitting corrosion in marine chloride environments.",
        "Workshop tips recommending caustic drain opener to degrease cast-aluminum engine blocks have been debunked after causing severe dimensional etching.",
    ),
    (
        "What worst-case time complexity characterizes binary heap insertion?",
        "Inserting an element into a binary min-heap or max-heap takes O(log n) worst-case time via upward sift-up swaps along tree height.",
        "Breadth-first search traverses unweighted adjacency lists in O(V + E) linear time.",
        "Claims that building a binary heap from an unsorted array requires O(n log n) minimum comparisons via Floyd's bottom-up heapify are incorrect; Floyd's algorithm runs in O(n).",
    ),
    (
        "Why is methylene blue contraindicated in patients with G6PD deficiency?",
        "Methylene blue must not be administered to G6PD-deficient patients because NADPH depletion prevents leukomethylene blue conversion and triggers acute Heinz-body hemolytic anemia.",
        "Oral ferrous sulfate replenishes iron stores over three months in microcytic iron-deficiency anemia.",
        "Reports suggesting higher doses of methylene blue overcome refractory methemoglobinemia in G6PD deficiency are contradicted by hematology toxicology alerts.",
    ),
    (
        "Which alloy serves as the historic international prototype cylinder for mass standards?",
        "Before the 2019 SI redefinition, the International Prototype of the Kilogram was machined from a 90% platinum, 10% iridium alloy cylinder stored at Sevres.",
        "Invar-36 nickel-iron alloy exhibits near-zero thermal expansion in precision pendulum clocks.",
        "The belief that the kilogram is still legally defined by a physical platinum-iridium cylinder in France is outdated since the 2019 Planck-constant redefinition.",
    ),
    (
        "What TLS version deprecated all static RSA key-transport cipher suites?",
        "TLS 1.3 (RFC 8446) completely removed static RSA key transport and mandated ephemeral Diffie-Hellman (ECDHE or DHE) for forward secrecy on every handshake.",
        "DNSSEC signs zone resource record sets using RRSIG and DNSKEY records to authenticate origin authority.",
        "Claims that TLS 1.3 breaks corporate passive RSA private-key packet decryption appliances by accident rather than deliberate forward-secrecy design are historically inaccurate.",
    ),
    (
        "Why must dry ice never be sealed inside an airtight glass or plastic bottle?",
        "Sublimating solid carbon dioxide expands nearly 800-fold into gas at room temperature; sealing dry ice in a rigid airtight container builds pressure past burst limits and causes shrapnel explosions.",
        "Insulated Dewar flasks vent boil-off nitrogen vapor safely through loose-fitting foam stoppers.",
        "Party tricks advising screw-cap soda bottles for dry-ice fog effects are condemned by university lab safety manuals due to severe blast injuries.",
    ),
    (
        "Which cranial nerve provides parasympathetic vagal innervation to thoracic and abdominal viscera?",
        "Cranial nerve X, the vagus nerve, carries efferent parasympathetic fibers from the medulla oblongata to cardiac, pulmonary, and upper gastrointestinal organs.",
        "Cranial nerve II, the optic nerve, transmits retinal ganglion axons through the optic chiasm.",
        "Commercial wellness claims that transcutaneous ear-clip buzzers cure autoimmune disorders via vagus nerve reset remain unproven and contested in clinical neurology.",
    ),
    (
        "What atomic number identifies technetium as the lightest element with no stable isotopes?",
        "Technetium has atomic number 43 and possesses zero stable isotopes; every technetium nuclide undergoes radioactive decay, making 99mTc valuable in nuclear medicine imaging.",
        "Zirconium (atomic number 40) forms low-neutron-capture cladding tubes in pressurized water reactors.",
        "Nineteenth-century announcements of stable terrestrial 'masurium' isolation were disputed and largely invalidated before Perrier and Segre confirmed synthetic element 43.",
    ),
    (
        "Why must warfarin dosing be monitored closely when starting trimethoprim-sulfamethoxazole?",
        "Trimethoprim-sulfamethoxazole inhibits CYP2C9 metabolism of S-warfarin and displaces protein binding, sharply elevating INR and major bleeding risk unless warfarin is reduced.",
        "Inhaled albuterol relaxes bronchial smooth muscle via beta-2 adrenergic receptors during acute bronchospasm.",
        "Claims that topical antibiotic creams carry identical CYP2C9 warfarin elevation risk to oral cotrimoxazole are exaggerated and unsupported by coagulation studies.",
    ),
    (
        "What HTTP response status code indicates rate limiting by an API gateway?",
        "RFC 6585 defines HTTP status code 429 Too Many Requests to indicate that the client has exceeded allowed request rate quotas within a time window, often accompanied by Retry-After.",
        "HTTP 204 No Content signals that a DELETE or PUT request succeeded with an empty response body.",
        "Using HTTP 503 Service Unavailable interchangeably with per-user rate limits is disputed in API design specifications because 503 implies upstream server outage.",
    ),
    (
        "Why should unpasteurized honey or raw milk be avoided in severely immunocompromised transplant recipients?",
        "Transplant infectious-disease protocols advise avoiding raw unpasteurized milk due to Listeria monocytogenes, Campylobacter, and Brucella bloodstream infection hazards.",
        "Ultra-high-temperature (UHT) milk is heated above 135 degrees Celsius for two to five seconds before aseptic packaging.",
        "Claims that raw unpasteurized milk retains active enzymes that cure lactose intolerance were refuted by randomized Stanford crossover trials.",
    ),
]

_STUB_TEMPLATES: Final[list[str]] = [
    "Just a moment... Checking your browser before accessing {slug}. Enable JavaScript and cookies to continue.",
    "403 Forbidden — Access to this resource on the server is denied. Cloudflare Ray ID: 8f91c2b3a.",
    "Temporarily unavailable due to scheduled maintenance. Please retry your request in a few minutes.",
    "404 Not Found. The requested article /{slug}/ could not be located on this server.",
    "Please verify you are a human to continue reading. DDoS protection by security gateway.",
]

_TOC_TEMPLATES: Final[list[str]] = [
    "Oct 14, 2025 · This guide covers {topic} in plain language. Read our table of contents to explore key concepts for beginners.",
    "Master {topic} in 10 minutes. Learn the background, terminology, and interview questions engineers ask most often.",
    "Understanding {topic} is important for modern practitioners. Subscribe to unlock all 12 chapters and downloadable flashcards.",
    "{topic} explained for students and professionals: overview, history, syllabus links, and related reading lists.",
]

_CORROBORATE_PREFIXES: Final[list[str]] = [
    "",
    "Reference summary: ",
    "According to standard technical documentation, ",
    "Clinical & engineering consensus notes: ",
    "Verified specification — ",
]

_DISPUTE_AUGMENTS: Final[list[str]] = [
    "",
    "Independent peer review notes conflicting evidence: ",
    "Fact-checkers classify the popular version of this claim as a persistent misconception. ",
    "Systematic reviews remain divided and report competing findings: ",
]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


def _shingles(text: str, k: int = 6) -> set[tuple[str, ...]]:
    toks = _normalize_text(text).split()
    if len(toks) < k:
        return {tuple(toks)} if toks else set()
    return {tuple(toks[i : i + k]) for i in range(len(toks) - k + 1)}


def verify_zero_benchmark_overlap(repo_root: Path, generated_queries: list[str]) -> dict[str, int]:
    """Hard assertion that generated training queries have 0 overlap with any web benchmark."""
    bench_files = [
        repo_root / "data" / "benchmarks" / "web_evidentiary_burden_360.jsonl",
        repo_root / "data" / "benchmarks" / "web_evidentiary_burden_60.jsonl",
        repo_root / "data" / "benchmarks" / "web_evidentiary_burden_real_v1.jsonl",
        repo_root / "data" / "benchmarks" / "web_evidentiary_burden_real_v2.jsonl",
        repo_root / "data" / "benchmarks" / "wo45_r33_sybil_dev_45.jsonl",
        repo_root / "data" / "benchmarks" / "wo45_r33_sybil_holdout_45.jsonl",
    ]
    forbidden_norm: set[str] = set()
    forbidden_shingles: set[tuple[str, ...]] = set()
    total_bench_rows = 0

    for bf in bench_files:
        if not bf.exists():
            continue
        for line in bf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            total_bench_rows += 1
            q = str(row.get("query") or row.get("question") or row.get("claim") or "")
            if q:
                forbidden_norm.add(_normalize_text(q))
                forbidden_shingles |= _shingles(q, k=6)

    exact_hits = 0
    shingle_hits = 0
    for gq in generated_queries:
        if _normalize_text(gq) in forbidden_norm:
            exact_hits += 1
        if _shingles(gq, k=6) & forbidden_shingles:
            shingle_hits += 1

    if exact_hits > 0 or shingle_hits > 0:
        raise AssertionError(
            f"Contamination detected: exact_hits={exact_hits}, shingle_hits={shingle_hits}"
        )
    return {
        "checked_benchmark_rows": total_bench_rows,
        "checked_unique_generated_queries": len(set(generated_queries)),
        "exact_query_overlaps": exact_hits,
        "six_token_shingle_overlaps": shingle_hits,
    }


def build_disjoint_web_evidence_splits(
    repo_root: Path,
    *,
    seed: int = 20261113,
) -> tuple[list[tuple[str, str, int]], list[tuple[str, str, int]], dict[str, int]]:
    """Build deterministic disjoint train/val splits by holding out entire seed topics."""
    rng = random.Random(seed)
    all_seeds = list(_FACT_SEEDS) + list(_EXTRA_SEEDS)

    all_queries = [s[0] for s in all_seeds]
    overlap_stats = verify_zero_benchmark_overlap(repo_root, all_queries)

    indices = list(range(len(all_seeds)))
    rng.shuffle(indices)
    # 36 train topics, 9 completely unseen validation topics
    val_topic_set = set(indices[:9])

    train_rows: list[tuple[str, str, int]] = []
    val_rows: list[tuple[str, str, int]] = []

    for idx, (query, corrob, tangent, dispute) in enumerate(all_seeds):
        target = val_rows if idx in val_topic_set else train_rows
        words = [w for w in re.findall(r"[a-zA-Z0-9\-]+", query) if len(w) > 3]
        topic = " ".join(words[-4:]) if words else "technical topic"
        slug = "-".join(w.lower() for w in words[:3]) or "article"

        # Class 0: CORROBORATES (base + prefixed variants + concise direct variant)
        for pfx in _CORROBORATE_PREFIXES:
            target.append((query, f"{pfx}{corrob}".strip(), 0))
        # Second independent phrasing (clause reorder / sentence trim)
        first_clause = corrob.split(";")[0].strip()
        if len(first_clause) > 35 and first_clause != corrob:
            target.append((query, f"{first_clause}.", 0))

        # Class 1: IRRELEVANT (entity-swap tangent + bot stub + TOC blurb + cross-topic negative)
        target.append((query, tangent, 1))
        for st in rng.sample(_STUB_TEMPLATES, k=2):
            target.append((query, st.format(slug=slug), 1))
        for toc in rng.sample(_TOC_TEMPLATES, k=2):
            target.append((query, toc.format(topic=topic), 1))
        other_idx = (idx + 7) % len(all_seeds)
        if (other_idx in val_topic_set) == (idx in val_topic_set):
            target.append((query, all_seeds[other_idx][1], 1))

        # Class 2: DISPUTES (myth/controversy/contradiction variants)
        for aug in _DISPUTE_AUGMENTS:
            target.append((query, f"{aug}{dispute}".strip(), 2))

    rng.shuffle(train_rows)
    rng.shuffle(val_rows)
    return train_rows, val_rows, overlap_stats
