"""SDLの共通ボタン割り当てを使ったゲームパッド入力。PS3を含む対応機種を自動認識する。"""

from dataclasses import dataclass

import pygame
from pygame._sdl2 import controller as sdl_controller


STICK_DEADZONE = 0.18
MENU_STICK_THRESHOLD = 0.55


@dataclass(frozen=True)
class GamepadInput:
    movement: tuple[float, float] = (0.0, 0.0)
    fire: bool = False
    precise: bool = False
    actions: tuple[str, ...] = ()
    bomb_held: bool = False


def stick_movement(x: float, y: float) -> pygame.Vector2:
    """中央付近の揺れを無視し、残りの範囲を0〜1へ滑らかに割り当てる。"""
    vector = pygame.Vector2(x, y)
    length = vector.length()
    if length <= STICK_DEADZONE:
        return pygame.Vector2()
    return vector / length * min(1.0, (length - STICK_DEADZONE) / (1 - STICK_DEADZONE))


class Gamepad:
    def __init__(self) -> None:
        self.device = None
        self.name = ""
        self.previous_buttons: set[int] = set()
        self.previous_menu_direction = 0
        pygame.joystick.init()
        sdl_controller.init()
        self.connect()

    @property
    def hint(self) -> str:
        if "ps3" in self.name.lower() or "playstation" in self.name.lower():
            return "X:FIRE O:BOMB L1/R1:SLOW"
        return "A:FIRE B:BOMB LB/RB:SLOW"

    def connect(self) -> None:
        """未接続なら、最初に見つかった対応コントローラーを開く。"""
        if self.device is not None:
            return
        for index in range(sdl_controller.get_count()):
            try:
                if not sdl_controller.is_controller(index):
                    continue
                self.device = sdl_controller.Controller(index)
                self.name = self.device.name
                # 接続時点の押下を初期値にする。押しっぱなしを新規入力にしない。
                pygame.event.pump()
                self.previous_buttons = self._read_buttons()
                return
            except pygame.error:
                # 列挙中に抜かれた場合は、次のフレームで改めて探す。
                self.disconnect()
                continue

    def _read_buttons(self) -> set[int]:
        return {
            button for button in range(pygame.CONTROLLER_BUTTON_MAX)
            if self.device.get_button(button)
        }

    def disconnect(self) -> None:
        if self.device is not None:
            try:
                self.device.quit()
            except pygame.error:
                pass
        self.device = None
        self.name = ""
        self.previous_buttons.clear()
        self.previous_menu_direction = 0

    def poll(self) -> GamepadInput:
        """イベントを取得した後に呼び、押し続ける入力と押した瞬間の操作を分ける。"""
        if self.device is None:
            self.connect()
            if self.device is None:
                return GamepadInput()
        try:
            if not self.device.attached():
                raise pygame.error("Controller disconnected")
            x = self.device.get_axis(pygame.CONTROLLER_AXIS_LEFTX) / 32767
            y = self.device.get_axis(pygame.CONTROLLER_AXIS_LEFTY) / 32767
            buttons = self._read_buttons()
        except pygame.error:
            self.disconnect()
            return GamepadInput(actions=("disconnected",))

        dpad = pygame.Vector2(
            int(pygame.CONTROLLER_BUTTON_DPAD_RIGHT in buttons) - int(pygame.CONTROLLER_BUTTON_DPAD_LEFT in buttons),
            int(pygame.CONTROLLER_BUTTON_DPAD_DOWN in buttons) - int(pygame.CONTROLLER_BUTTON_DPAD_UP in buttons),
        )
        movement = dpad.normalize() if dpad.length_squared() else stick_movement(x, y)
        pressed = buttons - self.previous_buttons
        actions = []
        for button, action in (
            (pygame.CONTROLLER_BUTTON_A, "confirm"),
            (pygame.CONTROLLER_BUTTON_B, "bomb"),
            (pygame.CONTROLLER_BUTTON_START, "start"),
            (pygame.CONTROLLER_BUTTON_BACK, "mute"),
        ):
            if button in pressed:
                actions.append(action)

        menu_direction = 1 if movement.x > MENU_STICK_THRESHOLD else -1 if movement.x < -MENU_STICK_THRESHOLD else 0
        if menu_direction and menu_direction != self.previous_menu_direction:
            actions.append("next_phase" if menu_direction > 0 else "previous_phase")
        self.previous_buttons = buttons
        self.previous_menu_direction = menu_direction
        return GamepadInput(
            movement=tuple(movement),
            fire=pygame.CONTROLLER_BUTTON_A in buttons,
            precise=bool({pygame.CONTROLLER_BUTTON_LEFTSHOULDER, pygame.CONTROLLER_BUTTON_RIGHTSHOULDER} & buttons),
            actions=tuple(actions),
            bomb_held=pygame.CONTROLLER_BUTTON_B in buttons,
        )

    def close(self) -> None:
        self.disconnect()
        sdl_controller.quit()
        pygame.joystick.quit()
