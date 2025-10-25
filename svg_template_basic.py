from pathlib import Path

OUTPUT_SVG = Path("img/template_basic.svg")

CELL_W = 20
CELL_H = 10
GAP = 0
LEFT_MARGIN = 35
TOP_MARGIN = 20

queues = [f"{i}.{j}" for i in range(1, 7) for j in range(1, 3)]  # 1.1–6.2
hours = [f"{h:02d}" for h in range(24)]

svg_w = LEFT_MARGIN + (CELL_W + GAP) * 48 + 20
svg_h = TOP_MARGIN + (CELL_H + GAP) * len(queues) + 20

parts = []
parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">')
parts.append('<style>text{font-family:sans-serif;font-size:8px;fill:#333}</style>')

# Верхній рядок — години
for h, hour in enumerate(hours):
    x = LEFT_MARGIN + h * (CELL_W * 2 + GAP * 2)
    parts.append(f'<text x="{x + CELL_W}" y="{TOP_MARGIN - 5}" text-anchor="middle">{hour}</text>')

# Таблиця
for qi, queue in enumerate(queues):
    y = TOP_MARGIN + qi * (CELL_H + GAP)
    # назва черги
    parts.append(f'<text x="{LEFT_MARGIN - 10}" y="{y + CELL_H - 2}" text-anchor="end">{queue}</text>')

    # клітинки 00:00–23:30
    for h in range(24):
        for half, label in enumerate(["a", "b"]):
            x = LEFT_MARGIN + (h * 2 + half) * (CELL_W + GAP)
            id_ = f"{queue}_{h:02d}{label}"
            parts.append(
                f'<rect id="{id_}" x="{x}" y="{y}" width="{CELL_W}" height="{CELL_H}" '
                f'fill="#eeeeee" stroke="#ccc" stroke-width="0.5"/>'
            )

parts.append("</svg>")
OUTPUT_SVG.write_text("\n".join(parts), encoding="utf-8")
print(f"[✓] SVG-шаблон створено: {OUTPUT_SVG}")
