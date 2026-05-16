import "@testing-library/jest-dom/vitest";

/** Valódi hálózat nélkül: a LiveUpdatesProvider ne próbáljon külső WS-t nyitni. */
class VitestStubWebSocket {
  url: string;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onopen: ((ev: Event) => void) | null = null;

  constructor(url: string | URL) {
    this.url = typeof url === "string" ? url : url.toString();
  }

  close(_code?: number, _reason?: string): void {}
  send(_data: string): void {}
}

vi.stubGlobal("WebSocket", VitestStubWebSocket as unknown as typeof WebSocket);

class VitestResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

vi.stubGlobal("ResizeObserver", VitestResizeObserver);
