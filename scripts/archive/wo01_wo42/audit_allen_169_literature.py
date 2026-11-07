"""
Audit Script: Programmatic Verification of Allen 1983 Table 1
=============================================================
Diffs every single cell of ALLEN_COMPOSITION_TABLE in `src/lucca/reasoning/relational/allen.py`
against the published CACM 1983 Table 1 reference table.
Zero reliance on synthetic sampling or `relation_1d`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lucca.reasoning.relational.allen import ALLEN_COMPOSITION_TABLE, AllenRelation

# Short codes from Allen 1983 CACM Table 1:
# <  : BEFORE
# >  : AFTER
# m  : MEETS
# mi : MET_BY
# o  : OVERLAPS
# oi : OVERLAPPED_BY
# s  : STARTS
# si : STARTED_BY
# d  : DURING
# di : CONTAINS
# f  : FINISHES
# fi : FINISHED_BY
# =  : EQUALS

R = AllenRelation

CODE_TO_REL = {
    "<": R.BEFORE,
    ">": R.AFTER,
    "m": R.MEETS,
    "mi": R.MET_BY,
    "o": R.OVERLAPS,
    "oi": R.OVERLAPPED_BY,
    "s": R.STARTS,
    "si": R.STARTED_BY,
    "d": R.DURING,
    "di": R.CONTAINS,
    "f": R.FINISHES,
    "fi": R.FINISHED_BY,
    "=": R.EQUALS,
}

ALL_13 = set(AllenRelation)

def parse_set(s: str) -> set[AllenRelation]:
    s = s.strip()
    if s == "ALL":
        return ALL_13
    tokens = s.split()
    return {CODE_TO_REL[t] for t in tokens}

# Canonical Allen 1983 CACM Table 1 (Row = R1, Col = R2)
# Order: <, >, d, di, o, oi, m, mi, s, si, f, fi, =
REFERENCE_ALLEN_1983: dict[tuple[AllenRelation, AllenRelation], set[AllenRelation]] = {}

# Row 1: < (BEFORE)
# < o < = <
# < o > = ALL
# < o d = < o m s d
# < o di = <
# < o o = <
# < o oi = < o m s d
# < o m = <
# < o mi = < o m s d
# < o s = <
# < o si = <
# < o f = < o m s d
# < o fi = <
# < o = = <
ROW_BEFORE = {
    "<": "<",
    ">": "ALL",
    "d": "< o m s d",
    "di": "<",
    "o": "<",
    "oi": "< o m s d",
    "m": "<",
    "mi": "< o m s d",
    "s": "<",
    "si": "<",
    "f": "< o m s d",
    "fi": "<",
    "=": "<",
}

# Row 2: > (AFTER)
# > o < = ALL
# > o > = >
# > o d = > oi mi f d
# > o di = >
# > o o = > oi mi f d
# > o oi = >
# > o m = > oi mi f d
# > o mi = >
# > o s = > oi mi f d
# > o si = >
# > o f = >
# > o fi = >
# > o = = >
ROW_AFTER = {
    "<": "ALL",
    ">": ">",
    "d": "> oi mi f d",
    "di": ">",
    "o": "> oi mi f d",
    "oi": ">",
    "m": "> oi mi f d",
    "mi": ">",
    "s": "> oi mi f d",
    "si": ">",
    "f": ">",
    "fi": ">",
    "=": ">",
}

# Row 3: d (DURING)
# d o < = <
# d o > = >
# d o d = d
# d o di = ALL
# d o o = < o m s d
# d o oi = > oi mi f d
# d o m = <
# d o mi = >
# d o s = d
# d o si = > oi mi f d
# d o f = d
# d o fi = < o m s d
# d o = = d
ROW_DURING = {
    "<": "<",
    ">": ">",
    "d": "d",
    "di": "ALL",
    "o": "< o m s d",
    "oi": "> oi mi f d",
    "m": "<",
    "mi": ">",
    "s": "d",
    "si": "> oi mi f d",
    "f": "d",
    "fi": "< o m s d",
    "=": "d",
}

# Row 4: di (CONTAINS)
# di o < = < o m di fi
# di o > = > oi mi di si
# di o d = o oi s si f fi d di =
# di o di = di
# di o o = o di fi
# di o oi = oi di si
# di o m = o di fi
# di o mi = oi di si
# di o s = o di fi
# di o si = di
# di o f = oi di si
# di o fi = di
# di o = = di
ROW_CONTAINS = {
    "<": "< o m di fi",
    ">": "> oi mi di si",
    "d": "o oi s si f fi d di =",
    "di": "di",
    "o": "o di fi",
    "oi": "oi di si",
    "m": "o di fi",
    "mi": "oi di si",
    "s": "o di fi",
    "si": "di",
    "f": "oi di si",
    "fi": "di",
    "=": "di",
}

# Row 5: o (OVERLAPS)
# o o < = <
# o o > = > oi mi di si
# o o d = o s d
# o o di = < o m di fi
# o o o = < o m
# o o oi = o oi s si f fi d di =
# o o m = <
# o o mi = oi di si
# o o s = o
# o o si = di fi o
# o o f = d s o
# o o fi = < o m
# o o = = o
ROW_OVERLAPS = {
    "<": "<",
    ">": "> oi mi di si",
    "d": "o s d",
    "di": "< o m di fi",
    "o": "< o m",
    "oi": "o oi s si f fi d di =",
    "m": "<",
    "mi": "oi di si",
    "s": "o",
    "si": "di fi o",
    "f": "d s o",
    "fi": "< o m",
    "=": "o",
}

# Row 6: oi (OVERLAPPED-BY)
# oi o < = < o m di fi
# oi o > = >
# oi o d = oi f d
# oi o di = > oi mi di si
# oi o o = o oi s si f fi d di =
# oi o oi = > oi mi
# oi o m = o di fi
# oi o mi = >
# oi o s = d f oi
# oi o si = < o m
# oi o f = oi
# oi o fi = di si oi
# oi o = = oi
ROW_OVERLAPPED_BY = {
    "<": "< o m di fi",
    ">": ">",
    "d": "oi f d",
    "di": "> oi mi di si",
    "o": "o oi s si f fi d di =",
    "oi": "> oi mi",
    "m": "o di fi",
    "mi": ">",
    "s": "d f oi",
    "si": "> oi mi",
    "f": "oi",
    "fi": "di si oi",
    "=": "oi",
}

# Row 7: m (MEETS)
# m o < = <
# m o > = > oi mi di si
# m o d = o s d
# m o di = <
# m o o = <
# m o oi = o s d
# m o m = <
# m o mi = f fi =
# m o s = m
# m o si = m
# m o f = d s o
# m o fi = <
# m o = = m
ROW_MEETS = {
    "<": "<",
    ">": "> oi mi di si",
    "d": "o s d",
    "di": "<",
    "o": "<",
    "oi": "o s d",
    "m": "<",
    "mi": "f fi =",
    "s": "m",
    "si": "m",
    "f": "d s o",
    "fi": "<",
    "=": "m",
}

# Row 8: mi (MET-BY)
# mi o < = < o m di fi
# mi o > = >
# mi o d = oi f d
# mi o di = >
# mi o o = oi f d
# mi o oi = >
# mi o m = s si =
# mi o mi = >
# mi o s = d f oi
# mi o si = >
# mi o f = mi
# mi o fi = mi
# mi o = = mi
ROW_MET_BY = {
    "<": "< o m di fi",
    ">": ">",
    "d": "oi f d",
    "di": ">",
    "o": "oi f d",
    "oi": ">",
    "m": "s si =",
    "mi": ">",
    "s": "d f oi",
    "si": ">",
    "f": "mi",
    "fi": "mi",
    "=": "mi",
}

# Row 9: s (STARTS)
# s o < = <
# s o > = >
# s o d = d
# s o di = < o m di fi
# s o o = < o m
# s o oi = oi f d
# s o m = <
# s o mi = mi
# s o s = s
# s o si = s si =
# s o f = d
# s o fi = < o m
# s o = = s
ROW_STARTS = {
    "<": "<",
    ">": ">",
    "d": "d",
    "di": "< o m di fi",
    "o": "< o m",
    "oi": "oi f d",
    "m": "<",
    "mi": "mi",
    "s": "s",
    "si": "s si =",
    "f": "d",
    "fi": "< o m",
    "=": "s",
}

# Row 10: si (STARTED-BY)
# si o < = < o m di fi
# si o > = >
# si o d = oi f d
# si o di = di
# si o o = o di fi
# si o oi = oi
# si o m = o di fi
# si o mi = mi
# si o s = s si =
# si o si = si
# si o f = oi
# si o fi = di
# si o = = si
ROW_STARTED_BY = {
    "<": "< o m di fi",
    ">": ">",
    "d": "oi f d",
    "di": "di",
    "o": "o di fi",
    "oi": "oi",
    "m": "o di fi",
    "mi": "mi",
    "s": "s si =",
    "si": "si",
    "f": "oi",
    "fi": "di",
    "=": "si",
}

# Row 11: f (FINISHES)
# f o < = <
# f o > = >
# f o d = d
# f o di = > oi mi di si
# f o o = o s d
# f o oi = > oi mi
# f o m = m
# f o mi = >
# f o s = d
# f o si = > oi mi
# f o f = f
# f o fi = f fi =
# f o = = f
ROW_FINISHES = {
    "<": "<",
    ">": ">",
    "d": "d",
    "di": "> oi mi di si",
    "o": "o s d",
    "oi": "> oi mi",
    "m": "m",
    "mi": ">",
    "s": "d",
    "si": "> oi mi",
    "f": "f",
    "fi": "f fi =",
    "=": "f",
}

# Row 12: fi (FINISHED-BY)
# fi o < = <
# fi o > = > oi mi di si
# fi o d = o s d
# fi o di = di
# fi o o = o
# fi o oi = oi di si
# fi o m = m
# fi o mi = oi di si
# fi o s = o
# fi o si = di
# fi o f = f fi =
# fi o fi = fi
# fi o = = fi
ROW_FINISHED_BY = {
    "<": "<",
    ">": "> oi mi di si",
    "d": "o s d",
    "di": "di",
    "o": "o",
    "oi": "oi di si",
    "m": "m",
    "mi": "oi di si",
    "s": "o",
    "si": "di",
    "f": "f fi =",
    "fi": "fi",
    "=": "fi",
}

# Row 13: = (EQUALS)
ROW_EQUALS = {k: k for k in ROW_BEFORE}

ALL_ROWS = {
    "<": (R.BEFORE, ROW_BEFORE),
    ">": (R.AFTER, ROW_AFTER),
    "d": (R.DURING, ROW_DURING),
    "di": (R.CONTAINS, ROW_CONTAINS),
    "o": (R.OVERLAPS, ROW_OVERLAPS),
    "oi": (R.OVERLAPPED_BY, ROW_OVERLAPPED_BY),
    "m": (R.MEETS, ROW_MEETS),
    "mi": (R.MET_BY, ROW_MET_BY),
    "s": (R.STARTS, ROW_STARTS),
    "si": (R.STARTED_BY, ROW_STARTED_BY),
    "f": (R.FINISHES, ROW_FINISHES),
    "fi": (R.FINISHED_BY, ROW_FINISHED_BY),
    "=": (R.EQUALS, ROW_EQUALS),
}

def main() -> int:
    print("=" * 80)
    print("PROGRAMMATIC 169-CELL AUDIT: allen.py vs CACM 1983 Table 1")
    print("=" * 80)
    
    mismatches: list[str] = []
    total_cells = 0
    
    for row_code, (r1, row_dict) in ALL_ROWS.items():
        for col_code, expected_str in row_dict.items():
            r2 = CODE_TO_REL[col_code]
            expected_set = parse_set(expected_str)
            actual_set = set(ALLEN_COMPOSITION_TABLE[(r1, r2)])
            total_cells += 1
            
            if expected_set != actual_set:
                mismatches.append(
                    f"Cell ({r1.name}, {r2.name}): Expected {expected_str} "
                    f"({[e.value for e in expected_set]}), Got {[a.value for a in actual_set]}"
                )

    print(f"Audited {total_cells} composition pairs.")
    if mismatches:
        print(f"\nFAILED: {len(mismatches)} mismatches detected against Allen 1983 CACM Table 1:")
        for m in mismatches:
            print(f"  [X] {m}")
        return 1
    else:
        print("\nSUCCESS: 100% exact symbolic match across all 169 cells against Allen (CACM 1983 Table 1).")
        print("Zero literature diff.")
        return 0

if __name__ == "__main__":
    sys.exit(main())
