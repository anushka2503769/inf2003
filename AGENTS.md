# Team agent entry point

Read [docs/team/README.md](docs/team/README.md) first, then the named teammate's guide.

| Teammate | Guide |
|---|---|
| Zhihao / Zhi Hao | [zhihao.md](docs/team/zhihao.md) |
| Jason | [jason.md](docs/team/jason.md) |
| Jiaxin / Jia Xin | [jiaxin.md](docs/team/jiaxin.md) |
| Nasya | [nasya.md](docs/team/nasya.md) |
| Anuska | [anuska.md](docs/team/anuska.md) |

If the person is not identified, ask which teammate they are before assigning personal
work. Do not infer identity from Git credentials. Identifying a teammate is routing,
not permission to access accounts or provision resources.

For "I'm Jason, what should I do?": read the shared and personal guides, inspect current
implementation/Git state, then explain the next unfinished task, dependencies and checks.
For an explicit request to implement that task, proceed within its agreed scope.

Preserve other people's edits. Check the shared-file ownership table before editing.
Use task branches from the team's current dev base; do not push directly to main/dev.
Zhihao performs final review and integration. A guide is not authorization to merge,
reset databases, buy services, create credentials or change collaborators' access.

The shared guides use repository-relative paths and require no personal agent setup.
Follow any applicable user/runtime governance (including JARVIS when configured) in
addition to these team instructions. Do not copy personal machine paths into team docs.

All other Markdown documentation belongs under docs/. This entry point is the agreed
exception so coding agents can discover the team instructions.
