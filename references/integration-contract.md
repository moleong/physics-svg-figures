# 繪圖與宿主頁面的整合契約

## 責任邊界

- **本 skill 負責**：SVG 內的物理／拓撲、幾何、符號、圖內標註、語義色、唯一 ID、viewBox 內容邊界及繪圖驗收。
- **宿主 skill 負責**：頁面主題色值、圖片外距、顯示寬度、響應式、分頁列印及與其他頁面元素的關係。
- 宿主不得覆寫圖內幾何或自行解釋物理規則；本 skill 不規定頁面欄寬或導航。

## 宿主提供的輸入

- 完整原圖及／或題設；
- `light`、`dark` 或 `print` 使用場景；
- 是否多圖並排、共同比例或對齊；
- 是否需要離線內聯 SVG。

## 回交的 SVG

使用：

```html
<svg class="diagram" viewBox="..." xmlns="http://www.w3.org/2000/svg">
  ...
</svg>
```

- 不在 SVG 寫死 `width:100%`、`max-width` 或頁面外距；由宿主設定。
- 每幅圖的 marker／pattern ID 加獨特前綴；不得依賴其他 SVG 的 `<defs>`。
- 保留語義色變數及淺色 fallback，確保獨立打開仍可顯示。
- 刻意留白或共同對齊時加 `data-viewbox="preserve"`。
- 所有工具豁免同時附 `data-check-reason`。

## 語義色接口

圖內使用下列變數；括號內是淺色 fallback：

| 變數 | 用途 |
|---|---|
| `--figure-structure`（`#333`） | 導線、支架、一般結構 |
| `--figure-fill`（`#fff`） | 符號內填充及遮罩 |
| `--figure-gravity`（`#333`） | 重力 |
| `--figure-motion`（`#e74c3c`） | 加速度／運動 |
| `--figure-force`（`#2980b9`） | 張力／分量 |
| `--figure-guide`（`#7f8c8d`） | 輔助線 |
| `--figure-current`（`#d63384`） | 電流箭頭 |
| `--figure-before`（`#3498db`） | 改裝前 |
| `--figure-after`（`#e74c3c`） | 改裝後 |

深色宿主至少覆寫 `--figure-structure`、`--figure-gravity`、`--figure-guide` 和 `--figure-fill`；其餘顏色也須通過實際對比檢查。列印深色簡報時，切回淺色紙面值。

## 宿主尺寸與驗收

講義可沿用 `max-width:{viewBox寬÷16}em` 作預設，但這是**頁面排版慣例**，不是繪圖正確性的條件。容器寬度成為限制時，裁 viewBox 可能令內容放大，不得宣稱「只裁不放大」必然成立。

交付前在宿主頁面檢查：

- 明暗主題及列印的線條、填充、箭頭和文字對比；
- 手機、平板、寬屏縮放後的實際標籤淨空；
- 多幅 SVG 的 ID 無衝突；
- 無非預期橫向捲軸、裁切或頁面重排；
- 圖已先通過本 skill 驗收，再以宿主渲染結果作整合終裁。
