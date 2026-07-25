"""워크플로우 라우팅 성능 벤치마크.

구조 자동 감지:
  - 신형: agent.workflow_routing.route_workflow 존재 → resolution 기반
  - 구형: 없으면 agent.workflow_matcher.match_workflow(단일 LLM + 결정론 가드)

사용:
  LLM_PROVIDER=ollama uv run python routing_benchmark.py <label> <out.json>
지표:
  clear_acc      명확+구어체 발화 정확도(resolved id == expected)
  overcapture_acc 부계좌+엔티티 과잉포섭 케이스 정확도
  ambiguity_safety 모호 발화를 잘못 확정하지 않은 비율(신형=ambiguous/no_match, 구형=None)
  overall_acc    위 셋을 합친 전체 정답률
  avg_latency_ms 발화당 평균 지연
"""

import json
import os
import sys
import time
from pathlib import Path

DATASET = Path(__file__).with_name("routing_eval_dataset.json")


def _load_dataset():
    return json.loads(DATASET.read_text(encoding="utf-8"))


def _predict_new(text):
    from agent.workflow_routing import route_workflow

    r = route_workflow(text)
    if r.status == "resolved":
        return r.workflow_id, r.status
    return None, r.status  # ambiguous | no_match | failed


def _predict_legacy(text):
    from agent.workflow_matcher import match_workflow

    wid = match_workflow(text)
    # 구형은 ambiguous 개념이 없다. None이면 no_match로 간주.
    return wid, ("resolved" if wid else "no_match")


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    out = sys.argv[2] if len(sys.argv) > 2 else "benchmark_result.json"

    try:
        import agent.workflow_routing  # noqa: F401

        structure = "new"
        predict = _predict_new
    except ImportError:
        structure = "legacy"
        predict = _predict_legacy

    dataset = _load_dataset()
    rows = []
    for item in dataset:
        t0 = time.perf_counter()
        try:
            wid, status = predict(item["text"])
            err = None
        except Exception as e:  # noqa: BLE001
            wid, status, err = None, "error", f"{type(e).__name__}: {e}"
        latency_ms = (time.perf_counter() - t0) * 1000
        rows.append(
            {
                "category": item["category"],
                "text": item["text"],
                "expected": item["expected"],
                "predicted": wid,
                "status": status,
                "latency_ms": round(latency_ms, 1),
                "error": err,
            }
        )

    def _correct(row):
        cat, exp, wid, status = row["category"], row["expected"], row["predicted"], row["status"]
        if cat == "ambiguous":
            # 안전: 잘못 확정하지 않음. 신형=ambiguous/no_match, 구형=None(no_match).
            return status in ("ambiguous", "no_match")
        # clear/colloquial/overcapture: 기대 워크플로우와 일치.
        return wid == exp

    def _acc(cats):
        subset = [r for r in rows if r["category"] in cats]
        if not subset:
            return None
        return round(100.0 * sum(_correct(r) for r in subset) / len(subset), 1)

    summary = {
        "label": label,
        "structure": structure,
        "provider": os.getenv("LLM_PROVIDER", "openai"),
        "model": os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL") or "(default)",
        "verifier": (
            "n/a"
            if structure == "legacy"
            else (
                "off"
                if os.getenv("WORKFLOW_VERIFIER_ENABLED", "true").strip().lower() in ("false", "0", "no", "off")
                else "on"
            )
        ),
        "n": len(rows),
        "clear_acc": _acc({"clear", "colloquial"}),
        "overcapture_acc": _acc({"overcapture"}),
        "ambiguity_safety": _acc({"ambiguous"}),
        "overall_acc": round(100.0 * sum(_correct(r) for r in rows) / len(rows), 1),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / len(rows), 1),
    }
    Path(out).write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    # 오답 목록
    wrong = [r for r in rows if not _correct(r)]
    if wrong:
        print(f"\n오답 {len(wrong)}건:")
        for r in wrong:
            print(f"  [{r['category']}] {r['text']} → pred={r['predicted']} ({r['status']}) / exp={r['expected']}")


if __name__ == "__main__":
    main()
