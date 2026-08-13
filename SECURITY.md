# Security Policy

## Supported versions

Until the first stable open-source release, only the latest commit on the default branch receives security fixes.

## Reporting a vulnerability

Please use the repository host's private security-advisory feature. If private reporting is not yet configured, contact the repository owner privately and request a secure reporting channel before sharing technical details.

Do not include API keys, OAuth tokens, email content, audio recordings, or personal data in a public issue.

Include:

- A concise description and affected component
- Reproduction steps or a minimal proof of concept
- Expected impact
- Suggested mitigation, if known

Please allow a reasonable period for investigation and a coordinated fix before public disclosure.

## Credential handling

Aylo stores supported credentials in Windows Credential Manager. Contributors must not add plaintext fallback credentials, print secrets in logs, or include real credentials in tests or fixtures.
