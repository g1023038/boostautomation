package com.boostautomation.actions;

import java.util.List;

/** One screen's worth of visible text, captured for verification -- the
 * Java equivalent of each dict appended to Python's state["screens"]. */
public class ScreenRecord {
    public String screen;
    public List<String> texts;

    public ScreenRecord() {
    }

    public ScreenRecord(String screen, List<String> texts) {
        this.screen = screen;
        this.texts = texts;
    }
}
