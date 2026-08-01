import unittest
from unittest.mock import Mock

from voiceflow_app.overlay import (
    BLDS,
    CX,
    CY,
    ORB_H,
    ORB_W,
    OUTER_RING_RADIUS,
    Overlay,
    PULSE_PADDING,
    R,
    TK_BASE_SCALING,
    animated_bar_height,
    normalize_tk_scaling,
    pulse_ring_style,
)


class FakePanel:
    def __init__(self):
        self.events = []

    def winfo_exists(self):
        return True

    def attributes(self, *args):
        self.events.append(("attributes", args))

    def geometry(self, value):
        self.events.append(("geometry", value))

    def deiconify(self):
        self.events.append(("deiconify",))

    def lift(self):
        self.events.append(("lift",))

    def focus_set(self):
        self.events.append(("focus_set",))


class OverlayGeometryTests(unittest.TestCase):
    def test_tk_scaling_is_normalized_for_physical_pixel_windows(self):
        window = Mock()
        normalize_tk_scaling(window)
        window.tk.call.assert_called_once_with("tk", "scaling", TK_BASE_SCALING)

    def test_orb_and_pulse_have_canvas_padding(self):
        self.assertEqual(OUTER_RING_RADIUS, R + PULSE_PADDING)
        self.assertGreaterEqual(CX - OUTER_RING_RADIUS, 0)
        self.assertLessEqual(CX + OUTER_RING_RADIUS, ORB_W)
        self.assertGreaterEqual(CY - OUTER_RING_RADIUS, 0)
        self.assertLessEqual(CY + OUTER_RING_RADIUS, ORB_H)

    def test_waveform_bars_stay_inside_inner_circle_width(self):
        inner_radius = R - 8
        for bar in BLDS:
            self.assertGreaterEqual(bar["dx"], -inner_radius)
            self.assertLessEqual(bar["dx"] + bar["w"], inner_radius)

    def test_logo_bars_are_equal_width_and_symmetric(self):
        self.assertEqual({bar["w"] for bar in BLDS}, {8})
        self.assertEqual([bar["baseH"] for bar in BLDS], [20, 32, 44, 56, 44, 32, 20])
        self.assertEqual([bar["dx"] for bar in BLDS], [-40, -28, -16, -4, 8, 20, 32])

    def test_orb_window_dimensions_are_fixed(self):
        self.assertEqual((ORB_W, ORB_H), (148, 168))

    def test_waveform_moves_while_speaking_and_thinking(self):
        bar = BLDS[1]
        self.assertNotEqual(
            animated_bar_height(bar, 0.0, "recording"),
            animated_bar_height(bar, 0.8, "recording"),
        )
        self.assertNotEqual(
            animated_bar_height(bar, 0.0, "thinking"),
            animated_bar_height(bar, 0.8, "thinking"),
        )
        self.assertEqual(animated_bar_height(bar, 0.8, "idle"), bar["baseH"])

    def test_outer_ring_pulses_without_resizing_the_orb_window(self):
        speaking_radius, speaking_color, speaking_width = pulse_ring_style("recording", 0.0)
        later_radius, _, _ = pulse_ring_style("recording", 0.4)
        thinking_radius, thinking_color, thinking_width = pulse_ring_style("thinking", 0.0)

        self.assertNotEqual(speaking_radius, later_radius)
        self.assertEqual((speaking_color, speaking_width), ("#ffffff", 3))
        self.assertEqual((thinking_color, thinking_width), ("#e5e5e5", 2))
        for radius in (speaking_radius, later_radius, thinking_radius):
            self.assertLessEqual(radius, min(CX, ORB_W - CX, CY, ORB_H - CY))

    def test_panel_is_fully_configured_before_becoming_visible(self):
        overlay = Overlay.__new__(Overlay)
        overlay._panel_geometry = lambda _panel: (760, 720, 100, 40)
        panel = FakePanel()

        overlay._present_panel(panel)

        self.assertEqual(
            panel.events,
            [
                ("attributes", ("-topmost", True)),
                ("geometry", "760x720+100+40"),
                ("deiconify",),
                ("lift",),
                ("focus_set",),
            ],
        )


if __name__ == "__main__":
    unittest.main()
