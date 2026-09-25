import { describe, expect, it } from "vitest"

import { journeyPage, shopFixture } from "../__fixtures__/fixtures.ts"
import { nodeKey, type Link, type ProductGraph } from "../model.ts"
import { buildGraph } from "./graph.ts"

const JOURNEY = "docs/journeys/checkout.mdx"
const step = (slug: string) => nodeKey("step", `${JOURNEY}#${slug}`)
const component = (file: string, name: string) =>
  nodeKey("component", `frontend/app/components/${file}#${name}`)

function links(graph: ProductGraph, kind: Link["kind"]) {
  return graph.links
    .filter((link) => link.kind === kind)
    .map(({ from, to, via, label }) => ({ from, to, via, label }))
}

function problems(files: Record<string, string>) {
  const { graph } = buildGraph(shopFixture(files))
  return graph.diagnostics
    .filter((d) => d.location?.file === "docs/journeys/broken.mdx")
    .map((d) => `${d.severity} ${d.code}: ${d.message}`)
}

describe("the shop fixture", () => {
  const { graph, componentImports, inputs } = buildGraph(shopFixture())

  it("reads the API and the database from their generated sources", () => {
    expect(Object.keys(graph.api.operations).sort()).toEqual([
      "create_payment",
      "create_shipping_address",
      "get_cart",
      "get_order",
      "health",
    ])
    // alembic_version is Alembic's, not the product's.
    expect(Object.keys(graph.database.tables).sort()).toEqual([
      "orders",
      "payments",
      "users",
    ])
  })

  it("only warns about the one component without stories", () => {
    expect(graph.diagnostics).toEqual([
      expect.objectContaining({
        severity: "warning",
        code: "component-without-stories",
        // A default export goes by the name it declares.
        message: expect.stringMatching(/^OrderConfirmation \(/),
        location: expect.objectContaining({ file: JOURNEY }),
      }),
    ])
  })

  it("titles pages as Storybook does, so links land on them", () => {
    const journey = graph.docs[JOURNEY]
    expect(journey).toMatchObject({
      kind: "journey",
      title: "Checkout",
      storyTitle: "Journeys/Checkout",
      docsId: "journeys-checkout--docs",
      description: "A shopper buys what is in their cart.",
    })
    expect(graph.docs["docs/concepts/billing.mdx"]).toMatchObject({
      kind: "concept",
      title: "Billing",
      docsId: "concepts-billing--docs",
    })
    expect(graph.docs["docs/index.mdx"]).toMatchObject({
      kind: "page",
      docsId: "overview--docs",
    })
  })

  it("numbers the steps in page order", () => {
    expect(
      graph.docs[JOURNEY].steps.map((s) => [s.number, s.title, s.key])
    ).toEqual([
      [1, "Cart", step("cart")],
      [2, "Shipping", step("shipping")],
      [3, "Payment", step("payment")],
      [4, "Confirmation", step("confirmation")],
    ])
  })

  it("traces screens to their components through aliases, relative paths and re-exports", () => {
    expect(links(graph, "shows")).toEqual([
      { from: step("cart"), to: component("cart.tsx", "Cart") },
      {
        from: step("shipping"),
        to: component("shipping/shipping-form.tsx", "ShippingForm"),
      },
      // Declared by the story's meta, not guessed from the step.
      {
        from: step("payment"),
        to: component("payment-screen.tsx", "PaymentScreen"),
      },
      {
        from: step("confirmation"),
        to: component("order-confirmation.tsx", "default"),
      },
    ])
    expect(
      componentImports.map((c) => `${c.key} ${c.exportName}`).sort()
    ).toEqual([
      `${component("cart.tsx", "Cart")} Cart`,
      `${component("order-confirmation.tsx", "default")} default`,
      `${component("shipping/shipping-form.tsx", "ShippingForm")} ShippingForm`,
    ])
  })

  it("knows each component's stories, with Storybook's ids", () => {
    expect(graph.components[component("cart.tsx", "Cart")].stories).toEqual([
      {
        id: "components-cart--default",
        name: "Default",
        title: "Components/cart",
      },
    ])
    // Imported through shipping/index.ts, documented from shipping-form.tsx.
    expect(
      graph.components[
        component("shipping/shipping-form.tsx", "ShippingForm")
      ].stories.map((s) => s.id)
    ).toEqual(["components-shipping-shipping-form--empty"])
    expect(
      graph.components[
        component("payment-screen.tsx", "PaymentScreen")
      ].stories.map((s) => s.id)
    ).toEqual([
      // A titlePrefix applies to a meta's own title too.
      "components-checkout-payment-screen--card",
      "components-checkout-payment-screen--declined",
    ])
  })

  it("accepts an operation by client name or operationId, tagged or not", () => {
    expect(links(graph, "calls")).toEqual([
      { from: step("cart"), to: "operation:get_cart" },
      { from: step("shipping"), to: "operation:create_shipping_address" },
      { from: step("payment"), to: "operation:create_payment" },
      { from: step("confirmation"), to: "operation:get_order" },
    ])
  })

  it("connects tables to operations only where a page says so", () => {
    expect(links(graph, "touches")).toEqual([
      { from: step("payment"), to: "table:payments" },
      { from: step("payment"), to: "column:orders.total" },
      { from: step("confirmation"), to: "table:orders" },
    ])
    expect(links(graph, "uses")).toEqual([
      {
        from: "operation:create_payment",
        to: "table:payments",
        via: step("payment"),
      },
      {
        from: "operation:create_payment",
        to: "table:payments",
        via: "doc:docs/concepts/billing.mdx",
      },
      {
        from: "operation:create_payment",
        to: "table:orders",
        via: "doc:docs/concepts/billing.mdx",
      },
    ])
  })

  it("follows decisions and related features", () => {
    expect(links(graph, "branch")).toEqual([
      { from: `doc:${JOURNEY}`, to: step("confirmation"), label: "Yes" },
      { from: `doc:${JOURNEY}`, to: step("payment"), label: "No" },
    ])
    expect(graph.docs[JOURNEY].decisions).toEqual([
      expect.objectContaining({
        title: "Did the payment go through?",
        branches: [
          expect.objectContaining({
            label: "Yes",
            target: step("confirmation"),
          }),
          expect.objectContaining({ label: "No", target: step("payment") }),
        ],
      }),
    ])
    expect(links(graph, "related")).toEqual([
      { from: `doc:${JOURNEY}`, to: "doc:docs/concepts/billing.mdx" },
      { from: "doc:docs/concepts/billing.mdx", to: `doc:${JOURNEY}` },
    ])
  })

  it("records what it read, for Storybook to watch", () => {
    const relative = inputs.map((file) =>
      file.slice(file.indexOf("/shop/") + 6)
    )
    expect(relative).toEqual(
      expect.arrayContaining([
        "frontend/openapi.json",
        "docs/database/schema.dbml",
        JOURNEY,
        "frontend/app/components/cart.stories.tsx",
        "frontend/app/components/cart.tsx",
      ])
    )
  })
})

describe("broken references", () => {
  const page = (body: string, imports?: string) => ({
    "docs/journeys/broken.mdx": journeyPage(body, imports),
  })

  it("names the operation it cannot find, with the closest ones", () => {
    expect(
      problems(
        page(
          `<Journey title="B"><Step title="S" api="payments.createPaymnt" /></Journey>`
        )
      )
    ).toEqual([
      "error unknown-operation: No operation payments.createPaymnt in frontend/openapi.json. Did you mean payments.createPayment?",
    ])
  })

  it("says which tag an operation really has", () => {
    expect(
      problems(
        page(
          `<Journey title="B"><Step title="S" api="orders.createPayment" /></Journey>`
        )
      )
    ).toEqual([
      "error wrong-tag: orders.createPayment: createPayment is tagged payments, so it is payments.createPayment.",
    ])
  })

  it("checks tables and columns against the schema", () => {
    expect(
      problems(
        page(`<Journey title="B">
  <Step title="S" tables={["payment", "orders.totl"]} />
  <Database table="orders" column="missing" />
</Journey>`)
      )
    ).toEqual([
      "error unknown-table: No table payment in docs/database/schema.dbml. Did you mean payments?",
      "error unknown-column: orders has no column totl. Did you mean total?",
      "error unknown-column: orders has no column missing.",
    ])
  })

  it("follows a component to its file and export", () => {
    expect(
      problems(
        page(
          `<Journey title="B">
  <Step title="A" component={Checkout} />
  <Step title="B" component={Basket} />
  <Step title="C" component={Nope} />
</Journey>`,
          `import { Basket } from "~/components/cart"
import { Nope } from "~/components/nope"`
        )
      )
    ).toEqual([
      "error unknown-component: Checkout is not imported in docs/journeys/broken.mdx.",
      "error missing-export: frontend/app/components/cart.tsx does not export Basket.",
      "error missing-module: Cannot find ~/components/nope, which docs/journeys/broken.mdx imports Nope from.",
    ])
  })

  it("wants stories imported relatively, as Storybook needs to render them", () => {
    expect(
      problems(
        page(
          `<Journey title="B">
  <Step title="A" story={Aliased.Default} />
  <Step title="B" story={Relative.Missing} />
</Journey>`,
          `import * as Aliased from "~/components/cart.stories"
import * as Relative from "../../frontend/app/components/cart.stories"`
        )
      )
    ).toEqual([
      "error story-import-not-relative: Import ~/components/cart.stories with a relative path: Storybook cannot render stories a page imports through an alias.",
      "error unknown-story: frontend/app/components/cart.stories.tsx has no story Missing.",
    ])
  })

  it("checks where decisions lead and what features relate to", () => {
    expect(
      problems(
        page(`<Journey title="B">
  <Step title="Start" />
  <Decision title="Which way?">
    <Branch label="Left" step="Strat" />
    <Branch label="Right" journey="Checkot" />
  </Decision>
</Journey>

<RelatedFeature concept="Shipping" />`)
      )
    ).toEqual([
      "error unknown-step: B has no step Strat. Did you mean Start?",
      "error unknown-journey: No journey called Checkot. Did you mean Checkout?",
      "error unknown-concept: No concept called Shipping.",
    ])
  })

  it("keeps a journey's structure sound", () => {
    expect(
      problems(
        page(`<Step title="Loose" />

<Journey title="Checkout">
  <Step title="Twice" />
  <Step title="Twice" />
  <Step title="Outer">
    <Step title="Inner" />
  </Step>
</Journey>`)
      )
    ).toEqual([
      "error duplicate-step: Checkout already has a step called Twice.",
      "error duplicate-journey: docs/journeys/checkout.mdx is also called Checkout; references to it would be ambiguous.",
      "error misplaced-step: A <Step> belongs inside a <Journey>.",
      "error nested-step: Steps cannot nest.",
    ])
  })

  it("wants primitives imported, and props it can follow", () => {
    expect(
      problems({
        "docs/journeys/broken.mdx": `<Journey title="B">
  <Step title="S" api={someVariable} tabels={["orders"]} />
</Journey>`,
      })
    ).toEqual([
      'error missing-import: <Journey> is used but not imported: import { Journey } from "@living-docs".',
      'error missing-import: <Step> is used but not imported: import { Step } from "@living-docs".',
      "warning unknown-prop: <Step> has no prop tabels; it takes title, component, api, tables, story.",
      'error invalid-prop: <Step api> takes a string or a list of strings, e.g. api={["…"]}.',
    ])
  })

  it("leaves a component named like a primitive alone", () => {
    expect(
      problems({
        "docs/journeys/broken.mdx": `import { Journey } from "~/components/cart"

<Journey title="B" />
`,
      })
    ).toEqual([
      "warning missing-journey: docs/journeys/broken.mdx is in docs/journeys but has no <Journey>.",
    ])
  })

  it("reports a spec it cannot read instead of failing", () => {
    const { graph } = buildGraph(
      shopFixture({ "frontend/openapi.json": "{ not json" })
    )
    expect(graph.diagnostics).toContainEqual(
      expect.objectContaining({
        code: "missing-source",
        message: expect.stringMatching(
          /^frontend\/openapi\.json is not valid JSON/
        ),
      })
    )
  })

  it("accepts a component from a package, and maps it for the preview", () => {
    const config = shopFixture({
      "docs/journeys/broken.mdx": journeyPage(
        `<Journey title="B"><Step title="S" component={SignIn} /></Journey>`,
        `import { SignIn } from "@clerk/react-router"`
      ),
    })
    const { graph, componentImports } = buildGraph(config)
    expect(
      graph.diagnostics.filter(
        (d) => d.location?.file === "docs/journeys/broken.mdx"
      )
    ).toEqual([])
    expect(componentImports).toContainEqual({
      key: "component:@clerk/react-router#SignIn",
      specifier: "@clerk/react-router",
      exportName: "SignIn",
    })
  })

  it("reports MDX it cannot parse", () => {
    expect(
      problems({ "docs/journeys/broken.mdx": '<Journey title="B">\n\n<Step' })
    ).toEqual([
      expect.stringMatching(
        /^error invalid-mdx: docs\/journeys\/broken\.mdx is not valid MDX/
      ),
      "warning missing-journey: docs/journeys/broken.mdx is in docs/journeys but has no <Journey>.",
    ])
  })
})
