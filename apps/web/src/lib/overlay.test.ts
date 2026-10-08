import { describe, expect, it } from "vitest";
import { boxesAt, chunkOf, containRect, type OverlayTrack } from "@/lib/overlay";

const car: OverlayTrack = {
  id: 1,
  cls: "car",
  points: [
    [1.0, 0, 0, 10, 10],
    [1.2, 10, 0, 20, 10],
    [5.0, 100, 0, 110, 10], // a long gap after 1.2
  ],
};

describe("boxesAt", () => {
  it("interpolates between neighbouring samples", () => {
    const [b] = boxesAt([car], 1.1);
    expect(b.x1).toBeCloseTo(5);
    expect(b.x2).toBeCloseTo(15);
  });

  it("returns the sample itself on an exact hit", () => {
    expect(boxesAt([car], 1.2)[0].x1).toBe(10);
  });

  it("hides a track that is outside its life or inside a long gap", () => {
    expect(boxesAt([car], 0.2)).toEqual([]);
    expect(boxesAt([car], 3)).toEqual([]);
    expect(boxesAt([car], 9)).toEqual([]);
  });

  it("holds the nearest sample just across a gap edge", () => {
    expect(boxesAt([car], 1.4)).toHaveLength(1);
  });

  it("copes with a track of no points", () => {
    expect(boxesAt([{ id: 2, cls: "car", points: [] }], 1)).toEqual([]);
  });
});

describe("containRect", () => {
  it("letterboxes a wide picture in a taller box", () => {
    const r = containRect(400, 400, 1280, 720);
    expect(r.w).toBe(400);
    expect(r.h).toBeCloseTo(225);
    expect(r.y).toBeCloseTo(87.5);
  });

  it("pillarboxes a tall picture in a wider box", () => {
    const r = containRect(400, 200, 100, 200);
    expect(r.w).toBe(100);
    expect(r.x).toBe(150);
  });
});

describe("chunkOf", () => {
  it("maps seconds to 30 s windows", () => {
    expect(chunkOf(0)).toBe(0);
    expect(chunkOf(29.9)).toBe(0);
    expect(chunkOf(30)).toBe(1);
  });
});
