import { addons } from "storybook/manager-api"
import { create } from "storybook/theming"

// Staff read these docs inside the admin app (/admin/docs), so the sidebar
// names them for what they are. The brand links to the docs' own start page,
// in the same frame.
addons.setConfig({
  theme: create({
    base: "light",
    brandTitle: "RemitX product docs",
    brandUrl: "./index.html",
    brandTarget: "_self",
  }),
})
