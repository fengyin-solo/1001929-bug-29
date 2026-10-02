"""偏航系统业务规则：状态流转、字段校验与筛选口径都收在这里。

状态只能沿 待润滑 → 运行正常 → 对风偏差大 → 已锁定 单向往前推进，每一步
对应一个动作，跳步、回退都会被拦下并说明卡在哪一项；已锁定是终态，不再
接受润滑与对风偏差提交。列表、明细、概览看到的偏航状态都以 status 为唯一
口径，派生字段（偏航状态展示值、pending、abnormal）始终与它对齐。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "yaw"
REQUIRED_FIELDS = ["系统编号", "所属机组", "偏航方式"]
STATUS_ORDER = ["待润滑", "运行正常", "对风偏差大", "已锁定"]
LOCKED_STATUS = STATUS_ORDER[-1]
ABNORMAL_STATUS = "对风偏差大"
DISPLAY_STATUS_FIELD = "偏航状态"
DEVIATION_FIELD = "对风偏差"
LUBRICATION_DATE_FIELD = "上次润滑日"
ACTION_RULES = {
    "提交润滑": "运行正常",
    "登记对风偏差": ABNORMAL_STATUS,
    "锁定偏航": LOCKED_STATUS,
}
# 状态 → 到达该状态所需的动作，跳步提示时用来指明卡在哪一项
STATUS_ACTIONS = {target: action for action, target in ACTION_RULES.items()}


class YawService:
    def __init__(self) -> None:
        # 启动时把示例数据的派生字段与 status 对齐，概览页待处理量不再残留旧标记
        for row in store.rows(MODULE):
            self._sync_derived(row)

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        for row in rows:
            self._sync_derived(row)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("系统编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._sync_derived(entry)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        rows.append(entry)
        return self._sync_derived(entry), []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"偏航系统 {entry_id} 不存在或已归档"
        self._sync_derived(entry)
        if action not in ACTION_RULES:
            return None, (
                f"动作「{action}」不属于偏航系统可执行范围，"
                f"可执行：提交润滑、登记对风偏差、锁定偏航"
            )

        current = str(entry["status"])
        target = ACTION_RULES[action]
        current_index = STATUS_ORDER.index(current)
        target_index = STATUS_ORDER.index(target)
        chain = " → ".join(STATUS_ORDER)

        # 终态保护：锁定后不再接受润滑与对风偏差提交，也不能重新锁定
        if current == LOCKED_STATUS:
            return None, (
                f"偏航系统已锁定，终态「{LOCKED_STATUS}」不再接受「{action}」，"
                "润滑与对风偏差提交均已关闭"
            )
        # 幂等：重复提交同一动作只保留一条记录（状态不变，不追加任何东西）
        if target_index == current_index:
            return entry, (
                f"偏航系统当前已是「{current}」，「{action}」此前已提交，"
                "重复提交不再生成新记录"
            )
        # 回退拦截：状态序列只许向前
        if target_index < current_index:
            return None, (
                f"状态只能按 {chain} 单向往前推进；当前为「{current}」，"
                f"不能「{action}」回退到「{target}」"
            )
        # 跳步拦截：点名卡在哪一项
        if target_index > current_index + 1:
            blocker = STATUS_ORDER[current_index + 1]
            blocker_action = STATUS_ACTIONS[blocker]
            return None, (
                f"当前卡在「{current}」：需先「{blocker_action}」流转到「{blocker}」，"
                f"才能「{action}」；已拦截直接跳到「{target}」的操作"
            )

        # 合法的单步推进
        if action == "登记对风偏差":
            deviation = str(values.get(DEVIATION_FIELD) or "").strip()
            if deviation:
                entry[DEVIATION_FIELD] = deviation
        if action == "提交润滑":
            lubrication_day = str(values.get(LUBRICATION_DATE_FIELD) or "").strip()
            entry[LUBRICATION_DATE_FIELD] = lubrication_day or date.today().isoformat()

        entry["status"] = target
        self._sync_derived(entry)
        return entry, f"偏航系统已{action}，状态由「{current}」推进到「{target}」"

    @staticmethod
    def _sync_derived(entry: dict[str, Any]) -> dict[str, Any]:
        """让偏航状态展示值、待处理/异常标记全部与 status 同源。"""
        status = entry.get("status")
        if status not in STATUS_ORDER:
            status = STATUS_ORDER[0]
            entry["status"] = status
        entry[DISPLAY_STATUS_FIELD] = status
        entry["pending"] = status != LOCKED_STATUS
        entry["abnormal"] = status == ABNORMAL_STATUS
        return entry
