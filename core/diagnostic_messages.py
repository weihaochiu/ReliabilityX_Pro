"""OI-057: framework-free operator explanations, evidence and safety summaries."""

import json
import traceback


class DiagnosticValidationError(ValueError):
    """Scientific validation failure with an explicit diagnostic category."""

    def __init__(self, code, message):
        """Capture a stable code without parsing user-facing text.

        Args:
            code: Failure category.
            message: Technical/scientific explanation.
        """
        super().__init__(message)
        self.code = code


STAGES = {
    "ready": "檢查硬體與通道設定", "smu_off": "確認 SMU 輸出關閉",
    "relay_reset": "確認 Relay 全部關閉", "relay_pair": "建立並確認選定 Relay 路徑",
    "smu_setup": "設定並讀回確認 SMU 輸出參數", "smu_on": "開啟並確認 SMU 輸出",
    "sample": "取得實測電壓／電流", "compliance": "讀取限壓／限流狀態",
    "qualification": "檢查實測值是否可用", "cleanup": "關閉輸出並清理 Relay",
    "save": "儲存校正結果", "polarity": "檢查受光太陽能電池極性",
    "chamber_open": "開啟 Chamber 序列埠", "chamber_telemetry": "讀取溫濕度箱數據",
}

ADVICE = {
    "smu_timeout": (
        "SMU 沒有在等待時間內回覆",
        "可能是查詢指令與韌體不相容、儀器忙碌或通訊中斷；不能據此判定夾子開路。",
        ["先確認 SMU 面板 OUTPUT OFF，再檢查連線及是否有其他軟體操作儀器。",
         "重新連線後若仍停在同一指令，複製診斷資料確認韌體／指令相容性；不要跳過驗證或持續重試。"],
    ),
    "smu_communication": (
        "SMU 設定或讀值未確認",
        "可能是連線中斷、儀器拒絕設定、回覆格式或設定讀回不符，不能當成開路結果。",
        ["先確認面板 OUTPUT OFF；檢查 IP/VISA、通訊線與儀器狀態。",
         "查看技術詳細資料中的指令、回覆與設定值；不要直接改接夾子來排除通訊問題。"],
    ),
    "relay": (
        "Relay 路徑未確認",
        "控制指令未成功或完整狀態讀回與預期不符；不能確認量測接到了選定的兩路。",
        ["先確認 SMU OUTPUT OFF，再檢查 Relay 的 USB、外部供電、COM 埠與接線。",
         "核對實體 Relay 編號；控制器讀回只代表邏輯狀態，不能證明接點實際導通。"],
    ),
    "rline_open": (
        "線阻無法成立：可能開路、接觸不良或阻值過高",
        "已取得量測，但限壓或實測電流未符合校正條件，不能把這筆數字當成線路電阻。",
        ["若你刻意讓兩夾分開，拒絕校正是預期結果，不代表程式沒有執行。",
         "若要校正：先確認 OUTPUT OFF、移除電池，再將選定正負兩夾互夾；檢查接觸面與線材後重測。"],
    ),
    "invalid_sample": (
        "儀器讀值無效或狀態未知",
        "沒有足夠可信的電壓、電流或保護狀態，無法判斷線路是否正常。",
        ["保持量測停止，確認輸出關閉後重新連線。", "提供原始 V/I、保護旗標與 TX/RX；不要把無效讀值當成 0 Ω。"],
    ),
    "cleanup": (
        "量測已停止，但安全清理未確認",
        "SMU OFF 或 Relay 全關未獲確認；不能宣稱設備已安全，也不能接受校正結果。",
        ["先在儀器面板確認或手動關閉 OUTPUT，未確認前不要換線或碰觸端子。",
         "依現場安全程序檢查 Relay 狀態與通訊，再恢復操作。"],
    ),
    "save": (
        "校正結果未能儲存",
        "硬體量測結果與寫檔是不同步驟；本次未確認校正檔更新成功。",
        ["檢查儲存位置、寫入權限、磁碟空間及檔案是否被其他軟體占用。",
         "保留診斷資料；未確認儲存成功前不要使用本次校正。"],
    ),
    "polarity": (
        "太陽能電池極性／連線未通過",
        "可能反接、開路、光照不足、訊號太小或觸發限流；沒有通過就不開始正式掃描。",
        ["先確認 OUTPUT OFF，再檢查正負夾、光源與電池接觸。",
         "核對日誌的帶符號電流、電壓及限流旗標；不要任意放寬門檻。"],
    ),
    "chamber_open": (
        "Chamber 通訊埠未開啟",
        "可能選錯 COM、轉接器未插入、驅動未安裝或埠被其他軟體占用。",
        ["選擇實際 USB-RS485 轉接器的 COM，關閉占用該埠的軟體。",
         "確認驅動與通訊設定；本次尚不能宣稱序列埠已成功開啟。"],
    ),
    "chamber_telemetry": (
        "Chamber 通訊埠已開啟，但沒有有效溫濕度回覆",
        "開啟 COM 不代表接到溫濕度箱；可能埠、站號、接線、Remote 或通訊格式不符。",
        ["核對 USB-RS485 實際 COM、站號、baud、8E1 與通訊啟用設定。",
         "依設備安全程序檢查 RS485 A/B 與 FCS；查看 TX/RX 詳細資料，不自動更換站號或 COM。"],
    ),
    "ready": (
        "無法開始：硬體未就緒、參數無效或已有量測執行中",
        "前置檢查未通過，本次尚未開始取樣。",
        ["先完成硬體連線並確認 Relay pair，等待現有量測結束。", "查看詳細原因，不要重複點擊量測。"],
    ),
}


def build_diagnostic_report(error, *, operation="線阻量測", stage="ready", facts=None, code=None):
    """Build a JSON-safe report from evidence, never inferring cleanup success.

    Args:
        error: Exception or technical explanation.
        operation: User-facing operation name.
        stage: Last attempted stage, not a claimed success.
        facts: Optional verified progress, samples and cleanup facts.
        code: Explicit category when the caller already knows it.

    Returns:
        Report with summary for users and copyable technical details.
    """
    facts = dict(facts or {})
    category = code or getattr(error, "code", None)
    if category not in ADVICE:
        category = ("relay" if stage.startswith("relay") else
                    "smu_communication" if stage.startswith("smu") else
                    "invalid_sample" if stage in {"sample", "compliance", "qualification"} else
                    stage if stage in ADVICE else "ready")
    title, explanation, actions = ADVICE[category]
    state = lambda key: "已確認" if facts.get(key) is True else "未確認"
    progress = []
    if "relay_pair_confirmed" in facts:
        progress.append("選定 Relay：" + state("relay_pair_confirmed") + "（僅控制器狀態，不代表接點導通）")
    if "output_attempted" in facts:
        progress.append("SMU 輸出：" + (
            "尚未送出 ON；尚未進入通電量測" if not facts["output_attempted"]
            else "已嘗試送出 ON；" + state("output_on_confirmed") + "開啟狀態"))
    if "sample_acquired" in facts:
        progress.append("實測 V/I：" + ("已取得，仍須通過有效性檢查" if facts["sample_acquired"] else "尚未取得；不能判定開路或阻值"))
    safety = "SMU OFF：" + state("smu_off_confirmed") + "；Relay 全關：" + state("relay_off_confirmed")
    if operation.startswith("Chamber"):
        safety = "本次僅測試通訊，未確認溫濕度控制就緒。"
    safety_warning = ""
    if facts.get("cleanup_attempted") and not all(facts.get(key) is True for key in ("smu_off_confirmed", "relay_off_confirmed")):
        safety_warning = "安全提醒：關閉狀態未完全確認，請先檢查儀器面板，不要換線。\n"
    outcome = "本次未確認校正檔更新成功。" if operation == "儲存線阻校正" else (
        "本次未更新線阻校正。" if operation == "線阻量測" else "本次操作未成功，請勿視為硬體就緒。")
    stage_label = "確認 SMU 10 mA／1.5 V 設定" if operation == "線阻量測" and stage == "smu_setup" else STAGES.get(stage, stage)
    summary = (f"{safety_warning}停止步驟：{stage_label}\n{explanation}\n\n"
               + "\n".join(progress) + ("\n\n" if progress else "") + outcome
               + f"\n{safety}\n\n建議處理：\n" + "\n".join(f"{i}. {text}" for i, text in enumerate(actions, 1)))
    evidence = {"operation": operation, "stage": stage, "code": category,
                "command": getattr(error, "command", None), "response": getattr(error, "response", None),
                "error": str(error), "facts": facts}
    detail = json.dumps(evidence, ensure_ascii=False, indent=2, default=str)
    if isinstance(error, BaseException):
        detail += "\n" + "".join(traceback.format_exception(type(error), error, error.__traceback__))
    return {"title": title, "summary": summary, "details": detail, **evidence}
