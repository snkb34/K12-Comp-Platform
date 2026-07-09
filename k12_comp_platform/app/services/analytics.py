from __future__ import annotations

from statistics import median
from sqlalchemy.orm import Session

from app.models import CompRow


def _money(value):
    try:
        return float(value) if value is not None else None
    except Exception:
        return None


def licensed_market_summary(db: Session):
    """
    Build a district-level licensed salary schedule summary.

    This does not assume districts use "BA Step 1".
    Minimum = lowest salary found.
    Midpoint = median of all schedule salaries.
    Maximum = highest salary found.
    Steps/Lanes = unique labels extracted by the parser.
    """
    rows = db.query(CompRow).filter(CompRow.category.ilike("%licensed%")).all()

    grouped = {}

    for r in rows:
        salaries = [_money(r.min_salary), _money(r.midpoint), _money(r.max_salary)]
        salaries = [s for s in salaries if s is not None and s > 0]

        if not salaries:
            continue

        district = r.district or "Unknown"
        state = r.state or ""
        year = r.year or ""

        key = (district, state, year)

        if key not in grouped:
            grouped[key] = {
                "district": district,
                "state": state,
                "year": year,
                "salaries": [],
                "steps": set(),
                "lanes": set(),
                "minimum_label": "",
                "minimum_salary": None,
                "maximum_label": "",
                "maximum_salary": None,
            }

        g = grouped[key]

        for salary in sorted(set(salaries)):
            g["salaries"].append(salary)

            label_parts = []
            if r.step:
                label_parts.append(f"Step {r.step}")
                g["steps"].add(str(r.step))
            if r.lane:
                label_parts.append(str(r.lane))
                g["lanes"].add(str(r.lane))

            label = " / ".join(label_parts) if label_parts else (r.raw_title or "")

            if g["minimum_salary"] is None or salary < g["minimum_salary"]:
                g["minimum_salary"] = salary
                g["minimum_label"] = label

            if g["maximum_salary"] is None or salary > g["maximum_salary"]:
                g["maximum_salary"] = salary
                g["maximum_label"] = label

    summary = []

    for g in grouped.values():
        salaries = sorted(g["salaries"])
        if not salaries:
            continue

        summary.append({
            "district": g["district"],
            "state": g["state"],
            "year": g["year"],
            "minimum_salary": min(salaries),
            "minimum_label": g["minimum_label"],
            "midpoint": round(median(salaries), 2),
            "maximum_salary": max(salaries),
            "maximum_label": g["maximum_label"],
            "steps": len(g["steps"]),
            "lanes": len(g["lanes"]),
            "rank": None,
        })

    summary.sort(key=lambda x: x["midpoint"], reverse=True)

    for idx, row in enumerate(summary, start=1):
        row["rank"] = idx

    if summary:
        midpoints = [r["midpoint"] for r in summary if r["midpoint"] is not None]
        minimums = [r["minimum_salary"] for r in summary if r["minimum_salary"] is not None]
        maximums = [r["maximum_salary"] for r in summary if r["maximum_salary"] is not None]

        stats = {
            "district_count": len(summary),
            "average_minimum": round(sum(minimums) / len(minimums), 2) if minimums else None,
            "average_midpoint": round(sum(midpoints) / len(midpoints), 2) if midpoints else None,
            "average_maximum": round(sum(maximums) / len(maximums), 2) if maximums else None,
            "market_midpoint_range": round(max(midpoints) - min(midpoints), 2) if len(midpoints) >= 2 else 0,
        }
    else:
        stats = {
            "district_count": 0,
            "average_minimum": None,
            "average_midpoint": None,
            "average_maximum": None,
            "market_midpoint_range": None,
        }

    jeffco = next((r for r in summary if "jeffco" in r["district"].lower()), None)

    if jeffco and stats["average_midpoint"]:
        jeffco["difference_from_average_midpoint"] = round(
            jeffco["midpoint"] - stats["average_midpoint"], 2
        )
        jeffco["percent_difference_from_average_midpoint"] = round(
            (jeffco["midpoint"] - stats["average_midpoint"]) / stats["average_midpoint"] * 100,
            2
        )
    elif jeffco:
        jeffco["difference_from_average_midpoint"] = None
        jeffco["percent_difference_from_average_midpoint"] = None

    return {
        "rows": summary,
        "stats": stats,
        "jeffco": jeffco,
    }
