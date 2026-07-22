"""BuilderDNA 2.0 report generation."""
from pathlib import Path
from datetime import datetime

def write_markdown(state: dict, output_dir: str = "output") -> str:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = output_dir / f"report-{timestamp}.md"
    topics = state.get("topic_trends", [])
    opportunities = state.get("opportunities", [])
    lines = ["# BuilderDNA 2.0 Analysis Report\n", f"**Generated:** {datetime.now().isoformat()}\n"]
    lines.append("## Trends\n")
    for t in topics:
        lines.append(f"- **{t.get('topic', '')}**: {t.get('stage', '')} (velocity: {t.get('growth_velocity', 0):.1f})\n")
    lines.append("\n## Opportunities\n")
    for i, opp in enumerate(opportunities, 1):
        lines.append(f"### {i}. {opp.get('title', 'Untitled')}\n")
        lines.append(f"- Score: {opp.get('score', 0)}/10\n- Risk: {opp.get('risk', 'unknown')}\n")
    path.write_text("".join(lines))
    return str(path)

def write_json(state: dict, output_dir: str = "output") -> str:
    import json
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = output_dir / f"report-{timestamp}.json"
    path.write_text(json.dumps({"trends": state.get("topic_trends", []), "opportunities": state.get("opportunities", [])}, indent=2))
    return str(path)
