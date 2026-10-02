"""偏航系统业务规则：状态流转、字段校验与筛选口径都收在这里。

状态只能沿 STATUS_ORDER 一步步推进：
待润滑 → 运行正常 → 对风偏差大 → 已锁定。
跳步一律拦截，并说明卡在哪一项；对同一状态重复提交视为幂等，只保留原记录、不新增。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "yaw"
REQUIRED_FIELDS = ["系统编号", "所属机组", "偏航方式"]
STATUS_ORDER = ["待润滑", "运行正常", "对风偏差大", "已锁定"]
# 每个动作对应状态序列中的下一步；只有处在“当前状态”时才能执行
ACTION_RULES = {
    "提交润滑": ("待润滑", "运行正常"),
    "登记对风偏差": ("运行正常", "对风偏差大"),
    "锁定偏航": ("对风偏差大", "已锁定"),
}
DEVIATION_FIELD = "对风偏差"
STATUS_FIELD = "偏航状态"


def sync_view(row: dict[str, Any]) -> None:
    """让展示字段与状态机口径保持一致：列表、详情、汇总都只读同一份状态。"""
    status = str(row.get("status") or STATUS_ORDER[0])
    row[STATUS_FIELD] = status
    row["pending"] = status != STATUS_ORDER[-1]
    row["abnormal"] = status == "对风偏差大"


class YawService:
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
            sync_view(row)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("系统编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is not None:
            sync_view(entry)
        return entry

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        sync_view(entry)
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"偏航系统 {entry_id} 不存在或已归档"
        sync_view(entry)
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于偏航系统可执行范围"

        required_status, target = ACTION_RULES[action]
        current = str(entry.get("status"))

        # 已锁定是终态：润滑、对风偏差等任何提交都不再接受
        if current == STATUS_ORDER[-1] and target != STATUS_ORDER[-1]:
            return None, f"偏航系统已锁定，不再接受{action}；如需处理请先解锁"

        if current == target:
            # 重复提交同一动作：保持原记录，不产生新状态/新记录
            return entry, f"偏航系统已是「{target}」状态，无需重复{action}"

        if current != required_status:
            # 跳步拦截：讲清楚当前卡在哪一项、下一步该做什么
            return None, (
                f"状态不能从「{current}」直接{action}："
                f"该操作要求当前为「{required_status}」，"
                f"请先完成「{self._next_action(current)}」"
            )

        if action == "登记对风偏差":
            deviation = str((values or {}).get(DEVIATION_FIELD) or "").strip()
            if not deviation:
                return None, f"请填写{DEVIATION_FIELD}后再登记，未填写的偏差不予登记"
            entry[DEVIATION_FIELD] = deviation

        entry["status"] = target
        sync_view(entry)
        return entry, f"偏航系统已{action}"

    @staticmethod
    def _next_action(status: str) -> str:
        """返回从指定状态继续推进时该执行的动作名，用于跳步提示。"""
        for action, (required_status, _target) in ACTION_RULES.items():
            if required_status == status:
                return action
        return "当前状态后续处理"
