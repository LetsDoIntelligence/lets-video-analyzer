import { describe, expect, expectTypeOf, it } from "vitest";
import type { components } from "@/lib/api/generated";
import {
  VideoApiError,
  createVideosClient,
  toVideoItem,
  type ApiVideo,
} from "@/lib/api/videos-client";

const BASE = "http://api.test";
const api: ApiVideo = {
  id: "abc",
  name: "Road Cam",
  sizeBytes: 1234,
  durationSec: 12.5,
  src: "/v1/videos/abc/file",
  thumbnailSrc: "/v1/videos/abc/thumbnail",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("generated API types", () => {
  it("backend VideoOut stays compatible with what the client reads", () => {
    // Fails `tsc` if the backend's OpenAPI schema drifts from apiVideoSchema.
    expectTypeOf<components["schemas"]["VideoOut"]>().toExtend<ApiVideo>();
  });
});

describe("toVideoItem", () => {
  it("makes media URLs absolute and maps nulls", () => {
    expect(toVideoItem(api, BASE)).toEqual({
      id: "abc",
      name: "Road Cam",
      source: "upload",
      src: "http://api.test/v1/videos/abc/file",
      thumbnailSrc: "http://api.test/v1/videos/abc/thumbnail",
      durationSec: 12.5,
      sizeBytes: 1234,
    });
    const bare = toVideoItem({ ...api, durationSec: null, thumbnailSrc: null }, BASE);
    expect(bare.durationSec).toBeUndefined();
    expect(bare.thumbnailSrc).toBeUndefined();
  });
});

describe("list / remove", () => {
  it("lists videos", async () => {
    const client = createVideosClient(BASE, (async () => json([api])) as typeof fetch);
    const [v] = await client.list();
    expect(v.src).toBe("http://api.test/v1/videos/abc/file");
  });

  it("explains a server error and an unreachable server", async () => {
    const down = createVideosClient(BASE, (async () => {
      throw new TypeError("fetch failed");
    }) as typeof fetch);
    await expect(down.list()).rejects.toThrow(/Is the API running/);

    const broken = createVideosClient(BASE, (async () => json({}, 500)) as typeof fetch);
    await expect(broken.list()).rejects.toBeInstanceOf(VideoApiError);
  });

  it("treats deleting a missing video as success, but surfaces other errors", async () => {
    const calls: string[] = [];
    const missing = createVideosClient(BASE, (async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method} ${url}`);
      return new Response(null, { status: 404 });
    }) as typeof fetch);
    await expect(missing.remove("a b")).resolves.toBeUndefined();
    expect(calls).toEqual(["DELETE http://api.test/v1/videos/a%20b"]);

    const failing = createVideosClient(BASE, (async () =>
      json({ detail: "Disk is read-only." }, 500)) as typeof fetch);
    await expect(failing.remove("x")).rejects.toThrow("Disk is read-only.");
  });
});

/** Minimal XHR double: lets a test drive progress and the final response. */
interface FakeXhr {
  status: number;
  responseText: string;
  upload: { onprogress: ((e: ProgressEvent) => void) | null };
  onload: (() => void) | null;
  onerror: (() => void) | null;
}

function fakeXhr(respond: (xhr: FakeXhr) => void): () => XMLHttpRequest {
  return () => {
    const xhr = {
      status: 0,
      responseText: "",
      upload: { onprogress: null },
      onload: null,
      onerror: null,
      open: () => {},
      send: () => queueMicrotask(() => respond(xhr)),
    } satisfies FakeXhr & Record<string, unknown>;
    return xhr as unknown as XMLHttpRequest;
  };
}
describe("upload", () => {
  const file = new File(["x"], "clip.mp4", { type: "video/mp4" });

  it("reports progress and resolves with the stored video", async () => {
    const progress: number[] = [];
    const client = createVideosClient(
      BASE,
      fetch,
      fakeXhr((x) => {
        x.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 } as ProgressEvent);
        x.status = 201;
        x.responseText = JSON.stringify(api);
        x.onload?.();
      }),
    );
    const item = await client.upload(file, (p) => progress.push(p));
    expect(progress).toEqual([0.5]);
    expect(item.id).toBe("abc");
  });

  it("surfaces the server's reason for rejecting a file", async () => {
    const client = createVideosClient(
      BASE,
      fetch,
      fakeXhr((x) => {
        x.status = 422;
        x.responseText = JSON.stringify({ detail: "That file couldn't be read as a video." });
        x.onload?.();
      }),
    );
    await expect(client.upload(file)).rejects.toThrow("couldn't be read as a video");
  });

  it("handles an unreachable server and a garbled reply", async () => {
    const down = createVideosClient(
      BASE,
      fetch,
      fakeXhr((x) => x.onerror?.()),
    );
    await expect(down.upload(file)).rejects.toThrow(/Is the API running/);

    const garbled = createVideosClient(
      BASE,
      fetch,
      fakeXhr((x) => {
        x.status = 201;
        x.responseText = "<html>";
        x.onload?.();
      }),
    );
    await expect(garbled.upload(file)).rejects.toThrow(/unexpected response/);
  });
});
