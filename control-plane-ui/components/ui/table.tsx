import { cn } from "@/lib/utils";

export function Table({
  columns,
  rows,
  onRowClick,
  rowTestIds,
}: {
  columns: string[];
  rows: Array<Array<React.ReactNode>>;
  /** When provided, clicking a row (outside nested controls) invokes this handler. */
  onRowClick?: (index: number) => void;
  rowTestIds?: Array<string | null | undefined>;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-base-200 bg-base-50">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead className="bg-base-100 text-ink-400">
          <tr>
            {columns.map((column, index) => (
              <th
                key={column || `col-${index}`}
                className="sticky top-0 z-[1] bg-base-100 px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wide"
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-base-200">
          {rows.map((row, index) => {
            const testId = rowTestIds?.[index] ?? undefined;
            return (
              <tr
                key={index}
                data-testid={testId}
                className={cn(
                  "h-12 bg-base-50",
                  onRowClick && "cursor-pointer hover:bg-base-700/40",
                )}
                onClick={
                  onRowClick
                    ? (event) => {
                        const target = event.target as HTMLElement;
                        if (target.closest("a,button,input,select,textarea,label")) {
                          return;
                        }
                        onRowClick(index);
                      }
                    : undefined
                }
              >
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="px-3 py-2.5 text-xs text-ink-700">
                    {cell}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
