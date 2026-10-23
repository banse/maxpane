"""Fresh pixel artwork following Little Computer People's three-storey cutaway.

The room arrangement is referenced from the C64 game, not extracted game assets:
https://i.sstatic.net/L0RIC.jpg . The palette and small drawing primitives adapt
aidude's ideas/evidence/seat-house-life-sim/house_demo_v2-2026-10-23.py.
All movement is a deterministic offline illustration, never seat telemetry.
"""
from __future__ import annotations

W, H = 320, 200
PAL = ("000000", "FFFFFF", "68372B", "70A4B2", "6F3D86", "588D43", "352879", "B8C76F",
       "6F4F25", "433900", "9A6759", "444444", "6C6C6C", "9AD284", "6C5EB5", "959595")
RGB = tuple(tuple(int(color[i:i + 2], 16) for i in (0, 2, 4)) for color in PAL)
BLACK, WHITE, RED, CYAN, PURPLE, GREEN, BLUE, YELLOW = range(8)
ORANGE, BROWN, LRED, DGREY, GREY, LGREEN, LBLUE, LGREY = range(8, 16)


def rect(buf, x0, y0, x1, y1, color):
    for y in range(max(0, y0), min(H, y1)):
        for x in range(max(0, x0), min(W, x1)):
            buf[y][x] = color


def line(buf, x0, y0, x1, y1, color):
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(steps + 1):
        x, y = round(x0 + (x1 - x0) * i / steps), round(y0 + (y1 - y0) * i / steps)
        rect(buf, x, y, x + 1, y + 1, color)


def disc(buf, cx, cy, radius, color):
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius:
                rect(buf, x, y, x + 1, y + 1, color)


def rug(buf, x0, y0, x1, y1, colors):
    for y in range(y0, y1):
        for x in range(x0, x1):
            buf[y][x] = colors[((x // 3) + (y // 2)) % len(colors)]


def door(buf, x, y, height=30):
    rect(buf, x, y, x + 11, y + height, WHITE)
    rect(buf, x + 3, y + 2, x + 9, y + height - 2, LGREY)
    for dy in (4, 16):
        rect(buf, x + 4, y + dy, x + 8, y + dy + 8, WHITE)
    rect(buf, x + 9, y + 15, x + 10, y + 17, DGREY)


def chair(buf, x, y, color=LBLUE):
    rect(buf, x + 4, y, x + 17, y + 15, color)
    rect(buf, x, y + 9, x + 19, y + 17, color)
    rect(buf, x + 2, y + 16, x + 5, y + 19, LGREY)
    rect(buf, x + 14, y + 16, x + 17, y + 19, LGREY)


def table(buf, x, y, width, color=LGREY):
    rect(buf, x, y, x + width, y + 3, color)
    rect(buf, x + 1, y + 3, x + 3, y + 12, color)
    rect(buf, x + width - 3, y + 3, x + width - 1, y + 12, color)


def base_house():
    """A complete 320×200 C64-palette house; caller owns the returned rows."""
    b = [bytearray([LBLUE]) * W for _ in range(H)]
    # Black attic under a low, broad roof, matching the original dollhouse.
    for y in range(15, 59):
        left = max(0, 84 - (y - 15) * 2)
        right = min(W, 236 + (y - 15) * 2)
        rect(b, left, y, right, y + 1, LRED)
        if y > 17:
            rect(b, left + 2, y, right - 2, y + 1, BLACK)
    rect(b, 0, 58, W, H, LRED)
    rect(b, 4, 72, 316, 120, BLACK)
    rect(b, 4, 138, 316, 186, BLACK)
    # Interior divisions are open at floor level, allowing the actor to pass.
    rect(b, 130, 71, 132, 118, LRED)
    rect(b, 240, 71, 242, 120, LRED)
    rect(b, 188, 138, 190, 183, LRED)
    rug(b, 5, 59, 144, 69, (LGREY, LGREY, WHITE))
    rug(b, 6, 122, 57, 129, (CYAN, LBLUE, LGREY))
    rect(b, 68, 130, 124, 135, YELLOW)
    rug(b, 154, 121, 240, 135, (CYAN, LBLUE, WHITE, LBLUE))
    rect(b, 242, 121, 316, 135, LGREEN)
    rug(b, 4, 186, 166, 198, (LGREEN, GREEN, CYAN, LGREEN))
    # Two stairs, the essential silhouette of the original house.
    for i in range(10):
        y = 118 - i * 5
        x = 132 if i < 4 else 132 + (i - 3) * 8
        rect(b, x, y, x + (20 if i < 4 else 9), y + 2, LRED)
        if i >= 4:
            rect(b, x + 7, y - 4, x + 9, y + 2, LRED)
    for i in range(10):
        y = 183 - i * 5
        x = 167 if i < 5 else 167 - (i - 4) * 8
        rect(b, x, y, x + (21 if i < 5 else 10), y + 2, LRED)
        if i >= 5:
            rect(b, x, y, x + 2, y + 6, LRED)
    # Attic: small TV, record player, armchair, piano, door and writing desk.
    rect(b, 31, 48, 48, 62, PURPLE)
    rect(b, 33, 50, 45, 59, LBLUE)
    line(b, 39, 47, 32, 43, WHITE)
    line(b, 39, 47, 46, 43, WHITE)
    rect(b, 55, 46, 89, 58, LGREEN)
    rect(b, 57, 48, 87, 56, BLACK)
    for x in range(59, 87, 3):
        rect(b, x, 48, x + 1, 56, WHITE)
    rect(b, 63, 40, 82, 45, LGREEN)
    rect(b, 66, 41, 79, 43, BLACK)
    line(b, 73, 40, 81, 39, WHITE)
    chair(b, 97, 49)
    rect(b, 137, 41, 166, 52, LGREEN)
    rect(b, 138, 49, 166, 53, WHITE)
    for x in range(140, 165, 3):
        rect(b, x, 49, x + 1, 51, BLACK)
    rect(b, 138, 53, 141, 58, WHITE)
    rect(b, 163, 53, 166, 58, WHITE)
    table(b, 147, 58, 10, LGREEN)
    door(b, 178, 26, 33)
    table(b, 202, 58, 51)
    rect(b, 216, 50, 235, 57, PURPLE)
    rect(b, 212, 56, 239, 58, WHITE)
    rect(b, 258, 48, 279, 59, LGREEN)
    rect(b, 261, 39, 274, 48, LGREEN)
    rect(b, 264, 41, 271, 45, BLACK)
    # Bedroom: bed, telephone, door, vanity mirror and drawers.
    rect(b, 13, 108, 47, 122, LGREEN)
    disc(b, 30, 109, 7, LGREEN)
    rect(b, 8, 117, 56, 121, WHITE)
    rect(b, 7, 119, 10, 132, LGREEN)
    rect(b, 53, 119, 56, 132, LGREEN)
    table(b, 49, 116, 18, LGREEN)
    rect(b, 53, 110, 62, 115, PURPLE)
    rect(b, 52, 109, 55, 111, LBLUE)
    rect(b, 61, 109, 64, 111, LBLUE)
    door(b, 74, 89, 34)
    rect(b, 101, 91, 123, 112, LGREEN)
    rect(b, 103, 94, 121, 111, CYAN)
    disc(b, 112, 92, 5, LGREEN)
    rect(b, 104, 94, 120, 110, CYAN)
    table(b, 96, 114, 32, LGREEN)
    for x in (100, 114):
        rect(b, x, 118, x + 8, 119, BLACK)
    # Bathroom: mirror, basin, shower and bathtub, round yellow mat.
    rect(b, 165, 92, 183, 107, WHITE)
    rect(b, 167, 94, 181, 105, CYAN)
    rect(b, 160, 112, 178, 115, WHITE)
    rect(b, 167, 115, 169, 124, WHITE)
    rect(b, 164, 124, 173, 126, WHITE)
    rect(b, 188, 92, 197, 121, LRED)
    rect(b, 189, 94, 190, 120, BLACK)
    line(b, 217, 90, 234, 90, LGREY)
    line(b, 234, 90, 234, 114, LGREY)
    rect(b, 217, 90, 221, 92, LGREY)
    rect(b, 207, 113, 236, 117, WHITE)
    rect(b, 210, 117, 233, 121, WHITE)
    disc(b, 229, 126, 8, YELLOW)
    # Study: bookcase, wall clock, writing desk and computer.
    rect(b, 245, 92, 263, 121, WHITE)
    for y in (94, 106):
        rect(b, 247, y, 261, y + 10, BLACK)
        for x, color, height in ((248, LRED, 6), (252, PURPLE, 8), (258, YELLOW, 7)):
            rect(b, x, y + 10 - height, x + 2, y + 10, color)
    disc(b, 279, 87, 8, LRED)
    line(b, 279, 87, 283, 83, WHITE)
    line(b, 279, 87, 279, 92, WHITE)
    table(b, 269, 113, 43, WHITE)
    rect(b, 290, 99, 309, 112, LBLUE)
    rect(b, 292, 101, 307, 109, BLACK)
    rect(b, 270, 110, 285, 112, WHITE)
    for x in range(271, 284, 3):
        rect(b, x, 109, x + 1, 110, WHITE)
    # Kitchen: fridge, wall cupboards/window, counter, table and hanging light.
    rect(b, 23, 160, 43, 185, WHITE)
    rect(b, 24, 170, 43, 171, BLACK)
    rect(b, 38, 167, 41, 168, BLACK)
    rect(b, 38, 173, 41, 174, BLACK)
    rect(b, 47, 151, 67, 169, WHITE)
    rect(b, 49, 153, 65, 167, YELLOW)
    rect(b, 50, 155, 64, 157, BLACK)
    rect(b, 50, 162, 64, 164, BLACK)
    rect(b, 57, 153, 58, 168, WHITE)
    rect(b, 73, 150, 94, 169, LBLUE)
    rect(b, 82, 150, 84, 169, WHITE)
    rect(b, 73, 158, 94, 160, WHITE)
    rect(b, 73, 149, 94, 152, LGREEN)
    rect(b, 46, 175, 97, 186, WHITE)
    rect(b, 46, 173, 97, 175, LGREEN)
    for x in (52, 72, 90):
        rect(b, x, 176, x + 3, 177, BLACK)
    line(b, 120, 138, 120, 158, WHITE)
    line(b, 114, 160, 126, 160, LGREEN)
    line(b, 114, 160, 120, 157, LGREEN)
    line(b, 126, 160, 120, 157, LGREEN)
    table(b, 105, 184, 32, WHITE)
    rect(b, 115, 180, 126, 183, WHITE)
    chair(b, 144, 166, CYAN)
    # Living room: armchair, telephone, lamp, picture, fireplace and front door.
    chair(b, 212, 170, LBLUE)
    rect(b, 193, 181, 205, 186, LGREEN)
    line(b, 194, 179, 204, 179, WHITE)
    rect(b, 197, 182, 201, 184, BLACK)
    rect(b, 245, 164, 247, 186, YELLOW)
    line(b, 238, 163, 253, 163, WHITE)
    line(b, 238, 163, 246, 159, WHITE)
    line(b, 253, 163, 246, 159, WHITE)
    rect(b, 263, 145, 284, 160, WHITE)
    rect(b, 265, 147, 282, 158, LBLUE)
    rect(b, 267, 153, 280, 158, LGREEN)
    rect(b, 270, 151, 278, 155, WHITE)
    line(b, 268, 151, 274, 148, LRED)
    line(b, 274, 148, 280, 151, LRED)
    rect(b, 259, 170, 289, 187, YELLOW)
    for y in range(172, 186, 4):
        rect(b, 259, y, 289, y + 1, LRED)
        for x in range(261 + (y % 8), 289, 7):
            rect(b, x, y - 2, x + 1, y, LRED)
    rect(b, 265, 176, 283, 186, BLACK)
    rect(b, 256, 186, 291, 188, WHITE)
    door(b, 305, 157, 31)
    return b


# Pose adapted from the original aidude demonstration; never taken from a ROM.
PERSON = ("..9999..", ".999999.", ".aaaaaa.", ".a0aa0a.", ".aaaaaa.", "..aaaa..",
          ".eeeeee.", "eeeeeeee", "aeeeeeea", "aeeeeeea", ".eeeeee.", ".ffffff.",
          ".ff..ff.", ".ff..ff.", ".ff..ff.", "11...11.")


def _route():
    steps = []
    current = (227, 186)

    def go(point, label, hold=0):
        nonlocal current
        distance = max(abs(point[0] - current[0]), abs(point[1] - current[1]))
        if distance:
            steps.append((distance / 18, current, point, label))
        if hold:
            steps.append((hold, point, point, label))
        current = point

    go(current, "living room", 3)
    for point in ((186, 186), (176, 160), (136, 138), (136, 128)):
        go(point, "stairs")
    go((42, 128), "bedroom", 3)
    for point in ((136, 128), (136, 106), (152, 91), (184, 72), (184, 64)):
        go(point, "stairs")
    go((149, 64), "playing piano", 4)
    go((246, 64), "writing upstairs", 4)
    for point in ((184, 64), (184, 72), (152, 91), (136, 106), (136, 128)):
        go(point, "stairs")
    go((199, 128), "bathroom", 2)
    go((279, 128), "typing in study", 4)
    for point in ((136, 128), (136, 138), (176, 160), (186, 186)):
        go(point, "stairs")
    go((105, 186), "kitchen", 3)
    go((227, 186), "living room", 3)
    return tuple(steps)


ROUTE = _route()
DURATION = sum(segment[0] for segment in ROUTE)


def frame_at(base, elapsed: float):
    """Return pixels, actor centre and sample action for an elapsed replay time."""
    elapsed = max(0, elapsed)
    phase = elapsed % DURATION
    for seconds, start, end, label in ROUTE:
        if phase < seconds:
            break
        phase -= seconds
    fraction = min(1, phase / seconds)
    foot_x = round(start[0] + (end[0] - start[0]) * fraction)
    foot_y = round(start[1] + (end[1] - start[1]) * fraction)
    b = [bytearray(row) for row in base]
    tick = int(elapsed * 10)
    # Flicker is seeded by frame number, not global random state.
    for x in (268, 272, 276, 280):
        flame = 2 + (tick + x) % 6
        rect(b, x, 186 - flame, x + 2, 186, YELLOW if (tick + x) % 3 else LRED)
    pose = list(PERSON)
    if start != end and tick % 4 < 2:
        pose[-3:] = ("ff....ff", "ff....ff", "11....11")
    elif "typing" in label or "playing" in label or "writing" in label:
        pose[7:10] = ("eeeeeeaa", "aeeeeee.", ".eeeeee.") if tick % 2 else ("eeeeaaa.", "aeeeeee.", ".eeeeee.")
    for dy, row in enumerate(pose):
        if end[0] < start[0]:
            row = row[::-1]
        for dx, color in enumerate(row):
            if color != ".":
                rect(b, foot_x - 4 + dx, foot_y - 16 + dy, foot_x - 3 + dx, foot_y - 15 + dy, int(color, 16))
    return b, (foot_x, foot_y - 8), "Pepe · " + label


def camera(actor, width, height):
    """Native pixel crop following the actor, aligned to half-block row pairs."""
    width = max(1, min(W, int(width)))
    height = max(2, min(H, int(height)))
    height -= height % 2
    x = max(0, min(W - width, actor[0] - width // 2))
    y = max(0, min(H - height, actor[1] - (height // 2 // 2) * 2))
    return x, y - y % 2, width, height
