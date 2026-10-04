"""Create a sample pptx exercising all 8 checker categories."""
import sys
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sample_deliverable.pptx")

prs = Presentation()
# Set metadata that should be flagged
prs.core_properties.author = "山田太郎(社内)"
prs.core_properties.last_modified_by = "鈴木一郎"
prs.core_properties.comments = "クライアント提出前にレビュー必須"
prs.core_properties.title = "XYZ社向け戦略提案_v3"

blank = prs.slide_layouts[6]

# Slide 1: URL contamination
s = prs.slides.add_slide(blank)
tb = s.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9), Inches(2))
tb.text_frame.text = (
    "市場規模: https://example.com/report?utm_source=chatgpt.com&utm_medium=claude\n"
    "参考: https://chatgpt.com/c/abc-123-def-456\n"
    "ソース: https://www.nikkei.com/article/foo?fbclid=IwAR1234"
)
# Speaker note (internal)
s.notes_slide.notes_text_frame.text = (
    "クライアントには言わないが、この数字の出典は実はChatGPTのハルシ。"
    "TODO: 本物の出典を探す。"
)

# Slide 2: AI traces + long text without citation
s = prs.slides.add_slide(blank)
tb = s.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9), Inches(4))
tb.text_frame.text = (
    "AIアシスタントとして、以下に市場動向をご説明します。\n"
    "**重要なポイント** は次の通りです：\n"
    "- 成長率は年率15%\n"
    "- 2024年1月時点の情報です\n"
    "As an AI, I cannot provide real-time data.\n"
    "🎯 📊 🚀 ✨ 💡"
)

# Slide 3: unit mixing + long text without citation
s = prs.slides.add_slide(blank)
tb = s.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9), Inches(5))
tb.text_frame.text = (
    "日本のサプライチェーン業界は、近年急速にデジタル化が進んでおり、"
    "特にAIを活用した需要予測やIoTを用いた在庫管理が主要企業で導入されている。"
    "これにより、業務効率が大幅に改善し、コスト削減と顧客満足度の向上を同時に"
    "実現している。売上高500億円、営業利益50百万円、R&D投資3,000千円。"
    "シェアは前年から5pp上昇し、成長率は15%に達した。"
)

# Slide 4: pie chart that doesn't sum to 100
s = prs.slides.add_slide(blank)
chart_data = CategoryChartData()
chart_data.categories = ["A", "B", "C", "D"]
chart_data.add_series("Share", (30, 25, 20, 15))  # sums to 90, not 100
s.shapes.add_chart(
    XL_CHART_TYPE.PIE, Inches(1), Inches(1), Inches(6), Inches(4.5),
    chart_data,
)
tb = s.shapes.add_textbox(Inches(0.5), Inches(6), Inches(9), Inches(0.8))
tb.text_frame.text = "市場シェア構成。出典: Euromonitor 2024"

# Slide 5: table with wrong row total
s = prs.slides.add_slide(blank)
rows, cols = 4, 4
left, top, width, height = Inches(0.5), Inches(1), Inches(9), Inches(3)
table_shape = s.shapes.add_table(rows, cols, left, top, width, height)
table = table_shape.table
# header
for c, t in enumerate(["製品", "Q1", "Q2", "合計"]):
    table.cell(0, c).text = t
# data
data = [
    ["A", "100", "120", "220"],
    ["B", "50",  "70",  "130"],  # correct
    ["C", "80",  "90",  "200"],  # WRONG: should be 170
]
for r, row in enumerate(data, start=1):
    for c, v in enumerate(row):
        table.cell(r, c).text = v

# Slide 6: dead URL
s = prs.slides.add_slide(blank)
tb = s.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9), Inches(2))
tb.text_frame.text = (
    "出典: https://this-domain-definitely-does-not-exist-12345.example/report.pdf"
)

# Slide 7: hidden slide
s = prs.slides.add_slide(blank)
tb = s.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9), Inches(1))
tb.text_frame.text = "このスライドは非表示（内部メモ）"
s.element.set("show", "0")

prs.save(str(out))
print(f"wrote {out}")
