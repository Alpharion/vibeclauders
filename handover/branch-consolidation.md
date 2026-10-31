# Branch consolidation — 31 October 2026

Main is the canonical presentation build. All branch tips below are preserved in its history. Four local review branches had previously been cherry-picked: patch equivalence was verified with git cherry before a history-only merge recorded their original commits.

The latest main README was reconciled with the current frontend and verified release. Historical handoffs and reviews remain audit records; their old build failures and branch ownership are superseded by README.md and output/delivery/verification.json.

The runtime fingerprint remains 2e642c20efbb58845dcaf73e79678a71f2473124914b3be62f8a481b2618b7f3: 537 passing tests, risk verification and dashboard smoke checks. Consolidation changes documentation and ancestry only; the rebuilt package retains matching verified execution evidence.

Merged remote branches are removed only after main is published, using expected-tip leases. Local worktrees are retained, detached from obsolete branch names; untracked local test output is preserved. No worktree directories or data caches are deleted.

| Previous ref | Preserved commit |
|---|---|
| `refs/heads/codex/challenge5-readiness` | `88c708ae6d456cb999b2c120c82a706fe78db4fe` |
| `refs/heads/codex/challenge5-readiness-reviewed` | `6492b89daa090a6b11cca50479cda1a6e0ba098d` |
| `refs/heads/codex/member-1-accuracy-handoff` | `37675388742bd14be97bdba1aba7c9366e6ae707` |
| `refs/heads/codex/member-1-accuracy-integration` | `3073f12c86ca830b4c87a98a92bb30b0d35ca5d3` |
| `refs/heads/codex/member-1-calibration-accuracy` | `a05882b3097bd448e83f09f763a67b210f3710f8` |
| `refs/heads/codex/member-1-validation-accuracy` | `9014bfb0bc33a38f947d46939bbdaf0d0233ffbf` |
| `refs/heads/codex/member-1-weather-accuracy` | `a970fe5c37592f8c4c99743eb7ac41383fe1dbf0` |
| `refs/heads/codex/member-2-delivery-30min` | `24d834bbb33e3e8ccc534a87df03dfd41f9d51be` |
| `refs/heads/codex/parallel-handoffs-30min` | `c01500a3bb247e7ab7882ae3d45e4b266d1b028e` |
| `refs/heads/codex/readiness-brief-review` | `be2d176873231f72fc2c97f7204d04a1a5f1d050` |
| `refs/heads/codex/readiness-docs-review` | `c0171bd3172885f6f241d28e33c661357449f2a1` |
| `refs/heads/codex/readiness-main-merge` | `a075bf69ad46f12d2e93ad00727940e5eac251d7` |
| `refs/heads/codex/readiness-release-review` | `6929ff77feafb9d0dfaad13f4799fceb37eeb43c` |
| `refs/remotes/origin/a` | `5c33fbcad22263f0b339e976adda258834a123e7` |
| `refs/remotes/origin/codex/challenge5-readiness` | `88c708ae6d456cb999b2c120c82a706fe78db4fe` |
| `refs/remotes/origin/codex/challenge5-readiness-reviewed` | `6492b89daa090a6b11cca50479cda1a6e0ba098d` |
| `refs/remotes/origin/codex/member-1-accuracy-handoff` | `37675388742bd14be97bdba1aba7c9366e6ae707` |
| `refs/remotes/origin/codex/member-1-accuracy-integration` | `c4ebef0faf310a4fedf20b8dd917e6bac3ab3be5` |
| `refs/remotes/origin/codex/member-1-calibration-accuracy` | `a05882b3097bd448e83f09f763a67b210f3710f8` |
| `refs/remotes/origin/codex/member-1-capacity-30min` | `5805f89b8ae908b330e1e981536f52ae1725c2ee` |
| `refs/remotes/origin/codex/member-1-validation-accuracy` | `9014bfb0bc33a38f947d46939bbdaf0d0233ffbf` |
| `refs/remotes/origin/codex/member-2-delivery-30min` | `24d834bbb33e3e8ccc534a87df03dfd41f9d51be` |
| `refs/remotes/origin/codex/parallel-handoffs-30min` | `c01500a3bb247e7ab7882ae3d45e4b266d1b028e` |
| `refs/remotes/origin/hm` | `36bfeb86850b2bfeef5e7bedb79584a9375b461a` |
| `refs/remotes/origin/main` | `e6aa1df99b32b199ac31c767840847379d5789bf` |
| `refs/remotes/origin/zeph` | `e6aa1df99b32b199ac31c767840847379d5789bf` |
