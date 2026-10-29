"""チュートリアルの達成状況と、入力ごとの長押し時間を管理する。"""

from dataclasses import dataclass, field
from enum import IntEnum


SKIP_HOLD_TIME = 2.0
MOVE_DISTANCE = 24.0
PHASE_READ_TIME = 1.0


class TutorialStep(IntEnum):
    MOVE = 0
    FIRE = 1
    ONE_ENEMY = 2
    BOMB = 3
    DAMAGE = 4
    PHASES = 5


INSTRUCTIONS = (
    "← → または A・D で左右に移動してください",
    "Spaceキーで弾を撃ってください",
    "敵を1機撃墜してください",
    "Bキーでボムを使って敵を倒してください",
    "敵弾に当たり、ハートの変化を見てください",
    "本編は全3フェーズです",
)

STEP_TITLES = ("移動方法", "発射方法", "撃墜", "ボムの使い方", "被弾", "フェーズ構成")

EXPLANATIONS = (
    ("自機を左右に動かして敵弾を避けます",),
    ("長押しすると続けて弾を撃てます",),
    ("弾を当てると敵を撃墜できます", "落下した敵との衝突で連鎖も起こせます"),
    ("周囲の敵をまとめて倒し、敵弾も消します", "本編のボムは各フェーズ1・2・3発です"),
    ("被弾するとハートが1つ減ります", "点滅中の約1.8秒間は続けて被弾しません", "ハートが0になるとゲームオーバーです"),
    ("敵を全滅させると次のフェーズに進みます",),
)


@dataclass
class TutorialProgress:
    step: TutorialStep = TutorialStep.MOVE
    left_distance: float = 0.0
    right_distance: float = 0.0
    shot_fired: bool = False
    bomb_launched: bool = False
    damage_taken: bool = False
    elapsed: float = 0.0
    damage_shot_timer: float = 1.5
    complete: bool = False
    blocked_keys: set[int] = field(default_factory=set)
    awaiting_pad_sample: bool = True
    block_pad_fire: bool = False
    block_pad_movement: bool = False
    hold_times: dict[int, float] = field(default_factory=dict)

    @property
    def enemy_count(self) -> int:
        return {TutorialStep.ONE_ENEMY: 1, TutorialStep.BOMB: 4}.get(self.step, 0)

    @property
    def allows_fire(self) -> bool:
        return self.step in (TutorialStep.FIRE, TutorialStep.ONE_ENEMY)

    @property
    def skip_progress(self) -> float:
        return min(1.0, max(self.hold_times.values(), default=0.0) / SKIP_HOLD_TIME)

    def update_holds(self, dt: float, keys: set[int]) -> bool:
        """入力をまたいで時間を足さず、同じ入力の継続時間だけを数える。"""
        self.hold_times = {key: self.hold_times.get(key, 0.0) + dt for key in keys}
        return self.skip_progress >= 1.0

    def record_movement(self, distance: float) -> None:
        self.left_distance += max(0.0, -distance)
        self.right_distance += max(0.0, distance)

    @property
    def movement_complete(self) -> bool:
        return self.left_distance >= MOVE_DISTANCE and self.right_distance >= MOVE_DISTANCE
