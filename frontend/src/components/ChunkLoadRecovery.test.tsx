import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChunkLoadRecovery } from "./ChunkLoadRecovery";

describe("ChunkLoadRecovery", () => {
  it("registers error listeners and renders nothing", () => {
    const addSpy = vi.spyOn(window, "addEventListener");
    const { container } = render(<ChunkLoadRecovery />);
    expect(container.firstChild).toBeNull();
    expect(addSpy).toHaveBeenCalledWith("error", expect.any(Function));
    expect(addSpy).toHaveBeenCalledWith(
      "unhandledrejection",
      expect.any(Function),
    );
    addSpy.mockRestore();
  });
});
