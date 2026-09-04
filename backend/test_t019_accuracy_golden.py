"""Script Test T-019 - Do do chinh xac FR-01 tren bo golden_scam_50.json.

Cach chay (venv local):
    cd e:\\lachanchongluadao\\backend
    .\\venv\\Scripts\\python.exe test_t019_accuracy_golden.py

Cach chay (Docker):
    docker compose exec backend python /app/test_t019_accuracy_golden.py

Ket qua bao gom:
  - Accuracy (ty le dung / tong 50 mau)
  - Accuracy theo tung cap do (AN_TOAN / NGHI_NGO / NGUY_HIEM)
  - Average distance (do xa muc tieu: 0=AN_TOAN,1=NGHI_NGO,2=NGUY_HIEM)
  - Confusion Matrix (actual \\\\ expected)
  - Danh sach cac mau sai + ly do (de biet "muc tieu bao xa")
"""

import json
import os
import sys
from collections import defaultdict, Counter

LEVELS = ["AN_TOAN", "NGHI_NGO", "NGUY_HIEM"]
LEVEL_IDX = {lvl: i for i, lvl in enumerate(LEVELS)}


def distance(a: str, b: str) -> int:
    return abs(LEVEL_IDX.get(a, 1) - LEVEL_IDX.get(b, 1))


def main():
    from app.core.database import SessionLocal
    from app.services.pipeline import execute_scan_pipeline

    base_dir = os.path.dirname(os.path.abspath(__file__))
    golden_path = os.path.join(base_dir, "golden_scam_50.json")
    with open(golden_path, "r", encoding="utf-8") as f:
        samples = json.load(f)

    print("=" * 78)
    print(f"🧪 T-019  FR-01 ACCURACY TEST  |  golden_scam_50.json  ({len(samples)} samples)")
    print("=" * 78)

    db = SessionLocal()
    try:
        results = []
        per_level_expected = defaultdict(lambda: {"total": 0, "correct": 0})
        per_level_predicted = defaultdict(lambda: {"total": 0, "correct_as_expected": 0})
        confusion = {e: Counter() for e in LEVELS}
        distances_sum = 0
        mismatches = []

        for s in samples:
            expected = s["expected_risk_level"]
            per_level_expected[expected]["total"] += 1

            try:
                r = execute_scan_pipeline(s["content"], db)
                actual = r.get("risk_level", "AN_TOAN")
                score = int(r.get("final_score") or 0)
            except Exception as exc:
                actual = f"ERROR:{type(exc).__name__}"
                score = -1

            pred_norm = actual if actual in LEVELS else ("NGHI_NGO" if isinstance(actual, str) and actual.startswith("NG") else "AN_TOAN")
            per_level_predicted[pred_norm]["total"] += 1
            confusion[expected][pred_norm] += 1

            ok = pred_norm == expected
            if ok:
                per_level_expected[expected]["correct"] += 1
            else:
                mismatches.append({
                    "id": s["id"],
                    "category": s["category"],
                    "content_preview": s["content"][:90].replace("\n", " "),
                    "expected": expected,
                    "actual": pred_norm,
                    "score": score,
                    "distance": distance(expected, pred_norm),
                })

            distances_sum += distance(expected, pred_norm)
            results.append((s["id"], expected, pred_norm, score, ok, s["category"]))

        total = len(samples)
        correct_cnt = sum(1 for x in results if x[4])
        accuracy = correct_cnt / total * 100
        avg_distance = distances_sum / total

        print(f"\n📊 TONG QUAN:")
        print(f"   - Tong mau:           {total}")
        print(f"   - Dung (match level): {correct_cnt}")
        print(f"   - Sai:                {total - correct_cnt}")
        print(f"   - Accuracy:           {accuracy:.2f} %")
        print(f"   - Avg Distance (0-2): {avg_distance:.3f}  (0 = hoan toan dung, 2 = NGUY_HIEM vs AN_TOAN)")

        print(f"\n📊 ACCURACY THEO MUC RUI RO (expected level):")
        for lvl in LEVELS:
            info = per_level_expected[lvl]
            if info["total"] == 0:
                continue
            pct = info["correct"] / info["total"] * 100
            bar = "█" * int(round(pct / 5)) + "░" * (20 - int(round(pct / 5)))
            print(f"   {lvl:10s} : {info['correct']:2d}/{info['total']:2d}  ({pct:5.1f}%)  {bar}")

        print(f"\n📊 CONFUSION MATRIX (expected = cot ngang, actual = cot doc):")
        print("                 " + "".join(f"{c:>12s}" for c in LEVELS))
        for exp in LEVELS:
            row = confusion[exp]
            cells = [f"{row.get(c, 0):>12d}" for c in LEVELS]
            marker = " ← expected"
            print(f"   {exp:12s} {''.join(cells)}{marker}")

        if mismatches:
            print(f"\n❌ DANH SACH {len(mismatches)} MAU SAI (do biet 'muc tieu bao xa'):")
            print(f"   {'ID':>3s}  {'DIST':>4s}  {'EXPECTED':>10s}  {'ACTUAL':>10s}  SCORE  CATEGORY / PREVIEW")
            print("   " + "-" * 110)
            for m in mismatches:
                print(f"   {m['id']:>3d}  {m['distance']:>4d}  {m['expected']:>10s}  {m['actual']:>10s}  {m['score']:>5d}  {m['category']}")
                print(f"                                                          : {m['content_preview']}")
        else:
            print("\n✅ 100% KHONG CO MAU NAO SAI!")

        print("\n" + "=" * 78)
        if accuracy >= 80 and avg_distance <= 0.3:
            print(f"✅ Ket luan: DO CHINH XAC CAO ({accuracy:.1f}%, avg_dist={avg_distance:.2f}) → Phat hien luadao phu hop quy dinh BR-01-3.")
        elif accuracy >= 60:
            print(f"⚠️  Ket luan: DO CHINH XAC TAM DUOC ({accuracy:.1f}%, avg_dist={avg_distance:.2f}) → Can bo sung rule hoac cai thien pattern.")
        else:
            print(f"❌ Ket luan: DO CHINH XAC THAP ({accuracy:.1f}%, avg_dist={avg_distance:.2f}) → Can xem lai rule engine va signal.")
        print("=" * 78)

        return 0 if correct_cnt == total else (0 if accuracy >= 70 else 1)
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
