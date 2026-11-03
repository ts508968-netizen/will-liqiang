const KEY = "current-clash-yaml";
const MAX_BYTES = 2 * 1024 * 1024;

function sameToken(actual, expected) {
  if (!actual || !expected) return false;
  const left = new TextEncoder().encode(actual);
  const right = new TextEncoder().encode(expected);
  let difference = left.length ^ right.length;
  for (let i = 0; i < Math.max(left.length, right.length); i++) {
    difference |= (left[i] || 0) ^ (right[i] || 0);
  }
  return difference === 0;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== "/subscription") return new Response("Not found", { status: 404 });

    if (request.method === "GET" || request.method === "HEAD") {
      if (!sameToken(url.searchParams.get("key"), env.READ_TOKEN)) {
        return new Response("Not found", { status: 404 });
      }
      const yaml = await env.SUBSCRIPTION.get(KEY);
      if (!yaml) return new Response("Subscription not ready", { status: 503 });
      return new Response(request.method === "HEAD" ? null : yaml, {
        headers: {
          "Content-Type": "text/yaml; charset=utf-8",
          "Cache-Control": "private, no-store",
          "X-Content-Type-Options": "nosniff",
        },
      });
    }

    if (request.method === "PUT") {
      const authorization = request.headers.get("Authorization") || "";
      if (!sameToken(authorization, `Bearer ${env.WRITE_TOKEN}`)) {
        return new Response("Not found", { status: 404 });
      }
      const bytes = await request.arrayBuffer();
      if (bytes.byteLength < 100 || bytes.byteLength > MAX_BYTES) {
        return new Response("Invalid length", { status: 400 });
      }
      const yaml = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      if (!yaml.includes("proxies:") || !yaml.includes("proxy-groups:")) {
        return new Response("Invalid config", { status: 400 });
      }
      await env.SUBSCRIPTION.put(KEY, yaml);
      return new Response("Updated", { status: 200 });
    }

    return new Response("Method not allowed", {
      status: 405,
      headers: { Allow: "GET, HEAD, PUT" },
    });
  },
};
