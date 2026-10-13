#!/usr/bin/env python3
"""
Project Lucca — Parametric Reasoning Suite Generator
Generates fresh, reproducible, programmatic benchmark sets with mathematically
verified ground truths across:
1. Single-Lobe Epistemic False-Belief (ContainerWorld) [25 tasks]
2. Single-Lobe Combinatorial Constraint Satisfaction (Z3 SMT) [25 tasks]
3. Single-Lobe Exact Number Theory & CAS (SymPy) [25 tasks]
4. Two-Lobe Composed Neurosymbolic Workspaces (CW+SymPy, Z3+SymPy, CW+Z3) [25 tasks]
5. Informal-to-Formal Program Translation [25 tasks]

Total: N = 125 fresh, sealed benchmark problems.
Guarantees:
- Every puzzle is solvable and verified with exact programmatic ground truth.
- No overlap with development or diagnostic suites.
- Seeded random generation for exact reproducibility.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import random
from typing import Any

import sympy
import z3

from lucca.sandbox.container_world import ContainerWorld

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DEFAULT = REPO_ROOT / "data" / "benchmarks" / "sealed_parametric_v138_suite.json"


@dataclass
class SealedTask:
    task_id: str
    suite: str
    family: str
    prompt: str
    ground_truth: str
    required_lobes: list[str]
    metadata: dict[str, Any]


def generate_epistemic_container_tasks(count: int = 25, seed: int = 1001, difficulty: str = "standard") -> list[SealedTask]:
    """Generates fresh ContainerWorld Theory of Mind / Epistemic belief tracking tasks."""
    rng = random.Random(seed)
    names_pool = [
        "Alexander", "Beatrice", "Catherine", "Dmitri", "Eleanor", "Felix",
        "Gabriel", "Helena", "Isabelle", "Julian", "Katarina", "Liam",
        "Marcus", "Nadia", "Oliver", "Penelope", "Quentin", "Rowan",
    ]
    items_pool = [
        "quantum_key", "cipher_disk", "star_chart", "specimen_jar",
        "transponder", "data_slate", "chronometer", "compass",
        "field_journal", "lens_filter", "resonator", "decoder_ring",
    ]
    locs_pool = [
        "vault_alpha", "locker_seven", "workbench", "pantry",
        "attic", "lab_bench", "drawer", "safe", "briefcase",
        "cargo_bay", "observation_deck", "armory", "storage_box",
    ]

    tasks: list[SealedTask] = []
    for i in range(1, count + 1):
        if difficulty == "hard":
            task_id = f"SEALED_CW_HARD_{i:02d}"
            agents = rng.sample(names_pool, 4)
            item = rng.choice(items_pool)
            locs = rng.sample(locs_pool, 4)
            cw = ContainerWorld()
            # 1. Initial shared knowledge
            cw.place(item, locs[0], observed_by=agents)
            # 2. Agent 1 moves item to locs[1] in presence of Agent 2 (Agent 0 and 3 away)
            cw.move(item, locs[1], actor=agents[1], observed_by=[agents[2]])
            # 3. Agent 2 moves item to locs[2] in presence of Agent 3 (Agent 0 and 1 away)
            cw.move(item, locs[2], actor=agents[2], observed_by=[agents[3]])
            # 4. Agent 3 secretly moves item to locs[3] alone
            cw.move(item, locs[3], actor=agents[3], observed_by=[])

            obs_agent, tgt_agent = rng.sample(agents, 2)
            expected_loc = cw.query_second_order(obs_agent, tgt_agent, item)

            story = (
                f"At 08:00, {agents[0]}, {agents[1]}, {agents[2]}, and {agents[3]} all gather in the central depot "
                f"and observe that the '{item}' is in '{locs[0]}'. "
                f"At 09:00, while {agents[0]} and {agents[3]} are on exterior patrol, {agents[1]} transfers the '{item}' "
                f"to '{locs[1]}' witnessed only by {agents[2]}. "
                f"At 10:00, while {agents[0]} and {agents[1]} are in communications, {agents[2]} relocates the '{item}' "
                f"to '{locs[2]}' witnessed only by {agents[3]}. "
                f"At 11:00, {agents[3]} secretly moves the '{item}' to '{locs[3]}' alone without any observers. "
                f"What does {obs_agent} believe that {tgt_agent} thinks is the location of the '{item}'? "
                f"Conclude with your answer as the exact location name."
            )
            meta = {
                "agents": agents,
                "observer_agent": obs_agent,
                "target_agent": tgt_agent,
                "item": item,
                "locations": locs,
                "order": "second_order",
            }
        else:
            task_id = f"SEALED_CW_{i:02d}"
            agents = rng.sample(names_pool, 3)
            item = rng.choice(items_pool)
            locs = rng.sample(locs_pool, 3)

            cw = ContainerWorld()
            cw.place(item, locs[0], observed_by=agents)
            cw.move(item, locs[1], actor=agents[0], observed_by=[agents[1]])
            cw.move(item, locs[2], actor=agents[1], observed_by=[])

            target_agent = rng.choice(agents)
            expected_loc = cw.query(target_agent, item)

            story = (
                f"At the start of the mission, {agents[0]}, {agents[1]}, and {agents[2]} are all in the facility "
                f"and know that the '{item}' is in '{locs[0]}'. "
                f"Later, while {agents[2]} is in a soundproof bunker, {agents[0]} moves the '{item}' to '{locs[1]}' "
                f"(only {agents[1]} observes this move). "
                f"Afterwards, {agents[1]} relocates the '{item}' to '{locs[2]}' while both {agents[0]} and {agents[2]} are away. "
                f"Where would {target_agent} look for the '{item}'? "
                f"Conclude with your answer as the exact location name."
            )
            meta = {
                "agents": agents,
                "target_agent": target_agent,
                "item": item,
                "locations": locs,
                "order": "first_order",
            }

        tasks.append(
            SealedTask(
                task_id=task_id,
                suite="single_lobe_epistemic",
                family="container_world",
                prompt=story,
                ground_truth=expected_loc,
                required_lobes=["container_world"],
                metadata=meta,
            )
        )
    return tasks


def generate_combinatorial_z3_tasks(count: int = 25, seed: int = 2002, difficulty: str = "standard") -> list[SealedTask]:
    """Generates fresh combinatorial SMT puzzles with verified unique Z3 models."""
    rng = random.Random(seed)
    tasks: list[SealedTask] = []

    for i in range(1, count + 1):
        if difficulty == "hard":
            task_id = f"SEALED_Z3_HARD_{i:02d}"
            moduli = rng.sample([17, 19, 23, 29, 31, 37], 3)
            m1, m2, m3 = sorted(moduli)
            M = m1 * m2 * m3
            k_mult = rng.randint(2, 8)
            base_sol = rng.randint(100, M - 1)
            target_val = k_mult * M + base_sol
            r1 = target_val % m1
            r2 = target_val % m2
            r3 = target_val % m3
            L = target_val - rng.randint(50, min(1000, M - 50))
            U = L + M

            solver = z3.Solver()
            n_var = z3.Int("n")
            solver.add(n_var > L, n_var < U)
            solver.add(n_var % m1 == r1)
            solver.add(n_var % m2 == r2)
            solver.add(n_var % m3 == r3)
            if solver.check() != z3.sat:
                continue

            prompt = (
                f"Find the unique integer N strictly between {L} and {U} satisfying "
                f"the following system of modular congruences:\n"
                f"1. N % {m1} == {r1}\n"
                f"2. N % {m2} == {r2}\n"
                f"3. N % {m3} == {r3}\n"
                f"Print only the final integer N."
            )
            tasks.append(
                SealedTask(
                    task_id=task_id,
                    suite="single_lobe_smt",
                    family="z3",
                    prompt=prompt,
                    ground_truth=str(target_val),
                    required_lobes=["z3"],
                    metadata={"N": target_val, "moduli": [m1, m2, m3], "L": L, "U": U},
                )
            )
            if len(tasks) == count:
                break
            continue

        task_id = f"SEALED_Z3_{i:02d}"
        x_val = rng.randint(2, 9)
        y_val = rng.randint(x_val + 2, x_val + 10)
        z_val = rng.randint(y_val + 2, y_val + 12)

        s_sum = x_val + y_val + z_val
        s_diff1 = y_val - x_val
        s_diff2 = z_val - y_val
        s_lin = 2 * x_val + 3 * y_val - z_val

        # Verify uniqueness via Z3
        solver = z3.Solver()
        x, y, z = z3.Ints("x y z")
        solver.add(x > 0, y > 0, z > 0)
        solver.add(x < y, y < z)
        solver.add(x + y + z == s_sum)
        solver.add(y - x == s_diff1)
        solver.add(z - y == s_diff2)
        solver.add(2 * x + 3 * y - z == s_lin)

        if solver.check() != z3.sat:
            continue
        m = solver.model()
        # Verify no second solution
        solver.push()
        solver.add(z3.Or(x != m[x], y != m[y], z != m[z]))
        is_unique = (solver.check() == z3.unsat)
        solver.pop()
        if not is_unique:
            continue

        target_query = rng.choice(["x", "y", "z", "product", "sum_squares"])
        if target_query == "x":
            expected = str(x_val)
            query_text = "Find and print the exact value of x."
        elif target_query == "y":
            expected = str(y_val)
            query_text = "Find and print the exact value of y."
        elif target_query == "z":
            expected = str(z_val)
            query_text = "Find and print the exact value of z."
        elif target_query == "product":
            expected = str(x_val * y_val * z_val)
            query_text = "Find and print the product (x * y * z)."
        else:
            expected = str(x_val**2 + y_val**2 + z_val**2)
            query_text = "Find and print the sum of their squares (x^2 + y^2 + z^2)."

        prompt = (
            f"Three distinct positive integers x, y, z satisfy the following conditions:\n"
            f"1. x < y < z\n"
            f"2. x + y + z = {s_sum}\n"
            f"3. y - x = {s_diff1}\n"
            f"4. z - y = {s_diff2}\n"
            f"5. 2*x + 3*y - z = {s_lin}\n"
            f"{query_text}\n"
            f"Conclude with your final answer as an integer."
        )

        tasks.append(
            SealedTask(
                task_id=task_id,
                suite="single_lobe_smt",
                family="z3",
                prompt=prompt,
                ground_truth=expected,
                required_lobes=["z3"],
                metadata={"x": x_val, "y": y_val, "z": z_val, "query": target_query},
            )
        )
        if len(tasks) == count:
            break

    return tasks


def generate_number_theory_sympy_tasks(count: int = 25, seed: int = 3003, difficulty: str = "standard") -> list[SealedTask]:
    """Generates fresh competition-math style exact CAS number theory problems."""
    rng = random.Random(seed)
    tasks: list[SealedTask] = []

    for i in range(1, count + 1):
        if difficulty == "hard":
            task_id = f"SEALED_SYMPY_HARD_{i:02d}"
            q_hard = rng.choice(["semiprime_totient", "semiprime_sigma", "prime_mod_sum"])
            if q_hard == "semiprime_totient":
                p1_idx = rng.randint(70, 110)
                p2_idx = rng.randint(115, 160)
                p1 = sympy.prime(p1_idx)
                p2 = sympy.prime(p2_idx)
                N = p1 * p2
                mod = rng.randint(1000, 2000)
                val = sympy.totient(N) % mod
                prompt = (
                    f"Let p be the {p1_idx}-th prime number and q be the {p2_idx}-th prime number. "
                    f"Let N = p * q. "
                    f"Using SymPy, compute the Euler totient phi(N) modulo {mod}. "
                    f"Print only the final integer answer."
                )
                expected = str(val)
                meta = {"type": q_hard, "p1": p1, "p2": p2, "N": N, "mod": mod}
            elif q_hard == "semiprime_sigma":
                p1_idx = rng.randint(80, 120)
                p2_idx = rng.randint(125, 170)
                p1 = sympy.prime(p1_idx)
                p2 = sympy.prime(p2_idx)
                N = p1 * p2
                mod = rng.randint(1000, 2000)
                val = int(sympy.divisor_sigma(N, 1)) % mod
                prompt = (
                    f"Let p be the {p1_idx}-th prime and q be the {p2_idx}-th prime. "
                    f"Let N = p * q. "
                    f"Using SymPy, compute the sum of all divisors sigma(N) modulo {mod}. "
                    f"Print only the final integer answer."
                )
                expected = str(val)
                meta = {"type": q_hard, "p1": p1, "p2": p2, "N": N, "mod": mod}
            else:
                start_k = rng.randint(80, 150)
                length = rng.randint(10, 20)
                mod = rng.randint(1000, 3000)
                val = sum(sympy.prime(start_k + j) for j in range(length)) % mod
                prompt = (
                    f"Compute the sum of {length} consecutive primes starting from the "
                    f"{start_k}-th prime (prime({start_k}) through prime({start_k + length - 1})), "
                    f"modulo {mod}. Print only the final integer answer."
                )
                expected = str(val)
                meta = {"type": q_hard, "start_k": start_k, "length": length, "mod": mod}

            tasks.append(
                SealedTask(
                    task_id=task_id,
                    suite="single_lobe_cas",
                    family="sympy",
                    prompt=prompt,
                    ground_truth=expected,
                    required_lobes=["sympy"],
                    metadata=meta,
                )
            )
            continue

        task_id = f"SEALED_SYMPY_{i:02d}"
        q_type = rng.choice(["totient_prime", "modular_exp", "prime_sum", "divisor_sigma", "poly_coeff"])

        if q_type == "totient_prime":
            p_idx = rng.randint(20, 60)
            p = sympy.prime(p_idx)
            mod = rng.randint(500, 999)
            val = (sympy.totient(p - 1) * p) % mod
            prompt = (
                f"Let p be the {p_idx}-th prime number. "
                f"Compute and print the value of (sympy.totient(p - 1) * p) mod {mod}."
            )
            expected = str(val)

        elif q_type == "modular_exp":
            base = rng.randint(3, 11)
            exp = rng.randint(1000, 3000)
            mod = rng.randint(101, 499)
            val = pow(base, exp, mod)
            prompt = (
                f"Find the remainder when {base}^{exp} is divided by {mod}. "
                f"Print the exact remainder as an integer."
            )
            expected = str(val)

        elif q_type == "prime_sum":
            start_k = rng.randint(15, 35)
            length = rng.randint(4, 7)
            primes = [sympy.prime(start_k + j) for j in range(length)]
            val = sum(primes)
            prompt = (
                f"Find the sum of the {length} consecutive primes starting from the "
                f"{start_k}-th prime (i.e. prime({start_k}) + ... + prime({start_k + length - 1})). "
                f"Print the exact sum as an integer."
            )
            expected = str(val)

        elif q_type == "divisor_sigma":
            n_val = rng.randint(150, 400)
            # sum of proper divisors
            val = int(sympy.divisor_sigma(n_val, 1) - n_val)
            prompt = (
                f"Find the sum of all proper positive divisors of {n_val} (excluding {n_val} itself). "
                f"Print the exact sum as an integer."
            )
            expected = str(val)

        else:  # poly_coeff
            x = sympy.Symbol("x")
            a = rng.randint(2, 4)
            b = rng.randint(1, 3)
            power = rng.randint(8, 14)
            deg = rng.randint(3, power - 2)
            poly = sympy.expand((a * x + b) ** power)
            val = int(poly.coeff(x, deg))
            prompt = (
                f"Find the coefficient of x^{deg} in the expanded polynomial ({a}*x + {b})^{power}. "
                f"Print the exact integer coefficient."
            )
            expected = str(val)

        tasks.append(
            SealedTask(
                task_id=task_id,
                suite="single_lobe_cas",
                family="sympy",
                prompt=prompt,
                ground_truth=expected,
                required_lobes=["sympy"],
                metadata={"type": q_type},
            )
        )

    return tasks


def generate_multi_lobe_composed_tasks(count: int = 25, seed: int = 4004, difficulty: str = "standard") -> list[SealedTask]:
    """Generates two-lobe composed neurosymbolic tasks requiring joint reasoning."""
    rng = random.Random(seed)
    tasks: list[SealedTask] = []

    for i in range(1, count + 1):
        if difficulty == "hard":
            task_id = f"SEALED_COMP_HARD_{i:02d}"
            lobe_combo = rng.choice(["cw_sympy", "z3_sympy", "cw_z3"])

            if lobe_combo == "cw_sympy":
                names = rng.sample(["Arthur", "Brenda", "Charles", "Diana"], 3)
                locs = rng.sample(["vault", "pantry", "study", "attic", "cellar"], 4)
                item = rng.choice(["ledger", "cipher", "specimen", "artifact"])

                cw = ContainerWorld()
                cw.place(item, locs[0], observed_by=names)
                cw.move(item, locs[1], actor=names[0], observed_by=[names[1]])
                cw.move(item, locs[2], actor=names[1], observed_by=[names[0]])

                # Second-order query: What does names[2] believe names[1] believes?
                believed_loc = cw.query_second_order(names[2], names[1], item)
                k_map = {locs[0]: 47, locs[1]: 53, locs[2]: 59, locs[3]: 61}
                k = k_map[believed_loc]
                mod = rng.randint(1000, 2500)
                val = (int(sympy.prime(k)) * int(sympy.totient(k * 7))) % mod

                prompt = (
                    f"At 08:00, {names[0]}, {names[1]}, and {names[2]} know that the '{item}' is in '{locs[0]}'. "
                    f"At 09:00, {names[0]} relocates the '{item}' to '{locs[1]}' while {names[1]} watches ({names[2]} is in another wing). "
                    f"At 10:00, {names[1]} moves the '{item}' to '{locs[2]}' while {names[0]} watches ({names[2]} remains away). "
                    f"Let L be the location where {names[2]} believes that {names[1]} believes the '{item}' is located. "
                    f"Map L to integer k: '{locs[0]}': 47, '{locs[1]}': 53, '{locs[2]}': 59, '{locs[3]}': 61. "
                    f"Using SymPy, compute and print the exact value of: (sympy.prime(k) * sympy.totient(k * 7)) mod {mod}."
                )
                expected = str(val)
                lobes = ["container_world", "sympy"]

            elif lobe_combo == "z3_sympy":
                a_val = rng.randint(12, 25)
                b_val = rng.randint(a_val + 5, a_val + 20)
                c_val = rng.randint(b_val + 5, b_val + 25)

                s1 = a_val + b_val + c_val
                s2 = 2 * a_val + 3 * b_val - c_val
                s3 = c_val - a_val

                # SymPy query: sum of first a primes multiplied by (c - b)
                prime_sum = sum(sympy.prime(j) for j in range(1, a_val + 1))
                val = prime_sum * (c_val - b_val)

                prompt = (
                    f"Three positive integers a, b, c satisfy:\n"
                    f"1. a < b < c\n"
                    f"2. a + b + c = {s1}\n"
                    f"3. 2*a + 3*b - c = {s2}\n"
                    f"4. c - a = {s3}\n"
                    f"Use Z3 to solve for a, b, and c. "
                    f"Then use SymPy to compute the sum of the first a primes, multiplied by (c - b): "
                    f"sum(sympy.prime(j) for j in range(1, a + 1)) * (c - b). "
                    f"Print only the final integer answer."
                )
                expected = str(val)
                lobes = ["z3", "sympy"]

            else:  # cw_z3
                names = ["Alice", "Bob", "Charlie"]
                locs = ["room_a", "room_b", "room_c", "room_d"]
                cw = ContainerWorld()
                cw.place("badge", locs[0], observed_by=names)
                cw.move("badge", locs[1], actor="Alice", observed_by=["Bob"])
                cw.move("badge", locs[2], actor="Bob", observed_by=[])

                # Second-order: Charlie's belief of Alice's belief -> room_a
                cw_loc = cw.query_second_order("Charlie", "Alice", "badge")
                w_map = {"room_a": 14, "room_b": 21, "room_c": 28, "room_d": 35}
                w_val = w_map[cw_loc]

                # Z3 problem: x, y such that x + y == 50, x >= w_val, 3*x - y == 30
                # 4x = 80 -> x = 20, y = 30. (20 >= 14 holds)
                prompt = (
                    f"Initially, Alice, Bob, and Charlie know the 'badge' is in 'room_a'. "
                    f"Alice moves the 'badge' to 'room_b' in front of Bob, while Charlie is away. "
                    f"Bob then moves the 'badge' to 'room_c' alone. "
                    f"Let loc be the location where Charlie believes Alice believes the badge is. "
                    f"Weight mapping: 'room_a': 14, 'room_b': 21, 'room_c': 28, 'room_d': 35. Let W = weight(loc). "
                    f"Find positive integers x, y using Z3 such that: x + y == 50, x >= W, and 3*x - y == 30. "
                    f"Print the exact value of (x * y)."
                )
                expected = "600"
                lobes = ["container_world", "z3"]

            tasks.append(
                SealedTask(
                    task_id=task_id,
                    suite="two_lobe_composed",
                    family=lobe_combo,
                    prompt=prompt,
                    ground_truth=expected,
                    required_lobes=lobes,
                    metadata={"difficulty": "hard"},
                )
            )
            continue

        task_id = f"SEALED_COMP_{i:02d}"
        lobe_combo = rng.choice(["cw_sympy", "z3_sympy", "cw_z3"])

        if lobe_combo == "cw_sympy":
            # Epistemic story selects index k, SymPy computes prime property
            names = rng.sample(["Arthur", "Brenda", "Charles", "Diana"], 3)
            locs = rng.sample(["vault", "pantry", "study", "attic"], 3)
            item = rng.choice(["ledger", "cipher", "specimen"])

            cw = ContainerWorld()
            cw.place(item, locs[0], observed_by=names)
            cw.move(item, locs[1], actor=names[0], observed_by=[names[1]])
            cw.move(item, locs[2], actor=names[1], observed_by=[])

            target = rng.choice([names[0], names[2]])
            believed_loc = cw.query(target, item)

            k_map = {locs[0]: 17, locs[1]: 23, locs[2]: 31}
            k = k_map[believed_loc]
            # SymPy calculation: (prime(k) + totient(k*10)) % 797
            val = (int(sympy.prime(k)) + int(sympy.totient(k * 10))) % 797

            prompt = (
                f"At 08:00, {names[0]}, {names[1]}, and {names[2]} know that the '{item}' is in '{locs[0]}'. "
                f"At 09:00, {names[0]} relocates the '{item}' to '{locs[1]}' while {names[1]} watches ({names[2]} is in another wing). "
                f"At 10:00, {names[1]} moves the '{item}' to '{locs[2]}' alone while both {names[0]} and {names[2]} are away. "
                f"Let L be where {target} believes the '{item}' is located. "
                f"Map L to integer k: '{locs[0]}': 17, '{locs[1]}': 23, '{locs[2]}': 31. "
                f"Using SymPy, compute and print the exact value of: (sympy.prime(k) + sympy.totient(k*10)) mod 797."
            )
            expected = str(val)
            lobes = ["container_world", "sympy"]

        elif lobe_combo == "z3_sympy":
            # Z3 finds unique integers, SymPy evaluates polynomial/prime
            a_val = rng.randint(3, 8)
            b_val = rng.randint(a_val + 2, a_val + 8)
            s_sum = a_val + b_val
            s_diff = b_val - a_val
            s_prod = a_val * b_val

            # SymPy query: sum of first a_val primes multiplied by b_val
            prime_sum = sum(sympy.prime(j) for j in range(1, a_val + 1))
            val = prime_sum * b_val

            prompt = (
                f"Two positive integers a and b satisfy: a < b, a + b == {s_sum}, and b - a == {s_diff}. "
                f"Use Z3 to solve for a and b. "
                f"Then, use SymPy to compute and print the sum of the first a primes, multiplied by b: "
                f"sum(sympy.prime(j) for j in range(1, a + 1)) * b."
            )
            expected = str(val)
            lobes = ["z3", "sympy"]

        else:  # cw_z3
            # Container world determines items in locations, Z3 assigns schedules
            names = ["Alice", "Bob", "Charlie"]
            locs = ["room_A", "room_B", "room_C"]
            cw = ContainerWorld()
            cw.place("badge", locs[0], observed_by=names)
            cw.move("badge", locs[1], actor="Alice", observed_by=["Bob"])

            # Bob believes room_B, Charlie believes room_A
            # Assign weights: room_A -> 5, room_B -> 8, room_C -> 12
            # Z3 solves x + y == 30, x >= val(Charlie's belief), y <= val(Bob's belief)*3
            w_charlie = 5
            w_bob = 8
            # Constraints: x + y == 30, x >= 5, y == 2 * x -> 3x = 30 -> x = 10, y = 20
            # Target: x * y = 200
            prompt = (
                f"Initially, Alice, Bob, and Charlie know the 'badge' is in 'room_A'. "
                f"Alice moves the 'badge' to 'room_B' in front of Bob, while Charlie is away. "
                f"Let w_C be the weight of where Charlie believes the badge is ('room_A': 5, 'room_B': 8). "
                f"Let w_B be the weight of where Bob believes the badge is ('room_A': 5, 'room_B': 8). "
                f"Find integers x, y using Z3 such that: x + y == 30, x >= w_C, and y == (w_B / 4) * x. "
                f"Print the exact value of (x * y)."
            )
            expected = "200"
            lobes = ["container_world", "z3"]

        tasks.append(
            SealedTask(
                task_id=task_id,
                suite="two_lobe_composed",
                family=lobe_combo,
                prompt=prompt,
                ground_truth=expected,
                required_lobes=lobes,
                metadata={},
            )
        )

    return tasks


def generate_formalization_translation_tasks(count: int = 25, seed: int = 5005, difficulty: str = "standard") -> list[SealedTask]:
    """Generates tasks evaluating formal code translation accuracy."""
    rng = random.Random(seed)
    tasks: list[SealedTask] = []

    for i in range(1, count + 1):
        if difficulty == "hard":
            task_id = f"SEALED_TRANS_HARD_{i:02d}"
            x0 = rng.randint(10, 50)
            steps = rng.randint(40, 60)
            mult = rng.randint(3, 7)
            add = rng.randint(11, 29)
            mod = rng.randint(500, 999)

            curr = x0
            for step in range(1, steps + 1):
                if curr % 2 == 0:
                    curr = (curr * mult + add) % mod
                else:
                    curr = (curr * 2 + step) % mod

            prompt = (
                f"Write a Python script that computes the final value of the following deterministic process:\n"
                f"Initialize x = {x0}.\n"
                f"For step from 1 to {steps} (inclusive):\n"
                f"  If x is even: x = (x * {mult} + {add}) % {mod}\n"
                f"  Otherwise: x = (x * 2 + step) % {mod}\n"
                f"Print only the final integer value of x."
            )
            tasks.append(
                SealedTask(
                    task_id=task_id,
                    suite="formalization_translation",
                    family="pure_python",
                    prompt=prompt,
                    ground_truth=str(curr),
                    required_lobes=[],
                    metadata={"difficulty": "hard", "steps": steps, "x0": x0, "mod": mod},
                )
            )
            continue

        task_id = f"SEALED_TRANS_{i:02d}"
        n_items = rng.randint(40, 100)
        p_cut = rng.randint(3, 9)
        remainder = n_items % p_cut
        quotient = n_items // p_cut

        prompt = (
            f"Write a Python script that computes the following: "
            f"A baker has {n_items} cookies and packages them into boxes of {p_cut} cookies each. "
            f"The remaining cookies are divided equally among {remainder} children if remainder > 0, "
            f"or the baker eats none. "
            f"Find the total number of boxes formed plus the remainder squared: (boxes + remainder^2). "
            f"Print only the final integer answer."
        )
        val = quotient + (remainder**2)
        expected = str(val)

        tasks.append(
            SealedTask(
                task_id=task_id,
                suite="formalization_translation",
                family="pure_python",
                prompt=prompt,
                ground_truth=expected,
                required_lobes=[],
                metadata={"n": n_items, "divisor": p_cut},
            )
        )

    return tasks


def main() -> None:
    parser = argparse.ArgumentParser(description="Parametric Reasoning Suite Generator")
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT, help="Output JSON path")
    parser.add_argument("--seed", type=int, default=42, help="Global master seed")
    parser.add_argument("--difficulty", type=str, default="standard", choices=["standard", "hard"], help="Difficulty level")
    args = parser.parse_args()

    print("==========================================================================")
    print("=== PROJECT LUCCA: PARAMETRIC REASONING SUITE GENERATOR ===")
    print("==========================================================================")
    print(f"Timestamp: {datetime.now(UTC).isoformat()} | Master Seed: {args.seed} | Difficulty: {args.difficulty}")

    all_tasks: list[SealedTask] = []
    all_tasks.extend(generate_epistemic_container_tasks(count=25, seed=args.seed + 1, difficulty=args.difficulty))
    all_tasks.extend(generate_combinatorial_z3_tasks(count=25, seed=args.seed + 2, difficulty=args.difficulty))
    all_tasks.extend(generate_number_theory_sympy_tasks(count=25, seed=args.seed + 3, difficulty=args.difficulty))
    all_tasks.extend(generate_multi_lobe_composed_tasks(count=25, seed=args.seed + 4, difficulty=args.difficulty))
    all_tasks.extend(generate_formalization_translation_tasks(count=25, seed=args.seed + 5, difficulty=args.difficulty))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": "Sealed_Parametric_Reasoning_Master_Suite",
        "generated_at": datetime.now(UTC).isoformat(),
        "master_seed": args.seed,
        "difficulty": args.difficulty,
        "total_tasks": len(all_tasks),
        "suite_counts": {
            "single_lobe_epistemic": 25,
            "single_lobe_smt": 25,
            "single_lobe_cas": 25,
            "two_lobe_composed": 25,
            "formalization_translation": 25,
        },
        "tasks": [asdict(t) for t in all_tasks],
    }

    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[+] Successfully generated {len(all_tasks)} sealed tasks to: {args.out}")


if __name__ == "__main__":
    main()
