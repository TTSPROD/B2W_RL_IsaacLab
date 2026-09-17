---
name: github-dns-bypass
description: Fetch, push, merge and download GitHub resources when local or remote system DNS cannot resolve GitHub. Uses verified DNS-over-HTTPS and temporary per-command address mappings on Windows or Linux without changing hosts files or global Git settings.
---

# GitHub without system DNS

Use `scripts/github_dns.py` with Python 3.9+ and Git. Resolve addresses afresh for each invocation. The helper contacts Cloudflare (`1.1.1.1`) or Google (`8.8.8.8`) over HTTPS with the original provider hostname for certificate validation and SNI. It then connects to GitHub addresses while retaining GitHub's TLS identity. These are DNS bootstrap addresses, not pinned GitHub addresses.

The helper changes no persistent configuration. By default Git receives `http.curloptResolve` and direct-connection settings only for that invocation; Python downloads also connect directly. It needs outbound HTTPS to the DNS providers and GitHub. Do not edit `hosts`, disable certificate verification, switch GitHub URLs to IP addresses, or paste secrets into commands/logs. Existing Git credential helpers supply authentication; never inspect or print their stored tokens.

Run commands from the intended checkout. The examples use the repository copy of the skill; for an installed copy, substitute its absolute script path. Use `python3` instead of `python` on Linux if needed.

```text
python skills/github-dns-bypass/scripts/github_dns.py resolve github.com
python skills/github-dns-bypass/scripts/github_dns.py git ls-remote https://github.com/OWNER/REPOSITORY.git HEAD
python skills/github-dns-bypass/scripts/github_dns.py git fetch origin
python skills/github-dns-bypass/scripts/github_dns.py --git-transport proxy git fetch origin
python skills/github-dns-bypass/scripts/github_dns.py download https://raw.githubusercontent.com/OWNER/REPOSITORY/COMMIT/FILE OUTPUT
python skills/github-dns-bypass/scripts/github_dns.py download https://codeload.github.com/OWNER/REPOSITORY/zip/COMMIT OUTPUT.zip --sha256 EXPECTED_SHA256
```

Use `git -- -C PATH ...` when forwarding Git options through the CLI parser. Downloads permit only HTTPS GitHub, API, codeload, and githubusercontent hosts, including redirects. They stream to a temporary sibling, verify length and optional SHA-256, then atomically replace the destination. They support public content; authenticated API requests are deliberately outside this helper. Record immutable commit IDs and the reported SHA-256 for vendored files. Do not commit credentials or caches.

Git URLs must use `https://github.com/...`, not SSH. Inspect both `git remote -v` and `git remote get-url --push origin` before mutations, including configured push URLs and URL rewrites. Preserve existing remote settings unless changing them is part of the task. An explicit HTTPS URL can be passed to `fetch`, `ls-remote`, or `push` instead. Repository-specific proxy/TLS settings can override generic Git settings: inspect and diagnose these if the helper still fails; do not disable verification.

The Git TLS backend stays unchanged by default. If a Windows Git build supports OpenSSL and Schannel fails, use `--ssl-backend openssl` **before** `git`. Some Windows builds support only Schannel; an “unsupported SSL backend” error is not a DNS error. A sandbox may lack credential access even when the same verified HTTPS command works with authorized execution outside that sandbox.

Older Git builds, including the tested server's Git 2.34.1, may silently ignore `http.curloptResolve`. If `resolve` works but Git still reports “Could not resolve host”, use `--git-transport proxy` **before** `git`. This explicit fallback starts an ephemeral HTTP CONNECT listener on `127.0.0.1`, forwards only `github.com:443` to freshly resolved public IPs, and passes its URL to Git via per-command `http.proxy`. It removes `NO_PROXY`/`no_proxy` only from the child environment. Git still performs the TLS handshake, SNI and certificate verification end to end; the tunnel forwards encrypted bytes unchanged and does not install a CA. The listener, active sockets and worker threads close when Git exits. It cannot proxy LFS storage, API hosts or arbitrary destinations. Use the separate download command for supported public asset URLs.

Select this transport before a mutation. The helper never automatically reruns a failed push with another transport; reconcile remote state first as described below.

## Push and merge

Existing explicit authorization to push or merge in this task remains sufficient; do not add duplicate approval steps. Authorization must identify the intended repository and operation. A push request alone does not authorize merging arbitrary branches, creating unrelated PRs, or changing repository protections.

1. Inspect `git status --short --branch`, current branch, remote URLs, and ongoing merge/rebase state. Preserve unrelated work. For an empty remote, confirm `ls-remote` is empty before creating the first branch. Otherwise fetch the intended remote through the wrapper and compare local/remote history.
2. Prepare the requested changes, inspect the staged diff and run relevant checks. Stage explicit paths. Confirm the exact source commit and destination ref; do not derive a branch name from untrusted output or silently guess the merge target.
3. Push the intended commit with an explicit refspec, for example `... git push origin HEAD:refs/heads/REQUESTED_BRANCH`. Never use `--force`, `--force-with-lease`, `--mirror`, branch deletion or a broad push to work around a failure. If the remote advanced, fetch and reconcile within the requested scope first.
4. For an explicitly requested local merge, require a clean destination worktree, fetch both requested branches, switch to the requested target and fast-forward it with `git merge --ff-only origin/TARGET`. Inspect the diff/history between the fetched target and source, run `git merge --no-ff origin/SOURCE`, then run relevant checks and push `HEAD:refs/heads/TARGET`. If the target moved again, fetch and reassess before another push. Preserve any conflict resolution or user changes; do not reset/clean them to make the merge proceed. For PR-only repositories, use their normal authenticated PR workflow and branch protections; this script does not implement PR API mutation.
5. Verify success with fresh `... git ls-remote origin refs/heads/REQUESTED_BRANCH` and compare its SHA to the local intended commit. A merge is complete only after the requested target ref is verified.

The wrapper executes Git exactly once. After an ambiguous push/merge transport failure, inspect the remote ref before retrying; a successful upstream mutation may have lost its response. Refresh DNS and retry a read-only request at most twice. Retry a push once only after remote state proves the intended update is absent and history remains compatible. Stop on repeated transport failure, rejected authentication, branch protection, changed scope, or unresolved conflicts, and report the actual blocker. Sandbox execution approval is separate from repository authorization and may still be required by the environment.

## Validation

```text
python -m unittest discover -s skills/github-dns-bypass/tests -v
```

The tests use mocked network responses and temporary files. A successful live `resolve` plus `git ls-remote` additionally verifies the machine's actual networking, TLS trust, Git build and credential context. The helper supports IPv4; networks requiring an HTTPS proxy or exclusively IPv6 need a separate transport configuration.

References: [Git HTTP configuration](https://git-scm.com/docs/git-config#Documentation/git-config.txt-httpcurloptResolve), [Cloudflare JSON DoH](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/dns-json/), [Google JSON DoH](https://developers.google.com/speed/public-dns/docs/doh/json).
