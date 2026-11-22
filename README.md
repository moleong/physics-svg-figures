# physics-svg-figures

物理／STEM 內聯 SVG 插圖技能：負責圖內的物理語義、電路拓撲、參數化幾何、符號、標註、語義色、唯一 ID 與 viewBox 驗收。HTML 頁面尺寸、外距、響應式及列印由 `teaching-ppt` 等宿主技能負責。

## 內容

- `SKILL.md`：共同核心、四層驗收、工作流程與共用工具。
- `references/mechanics.md`：受力、參考系、滑輪、繩、斜面與接觸。
- `references/circuits.md`：電路生成器、電源、元件、節點與變阻器。
- `references/graphs.md`：定量／定性圖象、公式取樣、關鍵點與刻度。
- `references/integration-contract.md`：明暗主題、唯一 ID、回交格式及宿主驗收。
- `assets/circuit.mjs`：靜態電路 SVG 生成器。
- `assets/svg_label_check.py`：text×線、text×text、viewBox 與豁免理由檢查。
- `assets/trim-viewbox.py`：瀏覽器量測後只整理 viewBox；支援刻意留白保留。

## 快速使用

```bash
# 電路範例
node assets/circuit.mjs assets/circuit-example.mjs --html > /tmp/circuit-example.html

# 標註檢查；距離以 400 單位參考圖寬表示
python3 assets/svg_label_check.py 成品.html --threshold 6 --reference-width 400

# viewBox 量測與回寫
python3 assets/trim-viewbox.py gen 成品.html -o /tmp/svg-harness.html
python3 assets/trim-viewbox.py apply bbox.txt 成品.html
```

刻意接觸須同時寫 `data-check="ignore"` 和 `data-check-reason="具體理由"`；刻意留白或共同對齊則在 SVG 加 `data-viewbox="preserve"`。工具通過不代表物理語義正確，仍須按 `SKILL.md` 做對抗式審查及實際宿主渲染。

## 安裝

把本目錄複製到 `~/.kimi-code/skills/physics-svg-figures/`，或安裝封裝後的 `.skill` 檔。需要物理插圖的 HTML 教材應同時載入本技能與宿主技能。
