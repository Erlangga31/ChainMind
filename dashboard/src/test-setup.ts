import "@testing-library/jest-dom/vitest";

globalThis.ResizeObserver = class implements ResizeObserver {
  constructor(private readonly callback: ResizeObserverCallback) {}

  observe(target: Element) {
    this.callback(
      [
        {
          target,
          contentRect: { width: 800, height: 256 } as DOMRectReadOnly,
        } as ResizeObserverEntry,
      ],
      this,
    );
  }

  unobserve() {}

  disconnect() {}
};
