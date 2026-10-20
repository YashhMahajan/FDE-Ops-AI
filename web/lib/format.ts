export const pct = (x: number, digits = 1) =>
  Number.isFinite(x) ? `${(x * 100).toFixed(digits)}%` : "n/a";

export const signed = (x: number, digits = 3) => `${x >= 0 ? "+" : ""}${x.toFixed(digits)}`;

export const money = (x: number, digits = 0) =>
  Number.isFinite(x)
    ? x.toLocaleString("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      })
    : "not possible";

export const num = (x: number, digits = 0) =>
  Number.isFinite(x) ? x.toLocaleString("en-US", { maximumFractionDigits: digits }) : "n/a";

export const short = (id: string, n = 10) => (id.length > n + 4 ? `${id.slice(0, n)}…` : id);

export const label = (s: string) => s.replaceAll("_", " ");
