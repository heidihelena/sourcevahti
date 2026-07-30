# DNS and custom domains

SourceVahti uses two separate public applications:

- `sourcevahti.vahtian.com` — the hosted Python HTTP/MCP service
- `trends.ntog.org` — the NTOG Shiny lung-cancer trends application

Both parent domains currently use Cloudflare DNS. Create the records only after
the application host has supplied a canonical target hostname. A DNS name alone
does not deploy either application.

## Cloudflare records

In Cloudflare, open the relevant zone and select **DNS → Records → Add record**.

For the SourceVahti service in the `vahtian.com` zone:

| Field | Value |
| --- | --- |
| Type | `CNAME` |
| Name | `sourcevahti` |
| Target | Canonical hostname supplied by the Python service host |
| Proxy status | DNS only during domain verification |
| TTL | Auto |

For the Shiny application in the `ntog.org` zone:

| Field | Value |
| --- | --- |
| Type | `CNAME` |
| Name | `trends` |
| Target | Canonical hostname supplied by the Shiny application host |
| Proxy status | DNS only during domain verification |
| TTL | Auto |

If a hosting provider supplies fixed IPv4 or IPv6 addresses instead of a
hostname, create the provider’s required `A` or `AAAA` records rather than the
`CNAME` shown above.

Do not place provider verification tokens, Cloudflare API tokens, account IDs, or
deployment credentials in either public repository. Store required credentials
in the deployment platform or GitHub Actions secrets.

## Provider-side configuration

1. Deploy the application and copy its canonical provider hostname.
2. Add the intended custom domain in the hosting provider:
   `sourcevahti.vahtian.com` or `trends.ntog.org`.
3. Add the corresponding Cloudflare record shown above.
4. Wait for the provider to verify ownership and issue its TLS certificate.
5. Keep the record DNS-only unless the provider explicitly supports operation
   behind Cloudflare’s proxy. If supported, proxying can be enabled after HTTPS
   works directly.

The Python deployment must expose a normal health endpoint in addition to its
MCP transport. The Shiny deployment must be configured to accept its public
hostname and WebSocket connections.

## Repository files

The existing `CNAME` file in `heidihelena/NTOG` belongs to the current GitHub
Pages site and must continue to contain:

```text
ntog.org
```

Do not replace it with `trends.ntog.org`. The Shiny process is a separate
deployment and receives its subdomain through Cloudflare and its application
host.

SourceVahti does not need a repository-level `CNAME` file because the Python
service is not a GitHub Pages site. Its custom domain likewise belongs in the
service host and Cloudflare configuration.

If a future static documentation site is deployed from a separate GitHub Pages
repository, that repository may have its own `CNAME` file containing its one
custom domain. It must not be shared with either running application.

## Verification

After the provider reports that TLS is active:

```bash
dig +short CNAME sourcevahti.vahtian.com
dig +short CNAME trends.ntog.org
curl --fail --silent --show-error --head \
  https://sourcevahti.vahtian.com/health
curl --fail --silent --show-error --head \
  https://trends.ntog.org/
```

The DNS answers must match the canonical provider hostnames. Both HTTPS requests
must return a successful response without certificate, redirect-loop, or
hostname errors.
