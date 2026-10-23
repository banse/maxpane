"""Pure scene checks for the offline house rendering spike."""
from scripts.seat_house_scene import H, RGB, W, base_house, camera, frame_at


def test_frames_are_native_palette_pixels_and_never_mutate_background():
    base = base_house()
    saved = [bytes(row) for row in base]
    assert (W, H, len(RGB)) == (320, 200, 16)
    for elapsed in (0, 3.7, 11, 24, 40, 59, 71, 1000):
        pixels, actor, label = frame_at(base, elapsed)
        assert len(pixels) == H and all(len(row) == W for row in pixels)
        assert all(0 <= color < 16 for row in pixels for color in row)
        assert pixels == frame_at(base, elapsed)[0]
        assert all(row is not original for row, original in zip(pixels, base))
        assert 0 <= actor[0] < W and 0 <= actor[1] < H
        assert label.startswith("Pepe · ")
    assert saved == base


def test_replay_moves_through_all_floors_and_uses_stairs():
    base = base_house()
    observed = [frame_at(base, step / 10) for step in range(800)]
    ys = {position[1] for _, position, _ in observed}
    assert min(ys) < 60 and max(ys) > 170
    # Intermediate heights ensure the replay climbs rather than teleporting.
    assert len(ys) > 80
    positions = [position for _, position, _ in observed]
    assert all(abs(x1 - x0) <= 3 and abs(y1 - y0) <= 3
               for (x0, y0), (x1, y1) in zip(positions, positions[1:]))
    assert len({label for _, _, label in observed}) >= 5


def test_camera_keeps_actor_visible_and_respects_pixel_pair_alignment():
    for actor in ((0, 0), (319, 199), (160, 80), (183, 127)):
        for size in ((99, 62), (149, 88), (320, 200), (1000, 600), (1, 2)):
            x, y, width, height = camera(actor, *size)
            assert y % 2 == 0
            assert 0 <= x <= W - width and 0 <= y <= H - height
            assert x <= actor[0] < x + width
            assert y <= actor[1] < y + height
    assert camera((99, 80), 320, 200) == (0, 0, 320, 200)
