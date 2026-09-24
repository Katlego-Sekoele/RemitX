import { FieldDescription } from "~/components/ui/field"
import { ItemTitle } from "~/components/ui/item"
import { Table, TableBody, TableCell, TableRow } from "~/components/ui/table"
import { TOKEN_LABEL, TOKEN_NOTE } from "~/lib/money"
import { quoteLines, type PricedQuote } from "~/lib/send"

/** The same quotation lines the review step confirms, reused on a receipt. */
export function QuoteLines({ quote }: { quote: PricedQuote }) {
  const lines = quoteLines(quote)

  return (
    <div className="flex flex-col gap-2">
      <Table>
        <TableBody>
          {lines.map((line, index) => (
            <TableRow key={line.label}>
              <TableCell>
                {index === lines.length - 1 ? (
                  <ItemTitle>{line.label}</ItemTitle>
                ) : (
                  line.label
                )}
              </TableCell>
              <TableCell>
                <div className="flex flex-col items-end gap-0.5">
                  {index === lines.length - 1 ? (
                    <ItemTitle>{line.value}</ItemTitle>
                  ) : (
                    line.value
                  )}
                  {line.detail ? (
                    <FieldDescription>{line.detail}</FieldDescription>
                  ) : null}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <FieldDescription>
        {TOKEN_LABEL}: {TOKEN_NOTE}
      </FieldDescription>
    </div>
  )
}
