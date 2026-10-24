import { flexRender, getCoreRowModel, useReactTable, type ColumnDef, type RowSelectionState, type OnChangeFn } from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/form";
import { cn } from "@/lib/utils";

export interface SortState { sort: string; direction: "asc" | "desc" }

interface Props<T> {
  columns: ColumnDef<T, unknown>[];
  data: T[];
  getRowId: (row: T) => string;
  rowSelection?: RowSelectionState;
  onRowSelectionChange?: OnChangeFn<RowSelectionState>;
  sort?: SortState;
  onSortChange?: (s: SortState) => void;
  onRowClick?: (row: T) => void;
  className?: string;
  caption?: string;
  loading?: boolean;
}

/** Server-driven table: sorting and pagination are performed by the API; this component only renders and reports intent. */
export function DataTable<T>({ columns, data, getRowId, rowSelection, onRowSelectionChange, sort, onSortChange, onRowClick, className, caption, loading }: Props<T>) {
  const table = useReactTable({
    data, columns, getRowId, getCoreRowModel: getCoreRowModel(), manualPagination: true, manualSorting: true,
    enableRowSelection: !!onRowSelectionChange, state: { rowSelection: rowSelection ?? {} }, onRowSelectionChange,
  });
  return (
    <div className={cn("overflow-x-auto rounded-lg border bg-card", loading && "opacity-70 transition-opacity", className)} aria-busy={loading}>
      <table className="w-full min-w-[720px] caption-bottom text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="border-b bg-muted/50 text-left text-xs font-medium text-muted-foreground">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => {
                const sortKey = (h.column.columnDef.meta as { sortKey?: string } | undefined)?.sortKey;
                const active = sort && sortKey === sort.sort;
                return (
                  <th key={h.id} scope="col" className="whitespace-nowrap px-3 py-2.5" aria-sort={active ? (sort!.direction === "asc" ? "ascending" : "descending") : undefined}>
                    {h.isPlaceholder ? null : sortKey && onSortChange ? (
                      <button className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => onSortChange({ sort: sortKey, direction: active && sort!.direction === "desc" ? "asc" : "desc" })}>
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        {active && (sort!.direction === "asc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
                      </button>
                    ) : flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              data-state={row.getIsSelected() ? "selected" : undefined}
              className={cn("border-b transition-colors duration-150 last:border-0 hover:bg-accent/40 data-[state=selected]:bg-accent/60", onRowClick && "cursor-pointer")}
              onClick={(e) => { if (onRowClick && !(e.target as HTMLElement).closest("button,a,input,[role=menuitem]")) onRowClick(row.original); }}
            >
              {row.getVisibleCells().map((c) => <td key={c.id} className="px-3 py-2.5 align-top">{flexRender(c.column.columnDef.cell, c.getContext())}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPage, onPageSize }: { page: number; pageSize: number; total: number; onPage: (p: number) => void; onPageSize?: (s: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <div className="flex flex-col items-center justify-between gap-2 pt-3 text-sm sm:flex-row">
      <p className="text-muted-foreground tabular" aria-live="polite">{total === 0 ? "No results" : `Showing ${from}–${to} of ${total.toLocaleString()}`}</p>
      <div className="flex items-center gap-2">
        {onPageSize && (
          <Select aria-label="Rows per page" className="h-8 w-[140px]" value={pageSize} onChange={(e) => onPageSize(Number(e.target.value))}>
            {[10, 25, 50, 100].map((n) => <option key={n} value={n}>{n} / page</option>)}
          </Select>
        )}
        <Button variant="outline" size="icon" className="h-8 w-8" aria-label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft /></Button>
        <span className="tabular text-muted-foreground">Page {page} / {pages}</span>
        <Button variant="outline" size="icon" className="h-8 w-8" aria-label="Next page" disabled={page >= pages} onClick={() => onPage(page + 1)}><ChevronRight /></Button>
      </div>
    </div>
  );
}
