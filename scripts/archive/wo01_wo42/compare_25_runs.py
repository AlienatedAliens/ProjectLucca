import json

orig = json.load(open("logs/test_reports/checkpoint_math500_v1.3-final-fresh-500.json"))[:25]
reprod = json.load(open("logs/test_reports/checkpoint_math500_test-25-reproduce.json"))
rep_a = json.load(open("logs/test_reports/checkpoint_math500_rep-A.json"))
rep_b = json.load(open("logs/test_reports/checkpoint_math500_rep-B.json"))

def compare_pair(name1, list1, name2, list2):
    matches = 0
    diffs = []
    for i in range(len(list1)):
        p1 = str(list1[i].get("predicted_ans", "")).strip()
        p2 = str(list2[i].get("predicted_ans", "")).strip()
        idx = list1[i].get("idx")
        if p1 == p2:
            matches += 1
        else:
            diffs.append((idx, p1, p2))
    print(f"{name1} vs {name2}: {matches} / {len(list1)} matching predicted_ans")
    if diffs:
        for idx, p1, p2 in diffs:
            print(f"   idx {idx}: {name1}=\"{p1}\" vs {name2}=\"{p2}\"")
    return matches, diffs

print("=== PAIRWISE PREDICTED_ANS COMPARISONS (N=25) ===")
compare_pair("rep-A", rep_a, "rep-B", rep_b)
print()
compare_pair("rep-A", rep_a, "historical", orig)
print()
compare_pair("rep-B", rep_b, "historical", orig)
print()
compare_pair("reprod", reprod, "rep-A", rep_a)
print()
compare_pair("reprod", reprod, "rep-B", rep_b)
