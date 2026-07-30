# Security policy

SourceVahti is an alpha proof of concept. It has no authentication, remote HTTP
transport, or write tools. Run it only as a local stdio subprocess.

## Reporting

Please report vulnerabilities privately to the repository maintainers rather
than opening a public issue. Include the affected version, reproduction steps,
impact, and any suggested mitigation. Do not include personal health information,
credentials, or source-system session tokens.

## Supported versions

Only the latest release on the default branch receives security fixes.

## Data safety

SourceVahti serves aggregate public statistics, not individual health records.
Adapters must never collect or expose row-level personal data. Provenance URLs are
public source links and must not contain authentication material or live session
identifiers.
