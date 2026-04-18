# TODO

## Blocked

- [ ] **Configure custom domain in GitHub Pages UI** -- `dangerousrobot.org` is verified at the account level, DNS records are set (A records + CNAME), repo is public, Pages is enabled (deploy from branch/main), but Settings > Pages still returns "You cannot set a custom domain at this time." CNAME file is committed to repo. Troubleshoot: check if the account is a free org (may need GitHub Pro/Team for custom domains on org repos), try the API (`gh api repos/dangerous-robot/site/pages -X PUT`), or contact GitHub Support.
