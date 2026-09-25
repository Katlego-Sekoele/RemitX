# Writing journeys

A journey is a user accomplishing something in RemitX: sending money,
verifying their identity, withdrawing to a bank. Each one is an MDX page in
this folder, and Storybook lists it under **Journeys**. A journey names the
real screens, API operations and tables each of its steps uses, and every
name is checked in CI against the code, the OpenAPI spec and the database
schema. A journey that drifts from the implementation fails the build.

```bash
cd frontend
npm run storybook     # http://localhost:6006, reloads as you edit
npm run docs:check    # what CI checks: every reference resolves
```

## A journey page

```mdx
{/* docs/journeys/checkout.mdx */}
import { Meta } from "@storybook/addon-docs/blocks"

import { Api, Branch, Database, Decision, Journey, RelatedFeature, Step } from "@living-docs"
import { Cart } from "~/components/cart/cart"
import { ShippingForm } from "~/components/shipping/shipping-form"
import * as PaymentScreenStories from "../../frontend/app/components/payments/payment-screen.stories"

<Meta title="Checkout" />

<Journey title="Checkout" description="A customer buys what is in their cart.">
  <Step title="Cart" component={Cart} api="cart.getCart" tables={["carts"]}>
    Any prose you like: why the step exists, what can go wrong.
  </Step>

  <Step title="Shipping" component={ShippingForm} api="shipping.createShippingAddress" />

  <Step title="Payment" story={PaymentScreenStories.Card}>
    Paying calls <Api operation="payments.createPayment" tables={["payments", "orders"]} />.
  </Step>

  <Decision title="Did the payment go through?">
    <Branch label="Yes" step="Confirmation" />
    <Branch label="No" step="Payment" />
  </Decision>

  <Step title="Confirmation" api="orders.getOrder">
    The order lives in <Database table="orders" />.
  </Step>
</Journey>

<RelatedFeature journey="Refund" />
```

`<Meta title="Checkout" />` puts the page at **Journeys › Checkout**. One
journey per page.

## Primitives

Import them from `@living-docs`; any you use without importing is an error.

| Primitive | Props | What it does |
|---|---|---|
| `Journey` | `title`, `description` | The journey. Its title is how other pages refer to it. |
| `Step` | `title`, `component`, `api`, `tables`, `story` | One step. Titles are unique within a journey; steps are numbered in page order. |
| `Decision` | `title` | A fork. Each `Branch` inside says where an outcome leads. |
| `Branch` | `label`, and one of `step`, `journey`, `concept` | One outcome of a decision. |
| `Screen` | `component` or `story` | A component reference anywhere in prose. |
| `Api` | `operation`, `tables` | An API operation. With `tables`, it declares which tables the operation uses. |
| `Database` | `table`, `column` | A table, or one of its columns. |
| `RelatedFeature` | `journey` or `concept` | A link to another journey or concept. |

Inside a `Step`, `Screen`, `Api` and `Database` belong to that step, as its
`component`, `api` and `tables` props do. Outside any step they are mentions
of the page.

## Referring to things

**API operations.** Write an operation the way the frontend calls it,
`quotes.createQuote` for `api.quotes.createQuote()`, or by its operationId,
`create_quote`. The tag prefix is optional and checked when given. Every
operation has a page under **APIs**, generated from `frontend/openapi.json`.

**Tables and columns.** `tables={["quotes", "quotes.status"]}` takes tables
and `table.column`s, or use `<Database table="quotes" column="status" />`.
Every table has a page under **Database**, generated from
`docs/database/schema.dbml`.

**Components.** Pass the component itself: `component={AmountStep}`, imported
from its file. Aliased (`~/components/...`) and relative imports both work,
barrel files included. A component with stories links to them; one without
is a warning.

**Live stories.** `story={Stories.Default}` renders the story in the page, in
a window that names the component and links to its story, so the product
never reads as part of the docs. Storybook can only find a stories file a
page imports **with a relative path**:

```mdx
import * as AmountStepStories from "../../frontend/app/components/send/amount-step.stories"
```

An aliased (`~/`) stories import is an error, because the story would not
render.

## Connecting APIs to tables

Nothing is inferred: an operation is tied to a table only where a page says
so. There are two ways:

- `<Api operation="payments.createPayment" tables={["payments"]} />`, in a
  step or on any page (a concept page is a good home), says the operation
  uses the table. The operation's page lists the table, and the table's page
  lists the operation, each linking to where it was declared.
- A step's `tables` say the *step* touches them, whichever operation does it.

## What the checks catch

`npm run docs:check` (CI, and the pre-commit hook) resolves every reference
and fails on:

- an operation, table, column, component, story, step, journey or concept
  that does not exist (with "did you mean" suggestions),
- an operation written with the wrong tag,
- a stories import through an alias,
- duplicate journey or step titles, nested steps, a `Step` outside a
  `Journey`, a `Branch` outside a `Decision`,
- a primitive used without importing it, and props it cannot follow
  (`api={someVariable}`: write the string).

It warns about a referenced component with no stories and a prop no
primitive takes (usually a typo). In Storybook, a broken reference shows as
a red chip, and the journey lists its broken references, then its warnings,
at the top.

When the API or the schema changes, `npm run docs:impact -- --base
origin/main` lists the journeys, steps and screens that use what changed;
CI posts it on every pull request.

## Concepts

Ideas that span journeys (the ledger, KYC tiers, fees) go in
`docs/concepts/*.mdx`, listed under **Concepts**. They use the same
primitives, apart from `Journey`, `Step` and `Decision`.
