import { afterEach, describe, expect, it, vi } from "vitest";
import { adaptVideoReview, api, buildFrameOverrides } from "./api";

describe("buildFrameOverrides", () => {
  it("emits only items the reviewer overrode, mapped to {value, confidence}", () => {
    const out = buildFrameOverrides([
      { key: "two_hands", state: "override-no" },
      { key: "holding_tool", state: "override-yes" },
      { key: "at_workstation", state: "confirmed" }, // accepted AI → no override
      { key: "holding_broom", state: "pending" }, // untouched → no override
    ]);
    expect(out).toEqual({
      two_hands: { value: false, confidence: 1 },
      holding_tool: { value: true, confidence: 1 },
    });
  });

  it("returns an empty object when nothing was overridden", () => {
    expect(buildFrameOverrides([{ key: "a", state: "confirmed" }])).toEqual({});
  });
});

describe("adaptVideoReview", () => {
  const raw = {
    id: "11111111-1111-1111-1111-111111111111",
    client_id: "22222222-2222-2222-2222-222222222222",
    external_ref: "EGO-1",
    priority: "high",
    duration_seconds: 75,
    latest_ai_run: { grade: 6, model: "stub", prompt_version: "1.0.0", summary: "ok" },
    checklist_items: [
      { key: "two_hands", label: "Two hands visible", type: "boolean", weight: 1 },
      { key: "holding_tool", label: "Hand holding a tool", type: "boolean", weight: 2 },
    ],
    frames: [
      {
        frame_id: "ffffffff-0000-0000-0000-000000000001",
        frame_index: 0,
        timecode_seconds: 0,
        timecode_label: "00:00:00",
        image_url: "https://s3/frame0.jpg",
        description: "frame 0",
        findings: { two_hands: { value: false, confidence: 0.9 }, holding_tool: { value: true, confidence: 0.8 } },
        flagged: true,
      },
    ],
  };

  it("maps the real video detail into the workbench Review model", () => {
    const r = adaptVideoReview(raw);
    expect(r.ref).toBe("EGO-1");
    expect(r.aiGrade).toBe(6);
    expect(r.duration).toBe("1:15");
    expect(r.frameCount).toBe(1);
    expect(r.flaggedIdx).toEqual([0]);

    const f = r.frames[0];
    expect(f.id).toBe("ffffffff-0000-0000-0000-000000000001"); // real frame UUID, for overrides
    expect(f.src).toBe("https://s3/frame0.jpg"); // real image
    expect(f.flagged).toBe(true);

    const byKey = Object.fromEntries(f.items.map((i) => [i.key, i]));
    // expect = AI value so confirming costs nothing; weight>=2 ⇒ risk
    expect(byKey.two_hands).toMatchObject({ aiValue: "No", expect: "No", risk: false, conf: 0.9 });
    expect(byKey.holding_tool).toMatchObject({ aiValue: "Yes", expect: "Yes", risk: true });
  });
});

describe("api.submitHumanReview", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("assigns, writes overrides only for changed frames, then grades + completes", async () => {
    const calls: { method: string; url: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit = {}) => {
        const method = init.method || "GET";
        calls.push({ method, url: String(url), body: init.body ? JSON.parse(init.body as string) : null });
        const payload = method === "POST" ? { id: "rev-1" } : {};
        return new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } });
      }),
    );

    const reviewId = await api.submitHumanReview("vid-9", {
      grade: 7.5,
      notes: "ok",
      frames: [
        { frameId: "f1", note: "", overrides: { two_hands: { value: false, confidence: 1 } } },
        { frameId: "f2", note: "", overrides: {} }, // unchanged → skipped
      ],
    });

    expect(reviewId).toBe("rev-1");
    expect(calls[0]).toMatchObject({ method: "POST", url: "/api/videos/vid-9/human-reviews" });

    const puts = calls.filter((c) => c.method === "PUT");
    expect(puts).toHaveLength(1); // only f1 (f2 had no override/note)
    expect(puts[0].url).toBe("/api/human-reviews/rev-1/frames/f1");
    expect((puts[0].body as { override_findings: unknown }).override_findings).toEqual({
      two_hands: { value: false, confidence: 1 },
    });

    const patch = calls.find((c) => c.method === "PATCH");
    expect(patch?.url).toBe("/api/human-reviews/rev-1");
    expect(patch?.body).toMatchObject({ grade: 7.5, status: "done", notes: "ok" });
  });
});
