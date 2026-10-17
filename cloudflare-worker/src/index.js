// Domain-free HTTPS gateway for Factory Monitor.
// VPC Service is restricted to the origin HTTP service 127.0.0.1:8000.
// The origin application's existing HTTP Basic authentication remains enforced.
export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    const target = new URL("http://127.0.0.1:8000");
    target.pathname = incoming.pathname;
    target.search = incoming.search;

    const headers = new Headers(request.headers);
    headers.delete("host");

    const options = { method: request.method, headers, redirect: "manual" };
    if (request.method !== "GET" && request.method !== "HEAD") {
      options.body = request.body;
    }

    try {
      const originResponse = await env.FACTORY_SERVICE.fetch(
        new Request(target.toString(), options)
      );
      const responseHeaders = new Headers(originResponse.headers);
      responseHeaders.set("Cache-Control", "no-store");
      responseHeaders.set("X-Content-Type-Options", "nosniff");

      return new Response(originResponse.body, {
        status: originResponse.status,
        statusText: originResponse.statusText,
        headers: responseHeaders,
      });
    } catch (_error) {
      return new Response("Factory Monitor is currently unavailable.", {
        status: 502,
        headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
      });
    }
  },
};
