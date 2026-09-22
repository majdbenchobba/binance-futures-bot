# Security

Never commit exchange credentials, webhook secrets, account exports, runtime
state, journals, or logs.

Use testnet-only keys with minimal permissions during development. Do not enable
withdrawal permissions. If a credential may have appeared in a commit, rotate
it immediately and review the complete Git history; deleting it from the latest
file is not sufficient.

Potential vulnerabilities should be reported privately through GitHub's
security-advisory feature rather than through a public issue.
