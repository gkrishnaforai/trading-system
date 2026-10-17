export const dynamic = 'force-dynamic';

// liveness probe — must not touch upstreams; a slow python-worker or
// go-api must never flap the frontend's own healthcheck
export function GET() {
    return new Response('ok', { status: 200 });
}
