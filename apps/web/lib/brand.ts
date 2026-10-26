import "server-only";

import { connection } from "next/server";

/** The product name is a variable (Q-07): CPORTAL_BRAND_NAME, read at request time. */
export async function brandName(): Promise<string> {
  await connection();
  return process.env.CPORTAL_BRAND_NAME || "ShipperFast";
}

/** "<Page> · <Brand>" for a page's metadata. Pages compose it themselves: a layout's title
 *  template does not reach static page titles while the layout's metadata streams. */
export async function titled(page: string): Promise<{ title: string }> {
  return { title: `${page} · ${await brandName()}` };
}
