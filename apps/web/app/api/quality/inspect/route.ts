import { NextRequest, NextResponse } from "next/server";

import { apiBase } from "@/lib/api/server";

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get("file");
    const category = formData.get("category");
    const threshold = formData.get("threshold");

    if (!file || !(file instanceof Blob)) {
      return NextResponse.json({ error: "Missing or invalid image file" }, { status: 400 });
    }

    const forwardData = new FormData();
    forwardData.append("file", file, (file as File).name || "inspect.png");
    if (category) {
      forwardData.append("category", String(category));
    }
    if (threshold !== null && threshold !== undefined && threshold !== "") {
      forwardData.append("threshold", String(threshold));
    }

    const backendUrl = `${apiBase()}/api/v1/quality/inspect`;
    const res = await fetch(backendUrl, {
      method: "POST",
      body: forwardData,
      cache: "no-store",
    });

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({ detail: res.statusText }));
      return NextResponse.json(errBody, { status: res.status });
    }

    const payload = await res.json();
    return NextResponse.json(payload);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { detail: `Failed to connect to inspection backend: ${message}` },
      { status: 502 },
    );
  }
}
