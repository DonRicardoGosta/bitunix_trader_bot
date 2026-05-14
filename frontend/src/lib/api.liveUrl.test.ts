import { describe, expect, it } from "vitest";
import { toLiveStreamWsUrl } from "./api";

describe("toLiveStreamWsUrl", () => {
  it("maps http to ws", () => {
    expect(toLiveStreamWsUrl("http://127.0.0.1:9000")).toBe(
      "ws://127.0.0.1:9000/api/live/stream",
    );
  });

  it("maps https to wss", () => {
    expect(toLiveStreamWsUrl("https://api.example.com")).toBe(
      "wss://api.example.com/api/live/stream",
    );
  });
});
