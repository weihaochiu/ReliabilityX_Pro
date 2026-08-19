import logging
import numpy as np
from scipy import stats

from core.numeric_utils import parse_float_or_nan

logger = logging.getLogger(__name__)


class IVAnalysisUtils:
    """
    專用於太陽能電池 I-V / J-V 曲線分析的工具類別。

    設計原則：
    1. 先清理有限值、依電壓排序並對重複電壓做平均，降低掃描方向與雜訊影響。
    2. Voc / Isc 以線性內插取得，且優先找「最合理的主交點」，不是盲目取第一個過零點。
    3. MPP 僅在 Voc 與 Isc 所定義的發電工作區內搜尋，並同時兼容兩種常見電流極性。
    4. Rs / Rsh 以局部線性擬合估算，擬合窗口由資料範圍與局部點數共同決定。
    """

    _EMPTY_RESULT = {
        "Voc": np.nan,
        "Isc": np.nan,
        "Jsc": np.nan,
        "PCE": np.nan,
        "FF": np.nan,
        "Rs": np.nan,
        "Rsh": np.nan,
        "Pmpp": np.nan,
        "Vmpp": np.nan,
        "Impp": np.nan,
        "Jmpp": np.nan,
        "valid": False,
    }

    @staticmethod
    def analyze_scan(voltage, current, area_cm2, pin_mw_cm2=100.0):
        """
        對單條 I-V 掃描進行參數提取。

        Parameters
        ----------
        voltage : array-like
            電壓陣列，單位 V。
        current : array-like
            電流陣列，單位 A。
        area_cm2 : float
            有效面積，單位 cm^2。
        pin_mw_cm2 : float, default 100.0
            入射光功率密度，單位 mW/cm^2。

        Returns
        -------
        dict
            Voc, Isc, Jsc, PCE, FF, Rs, Rsh, Pmpp, Vmpp, Impp, Jmpp
        """
        area_cm2 = parse_float_or_nan(area_cm2, field_name="area_cm2", context="IVAnalysisUtils.analyze_scan", logger=logger, warn_invalid=True)
        if not np.isfinite(area_cm2) or area_cm2 <= 0:
            area_cm2 = np.nan

        v = IVAnalysisUtils._to_float_array(voltage, field_name="voltage")
        i = IVAnalysisUtils._to_float_array(current, field_name="current")

        if v.size == 0 or i.size == 0 or v.size != i.size:
            return IVAnalysisUtils._empty_result()

        v, i = IVAnalysisUtils._prepare_iv_data(v, i)
        if v.size < 2:
            return IVAnalysisUtils._empty_result()

        voc = IVAnalysisUtils._find_voc(v, i)
        isc = IVAnalysisUtils._find_isc(v, i)

        pmax, vmpp, impp = IVAnalysisUtils._find_mpp_in_generation_quadrant(v, i, voc=voc, isc=isc)

        jsc = (isc / area_cm2) if np.isfinite(area_cm2) and area_cm2 > 0 else np.nan
        jmpp = (impp / area_cm2) if np.isfinite(area_cm2) and area_cm2 > 0 else np.nan

        denominator = abs(voc) * abs(isc) if np.isfinite(voc) and np.isfinite(isc) else np.nan
        ff = (pmax / denominator) * 100.0 if np.isfinite(denominator) and denominator > 1e-15 else np.nan

        pin_w_cm2 = pin_mw_cm2 * 1e-3
        pin_total_w = pin_w_cm2 * area_cm2 if np.isfinite(area_cm2) else np.nan
        pce = (pmax / pin_total_w) * 100.0 if np.isfinite(pin_total_w) and pin_total_w > 0 else np.nan

        rs = IVAnalysisUtils._calculate_resistance_robust(v, i, target="voc", val=voc)
        rsh = IVAnalysisUtils._calculate_resistance_robust(v, i, target="isc", val=0.0)

        return {
            "Voc": float(voc),
            "Isc": float(isc),
            "Jsc": float(jsc),
            "PCE": float(max(pce, 0.0)) if np.isfinite(pce) else np.nan,
            "FF": float(max(ff, 0.0)) if np.isfinite(ff) else np.nan,
            "Rs": float(rs) if np.isfinite(rs) else np.nan,
            "Rsh": float(rsh) if np.isfinite(rsh) else np.nan,
            "Pmpp": float(max(pmax, 0.0)) if np.isfinite(pmax) else np.nan,
            "Vmpp": float(vmpp),
            "Impp": float(impp),
            "Jmpp": float(jmpp) if np.isfinite(jmpp) else np.nan,
            "valid": True,
        }

    @staticmethod
    def calculate_hysteresis_index(pce_fwd, pce_rev):
        """
        使用 (PCE_fwd - PCE_rev) / max(|PCE_fwd|, |PCE_rev|) 計算遲滯係數。
        """
        f_val = parse_float_or_nan(pce_fwd, field_name="pce_fwd", context="hysteresis", logger=logger, warn_invalid=True)
        r_val = parse_float_or_nan(pce_rev, field_name="pce_rev", context="hysteresis", logger=logger, warn_invalid=True)
        if not np.isfinite(f_val) or not np.isfinite(r_val):
            return np.nan
        max_pce = max(abs(f_val), abs(r_val))
        if max_pce == 0:
            return np.nan
        return (f_val - r_val) / max_pce

    @staticmethod
    def _empty_result():
        return dict(IVAnalysisUtils._EMPTY_RESULT)

    @staticmethod
    def _to_float_array(values, *, field_name: str = "value"):
        if values is None:
            return np.array([], dtype=float)
        parsed = []
        invalid_count = 0
        for idx, value in enumerate(values):
            number = parse_float_or_nan(
                value,
                field_name=f"{field_name}[{idx}]",
                context="IVAnalysisUtils",
                logger=logger,
                warn_invalid=False,
            )
            if not np.isfinite(number):
                invalid_count += 1
            parsed.append(number)
        if invalid_count:
            logger.warning("IVAnalysisUtils parsed %s invalid %s value(s) as NaN, not 0.0", invalid_count, field_name)
        return np.asarray(parsed, dtype=float)

    @staticmethod
    def _prepare_iv_data(v, i):
        """
        1. 移除 NaN / inf
        2. 依電壓排序
        3. 對重複電壓點以平均電流合併，避免 zero-crossing / regression 受重複點影響
        """
        finite_mask = np.isfinite(v) & np.isfinite(i)
        v = v[finite_mask]
        i = i[finite_mask]

        if v.size == 0:
            return np.array([], dtype=float), np.array([], dtype=float)

        sort_idx = np.argsort(v)
        v = v[sort_idx]
        i = i[sort_idx]

        unique_v, inverse = np.unique(v, return_inverse=True)
        if unique_v.size == v.size:
            return v, i

        sum_i = np.zeros_like(unique_v, dtype=float)
        count_i = np.zeros_like(unique_v, dtype=float)
        np.add.at(sum_i, inverse, i)
        np.add.at(count_i, inverse, 1.0)
        avg_i = sum_i / np.maximum(count_i, 1.0)
        return unique_v, avg_i

    @staticmethod
    def _find_voc(v, i):
        """找 I=0 時的 Voc。"""
        return IVAnalysisUtils._find_zero_crossing(target_array=v, reference_array=i, target_zero=0.0)

    @staticmethod
    def _find_isc(v, i):
        """找 V=0 時的 Isc。"""
        return IVAnalysisUtils._find_zero_crossing(target_array=i, reference_array=v, target_zero=0.0)

    @staticmethod
    def _find_zero_crossing(target_array, reference_array, target_zero=0.0):
        """
        線性內插尋找 reference_array = target_zero 時對應的 target_array。

        與舊版不同：
        - 不是直接取第一個過零點
        - 若有多個候選交點，優先取最接近 target_zero 的主交點
        - 若無過零，退回最近點估計
        """
        target_array = np.asarray(target_array, dtype=float)
        reference_array = np.asarray(reference_array, dtype=float)

        if target_array.size == 0 or reference_array.size == 0 or target_array.size != reference_array.size:
            return np.nan

        ref = reference_array - float(target_zero)

        exact_idx = np.where(np.isclose(ref, 0.0, atol=1e-15))[0]
        if exact_idx.size > 0:
            # 多個點剛好在零附近時，取 target 最接近中位數者，避免邊緣異常點
            exact_targets = target_array[exact_idx]
            center = np.median(exact_targets)
            best_local = int(np.argmin(np.abs(exact_targets - center)))
            return float(exact_targets[best_local])

        candidates = []
        for idx in range(ref.size - 1):
            x0 = ref[idx]
            x1 = ref[idx + 1]
            if np.isnan(x0) or np.isnan(x1):
                continue
            if x0 == 0 or x1 == 0:
                continue
            if x0 * x1 < 0:
                y0 = target_array[idx]
                y1 = target_array[idx + 1]
                crossing = y0 - x0 * (y1 - y0) / (x1 - x0)
                interval_score = min(abs(x0), abs(x1))
                target_proximity = abs(crossing)
                candidates.append((interval_score, target_proximity, float(crossing)))

        if candidates:
            # 先選 reference 最靠近 0 的交會區間；若並列，再選 target 值較接近 0 的交點
            candidates.sort(key=lambda x: (x[0], x[1]))
            return candidates[0][2]

        closest_idx = int(np.argmin(np.abs(ref)))
        return float(target_array[closest_idx])

    @staticmethod
    def _find_mpp_in_generation_quadrant(v, i, voc=None, isc=None):
        """
        尋找最大輸出功率點。

        規則：
        1. 先用 Voc 限制電壓搜尋區間在 0 到 Voc 之間（若 Voc 有效）
        2. 同時評估兩種極性：
           - 發電時 I <= 0, Pout = -V * I
           - 發電時 I >= 0, Pout =  V * I
        3. 若無法判定，退回有限資料中的最大 |V*I| 正功率候選，但仍限制在合理電壓範圍
        """
        v = np.asarray(v, dtype=float)
        i = np.asarray(i, dtype=float)

        if v.size == 0 or i.size == 0 or v.size != i.size:
            return np.nan, np.nan, np.nan

        valid_v_mask = np.isfinite(v) & np.isfinite(i)
        v = v[valid_v_mask]
        i = i[valid_v_mask]
        if v.size == 0:
            return np.nan, np.nan, np.nan

        if voc is None or not np.isfinite(voc) or abs(voc) < 1e-15:
            base_mask = v >= 0
        else:
            v_low = min(0.0, voc)
            v_high = max(0.0, voc)
            tol = max(1e-12, 0.01 * max(abs(voc), np.ptp(v) if v.size > 1 else abs(voc)))
            base_mask = (v >= v_low - tol) & (v <= v_high + tol)

        candidates = []

        p_out_neg_i = -v * i
        mask_neg = base_mask & (i <= 0) & (p_out_neg_i >= 0)
        if np.any(mask_neg):
            idx_local = int(np.argmax(p_out_neg_i[mask_neg]))
            v_sel = v[mask_neg]
            i_sel = i[mask_neg]
            p_sel = p_out_neg_i[mask_neg]
            candidates.append((float(p_sel[idx_local]), float(v_sel[idx_local]), float(i_sel[idx_local])))

        p_out_pos_i = v * i
        mask_pos = base_mask & (i >= 0) & (p_out_pos_i >= 0)
        if np.any(mask_pos):
            idx_local = int(np.argmax(p_out_pos_i[mask_pos]))
            v_sel = v[mask_pos]
            i_sel = i[mask_pos]
            p_sel = p_out_pos_i[mask_pos]
            candidates.append((float(p_sel[idx_local]), float(v_sel[idx_local]), float(i_sel[idx_local])))

        if candidates:
            best = max(candidates, key=lambda x: x[0])
            return best

        fallback_mask = base_mask & np.isfinite(v) & np.isfinite(i)
        if np.any(fallback_mask):
            p_mag = np.abs(v[fallback_mask] * i[fallback_mask])
            idx_local = int(np.argmax(p_mag))
            v_sel = v[fallback_mask]
            i_sel = i[fallback_mask]
            return float(p_mag[idx_local]), float(v_sel[idx_local]), float(i_sel[idx_local])

        return np.nan, np.nan, np.nan

    @staticmethod
    def _calculate_resistance_robust(v, i, target="voc", val=0.0):
        """
        以局部線性擬合估算阻抗。

        - Rsh：在 V ≈ 0 附近用 dI/dV 反推 |dV/dI|
        - Rs ：在 V ≈ Voc 附近用 dI/dV 反推 |dV/dI|

        擬合策略：
        1. 先用資料範圍建立局部窗口
        2. 若窗口點數不足，退回最近鄰點法
        3. 使用 scipy.stats.linregress 擬合 I-V 斜率
        """
        try:
            v = np.asarray(v, dtype=float)
            i = np.asarray(i, dtype=float)
            finite_mask = np.isfinite(v) & np.isfinite(i)
            v = v[finite_mask]
            i = i[finite_mask]

            if v.size < 2:
                return np.inf

            sort_idx = np.argsort(v)
            v = v[sort_idx]
            i = i[sort_idx]

            v_span = float(np.ptp(v)) if v.size > 1 else 0.0
            if v_span <= 0:
                return np.inf

            center = float(val if np.isfinite(val) else 0.0)

            if target == "voc":
                window = max(0.05 * v_span, 0.025, 0.03 * abs(center))
            else:
                window = max(0.05 * v_span, 0.025)
                center = 0.0

            mask = np.abs(v - center) <= window

            min_points = min(8, v.size)
            if np.sum(mask) < max(4, min_points // 2):
                dist = np.abs(v - center)
                idx = np.argsort(dist)[:max(4, min_points)]
                mask = np.zeros_like(v, dtype=bool)
                mask[idx] = True

            v_fit = v[mask]
            i_fit = i[mask]

            if v_fit.size < 2 or np.allclose(v_fit, v_fit[0]):
                return np.inf

            slope, _, _, _, _ = stats.linregress(v_fit, i_fit)
            if np.isclose(slope, 0.0, atol=1e-15):
                return np.inf

            resistance = abs(1.0 / slope)
            return float(resistance) if np.isfinite(resistance) else np.inf
        except Exception:
            return np.inf


def _standardize_units(results):
    """Apply reporting units while preserving validity booleans.

    Args:
        results: Analysis result dictionary in SI-scale internal units.

    Returns:
        The same dictionary with standardized reporting units and unchanged
        boolean ``valid_*`` flags.

    Notes:
        Currents are positive mA, Rsh is kOhm, Pmpp is positive W, and PCE/FF
        remain percentage values. Validity flags are metadata and must never be
        numerically coerced to ``1.0`` or ``0.0``.
    """
    for key, value in list(results.items()):
        base_key = key.split('_')[0]
        if base_key == "valid":
            results[key] = bool(value)
            continue

        number = parse_float_or_nan(value, field_name=key, context="standardize_units", logger=logger, warn_invalid=True)
        if not np.isfinite(number):
            results[key] = np.nan
            continue

        # Strip suffix like _F_Raw to get the base parameter key
        if base_key in ["Isc", "Impp", "Jsc", "Jmpp"]:
            results[key] = abs(number * 1000.0)
        elif base_key == "Rsh":
            results[key] = number / 1000.0 if number != 0 else 0
        elif base_key == "Pmpp":
            results[key] = abs(number)
        elif base_key in ["PCE", "FF"]:
            # Already calculated as percent (0-100 scale); ensure positive.
            results[key] = abs(number)
        else:
            results[key] = number

    return results


def calculate_iv_parameters(fwd_raw_data, rev_raw_data, area_cm2):
    """
    同時處理 forward / reverse 掃描的原始與校正數據，並回傳整合結果。
    """

    def _safe_extract(data_list, key):
        if not data_list:
            return np.array([], dtype=float)
        values = []
        for row in data_list:
            value = parse_float_or_nan(row.get(key, np.nan), field_name=key, context="calculate_iv_parameters", logger=logger, warn_invalid=True)
            values.append(value)
        return np.asarray(values, dtype=float)

    v_f_raw = _safe_extract(fwd_raw_data, "v_src")
    i_f_raw = _safe_extract(fwd_raw_data, "i_msd")
    v_f_corr = _safe_extract(fwd_raw_data, "v_corr")
    i_f_corr = _safe_extract(fwd_raw_data, "i_corr")

    v_r_raw = _safe_extract(rev_raw_data, "v_src")
    i_r_raw = _safe_extract(rev_raw_data, "i_msd")
    v_r_corr = _safe_extract(rev_raw_data, "v_corr")
    i_r_corr = _safe_extract(rev_raw_data, "i_corr")

    f_raw_res = IVAnalysisUtils.analyze_scan(v_f_raw, i_f_raw, area_cm2) if v_f_raw.size else IVAnalysisUtils._empty_result()
    r_raw_res = IVAnalysisUtils.analyze_scan(v_r_raw, i_r_raw, area_cm2) if v_r_raw.size else IVAnalysisUtils._empty_result()
    f_corr_res = IVAnalysisUtils.analyze_scan(v_f_corr, i_f_corr, area_cm2) if v_f_corr.size else IVAnalysisUtils._empty_result()
    r_corr_res = IVAnalysisUtils.analyze_scan(v_r_corr, i_r_corr, area_cm2) if v_r_corr.size else IVAnalysisUtils._empty_result()

    hi_raw = IVAnalysisUtils.calculate_hysteresis_index(
        f_raw_res.get("PCE", 0.0),
        r_raw_res.get("PCE", 0.0),
    )
    hi_corr = IVAnalysisUtils.calculate_hysteresis_index(
        f_corr_res.get("PCE", 0.0),
        r_corr_res.get("PCE", 0.0),
    )

    def prefix_keys(data, prefix):
        return {f"{key}_{prefix}": value for key, value in data.items()}

    area_value = parse_float_or_nan(area_cm2, field_name="area_cm2", context="calculate_iv_parameters", logger=logger, warn_invalid=True)

    results = {
        **prefix_keys(f_raw_res, "F_Raw"),
        **prefix_keys(r_raw_res, "R_Raw"),
        **prefix_keys(f_corr_res, "F_Corr"),
        **prefix_keys(r_corr_res, "R_Corr"),
        "HI_Raw": hi_raw,
        "HI_Corr": hi_corr,
        "area": area_value if np.isfinite(area_value) else np.nan,
    }
    
    return _standardize_units(results)
