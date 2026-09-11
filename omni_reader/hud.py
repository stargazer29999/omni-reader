"""Floating teleprompter HUD overlay for OmniReader on macOS.

Renders a translucent, non-activating floating window that:
- Highlights the current sentence being spoken.
- Dims previously read sentences to show progress.
- Auto-scrolls so the active sentence always stays in visual scope.
- Automatically closes when reading completes or parent process exits.
"""

import json
import os
import sys
import threading
import time
from typing import List

try:
    import objc
    import AppKit
    from AppKit import (
        NSApplication, NSPanel, NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel,
        NSBackingStoreBuffered, NSRect, NSPoint, NSSize, NSScreen, NSColor, NSFont,
        NSVisualEffectView, NSVisualEffectMaterialHUDWindow, NSVisualEffectBlendingModeBehindWindow,
        NSScrollView, NSTextView, NSMutableAttributedString,
        NSForegroundColorAttributeName, NSBackgroundColorAttributeName, NSFontAttributeName,
        NSTextField
    )
    from Foundation import NSRange, NSObject
    from PyObjCTools import AppHelper
    HAS_APPKIT = True
except ImportError:
    HAS_APPKIT = False


class HUDController(NSObject):
    def init(self):
        self = objc.super(HUDController, self).init()
        if self is None:
            return None
        self.sentences = []
        self.current_index = 0
        self.sentence_ranges = []
        self.full_text = ""
        self.window = None
        self.text_view = None
        self.header_label = None
        return self

    def setup_ui(self):
        screen = NSScreen.mainScreen()
        screen_frame = screen.frame() if screen else NSRect(NSPoint(0, 0), NSSize(1440, 900))

        width = min(740.0, screen_frame.size.width - 80.0)
        height = 170.0
        x = (screen_frame.size.width - width) / 2.0
        y = 52.0  # Floating above dock/bottom edge

        window_rect = NSRect(NSPoint(x, y), NSSize(width, height))

        # Floating non-activating panel (never steals focus from active app)
        style_mask = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            window_rect, style_mask, NSBackingStoreBuffered, False
        )
        panel.setLevel_(AppKit.NSStatusWindowLevel + 2)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setIgnoresMouseEvents_(False)

        # Translucent glass blur
        visual_effect = NSVisualEffectView.alloc().initWithFrame_(NSRect(NSPoint(0, 0), NSSize(width, height)))
        visual_effect.setMaterial_(NSVisualEffectMaterialHUDWindow)
        visual_effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        visual_effect.setState_(1)
        visual_effect.setWantsLayer_(True)
        visual_effect.layer().setCornerRadius_(14.0)
        visual_effect.layer().setMasksToBounds_(True)

        # Header Progress Bar
        header_height = 26.0
        header_rect = NSRect(NSPoint(16, height - header_height - 8), NSSize(width - 32, header_height))
        header = NSTextField.alloc().initWithFrame_(header_rect)
        header.setEditable_(False)
        header.setBezeled_(False)
        header.setDrawsBackground_(False)
        header.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.95, 0.9))
        header.setFont_(NSFont.boldSystemFontOfSize_(12.5))
        header.setStringValue_("🔊 OmniReader • Reading...")
        visual_effect.addSubview_(header)
        self.header_label = header

        # Text View inside Scroll View
        content_rect = NSRect(NSPoint(14, 10), NSSize(width - 28, height - header_height - 18))
        scroll_view = NSScrollView.alloc().initWithFrame_(content_rect)
        scroll_view.setHasVerticalScroller_(True)
        scroll_view.setHasHorizontalScroller_(False)
        scroll_view.setAutohidesScrollers_(True)
        scroll_view.setDrawsBackground_(False)
        scroll_view.setBorderType_(0)

        text_view = NSTextView.alloc().initWithFrame_(scroll_view.contentView().bounds())
        text_view.setEditable_(False)
        text_view.setSelectable_(True)
        text_view.setDrawsBackground_(False)
        text_view.setTextContainerInset_(NSSize(6.0, 4.0))

        scroll_view.setDocumentView_(text_view)
        visual_effect.addSubview_(scroll_view)

        panel.contentView().addSubview_(visual_effect)
        panel.orderFrontRegardless()

        self.window = panel
        self.text_view = text_view

    def set_content(self, sentences: List[str]):
        self.sentences = sentences
        self.sentence_ranges = []
        full_parts = []
        curr_offset = 0

        for s in sentences:
            s_clean = s.strip()
            full_parts.append(s_clean)
            start = curr_offset
            length = len(s_clean)
            self.sentence_ranges.append(NSRange(start, length))
            curr_offset += length + 2

        self.full_text = "\n\n".join(full_parts)
        self.update_highlight(0)

    def update_highlight(self, index: int):
        if not self.text_view or not self.sentences:
            return

        self.current_index = max(0, min(len(self.sentences) - 1, index))
        total = len(self.sentences)
        progress_pct = int(((self.current_index + 1) / total) * 100)

        if self.header_label:
            self.header_label.setStringValue_(
                f"🔊 OmniReader • Sentence {self.current_index + 1} of {total} ({progress_pct}%)"
            )

        attr_str = NSMutableAttributedString.alloc().initWithString_(self.full_text)
        base_font = NSFont.systemFontOfSize_(14.0)
        bold_font = NSFont.boldSystemFontOfSize_(14.5)

        for i, rng in enumerate(self.sentence_ranges):
            if i < self.current_index:
                # Dim past text
                attr_str.addAttribute_value_range_(
                    NSForegroundColorAttributeName,
                    NSColor.colorWithCalibratedWhite_alpha_(0.50, 0.75),
                    rng
                )
                attr_str.addAttribute_value_range_(NSFontAttributeName, base_font, rng)

            elif i == self.current_index:
                # Vivid glowing highlight on active sentence
                attr_str.addAttribute_value_range_(
                    NSForegroundColorAttributeName,
                    NSColor.whiteColor(),
                    rng
                )
                highlight_bg = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.14, 0.46, 0.90, 0.50)
                attr_str.addAttribute_value_range_(
                    NSBackgroundColorAttributeName,
                    highlight_bg,
                    rng
                )
                attr_str.addAttribute_value_range_(NSFontAttributeName, bold_font, rng)

            else:
                # Upcoming text
                attr_str.addAttribute_value_range_(
                    NSForegroundColorAttributeName,
                    NSColor.colorWithCalibratedWhite_alpha_(0.85, 0.90),
                    rng
                )
                attr_str.addAttribute_value_range_(NSFontAttributeName, base_font, rng)

        self.text_view.textStorage().setAttributedString_(attr_str)

        # Auto-scroll so active sentence is centered
        if self.current_index < len(self.sentence_ranges):
            target_range = self.sentence_ranges[self.current_index]
            self.text_view.scrollRangeToVisible_(target_range)

    def close(self):
        if self.window:
            self.window.close()
            self.window = None
        AppHelper.stopEventLoop()


def stdin_reader_thread(controller: HUDController):
    """Processes stdin JSON commands from the main omnisay process."""
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            cmd = json.loads(line.strip())
            action = cmd.get("action")
            if action == "init":
                sentences = cmd.get("sentences", [])
                AppHelper.callAfter(controller.set_content, sentences)
            elif action == "highlight":
                idx = cmd.get("index", 0)
                AppHelper.callAfter(controller.update_highlight, idx)
            elif action in ("stop", "close"):
                break
        except Exception:
            pass

    AppHelper.callAfter(controller.close)


def main():
    if not HAS_APPKIT:
        sys.exit(0)

    app = NSApplication.sharedApplication()
    controller = HUDController.alloc().init()
    controller.setup_ui()

    t = threading.Thread(target=stdin_reader_thread, args=(controller,), daemon=True)
    t.start()

    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
