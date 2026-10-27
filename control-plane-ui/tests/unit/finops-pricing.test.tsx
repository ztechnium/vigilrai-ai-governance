import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  apiGet: vi.fn((path: string) => {
    if (path === "/v1/finops/pricing/cursor") {
      return Promise.resolve({
        data: {
          version: "2026-09-26",
          source_url: "https://cursor.com/docs/models-and-pricing",
          pricing_unit: 1000000,
          cursor_token_rate_per_million: 0.25,
          plans: [
            { id: "pro", name: "Pro", price: 20, currency: "USD" },
            { id: "ultra", name: "Ultra", price: 200, currency: "USD" },
          ],
          models: [
            {
              id: "grok-4.7",
              display_name: "Grok 4.7",
              vendor: "Cursor",
              pool: "cursor_models",
              input_token_price: 2,
              output_token_price: 6,
              cached_input_token_price: 0.5,
              cache_write_token_price: null,
              cursor_token_rate_exempt: true,
            },
            {
              id: "gpt-5.4-mini",
              display_name: "GPT-5.4 Mini",
              vendor: "OpenAI",
              pool: "other_models",
              input_token_price: 0.75,
              output_token_price: 4.5,
              cached_input_token_price: 0.075,
              cache_write_token_price: null,
              cursor_token_rate_exempt: false,
            },
          ],
        },
      });
    }
    return Promise.resolve({ data: { items: [] } });
  }),
}));

import FinOpsPricingPage from "@/app/(app)/finops/pricing/page";

describe("FinOps pricing page", () => {
  it("shows Cursor plan prices and filters published model rates", async () => {
    render(<FinOpsPricingPage />);

    expect(await screen.findByTestId("cursor-model-grok-4.7")).toHaveTextContent("Grok 4.7");
    expect(screen.getByTestId("cursor-model-grok-4.7")).toHaveTextContent("$2");
    expect(screen.getByTestId("cursor-model-grok-4.7")).toHaveTextContent("$6");
    expect(screen.getByTestId("cursor-plans")).toHaveTextContent("Pro $20/mo");
    expect(screen.getByTestId("cursor-model-gpt-5.4-mini")).toHaveTextContent("Teams / Enterprise");

    fireEvent.change(screen.getByLabelText("Filter Cursor models"), {
      target: { value: "grok" },
    });

    await waitFor(() => {
      expect(screen.queryByTestId("cursor-model-gpt-5.4-mini")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("cursor-model-grok-4.7")).toBeInTheDocument();
  });
});
