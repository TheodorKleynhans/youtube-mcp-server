# Local patches

This fork (branch `fix/oauth-force-ssl-scope-and-validation` on
github.com/TheodorKleynhans/youtube-mcp-server) carries these changes over
upstream `pauling-ai/youtube-mcp-server`. Upstream has been dormant since
2026-02-12. Author of all three: Theodor Kleynhans.

| Applied | Commit | Purpose | Upstream |
|---|---|---|---|
| 2026-04-17 | `bec8d0d` | Add the `youtube.force-ssl` OAuth scope and validate cached token scopes. `commentThreads.insert` / `comments.insert` need it; without it every comment write returns 403. | none filed |
| 2026-07-10 | `8486479` | `youtube_update_video` reads `status` defensively (no cosmetic `'status'` KeyError on snippet-only updates) and read-modify-writes the status block, preserving `embeddable`, `publishAt` and the other sibling fields instead of resetting them. | PRs #4 (the KeyError) and #6 (publish_at, does not preserve `embeddable`) are open, unmerged |
| 2026-10-06 | `117e21f` | Uploads no longer count against the 10,000-unit pool. Since 2026-06-01 Google bills `videos.insert` to a separate Video Uploads bucket (1 unit, 100 per day); the client-side tally still charged 1,600 units and raised `QuotaExhaustedError` after about six uploads. `QuotaTracker` now tallies uploads in their own bucket. | none filed |
