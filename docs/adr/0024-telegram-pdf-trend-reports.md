# ADR-0024: Telegram Trend Notifications Use Active-Scope PDF Reports

- Status: Accepted
- Date: 2026-04-01

## Context

先前 Telegram 趨勢通知有三個主要問題：

1. 推播內容容易被誤解成來自 `TrendChartWindow` 目前畫面
2. 同一個使用者/專案若勾選多個 metric，會一次收到大量獨立圖片
3. 若要保留高解析度並加入文字說明，單張 PNG 不適合長期存檔與閱讀

使用者明確要求：
- 分組模式只需要「整體」與「依使用者+專案」
- 只推送目前量測中的 active scope
- Telegram 改推送 PDF 報告
- PDF 採每頁一張圖
- 若有環境資料，則每頁圖下方都要有環境子圖；若無資料則不顯示

## Decision

我們決定：

1. 將 Telegram 趨勢推播與 `TrendChartWindow` 的 UI 狀態解耦
2. 使用 `core/trend_scope_utils.py` 統一 active scope / group 規則
3. 在 `NotificationManager` 新增 PDF report dispatch 流程
4. 在 `TrendSnapshotRenderer` 新增多頁 PDF 報告輸出能力
5. 在 `notification_tab.py` 提供 Telegram 專用設定：
   - `整體`
   - `依使用者+專案`
   - `以 PDF 報告推送（每頁一張圖）`

## Consequences

### Positive

- Telegram 推播規則更清楚，不再受 Trend 視窗畫面影響
- 同一個群組只會收到一份 PDF，不會被多張圖片轟炸
- PDF 能保留高解析度，適合手機與電腦閱讀，也利於存檔
- 每頁都可加入頁首說明，使報告更正式完整
- 環境子圖與主圖共 X 軸，判讀更直觀

### Negative

- renderer 與通知中心邏輯變得更複雜
- PDF 生成時間與檔案大小會高於單張 PNG
- 若 metric 很多，PDF 頁數也會增加

## Implementation Notes

- `trend_pdf_enabled=True` 時，schedule timer 會為每個群組建立一份 PDF
- PDF 每頁一個 metric，主圖格式沿用 Trend Plot 的主圖 + 環境子圖概念
- 環境子圖不再由通知頁單獨勾選；改成有 `temp`/`hum` 資料就自動附加
- 舊有 PNG 推播邏輯保留為相容模式
