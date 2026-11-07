"""
Project Lucca — Controlled Paired Single-Shot Benchmark
Verifies back-to-back interleaved execution of list_dir vs run_python
under identical host and WSL2 container conditions.
"""

import statistics
import time

from lucca.sandbox.rpc import DockerRPCTransport


def run_paired_benchmark(n_pairs: int = 10) -> None:
    transport = DockerRPCTransport(container_name="lucca-file-sandbox", use_persistent_worker=False)
    try:
        if not transport.is_container_running():
            transport.ensure_container_running()

        # Warmup
        transport.execute("warmup", "list_dir", {"path": "."})

        fs_lats: list[float] = []
        py_lats: list[float] = []
        deltas: list[float] = []

        print(f"Running {n_pairs} strictly interleaved single-shot trials...")
        for i in range(n_pairs):
            res_fs = transport.execute(f"pair-{i}-fs", "list_dir", {"path": "."})
            assert res_fs.ok, f"FS failed: {res_fs.stderr}"
            fs_lats.append(res_fs.elapsed_ms)

            res_py = transport.execute(
                f"pair-{i}-py", "run_python", {"code": "import math; math.sqrt(1764)"}
            )
            assert res_py.ok, f"PY failed: {res_py.stderr}"
            py_lats.append(res_py.elapsed_ms)

            diff = res_py.elapsed_ms - res_fs.elapsed_ms
            deltas.append(diff)
            print(
                f"  Pair {i+1:2d}: list_dir={res_fs.elapsed_ms:6.2f} ms | "
                f"run_python={res_py.elapsed_ms:6.2f} ms | delta={diff:+6.2f} ms"
            )

        print("\n" + "=" * 65)
        print("PAIRED SINGLE-SHOT BENCHMARK RESULTS (Interleaved N=10 Pairs)")
        print("=" * 65)
        print(
            f"  list_dir P50    : {statistics.median(fs_lats):6.2f} ms "
            f"(Mean: {statistics.mean(fs_lats):6.2f} ms, Min: {min(fs_lats):6.2f} ms, Max: {max(fs_lats):6.2f} ms)"
        )
        print(
            f"  run_python P50  : {statistics.median(py_lats):6.2f} ms "
            f"(Mean: {statistics.mean(py_lats):6.2f} ms, Min: {min(py_lats):6.2f} ms, Max: {max(py_lats):6.2f} ms)"
        )
        print(
            f"  Paired Delta P50: {statistics.median(deltas):+6.2f} ms "
            f"(Mean: {statistics.mean(deltas):+6.2f} ms)"
        )
        print(
            f"  Python > FS in  : {sum(1 for d in deltas if d > 0)} / {n_pairs} pairs "
            f"({sum(1 for d in deltas if d > 0)*100//n_pairs}%)"
        )
        print("=" * 65)
    finally:
        transport.close()


if __name__ == "__main__":
    run_paired_benchmark()
